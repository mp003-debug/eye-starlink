"""Bounded dwell control. Fresh samples trigger events; clocks never trigger actions."""
from dataclasses import dataclass
import math
from .calibration import Context, pair
from .phrases import PHRASE_TEXT, PHRASE_LABELS, RESPONSE_KEYS, CARE_KEYS
from .emotions import CARDS, MOOD_KEYS, AFFECTION_KEYS, validate_options
from .daily_tools import SLOT_KEYS


@dataclass(frozen=True)
class Target:
    key: str
    label: str
    phrase: str
    rect: tuple

    def contains(self, point):
        x, y = point
        left, top, right, bottom = self.rect
        return left <= x < right and top <= y < bottom


MAIN_TARGETS = (
    Target("water", "喝水", PHRASE_TEXT['water'], (.05,.24,.475,.52)),
    Target("rest", "休息", PHRASE_TEXT['rest'], (.525,.24,.95,.52)),
    Target("help", "需要帮助", PHRASE_TEXT['help'], (.05,.56,.475,.84)),
    Target("more", "更多", "", (.525,.56,.95,.84)),
)
MORE_TARGETS = (Target("back", "返回", "", (.2,.3,.8,.75)),)
MENU_TARGETS = (
    Target('music_open','本地音乐','',MAIN_TARGETS[0].rect),
    Target('menu_back','返回','',MAIN_TARGETS[3].rect),
)
MUSIC_TARGETS = (
    Target('music_toggle','播放 / 暂停','',MAIN_TARGETS[0].rect),
    Target('music_next','下一首','',MAIN_TARGETS[1].rect),
    MAIN_TARGETS[2],
    Target('music_back','返回','',MAIN_TARGETS[3].rect),
)
PAGE_TARGETS={'main':MAIN_TARGETS,'more':MORE_TARGETS,'menu':MENU_TARGETS,'music':MUSIC_TARGETS}
PAGE_TARGETS.update(
    music_hub=(Target('music_player_open','播放控制','',MAIN_TARGETS[0].rect),
               Target('music_volume_open','音乐音量','',MAIN_TARGETS[1].rect),
               MAIN_TARGETS[2],Target('music_menu_back','返回','',MAIN_TARGETS[3].rect)),
    music_volume=(Target('music_volume_down','小声一点','',MAIN_TARGETS[0].rect),
                  Target('music_volume_up','大声一点','',MAIN_TARGETS[1].rect),
                  MAIN_TARGETS[2],Target('music_volume_back','返回','',MAIN_TARGETS[3].rect)))
QUICK_OPEN=Target('quick_open','回应交流','',MAIN_TARGETS[1].rect)
CARE_OPEN=Target('care_open','日常照护','',MAIN_TARGETS[2].rect)
QUICK_TARGETS=tuple(Target(key,PHRASE_LABELS[key],PHRASE_TEXT[key],MAIN_TARGETS[i].rect)
                    for i,key in enumerate(RESPONSE_KEYS))+(Target('quick_back','返回','',MAIN_TARGETS[3].rect),)
CARE_TARGETS=tuple(Target(key,PHRASE_LABELS[key],PHRASE_TEXT[key],MAIN_TARGETS[i].rect)
                    for i,key in enumerate(CARE_KEYS))+(Target('care_back','返回','',MAIN_TARGETS[3].rect),)
PAGE_TARGETS.update(quick=QUICK_TARGETS,care=CARE_TARGETS,
                    quick_menu=(QUICK_OPEN,CARE_OPEN,MENU_TARGETS[1]),
                    full_menu=(MENU_TARGETS[0],QUICK_OPEN,CARE_OPEN,MENU_TARGETS[1]))
def local_target(key, label, region):
    return Target(key, label, '', MAIN_TARGETS[region].rect)

