"""Offline card artwork shared by static pages and compiled local-page shells."""
from PIL import ImageDraw

BG='#F1F6F2'
THEMES={
    'mint':('#13796E','#E5F4EE','leaf'),
    'blue':('#356DAD','#EAF2FD','orbit'),
    'music':('#7253AA','#F1EBFA','wave'),
    'rose':('#AE526F','#FCEBF1','orbit'),
    'album':('#42764E','#EBF4E5','leaf'),
    'video':('#5367AF','#EDF0FE','film'),
    'warm':('#985D23','#FBF0DD','orbit'),
    'game':('#506FAD','#EEF2FC','orbit'),
    'book':('#896342','#FAF0E4','leaf'),
}
LOCAL_THEMES=('mint','warm','album','video','blue','game','book')


def local_theme(state):
    if state.startswith('game') or state=='pastimes':return 'game'
    if state.startswith('book'):return 'book'
    if state in ('album','photo_view'):return 'album'
    if state in ('media','video','video_view'):return 'video'
    if state in ('expressions','phrases','favorites','favorite','load_confirm','delete_confirm'):return 'warm'
    return 'mint'


def key_theme(key):
    if key=='help':return 'warm'
    if key=='pastimes_open':return 'game'
    if key=='memories_open':return 'album'
    if 'back' in key or key=='emotion_close':return 'blue'
    if key.startswith('music'):return 'music'
    if key.startswith('emotion') or key=='cards_open':return 'rose'
    if key in ('album_open','leisure_open'):return 'album'
    if key in ('rest','quick_open','response_open','communication_open','no'):return 'blue'
    if key in ('care_open','caring_open','unwell','please_stop'):return 'warm'
    if key=='more':return 'music'
    return 'mint'


def card_shell(image,box,theme,active=False):
    """All decoration stays outside the central caption and dwell bar."""
    l,t,r,b=box;d=ImageDraw.Draw(image);accent,soft,motif=THEMES[theme]
    d.rectangle((l,t,r-1,b+2),fill=BG)
    d.rounded_rectangle((l,t+3,r-1,b+2),radius=20,fill='#DDE6E3')
    d.rounded_rectangle((l,t,r-1,b-1),radius=20,fill=soft if active else '#FFFFFF',
                        outline=accent if active else '#D2DFDC',width=3 if active else 1)
    d.rounded_rectangle((l+13,t+14,l+17,t+42),radius=2,fill=accent)
    d.rounded_rectangle((l+25,t+10,l+62,t+47),radius=11,fill=soft)
    # Small theme motifs are baked once, with no blinking or motion.
    x=r-72;y=t+21
    if motif=='wave':
        for i,h in enumerate((6,16,23,13,8)):
            d.rounded_rectangle((x+i*7,y+12-h//2,x+i*7+3,y+12+h//2),radius=1,fill=accent if active else soft)
    elif motif=='leaf':
        d.ellipse((x,y,x+24,y+15),fill=soft,outline=accent if active else '#CDDFD1')
        d.line((x+4,y+13,x+26,y-1),fill=accent if active else '#9DBBA8',width=1)
    elif motif=='film':
        d.rounded_rectangle((x,y-2,x+36,y+20),radius=5,outline=accent if active else '#C9D2EC',width=2)
        d.polygon(((x+15,y+3),(x+15,y+15),(x+24,y+9)),fill=accent if active else '#C9D2EC')
    else:
        d.arc((x,y-7,x+38,y+25),20,230,fill=accent if active else '#D1DCE9',width=2)
        d.ellipse((x+30,y+11,x+36,y+17),fill=accent if active else soft)


ICON_ALIASES={
    'ai_open':'typing_open','ai_generate':'quick_open','ai_speech':'book','ai_present':'display',
    'ai_reviewed':'display','ai_adopt':'typing_open','ai_cancel':'pause','ai_play':'book',
    'share_open':'display','share_phrases':'quick_open','share_emotions':'quick_open',
    'share_text':'typing_open','share_pick':'quick_open','share_next':'music_next',
    'share_draft':'display','share_reviewed':'display','share_confirm':'display',
    'share_activity':'more','share_activity_info':'more','share_toggle':'more',
    'share_enable':'display','share_again':'display',
    'input_methods':'typing_open','word_keyboard':'typing_open','initial_letters':'typing_open',
    'word_commit':'quick_open','next_words':'music_next','word_actions':'more','initial_erase':'erase','undo':'back',
    'games':'game','game_start':'game','game_answer':'game','game_next':'music_next','game_finish':'display',
    'book_open':'book','book_toggle':'book','book_options':'more','book_chapters':'book',
    'book_restart':'book','book_next':'music_next','book_previous':'back',
    'keyboard':'typing_open','letters':'typing_open','candidates':'typing_open','candidate':'typing_open',
    'keyboard_actions':'more','keyboard_erase':'erase','erase':'erase','edit':'erase',
    'more':'more','compose':'typing_open','expressions':'quick_open','phrase_group':'quick_open','phrase':'quick_open',
    'phrase_candidate':'quick_open','continuation':'quick_open',
    'favorites':'save','favorite':'save','save':'save','present':'display','show_draft':'display','show_favorite':'display',
    'media_album':'album_open','photo_view':'album_open','media_video':'video','video_toggle':'video',
    'video_controls':'pause','video_next':'music_next','photo_next':'music_next',
    'next_candidates':'music_next','next_favorites':'music_next','next_phrases':'music_next',
    'help':'help','symbols':'typing_open','symbols_choose':'typing_open',
    'clear':'erase','clear_confirm':'erase','delete':'erase','delete_confirm':'erase',
}


def icon_name(command):return ICON_ALIASES.get(command,'back')


def local_icon_names():return sorted(set(ICON_ALIASES.values())|{'back'})
