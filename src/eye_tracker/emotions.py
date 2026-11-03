"""Fixed local visual expressions; no speech, network or inferred emotion."""
CARDS = {
    'emotion_happy': ('开心', '我很开心', 'emotion_mood', '#A47217', '#FFF3D7'),
    'emotion_sad': ('难过', '我有些难过', 'emotion_mood', '#4B729E', '#EAF1FA'),
    'emotion_worried': ('担心', '我有些担心', 'emotion_mood', '#8667A2', '#F0EAF7'),
    'emotion_like': ('喜欢', '我很喜欢', 'emotion_affection', '#B65E74', '#FCECF0'),
    'emotion_thanks': ('谢谢', '谢谢你', 'emotion_affection', '#347F6F', '#E8F5ED'),
    'emotion_miss': ('想你', '我想你了', 'emotion_affection', '#7D6BAD', '#F0EDF9'),
}
MOOD_KEYS = tuple(k for k, v in CARDS.items() if v[2] == 'emotion_mood')
AFFECTION_KEYS = tuple(k for k, v in CARDS.items() if v[2] == 'emotion_affection')
PANEL_BOX = (32, 112, 608, 257)
LOCAL_ACTIONS = frozenset(CARDS) | frozenset((
    'communication_open', 'communication_back', 'response_open', 'caring_open',
    'emotion_open', 'emotion_menu_back', 'emotion_mood_open', 'emotion_affection_open',
    'emotion_mood_back', 'emotion_affection_back', 'emotion_close'))


def selected_card(controller):
    key = getattr(controller, 'emotion_key', None)
    if key not in CARDS:
        raise ValueError('emotion display requires an explicitly selected card')
    return key


def validate_options(enabled, music, quick_phrases, wireless=False):
    if enabled and (not music or not quick_phrases):
        raise ValueError('emotion cards require local music + quick phrases')