PAGE_TARGETS.update(
    extended_menu=(MENU_TARGETS[0], local_target('communication_open','快捷交流',1),
                   local_target('emotion_open','表情心意',2), MENU_TARGETS[1]),
    communication_menu=(local_target('response_open','回应交流',0),
                        local_target('caring_open','日常照护',1), MAIN_TARGETS[2],
                        local_target('communication_back','返回',3)),
    emotion_hub=(local_target('emotion_mood_open','心情',0),
                 local_target('emotion_affection_open','心意',1), MAIN_TARGETS[2],
                 local_target('emotion_menu_back','返回',3)),
    emotion_mood=tuple(local_target(k,CARDS[k][0],i) for i,k in enumerate(MOOD_KEYS))+
                 (local_target('emotion_mood_back','返回',3),),
    emotion_affection=tuple(local_target(k,CARDS[k][0],i) for i,k in enumerate(AFFECTION_KEYS))+
                      (local_target('emotion_affection_back','返回',3),),
    emotion_display=(MAIN_TARGETS[2],local_target('emotion_close','返回',3)))
PAGE_TARGETS.update(
    daily_menu=(MENU_TARGETS[0],local_target('communication_open','快捷交流',1),
                local_target('leisure_open','休闲心意',2),MENU_TARGETS[1]),
    daily_communication=(local_target('response_open','回应交流',0),local_target('caring_open','日常照护',1),
                         local_target('typing_open','文字输入',2),local_target('communication_back','返回',3)),
    leisure=(local_target('cards_open','表情心意',0),local_target('album_open','本地相册',1),
             MAIN_TARGETS[2],local_target('leisure_back','返回',3)),
    pastimes_leisure=(local_target('memories_open','相册心意',0),local_target('pastimes_open','游戏听书',1),
                     MAIN_TARGETS[2],local_target('pastimes_back','返回',3)),
    local_tools=tuple(local_target(key,'',i) for i,key in enumerate(SLOT_KEYS)))
ALL_TARGETS=tuple({t.key:t for targets in PAGE_TARGETS.values() for t in targets}.values())


@dataclass(frozen=True)
class GazeSample:
    context: Context
    calibration_id: str
    sequence: int
    source_time_ms: float
    status: str
    screen: object = None


@dataclass(frozen=True)
class Action:
    key: str
    phrase: str
    source: str
    source_time_ms: float


