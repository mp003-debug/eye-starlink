"""Read-only user guidance. Display timing never authorizes an eye action."""
import math


POSITION_REJECTIONS = frozenset({
    'neighborhood_not_matched', 'motion_envelope', 'corner_not_matched',
    'corner_search_outside', 'eye_crop_outside_frame', 'corner_pair_not_matched',
    'corner_pair_ambiguous',
})


class UsageGuidance:
    # Only changes the explanatory text after sustained unavailable input.
    # Dwell invalidation still happens immediately in the existing controller.
    REPOSITION_AFTER_SECONDS = 2.

    def __init__(self):
        self.unavailable_since = None
        self.last_time = None

    def feedback(self, controller, observation, now):
        if not math.isfinite(now) or (self.last_time is not None and now < self.last_time):
            self.unavailable_since = None
            return 'guide_input'
        self.last_time = now
        if controller.closed:
            self.unavailable_since = None
            return 'guide_stopped'
        if not controller.calibration_id:
            self.unavailable_since = None
            return 'guide_uncalibrated'
        if controller.paused:
            self.unavailable_since = None
            return 'guide_paused'
        if controller.reason == 'speaking':
            self.unavailable_since = None
            return 'guide_speaking'
        if controller.reason == 'page_release':return 'guide_page_release'
        if controller.reason in ('stale', 'gap', 'future', 'out_of_order',
                                 'bad_sample', 'bad_coordinate', 'clock_fault'):
            self.unavailable_since = None
            return 'guide_input'
        if controller.reason in ('tracking', 'selected', 'locked'):
            self.unavailable_since = None
            if controller.reason == 'locked':
                return 'guide_release'
            if controller.page=='more':return 'guide_back'
            if controller.page=='communication_menu':return 'guide_communication'
            if controller.page in ('menu','quick_menu','full_menu','extended_menu','daily_menu','leisure','daily_communication'):return 'guide_menu'
            if controller.page in ('quick','care'):return 'guide_'+controller.page
            return 'guide_ready'
        if controller.reason == 'cancelled':
            self.unavailable_since = None
            return 'guide_cancelled'
        if controller.reason == 'waiting':
            self.unavailable_since = None
            return 'guide_waiting'
        if self.unavailable_since is None:
            self.unavailable_since = now
        if now - self.unavailable_since < self.REPOSITION_AFTER_SECONDS:
            return 'guide_unavailable'
        observation = observation or {}
        if observation.get('rejection') in POSITION_REJECTIONS:
            return 'guide_reposition'
        if (observation.get('classification') or {}).get('reason') in (
                'unfamiliar_appearance', 'ambiguous_appearance'):
            return 'guide_appearance'
        # Do not infer closed eyes, absence, or a new calibration from rejection.
        return 'guide_unavailable_long'
