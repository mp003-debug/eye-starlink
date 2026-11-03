"""Version-gated, explicitly committed sharing; care traffic always wins."""
from .event_link import EventLink
from .event_protocol import PING, EVENT, ACK, OK, DUPLICATE
from .share_protocol import CAPS, COMMIT, SharePacket, MixedDecoder, fragments


class SharingEventLink(EventLink):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.decoder = MixedDecoder()
        self.capable_session = 0
        self.unsupported = False
        self.transfer = None
        self.share_status = '等待连接'

    def _log(self, event, now, **values):
        # A DATA code is one byte of private text, never diagnostic metadata.
        if values.get('kind') in (CAPS, 33, 34, COMMIT):
            values.pop('code', None)
        super()._log(event, now, **values)

    def _share_request(self, kind, code, detail, now):
        if self.sequence >= 0xffffffff:
            self.abort(now, 'sequence_exhausted')
            return
        self.sequence += 1
        self.pending = dict(packet=SharePacket(kind, self.session, self.sequence, code, detail),
                            created=now, sent=None, attempts=0)
        self.state = 'busy'

    def abort(self, now, reason='cancel'):
        pending = self.pending
        if pending and getattr(pending['packet'], 'version', 1) == 2:
            if pending['packet'].kind == CAPS and reason in ('ack_timeout', 'remote_rejected'):
                self.unsupported = True
            if self.transfer:
                self._log('share_unknown' if pending['packet'].kind == COMMIT and pending['attempts'] else 'share_cancelled',
                          now, reason=reason)
        if self.transfer:
            committed=bool(pending and pending['packet'].kind==COMMIT and pending['attempts'])
            self.share_status = ('接纳结果不确定，请查看接收屏' if committed else
                '发送已停止，请重新确认' if reason != 'remote_rejected' else '接收端未接纳，请稍后重新确认')
        elif self.unsupported:
            self.share_status = '接收端版本未就绪，未发送'
        self.transfer = None
        self.capable_session = 0
        super().abort(now, reason)
        self.decoder = MixedDecoder()

    def submit(self, action, now):
        fresh=(action.source==('simulated' if self.simulation else 'live') and
               0<=now-action.source_time_ms<=150 and action.source_time_ms>self.last_action)
        if fresh and action.key in ('water', 'rest', 'help') and (self.transfer or
                self.pending and getattr(self.pending['packet'],'version',1)==2):
            # Fragments cannot display before COMMIT. A possibly accepted COMMIT
            # is never claimed rolled back; receiver care priority still applies.
            p = self.pending
            self._log('share_preempted', now, commit_in_flight=bool(p and p['packet'].kind == COMMIT and p['attempts']))
            self.transfer = None
            if p and getattr(p['packet'], 'version', 1) == 2:
                self.pending = None
            self.share_status = '照护优先，分享已停止'
        return super().submit(action, now)

    def submit_activity(self, text, now):
        from .share_protocol import ACTIVITY
        parts=fragments(ACTIVITY,text)
        if (self.unsupported or not self.ready or self.capable_session!=self.session or
            self.pending or self.deferred or self.transfer or now-self.last_ack>1500):
            self._log('activity_dropped',now)
            return False
        self.transfer=dict(parts=parts,index=0,started=now,category=ACTIVITY)
        self._share_request(*parts[0],now)
        self.pending['fresh_until']=now+150
        self._log('activity_transition',now,category=ACTIVITY)
        return True

    def submit_share(self, action, category, text, now):
        raw_fragments = fragments(category, text)
        stamp = action.source_time_ms
        if (action.source != ('simulated' if self.simulation else 'live') or
            not 0 <= now - stamp <= 150 or stamp <= self.last_action):
            self._log('invalid_share_action', now)
            return False
        self.last_action = stamp
        if category==4 and text=='活动分享已关闭' and self.transfer and self.transfer['category']==4:
            # A fresh, explicit opt-out supersedes unfinished automatic status.
            # A COMMIT already delivered cannot be recalled; the new closure is
            # ordered after it in the same session, without replaying content.
            self.transfer=None
            if self.pending and getattr(self.pending['packet'],'version',1)==2:self.pending=None
            self._log('activity_superseded_by_opt_out',now)
        if (self.unsupported or self.capable_session != self.session or not self.ready or
            self.transfer or self.last_service is None or now - self.last_service > 250 or
            now - self.last_ack > 1500 or self.pending and self.pending['packet'].kind!=PING or self.deferred):
            self.share_status = '连接未就绪，未发送；请重新确认'
            self._log('share_not_sent', now, category=category)
            return False
        self.transfer = dict(parts=raw_fragments, index=0, started=now, category=category,
                             fresh_until=stamp+150,waiting_ping=bool(self.pending and self.pending['attempts']))
        self.share_status = '发送中，可取消或求助'
        self._log('share_started', now, category=category, characters=len(text))
        if not self.transfer['waiting_ping']:
            self._share_request(*raw_fragments[0], now)
            self.pending['fresh_until'] = stamp + 150
        return True

    def service(self, now, enabled=True, allow_heartbeat=True):
        # Explicitly confirmed payload is frozen, like a committed utterance.
        # Natural blinking cannot turn its tail into a new selection. Helper
        # commands, page cancellation and close() explicitly call abort().
        before = self.pending
        if not allow_heartbeat and before and getattr(before['packet'],'version',1)==2:
            self._clock(now)
            if self.last_service is not None and now-self.last_service>250:
                self.abort(now,'service_gap')
            self.last_service=now
            return  # The fresh care action is submitted next, before v2 traffic.
        if self.transfer and now - self.transfer['started'] > 20000:
            self.abort(now, 'share_total_timeout')
            return
        if self.transfer and self.transfer.get('waiting_ping') and now>self.transfer['fresh_until']:
            self.abort(now,'share_start_expired')
            return
        if before and getattr(before['packet'], 'version', 1) == 2 and before['attempts'] == 0:
            if now > before.get('fresh_until', now):
                self.abort(now, 'share_start_expired')
                return
        super().service(now, enabled=enabled or self.transfer is not None,
                        allow_heartbeat=allow_heartbeat and self.transfer is None)
        if before and getattr(before['packet'], 'version', 1) == 2 and self.pending is None and self.ready:
            if before['packet'].kind == CAPS:
                self.capable_session = self.session
                self.share_status = '接收端已就绪'
                self._log('share_capabilities', now, version=2)
            elif self.transfer:
                self.transfer['index'] += 1
                if self.transfer['index'] == len(self.transfer['parts']):
                    self._log('share_accepted', now, category=self.transfer['category'])
                    self.transfer = None
                    self.share_status = '三端已接纳，并非护理确认'
        # Once explicitly confirmed, advance the frozen payload even while
        # gaze is unknown. Waiting here can expire the receiver's 2 s session
        # between DATA and COMMIT. Helper/cancel/expiry paths still abort it.
        if self.ready and self.pending is None and (enabled or self.transfer is not None):
            if self.transfer:
                self._share_request(*self.transfer['parts'][self.transfer['index']], now)
                if self.transfer.get('waiting_ping'):
                    self.transfer['waiting_ping']=False
                    self.pending['fresh_until']=self.transfer['fresh_until']
                # Promote an acknowledged fragment/PING without adding a whole
                # camera frame to the first-send deadline. Bounded, no wait.
                if self.pending:
                    super().service(now, enabled=True, allow_heartbeat=False)
            elif self.capable_session != self.session and not self.unsupported and allow_heartbeat:
                self._share_request(CAPS, 2, int(self.wire_test), now)

    def snapshot(self):
        return dict(super().snapshot(), sharing_version=2, sharing_status=self.share_status,
                    sharing_busy=self.transfer is not None, sharing_supported=self.capable_session == self.session and bool(self.session))
