"""Compiled RGB565 communication UI, baked from the authoritative Renderer.

The renderer consumes controller state only; it cannot generate selections.
Chinese text/icons are packaged pixels. No system font is required on PYNQ.
"""
import json
from pathlib import Path
import numpy as np
from .interaction import ALL_TARGETS, PAGE_TARGETS
from .render import REASONS, SOURCE_LABELS, EXTRA_MESSAGES
from .emotions import CARDS, PANEL_BOX, selected_card
from .visual_theme import LOCAL_THEMES,local_icon_names
from .music_ui import (MUSIC_PAGES, MUSIC_TRACK_BOX, MUSIC_FOOTER_BOX, MUSIC_VOLUME_BOX,
                       MUSIC_BAR_BOX, TIME_ORIGIN, TIME_GLYPH_SIZE, TIME_GLYPHS,
                       FOOTER_COLOR, BAR_COLOR, FILL_COLOR, display_values)

ASSET = Path(__file__).resolve().parents[2] / "assets/communication_ui.npz"
SOURCE_BOX = (330, 20, 616, 60)
REASON_BOX = (32, 76, 608, 101)
MESSAGE_BOX = (32, 418, 608, 451)
SETUP_PROGRESS_BOX = (180, 314, 460, 374)
PROGRESS_STEPS = 20
POSITION_PREVIEW_BOX = (160,144,480,384)
POSITION_COLLECT_BOX = (40,216,168,312)
_gray=np.arange(256,dtype=np.uint16)
GRAY565=((_gray>>3)<<11)|((_gray>>2)<<5)|(_gray>>3)


def card_box(target):
    left, top, right, bottom = [round(v * s) for v, s in zip(target.rect, (640,480,640,480))]
    return left, top, right, bottom + 3


def progress_box(target):
    left, _, right, bottom = card_box(target)
    return left, bottom - 36, right, bottom


def target_signature():
    return [{"key": t.key, "label": t.label, "phrase": t.phrase, "rect": list(t.rect)}
            for t in ALL_TARGETS]


