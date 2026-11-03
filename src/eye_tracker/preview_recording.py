"""Bounded raw preview samples and temporal measurements; never emits gaze."""
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image
from .preview import CROP, frame_statistics


class PreviewRecording:
    MAX_SAMPLES = 12
    MAX_MEASUREMENTS = 20000

    def __init__(self, seconds):
        if isinstance(seconds, bool) or not math.isfinite(seconds) or not 0 < seconds <= 120:
            raise ValueError("recording duration must be in (0,120]")
        self.seconds = float(seconds)
        self.measurements = []
        self.samples = []
        self.last_slot = -1
        self.region_enabled = False

    def observe(self, pixels, frame_index, elapsed, stats=None, region=None):
        if not isinstance(pixels, np.ndarray) or pixels.shape != (480,640) or pixels.dtype != np.uint8:
            raise ValueError("recording requires native640x480 uint8")
        if type(frame_index) is not int or frame_index < 1 or not math.isfinite(elapsed) or elapsed <= 0:
            raise ValueError("invalid capture identity/time")
        if self.measurements and (frame_index <= self.measurements[-1]['frame_index'] or elapsed <= self.measurements[-1]['copied_elapsed_s']):
            raise ValueError("capture identity/time must increase")
        if len(self.measurements) >= self.MAX_MEASUREMENTS:
            raise ValueError("bounded recording measurement capacity exceeded")
        stats = frame_statistics(pixels) if stats is None else stats
        x0,y0,x1,y1 = CROP
        roi = pixels[y0:y1,x0:x1].astype(np.int16)
        difference = np.abs(np.diff(roi,axis=0)).sum() + np.abs(np.diff(roi,axis=1)).sum()
        pairs = (roi.shape[0]-1)*roi.shape[1] + (roi.shape[1]-1)*roi.shape[0]
        row = {'frame_index':frame_index,'copied_elapsed_s':float(elapsed),
               'full_mean':float(stats['mean']),'full_bright_percent':float(stats['bright_percent']),
               'center_mean':float(roi.mean()),'center_std':float(roi.std()),
               'center_mean_absolute_gradient':float(difference/pairs)}
        if region is not None:
            self.region_enabled = True
            row.update(eye_state=region["state"],eye_box=json.dumps(region["box"]),
                       eye_crop=json.dumps(region["crop"]),eye_track_id=region["track_id"],
                       eye_detector_ms=region["detector_ms"],eye_candidate_count=region["candidate_count"])
        self.measurements.append(row)
        slot = min(self.MAX_SAMPLES-1,int(elapsed/self.seconds*self.MAX_SAMPLES))
        if slot > self.last_slot:
            # Own the bytes: capture/display arrays may be reused next frame.
            self.samples.append((row.copy(),pixels.copy()))
            self.last_slot = slot

    def save(self, output, completed):
        if not self.measurements:
            return {'measurements':0,'samples':0,'source':'live_camera','gaze_validated':False}
        destination = Path(output)/'recording'
        destination.mkdir(parents=True,exist_ok=False)
        with (destination/'measurements.csv').open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(self.measurements[0]))
            writer.writeheader();writer.writerows(self.measurements)
        samples=[]
        for index,(row,pixels) in enumerate(self.samples):
            name='sample_%02d'%index
            raw=pixels.tobytes()
            (destination/(name+'.gray8')).write_bytes(raw)
            Image.fromarray(pixels,mode='L').save(destination/(name+'.png'))
            samples.append(dict(row,raw=name+'.gray8',png=name+'.png',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        means=np.array([r['full_mean'] for r in self.measurements])
        summary={'source':'live_camera','completed_run':bool(completed),'measurements':len(self.measurements),
                 'samples':len(samples),'raw_sample_bytes':sum(s['bytes'] for s in samples),
                 'measurements_file':'recording/measurements.csv','sample_manifest':'recording/manifest.json',
                 'full_mean_min':float(means.min()),'full_mean_max':float(means.max()),
                 'full_mean_p05':float(np.percentile(means,5)),'full_mean_p95':float(np.percentile(means,95)),
                 'full_mean_largest_adjacent_change':float(np.max(np.abs(np.diff(means)))) if len(means)>1 else 0.,
                 'focus_roi_xyxy':list(CROP),'focus_metric_is_image_content_dependent':True,
                 'eye_detection_enabled':self.region_enabled,'gaze_validated':False,
                 'timing_scope':'software copy completion; not sensor exposure timestamps',
                 'sampling_scope':'at most12 native frames from successive time bins; missed bins are not synthesized',
                 'brightness_scope':'preview-sampled values only; cannot identify mains flicker frequency or prove absence of higher-frequency modulation',
                 'focus_scope':'gradient is affected by target placement, exposure and noise; not an optical acceptance threshold'}
        (destination/'manifest.json').write_text(json.dumps(dict(summary,frames=samples),indent=2)+'\n',encoding='utf-8')
        return summary
