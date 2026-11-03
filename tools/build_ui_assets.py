"""Compile the existing UI artwork and text into portable RGB565 tiles."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from eye_tracker.render import Renderer, REASONS, SOURCE_LABELS, EXTRA_MESSAGES, feedback_message
from eye_tracker.interaction import DwellController, ALL_TARGETS, PAGE_TARGETS
from eye_tracker.calibration import Context
from eye_tracker.framebuffer import pack_rgb565, unpack_rgb565
from eye_tracker.ui import ASSET, SOURCE_BOX, REASON_BOX, MESSAGE_BOX, SETUP_PROGRESS_BOX, MUSIC_TRACK_BOX, PROGRESS_STEPS, card_box, progress_box, target_signature, BoardRenderer
from eye_tracker.music_ui import MUSIC_VOLUME_BOX,TIME_GLYPHS,TIME_GLYPH_SIZE,FOOTER_COLOR
from eye_tracker.render import MUTED
from eye_tracker.emotions import CARDS,PANEL_BOX
from eye_tracker.visual_theme import LOCAL_THEMES,THEMES,card_shell,local_icon_names
from eye_tracker.pastimes import SHAPES
from eye_tracker.game_art import shape_image


def main():
    (ROOT/'build/previews').mkdir(parents=True,exist_ok=True)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font",type=Path,default=Path("assets/fonts/noto_sans_cjk_sc.otf"))
    args=parser.parse_args()
    renderer=Renderer(args.font)
    tiles={}
    def save(name,image,box=None):
        tiles[name]=pack_rgb565(np.asarray(image.crop(box) if box else image))
    for name in SHAPES:save('game_shape_'+name,shape_image(name))
    for page in PAGE_TARGETS:
        base_controller=DwellController(Context("asset-bake","640x480","simulated"),"asset-only")
        base_controller.page=page
        save("base_"+page,renderer.frame(base_controller))
    for key in CARDS:
        picture=renderer.bases['emotion_display'].copy()
        renderer.emotion_details(picture,key)
        save('panel_'+key,picture,PANEL_BOX)
    for count in range(6):
        for failed in (False,True):
            name='setup_'+('failed' if failed else 'collecting')
            image=renderer.setup_frame(count,failed)
            if count==0:save(name,image)
            save(name+'_'+str(count),image,SETUP_PROGRESS_BOX)
    for state in ('preview','collecting','failed','limit'):
        save('position_'+state,renderer.position_frame(state))
    for source in SOURCE_LABELS:
        controller=DwellController(Context("asset-bake","640x480",source),"asset-only")
        save("source_"+source,renderer.frame(controller),SOURCE_BOX)
        for key in [None]+[t.key for t in ALL_TARGETS]+list(EXTRA_MESSAGES):
            save("message_"+source+"_"+(key or "none"),
                 renderer.frame(controller,message=feedback_message(source,key)),MESSAGE_BOX)
    controller=DwellController(Context("asset-bake","640x480","simulated"),"asset-only")
    controller.page='music'
    for index in range(-1,32):
        controller.music_track_index=index
        save('music_track_'+str(index),renderer.frame(controller),MUSIC_TRACK_BOX)
    controller.page='music_volume'
    for level in range(1,6):
        controller.music_volume_level=level
        picture=renderer.frame(controller)
        save('music_volume_title_'+str(level),picture,MUSIC_TRACK_BOX)
        save('music_volume_'+str(level),picture,MUSIC_VOLUME_BOX)
    for i,char in enumerate(TIME_GLYPHS):
        picture=Image.new('RGB',TIME_GLYPH_SIZE,FOOTER_COLOR)
        renderer._text(ImageDraw.Draw(picture),(1,0),char,12,MUTED)
        save('music_glyph_'+str(i),picture)
    controller.page='main'
    for reason in REASONS:
        controller.reason=reason
        save("reason_"+reason,renderer.frame(controller),REASON_BOX)
    for target in ALL_TARGETS:
        page=next(page for page,targets in PAGE_TARGETS.items() if target in targets)
        for name,active,locked in (("active",True,False),("locked",True,True),("locked_idle",False,True)):
            image=renderer.bases[page].copy()
            renderer._card(image,target,active=active,locked=locked)
            save(target.key+"_"+name,image,card_box(target))
        for step in range(1,PROGRESS_STEPS+1):
            image=renderer.bases[page].copy()
            renderer._card(image,target,active=True,progress=step/PROGRESS_STEPS)
            save(target.key+"_progress_"+str(step),image,progress_box(target))
    # One reusable shell per theme, independent of which fixed quadrant owns it.
    picture=Image.new('RGB',(576,33),'#F1F6F2')
    ImageDraw.Draw(picture).rounded_rectangle((0,0,575,32),radius=11,fill='#FFFFFF',outline='#DBE6E0')
    save('local_blank_hint',picture)
    target=next(t for t in ALL_TARGETS if t.key=='tool_slot_0')
    l,t,r,b=card_box(target);b-=3
    for theme in LOCAL_THEMES:
        accent,soft,_=THEMES[theme]
        for state in ('idle','active','locked','locked_idle'):
            picture=renderer.bases['local_tools'].copy();card_shell(picture,(l,t,r,b),theme,state in ('active','locked'))
            renderer._text(ImageDraw.Draw(picture),(l+20,b-31),'已选择 · 请移开视线' if 'locked' in state else '注视选择',13,accent)
            save('local_'+theme+'_'+state,picture,card_box(target))
        for step in range(1,PROGRESS_STEPS+1):
            picture=renderer.bases['local_tools'].copy();card_shell(picture,(l,t,r,b),theme,True);draw=ImageDraw.Draw(picture)
            renderer._text(draw,(l+20,b-31),'保持注视',13,accent)
            renderer._text(draw,(r-20,b-31),str(step*5)+'%',13,accent,'rt')
            draw.rounded_rectangle((l+20,b-12,r-21,b-8),radius=2,fill='#CEDFD9')
            draw.rounded_rectangle((l+20,b-12,l+20+(r-l-41)*step/PROGRESS_STEPS,b-8),radius=2,fill=accent)
            save('local_'+theme+'_progress_'+str(step),picture,progress_box(target))
        for key in local_icon_names():
            save('local_'+theme+'_icon_'+key,renderer._icon(key,accent,soft).resize((30,30),Image.Resampling.LANCZOS))
    cursor=Image.new("RGB",(31,31));d=ImageDraw.Draw(cursor)
    mask=Image.new("L",(31,31));m=ImageDraw.Draw(mask)
    for box,color,width in (((3,3,27,27),"white",4),((5,5,25,25),"#13796E",2)):
        d.ellipse(box,outline=color,width=width);m.ellipse(box,outline=255,width=width)
    d.ellipse((13,13,17,17),fill="#13796E");m.ellipse((13,13,17,17),fill=255)
    save("cursor",cursor);tiles["cursor_mask"]=np.asarray(mask,dtype=np.uint8)
    meta={"version":11,"targets":target_signature(),"progress_steps":PROGRESS_STEPS,"dwell_ms":1000,
          "local_themes":list(LOCAL_THEMES),
          "emotion_cards":list(CARDS),
          "music_tracks":renderer.music_tracks,
          "generator":"tools/build_ui_assets.py from eye_tracker.render.Renderer",
          "font_file_not_distributed":True}
    tiles["metadata"]=np.frombuffer(json.dumps(meta,ensure_ascii=False).encode("utf-8"),dtype=np.uint8)
    ASSET.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(ASSET,**tiles)
    board=BoardRenderer()
    controller.reason="tracking";controller.target_key="water";controller.progress=.6;controller.cursor=(.25,.37)
    raw=board.rgb565(controller)
    Image.fromarray(unpack_rgb565(np.frombuffer(raw,dtype="<u2").reshape(480,640))).save(ROOT/"build/previews/board_interaction.png")
    print(json.dumps({"path":str(ASSET),"bytes":ASSET.stat().st_size,"uncompressed_bytes":sum(v.nbytes for v in tiles.values())}))


if __name__=="__main__":main()