class BoardRenderer:
    def __init__(self, path=ASSET):
        with np.load(path, allow_pickle=False) as archive:
            meta = json.loads(archive["metadata"].tobytes().decode("utf-8"))
            if (meta.get("version") != 11 or meta.get("targets") != target_signature()
                    or meta.get('local_themes') != list(LOCAL_THEMES)
                    or meta.get('emotion_cards') != list(CARDS)
                    or meta.get("progress_steps") != PROGRESS_STEPS or meta.get("dwell_ms") != 1000):
                raise ValueError("UI assets do not match the current interaction geometry/policy")
            self.tiles = {name: archive[name] for name in archive.files if name != "metadata"}
        specs = {'base_'+page:(480,640) for page in PAGE_TARGETS}
        from .pastimes import SHAPES
        specs.update({'game_shape_'+name:(48,48) for name in SHAPES})
        specs['local_blank_hint']=(33,576)
        for theme in LOCAL_THEMES:
            for state in ('idle','active','locked','locked_idle'):specs['local_'+theme+'_'+state]=(138,272)
            for step in range(1,PROGRESS_STEPS+1):specs['local_'+theme+'_progress_'+str(step)]=(36,272)
            for key in local_icon_names():specs['local_'+theme+'_icon_'+key]=(30,30)
        for key in CARDS:specs['panel_'+key]=(145,576)
        for state in ('preview','collecting','failed','limit'):specs['position_'+state]=(480,640)
        for index in range(-1,32):specs['music_track_'+str(index)]=(19,576)
        for level in range(1,6):
            specs['music_volume_title_'+str(level)]=(19,576)
            specs['music_volume_'+str(level)]=(28,144)
        for i in range(len(TIME_GLYPHS)):specs['music_glyph_'+str(i)]=(16,10)
        for state in ('collecting', 'failed'):
            specs['setup_'+state] = (480,640)
            for count in range(6):
                specs['setup_'+state+'_'+str(count)] = (60,280)
        for source in SOURCE_LABELS:
            specs["source_"+source] = (40,286)
            for key in ["none"] + [t.key for t in ALL_TARGETS] + list(EXTRA_MESSAGES):
                specs["message_"+source+"_"+key] = (33,576)
        for reason in REASONS:
            specs["reason_"+reason] = (25,576)
        for target in ALL_TARGETS:
            left, top, right, bottom = card_box(target)
            for state in ("active","locked","locked_idle"):
                specs[target.key+"_"+state] = (bottom-top,right-left)
            for step in range(1,PROGRESS_STEPS+1):
                specs[target.key+"_progress_"+str(step)] = (36,right-left)
        for name, shape in specs.items():
            tile = self.tiles.get(name)
            if tile is None or tile.shape != shape or tile.dtype != np.dtype("<u2"):
                raise ValueError("invalid UI tile: "+name)
        if self.tiles["cursor"].shape != (31,31) or self.tiles["cursor_mask"].shape != (31,31):
            raise ValueError("invalid cursor tile")
        self.dwell_ms = meta["dwell_ms"]
        self.asset_metadata = meta
        self.daily_renderer=None

    def bind_daily_tools(self,tools):
        from .text_ui import DailyRenderer
        self.daily_renderer=DailyRenderer(tools,tiles=self.tiles)

    def bind_music(self,library):
        if self.asset_metadata.get('music_tracks') != library.provenance()['tracks']:
            raise ValueError('music titles do not match playlist; rebuild UI assets after importing music')

    def setup_frame(self, count=0, failed=False):
        if type(count) is not int or not 0 <= count <= 5:
            raise ValueError('reference count must be 0..5')
        name='setup_'+('failed' if failed else 'collecting')
        words=self.tiles[name].copy()
        left,top,right,bottom=SETUP_PROGRESS_BOX
        words[top:bottom,left:right]=self.tiles[name+'_'+str(count)]
        return words.tobytes()

    def rgb565(self, controller, feedback=None):
        if controller.dwell_ms != self.dwell_ms:
            raise ValueError("UI dwell label differs from controller policy; rebuild assets")
        if controller.page not in PAGE_TARGETS:
            raise ValueError("unknown communication page")
        words = self.tiles["base_"+controller.page].copy()
        def paste(box, tile):
            left, top, right, bottom = box
            words[top:bottom,left:right] = tile
        source = controller.context.source
        paste(SOURCE_BOX, self.tiles["source_"+source])
        reason = controller.reason if controller.reason in REASONS else "unknown"
        paste(REASON_BOX, self.tiles["reason_"+reason])
        paste(MESSAGE_BOX, self.tiles["message_"+source+"_"+(feedback or "none")])
        for target in controller.targets:
            tile_key='tool_slot_2' if controller.page=='local_tools' and target.key=='help' else target.key
            active = controller.target_key == target.key
            locked = target.key in controller.locks
            if active or locked:
                state = "locked" if active and locked else "locked_idle" if locked else "active"
                paste(card_box(target), self.tiles[tile_key+"_"+state])
                if active and not locked and controller.progress > 0:
                    step = min(PROGRESS_STEPS, int(controller.progress * PROGRESS_STEPS))
                    if step > 0:
                        paste(progress_box(target), self.tiles[tile_key+"_progress_"+str(step)])
        if controller.page=='leisure' and self.daily_renderer is not None:
            self.daily_renderer.media_entry(words,controller)
        if controller.cursor is not None:
            x, y = int(controller.cursor[0] * 640), int(controller.cursor[1] * 480)
            left, top, right, bottom = max(0,x-15), max(0,y-15), min(640,x+16), min(480,y+16)
            if left < right and top < bottom:
                sx, sy = left-(x-15), top-(y-15)
                cursor = self.tiles["cursor"][sy:sy+bottom-top,sx:sx+right-left]
                mask = self.tiles["cursor_mask"][sy:sy+bottom-top,sx:sx+right-left].astype(bool)
                dest = words[top:bottom,left:right]
                dest[mask] = cursor[mask]
        if controller.page=='local_tools':
            if self.daily_renderer is None or self.daily_renderer.tools is not controller.daily_tools:raise ValueError('daily renderer is not bound')
            self.daily_renderer.overlay(words,controller,feedback)
            # The cached page covers card text regions; the live cursor stays on top.
            if controller.cursor is not None:
                x,y=int(controller.cursor[0]*640),int(controller.cursor[1]*480)
                left,top,right,bottom=max(0,x-15),max(0,y-15),min(640,x+16),min(480,y+16)
                if left<right and top<bottom:
                    sx,sy=left-(x-15),top-(y-15)
                    cursor=self.tiles['cursor'][sy:sy+bottom-top,sx:sx+right-left]
                    mask=self.tiles['cursor_mask'][sy:sy+bottom-top,sx:sx+right-left].astype(bool)
                    words[top:bottom,left:right][mask]=cursor[mask]
        if controller.page=='emotion_display':
            paste(PANEL_BOX,self.tiles['panel_'+selected_card(controller)])
        if controller.page in MUSIC_PAGES:
            index,level,time_text,width=display_values(controller)
            name='music_volume_title_'+str(level) if controller.page=='music_volume' else 'music_track_'+str(index)
            paste(MUSIC_TRACK_BOX,self.tiles[name])
            def color(hex_color):
                r,g,b=(int(hex_color[i:i+2],16) for i in (1,3,5))
                return ((r>>3)<<11)|((g>>2)<<5)|(b>>3)
            l,t,r,b=MUSIC_FOOTER_BOX;words[t:b,l:r]=color(FOOTER_COLOR)
            for i,char in enumerate(time_text):
                x=TIME_ORIGIN[0]+i*TIME_GLYPH_SIZE[0];y=TIME_ORIGIN[1]
                words[y:y+16,x:x+10]=self.tiles['music_glyph_'+str(TIME_GLYPHS.index(char))]
            l,t,r,b=MUSIC_BAR_BOX;words[t:b,l:r]=color(BAR_COLOR)
            if width:words[t:b,l:l+width]=color(FILL_COLOR)
            paste(MUSIC_VOLUME_BOX,self.tiles['music_volume_'+str(level)])
        return words.tobytes()

    def position_frame(self,pixels,state='preview',count=0):
        if state not in ('preview','collecting','failed','limit'):raise ValueError('unknown position state')
        if type(count) is not int or not 0<=count<=5:raise ValueError('reference count must be 0..5')
        if not isinstance(pixels,np.ndarray) or pixels.shape!=(480,640) or pixels.dtype!=np.uint8:
            raise ValueError('position preview requires native GRAY8 640x480')
        words=self.tiles['position_'+state].copy()
        if state=='collecting':
            left,top,right,bottom=SETUP_PROGRESS_BOX
            words[top:bottom,left:right]=self.tiles['setup_collecting_'+str(count)]
        box=POSITION_COLLECT_BOX if state=='collecting' else POSITION_PREVIEW_BOX
        left,top,right,bottom=box
        step=5 if state=='collecting' else 2
        words[top:bottom,left:right]=GRAY565[pixels[::step,::step]]
        return words.tobytes()
