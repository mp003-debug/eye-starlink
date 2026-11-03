"""Offline simulation through the same numerical and interaction core; no hardware."""
import argparse
from dataclasses import asdict
from pathlib import Path
import json
from .calibration import Context, Observation, CalibrationPoint, AffineCalibration
from .interaction import GazeSample, DwellController
from .render import Renderer
from .framebuffer import pack_rgb565,unpack_rgb565,encode_frame,DISPLAY
from PIL import Image

FIT_TARGETS = ((.5,.5),(.15,.2),(.85,.2),(.15,.8),(.85,.8))
CHECK_TARGETS = ((.5,.3),(.7,.5),(.5,.7),(.3,.5))


def synthetic_observation(frame_id, target, context, shift=(0.,0.)):
    x,y = target
    # Analytic fixture only. This is NOT an image detector or a real eye model.
    return Observation(frame_id,context,(160+40*(x-.5)+shift[0],120+30*(y-.5)+shift[1]),
                       (158+shift[0],118+shift[1]),(320,240))


def synthetic_calibration(context):
    fit = [CalibrationPoint(synthetic_observation('fit-'+str(i),p,context),p) for i,p in enumerate(FIT_TARGETS)]
    checks = [CalibrationPoint(synthetic_observation('check-'+str(i),p,context),p) for i,p in enumerate(CHECK_TARGETS)]
    return AffineCalibration.fit(fit,checks)


def run(output,font):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    context=Context('local-simulation','screen-fixed-demo','simulated')
    model=synthetic_calibration(context)
    renderer=Renderer(font)
    def frame(*args,**kwargs):
        return Image.fromarray(unpack_rgb565(pack_rgb565(renderer.frame(*args,**kwargs))))
    control=DwellController(context)
    frame(control).save(output/'uncalibrated.png')
    frame(control,calibration_target=(.5,.5),message='模拟校准目标 · 尚无真实眼图').save(output/'calibration.png')
    control=DwellController(context,model.calibration_id)
    actions=[];frames=[]
    for seq,t in enumerate(range(0,1801,50)):
        observation=synthetic_observation('demo-'+str(seq),(.25,.37),context)
        screen=model.project(observation)
        event=control.feed(GazeSample(context,model.calibration_id,seq,t,'valid',screen),t)
        if event:actions.append(asdict(event))
        message='模拟选择：我想喝水（未播放声音）' if actions else ''
        picture=frame(control,message=message)
        frames.append(picture)
        if t==600:
            picture.save(output/'dwell.png')
            (output/'dwell.rgb565').write_bytes(encode_frame(picture))
        if t==1100:picture.save(output/'selected.png')
    control.feed(GazeSample(context,model.calibration_id,100,1850,'lost'),1850)
    lost=frame(control);lost.save(output/'lost.png')
    frames.extend([lost]*12)
    frames[0].save(output/'interaction.gif',save_all=True,append_images=frames[1:],duration=50,loop=0)
    for seq,t in enumerate(range(1900,3001,50),start=101):
        event=control.feed(GazeSample(context,model.calibration_id,seq,t,'valid',(.75,.7)),t)
        if event:actions.append(asdict(event))
    frame(control,message='模拟更多页 · 注视返回').save(output/'more.png')
    control.pause(3100)
    frame(control).save(output/'paused.png')
    result={'input':'synthetic_only','hardware_access':False,'audio_played':False,
            'calibration':model.metrics,'actions':actions,'image_size':[640,480], 'display_format':'RGB565_LE',
            'display_stride_bytes':DISPLAY.stride_bytes,'display_frame_bytes':DISPLAY.size_bytes,
            'board_tested':False,'real_gaze_accuracy_measured':False}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('build/previews'))
    parser.add_argument('--font',type=Path,required=True,help='Local Chinese font; not redistributed')
    args=parser.parse_args()
    run(args.output,args.font)