class DwellController:
    def __init__(self, context, calibration_id=None, dwell_ms=1000, release_ms=300,
                 max_age_ms=150, max_gap_ms=250, music_enabled=False, quick_phrases=False,
                 emotion_cards=False,daily_tools=None):
        if not isinstance(context, Context):
            raise ValueError("missing context")
        if any(not math.isfinite(v) or v <= 0 for v in (dwell_ms, release_ms, max_age_ms, max_gap_ms)):
            raise ValueError("invalid timing policy")
        self.context, self.calibration_id = context, calibration_id
        self.dwell_ms, self.release_ms = dwell_ms, release_ms
        self.max_age_ms, self.max_gap_ms = max_age_ms, max_gap_ms
        self.page = "main"
        self.music_enabled=music_enabled
        self.quick_phrases=quick_phrases
        validate_options(emotion_cards,music_enabled,quick_phrases)
        self.emotion_cards=bool(emotion_cards)
        self.emotion_key=None
        if daily_tools is not None:
            from .daily_tools import validate_options as validate_daily
            validate_daily(True,music_enabled,quick_phrases,emotion_cards)
        self.daily_tools=daily_tools
        self.navigation_block=None;self.navigation_outside_since=None
        self.paused = False
        self.closed = False
        self.last_seq = -1
        self.last_source = None
        self.last_now = None
        self.target_key = None
        self.start_time = None
        self.progress = 0.
        self.cursor = None
        self.locks = set()
        self.outside_since = {}
        self.reason = "uncalibrated" if calibration_id is None else "waiting"

    @property
    def targets(self):
        if self.page=='local_tools':
            if self.daily_tools is None:raise ValueError('local tools are not enabled')
            return tuple(Target('help' if c.command=='help' else SLOT_KEYS[i],c.label,
                                PHRASE_TEXT['help'] if c.command=='help' else '',MAIN_TARGETS[i].rect)
                         for i,c in enumerate(self.daily_tools.view().choices) if c is not None)
        return PAGE_TARGETS[self.page]

    @property
    def menu_page(self):
        if self.daily_tools is not None:return 'daily_menu'
        if self.emotion_cards:return 'extended_menu'
        if self.quick_phrases:return 'full_menu' if self.music_enabled else 'quick_menu'
        return 'menu' if self.music_enabled else 'more'

    @property
    def communication_page(self):return 'daily_communication' if self.daily_tools is not None else 'communication_menu'

    def _reset(self, reason):
        self.target_key = None
        self.start_time = None
        self.progress = 0.
        self.cursor = None
        self.outside_since.clear()
        self.navigation_outside_since=None
        self.reason = reason

    def _clock(self, now):
        if isinstance(now, bool) or not isinstance(now, (float, int)) or not math.isfinite(now) or now < 0:
            self.closed = True
            self._reset("clock_fault")
            return False
        if self.last_now is not None and now < self.last_now:
            self.closed = True
            self._reset("clock_fault")
            return False
        self.last_now = now
        return True

    def tick(self, now):
        if not self._clock(now):
            return
        if self.closed or self.paused or not self.calibration_id:
            return
        if self.last_source is not None and now-self.last_source > self.max_age_ms:
            self._reset("stale")

    def pause(self, now):
        self.tick(now)
        self.paused = True
        self._reset("paused")

    def resume(self, now):
        self.tick(now)
        self.paused = False
        self._reset("waiting")

    def cancel(self, now):
        self.tick(now)
        self._reset("cancelled")

    def invalidate_calibration(self):
        self.calibration_id = None
        self._reset("uncalibrated")

    def stop(self, now):
        self.tick(now)
        self.closed = True
        self._reset("stopped")

    def feed(self, sample, now):
        if not self._clock(now):
            return None
        if self.closed or self.paused or not self.calibration_id:
            self._reset("stopped" if self.closed else "paused" if self.paused else "uncalibrated")
            return None
        if sample.context != self.context or sample.calibration_id != self.calibration_id:
            self.calibration_id = None
            self._reset("context_mismatch")
            return None
        t = sample.source_time_ms
        if (type(sample.sequence) is not int or sample.sequence < 0 or isinstance(t, bool)
                or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0):
            self._reset("bad_sample")
            return None
        if (sample.sequence <= self.last_seq or (self.last_source is not None and t <= self.last_source)):
            self._reset("out_of_order")
            return None
        if t > now or now-t > self.max_age_ms:
            self._reset("future" if t > now else "stale")
            return None
        gap = None if self.last_source is None else t-self.last_source
        self.last_seq, self.last_source = sample.sequence, t
        if sample.status != "valid":
            self._reset(sample.status if sample.status in ("closed", "lost", "unknown") else "unknown")
            return None
        try:
            point = pair(sample.screen)
        except (ValueError, TypeError, OverflowError):
            self._reset("bad_coordinate")
            return None
        if not all(0 <= x <= 1 for x in point):
            self._reset("bad_coordinate")
            return None
        if gap is not None and gap > min(self.max_gap_ms, self.max_age_ms):
            self._reset("gap")
        self.cursor = point
        hit = next((target for target in self.targets if target.contains(point)), None)
        key = hit.key if hit else None
        # Hidden-page targets cannot be unlocked merely by a page change.
        visible = {target.key for target in self.targets}
        for locked in tuple(self.locks):
            if locked not in visible or key == locked:
                self.outside_since.pop(locked, None)
            else:
                start = self.outside_since.setdefault(locked, t)
                if t-start >= self.release_ms:
                    self.locks.remove(locked)
                    self.outside_since.pop(locked, None)
        if self.navigation_block is not None:
            # Valid outside gaze serves both release guards concurrently.
            # No dwell is credited until the page guard is fully released.
            if self.navigation_block.contains(point):self.navigation_outside_since=None
            elif self.navigation_outside_since is None:self.navigation_outside_since=t
            if self.navigation_outside_since is None or t-self.navigation_outside_since<self.release_ms:
                self.target_key=None;self.start_time=None;self.progress=0.;self.reason='page_release'
                return None
            self.navigation_block=None;self.navigation_outside_since=None
        if key is None or key in self.locks:
            self.target_key, self.start_time, self.progress = key, None, 0.
            self.reason = "locked" if key in self.locks else "tracking"
            return None
        if key != self.target_key or self.start_time is None:
            self.target_key, self.start_time = key, t
        self.progress = min(1., (t-self.start_time)/self.dwell_ms)
        self.reason = "tracking"
        if self.progress < 1.:
            return None
        action = Action(key, hit.phrase, self.context.source, t)
        self.locks.add(key)
        self._reset("selected")
        previous_page=self.page
        local_navigation=False
        if self.page=='local_tools':
            slot=2 if key=='help' else SLOT_KEYS.index(key)
            outcome=self.daily_tools.select(slot)
            local_navigation=True
            if outcome=='leisure':self.page='leisure'
            elif outcome=='pastimes':self.page='pastimes_leisure'
            elif outcome=='communication':self.page=self.communication_page
        elif key in ('album_open','typing_open'):
            if self.daily_tools is None:raise ValueError('local tools are not enabled')
            self.daily_tools.open('album' if key=='album_open' else 'compose');self.page='local_tools'
        elif key in ('leisure_open','leisure_back','cards_open'):
            self.page={'leisure_open':'leisure','leisure_back':self.menu_page,'cards_open':'emotion_hub'}[key]
            if self.daily_tools is not None and self.daily_tools.pastimes and key in ('leisure_open','leisure_back'):
                self.page='pastimes_leisure'
        elif key=='memories_open':self.page='leisure'
        elif key=='pastimes_back':self.page=self.menu_page
        elif key=='pastimes_open':
            self.daily_tools.open('pastimes');self.page='local_tools'
        elif key in ("more", "back"):
            self.page = self.menu_page if key == "more" else "main"
            if key == "more":
                # Return belongs to this page visit. It still needs a new full
                # dwell; main-page command locks and invalid-input rules stay.
                self.locks.discard("back")
        elif key in ('music_open','menu_back','music_back','quick_open','quick_back','care_open','care_back',
                     'music_player_open','music_volume_open','music_volume_back','music_menu_back'):
            self.page={'music_open':'music_hub','menu_back':'main','music_back':'music_hub',
                       'music_player_open':'music','music_volume_open':'music_volume',
                       'music_volume_back':'music_hub','music_menu_back':self.menu_page,
                       'quick_open':'quick','quick_back':self.communication_page if self.emotion_cards else self.menu_page,
                       'care_open':'care','care_back':self.communication_page if self.emotion_cards else self.menu_page}[key]
        elif key in CARDS:
            self.emotion_key=key
            self.page='emotion_display'
        elif key=='emotion_close':
            self.page=CARDS[self.emotion_key][2]
            self.emotion_key=None
        elif key in ('communication_open','communication_back','response_open','caring_open',
                     'emotion_open','emotion_menu_back','emotion_mood_open','emotion_affection_open',
                     'emotion_mood_back','emotion_affection_back'):
            self.page={'communication_open':self.communication_page,'communication_back':self.menu_page,
                       'response_open':'quick','caring_open':'care', 'emotion_open':'emotion_hub',
                       'emotion_menu_back':'leisure' if self.daily_tools is not None else self.menu_page,'emotion_mood_open':'emotion_mood',
                       'emotion_affection_open':'emotion_affection',
                       'emotion_mood_back':'emotion_hub','emotion_affection_back':'emotion_hub'}[key]
        if (self.music_enabled or self.quick_phrases or self.emotion_cards) and (self.page!=previous_page or local_navigation):
            self.navigation_block=hit
        return action
