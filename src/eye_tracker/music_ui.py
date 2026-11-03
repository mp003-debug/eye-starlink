"""Shared, font-free music display geometry and sample-based progress values."""
MUSIC_PAGES = ('music_hub', 'music', 'music_volume')
MUSIC_TRACK_BOX = (32, 59, 608, 78)
MUSIC_FOOTER_BOX = (32, 452, 608, 480)
MUSIC_VOLUME_BOX = (464, 452, 608, 480)
MUSIC_BAR_BOX = (166, 464, 446, 470)
TIME_ORIGIN = (32, 458)
TIME_GLYPH_SIZE = (10, 16)
TIME_GLYPHS = '0123456789:-/ '
FOOTER_COLOR = '#F1F6F2'
BAR_COLOR = '#CEDFD9'
FILL_COLOR = '#13796E'


def display_values(controller):
    index = getattr(controller, 'music_track_index', 0)
    level = getattr(controller, 'music_volume_level', 5)
    position = getattr(controller, 'music_position_samples', 0)
    total = getattr(controller, 'music_total_samples', 0)
    if (type(index) is not int or not -1 <= index < 32 or
            type(level) is not int or not 1 <= level <= 5 or
            type(position) is not int or type(total) is not int or
            not 0 <= position <= 16000*3600 or not 0 <= total <= 16000*3600):
        raise ValueError('invalid music display state')
    position = min(position, total)
    def stamp(samples):
        seconds = samples // 16000
        return f'{seconds//60:02d}:{seconds%60:02d}'
    time_text = stamp(position)+' / '+stamp(total) if total else '--:-- / --:--'
    width = (MUSIC_BAR_BOX[2]-MUSIC_BAR_BOX[0])*position//total if total else 0
    return index, level, time_text, width
