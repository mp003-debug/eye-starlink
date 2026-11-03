"""Stop-and-wait event sender. All times use the caller's monotonic milliseconds.

No action is queued while disconnected or an event is outstanding. Fresh actions
precede unsent heartbeats; one can wait <=150ms behind an in-flight heartbeat.
A failed ACK is delivery UNKNOWN,
not proof that the remote did not receive it. Retry only the same session/seq.
"""
from collections import Counter, deque
import math
import secrets
from .event_protocol import Packet, Decoder, HELLO, PING, EVENT, ACK, OK, DUPLICATE, EVENTS, TEST
from .event_uart import UartError


class EventLink:
    def __init__(self, transport, simulation=False, session_factory=None, wire_test=None):
        self.transport = transport
        self.simulation = simulation
        # Input provenance and receiver dry-run flag are independent.
        self.wire_test = simulation if wire_test is None else bool(wire_test)
        if simulation and not self.wire_test:
            raise ValueError("simulated input cannot drive LIVE receivers")
        self.trace_index = 0
        self.session_factory = session_factory or (lambda: secrets.randbelow(0xffffffff) + 1)
        self.session = 0
        self.sequence = 0
        self.decoder = Decoder()
        self.pending = None
        self.deferred = None
        self.state = "disabled"
        self.ready = False
        self.last_ack = -math.inf
        self.last_service = None
        self.last_action = -math.inf
        self.retry_after = 0.
        self.trace = deque(maxlen=256)
        self.counts = Counter()
        self._retired_session = None

    def _log(self, event, now, **values):
        self.counts[event] += 1
        self.trace_index += 1
        self.trace.append(dict(event=event, time_ms=now, session=self.session, trace_index=self.trace_index, **values))

    def _clock(self, now):
        if not math.isfinite(now) or now < 0 or (self.last_service is not None and now < self.last_service):
            self.transport.reset()
            self.pending = None
            self.deferred = None
            self.ready = False
            self.state = "fault"
            raise ValueError("sender clock regressed/nonfinite")

    def abort(self, now, reason="cancel"):
        self._clock(now)
        if self.pending and self.pending["packet"].kind == EVENT:
            self._log("delivery_unknown" if self.pending["attempts"] else "not_sent",
                      now, sequence=self.pending["packet"].sequence, reason=reason)
        if self.deferred:
            self._log("not_sent", now, code=self.deferred[0], reason=reason)
        self.deferred = None
        self.transport.reset()
        self.decoder = Decoder()
        self.pending = None
        self.ready = False
        self.state = "disabled"
        self._retired_session = self.session
        self.session = 0
        self.retry_after = now + 300
        self._log("aborted", now, reason=reason)

    def _request(self, kind, now, code=0):
        if kind != HELLO:
            self.sequence += 1
        packet = Packet(kind, self.session, self.sequence, code, TEST if self.wire_test else 0)
        self.pending = dict(packet=packet, created=now, sent=None, attempts=0)
        self.state = "handshake" if kind == HELLO else "busy"

    def service(self, now, enabled=True, allow_heartbeat=True):
        self._clock(now)
        gap = self.last_service is not None and now - self.last_service > 250
        self.last_service = now
        if not enabled:
            if self.state != "disabled":
                self.abort(now, "input_disabled")
            return
        if gap and self.state != "disabled":
            self.abort(now, "service_gap")
            return
        try:
            replies = self.decoder.feed(self.transport.read())
            for reply in replies:
                p = self.pending
                if (not p or p["attempts"] == 0 or reply.kind != ACK or
                    getattr(reply, 'version', 1) != getattr(p['packet'], 'version', 1) or
                    (reply.session, reply.sequence, reply.code) !=
                    (p["packet"].session, p["packet"].sequence, p["packet"].code)):
                    self._log("ignored_reply", now)
                    continue
                if now - p["created"] >= 600:
                    continue  # late ACK cannot validate a timed-out transaction
                if reply.detail not in (OK, DUPLICATE):
                    self._log("rejected", now, status=reply.detail)
                    self.abort(now, "remote_rejected")
                    return
                if p["packet"].kind == EVENT:
                    self._log("remote_accepted", now, code=reply.code, sequence=reply.sequence,
                              source_time_ms=p.get("source_time_ms"), duplicate_ack=reply.detail == DUPLICATE)
                self.pending = None
                self.ready = True
                self.last_ack = now
                self.state = "ready"
            if self.deferred and now - self.deferred[1] > 150:
                self._log("not_sent", now, code=self.deferred[0], reason="expired_waiting_for_ping")
                self.deferred = None
            if self.deferred and self.pending is None:
                code, stamp = self.deferred
                self.deferred = None
                self._request(EVENT, now, code)
                self.pending["fresh_until"] = stamp + 150
                self.pending["source_time_ms"] = stamp
                # ACK processing must not add another camera-frame delay before
                # the first event send. The original freshness deadline remains.
            if self.pending:
                p = self.pending
                if p["packet"].kind == PING and p["attempts"] == 0 and not allow_heartbeat:
                    return  # submit() may replace this unsent heartbeat below.
                if p["packet"].kind == EVENT and p["attempts"] == 0 and now > p.get("fresh_until", p["created"] + 150):
                    self._log("not_sent", now, code=p["packet"].code, reason="expired_before_first_send")
                    self.pending = None
                    self.state = "ready"
                    return
                if now - p["created"] >= 600:
                    self._log("timeout", now)
                    self.abort(now, "ack_timeout")
                    return
                if p["attempts"] < 3 and (p["sent"] is None or now - p["sent"] >= 180):
                    if self.transport.try_write(p["packet"].encode()):
                        p["attempts"] += 1
                        p["sent"] = now
                        self._log("sent", now, kind=p["packet"].kind,
                                  sequence=p["packet"].sequence, code=p["packet"].code, source_time_ms=p.get("source_time_ms"), attempt=p["attempts"])
                return
            if not self.ready:
                if now < self.retry_after:
                    return
                self.session = int(self.session_factory())
                if not 1 <= self.session <= 0xffffffff or self.session == self._retired_session:
                    raise ValueError("session must be a new nonzero uint32")
                self.sequence = 0
                self._request(HELLO, now)
            elif allow_heartbeat and now - self.last_ack >= 500:
                if self.sequence >= 0xffffffff:
                    self.abort(now, "sequence_exhausted")
                else:
                    self._request(PING, now)
        except UartError as exc:
            self._log("uart_error", now, message=str(exc))
            self.abort(now, "uart_error")

    def submit(self, action, now):
        """Only consume an Action returned by DwellController.feed(), once."""
        self._clock(now)
        expected_source = "simulated" if self.simulation else "live"
        stamp = action.source_time_ms
        if (action.source != expected_source or action.key not in EVENTS or
            not math.isfinite(stamp) or not 0 <= now - stamp <= 150 or stamp <= self.last_action):
            self._log("invalid_action", now)
            return False
        # Consume even if unavailable. Reconnection must not replay a selection.
        self.last_action = stamp
        if (not self.ready or (self.pending and self.pending["packet"].kind != PING) or self.deferred or self.last_service is None or
            now - self.last_service > 250 or now - self.last_ack > 1500 or self.sequence >= 0xffffffff):
            self._log("not_sent", now, code=EVENTS[action.key], reason="link_not_ready")
            return False
        if self.pending and self.pending["attempts"] > 0:
            self.deferred = (EVENTS[action.key], stamp)
        else:
            # Only an unsent PING can be replaced. Never cancel or replay an
            # in-flight packet; skipped sequence numbers are valid in v1.
            if self.pending:
                self._log("heartbeat_superseded", now, sequence=self.pending["packet"].sequence)
            self._request(EVENT, now, EVENTS[action.key])
            self.pending["fresh_until"] = stamp + 150
            self.pending["source_time_ms"] = stamp
        return True

    def snapshot(self):
        return dict(state=self.state, simulation=self.simulation, wire_test=self.wire_test, counts=dict(self.counts),
                    trace=list(self.trace), crc_errors=self.decoder.bad_frames,
                    scope="remote receive ACK only; no actuator completion or real gaze claim")


def service_controller(link, controller, now, action=None):
    """Shared UI boundary: invalid samples/commands stop unsent data and retries."""
    enabled = bool(controller.calibration_id and not controller.paused and not controller.closed
                   and controller.reason in ("waiting", "tracking", "locked", "selected", "speaking"))
    link.service(now, enabled=enabled, allow_heartbeat=action is None)
    return link.submit(action, now) if action is not None and enabled else False
