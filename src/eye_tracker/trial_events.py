"""Live dwell to UART; log mode changes wire flag, never eye-input provenance."""
from .event_link import service_controller
from .trial_limits import EventHistory
from .event_protocol import EVENTS


class TrialEvents:
    def __init__(self, link, controller):
        if link.simulation or controller.context.source != 'live':
            raise ValueError('real_eye_input_required')
        self.link, self.controller = link, controller
        self.events = EventHistory()
        self.selections = EventHistory()
        self.last_trace = 0
        self.suspended = False
        self.last_service = None
        self.max_service_gap_ms = 0.
        self.service_calls = 0
        self.controller_bindings = 1
        self.action_epoch_ms = 0.

    def suspend(self, now, reason='reference_setup'):
        """Cancel old requests before any blocking setup; never replay them."""
        self.suspended = True
        if self.link.state != 'disabled':self.link.abort(now, reason)
        self._collect()

    def resume(self, controller, now):
        """Bind only the current live controller; calibration gates still apply."""
        if controller.context.source != 'live':raise ValueError('real_eye_input_required')
        if controller is not self.controller:
            self.suspend(now, 'controller_changed')
            self.controller = controller
            self.controller_bindings += 1
        self.suspended = False
        self.last_service = now
        self.action_epoch_ms = now

    def _collect(self):
        for row in self.link.trace:
            if row['trace_index'] > self.last_trace:
                self.events.append(dict(row))
                self.last_trace = row['trace_index']

    def update(self, now, action=None, frame_index=None):
        original_action=action
        tools=getattr(self.controller,'daily_tools',None)
        sharing=getattr(tools,'sharing',None)
        request=None
        if sharing is not None and hasattr(self.link,'submit_share'):
            sharing.status=self.link.share_status
            sharing.busy=self.link.transfer is not None
            if self.link.transfer and (not self.controller.calibration_id or self.controller.paused or self.controller.closed):
                self.link.abort(now,'controller_disabled')
            if sharing.cancel_requested:
                sharing.cancel_requested=False
                if self.link.transfer:self.link.abort(now,'user_share_cancel')
            if original_action is not None:
                request=sharing.request;sharing.request=None
        # A whitelist also excludes future local features without new deny lists.
        if action is not None and action.key not in EVENTS:action=None
        if action is not None and action.source_time_ms < self.action_epoch_ms:action=None
        if self.last_service is not None and not self.suspended:
            self.max_service_gap_ms=max(self.max_service_gap_ms,now-self.last_service)
        self.last_service=now;self.service_calls+=1
        if self.suspended:
            self.link.service(now, enabled=False);self._collect();return False
        if request is not None:
            enabled=bool(self.controller.calibration_id and not self.controller.paused and not self.controller.closed
                and self.controller.reason in ('waiting','tracking','locked','selected','speaking'))
            self.link.service(now,enabled=enabled,allow_heartbeat=False)
            accepted=False
        else:accepted = service_controller(self.link, self.controller, now, action)
        if request is not None and original_action.source_time_ms>=self.action_epoch_ms:
            enabled=bool(self.controller.calibration_id and not self.controller.paused and not self.controller.closed
                and self.controller.reason in ('waiting','tracking','locked','selected','speaking'))
            if enabled:
                accepted=self.link.submit_share(original_action,*request,now)
                self.selections.append(dict(event='share_submission',category=request[0],characters=len(request[1]),
                    source=original_action.source,source_time_ms=original_action.source_time_ms,
                    frame_index=frame_index,time_ms=now,queued=accepted))
        if action is not None:
            self.selections.append(dict(event='selection_submission', key=action.key,
                source=action.source, source_time_ms=action.source_time_ms,
                frame_index=frame_index, time_ms=now, queued=accepted,
                receiver_mode='log' if self.link.wire_test else 'live'))
        # Service a new request immediately; never wait synchronously for an ACK.
        if accepted:
            service_controller(self.link, self.controller, now)
        self._collect()
        return accepted

    def activity(self,now,label):
        """Coarse state transitions only; explicit opt-in, no user content."""
        tools=getattr(self.controller,'daily_tools',None)
        sharing=getattr(tools,'sharing',None)
        if sharing is None or not sharing.activity_enabled or self.suspended:return
        if getattr(self,'_activity_revision',None)!=sharing.activity_revision:
            self._activity_revision=sharing.activity_revision
            self._last_activity=None
            self._activity_at=-10000
        if label==getattr(self,'_last_activity',None):return
        self._last_activity=label  # Do not store and replay a transition after reconnect.
        if now-getattr(self,'_activity_at',-10000)<5000:return
        self._activity_at=now
        if self.controller.calibration_id and not self.controller.paused and not self.controller.closed:
            self.link.submit_activity(label,now)
        self._collect()

    def close(self, now):
        self.suspended = True
        if self.link.state != 'disabled':
            self.link.abort(now, 'trial_exit')
        self._collect()

    def snapshot(self):
        return dict(self.link.snapshot(), source='live_camera_dwell',
            receiver_mode='log' if self.link.wire_test else 'live',
            events=list(self.events), selections=list(self.selections),
            event_retention=self.events.summary(), selection_retention=self.selections.summary(),
            service_calls=self.service_calls,max_service_gap_ms=self.max_service_gap_ms,
            controller_bindings=self.controller_bindings,suspended=self.suspended,
            scope='Real dwell to receiver acceptance; log mode does not invoke teammate actions. ACK is not action completion.')
