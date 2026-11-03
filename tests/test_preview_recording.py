import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
from eye_tracker.preview_recording import PreviewRecording


class PreviewRecordingTests(unittest.TestCase):
    def test_owned_samples_survive_reused_camera_buffer(self):
        r=PreviewRecording(120)
        pixels=np.full((480,640),37,dtype=np.uint8)
        r.observe(pixels,1,.1)
        pixels.fill(91)
        r.observe(pixels,2,.2)
        self.assertEqual(len(r.samples),1)
        self.assertEqual(int(r.samples[0][1][0,0]),37)
        self.assertEqual(r.measurements[-1]['full_mean'],91)

    def test_sampling_is_bounded_and_skips_missing_bins(self):
        r=PreviewRecording(12)
        pixels=np.zeros((480,640),dtype=np.uint8)
        for i in range(1,131):r.observe(pixels,i,i*.1)
        self.assertEqual(len(r.samples),12)
        slow=PreviewRecording(12)
        for i,t in enumerate((.1,5.1,11.9),1):slow.observe(pixels,i,t)
        self.assertEqual(len(slow.samples),3)
        self.assertEqual([s[0]['frame_index'] for s in slow.samples],[1,2,3])

    def test_brightness_changes_and_roi_edges_are_measured(self):
        r=PreviewRecording(10)
        a=np.full((480,640),20,dtype=np.uint8)
        r.observe(a,1,.1)
        a[176:304,320:384]=100
        r.observe(a,2,1)
        self.assertEqual(r.measurements[0]['center_mean_absolute_gradient'],0)
        self.assertGreater(r.measurements[1]['center_mean_absolute_gradient'],0)
        self.assertEqual(r.measurements[1]['center_mean'],60)
        with tempfile.TemporaryDirectory() as tmp:
            summary=r.save(tmp,True)
            self.assertGreater(summary['full_mean_largest_adjacent_change'],0)
            manifest=json.loads((Path(tmp)/'recording/manifest.json').read_text())
            self.assertFalse(manifest['gaze_validated'])
            for frame in manifest['frames']:
                p=Path(tmp)/'recording'
                raw=np.frombuffer((p/frame['raw']).read_bytes(),dtype=np.uint8).reshape(480,640)
                self.assertTrue(np.array_equal(raw,np.asarray(Image.open(p/frame['png']))))
            with self.assertRaises(FileExistsError):r.save(tmp,True)

    def test_invalid_input_does_not_append_measurements(self):
        for duration in (0,121,float('nan'),True):
            with self.assertRaises(ValueError):PreviewRecording(duration)
        r=PreviewRecording(10);a=np.zeros((480,640),dtype=np.uint8)
        r.observe(a,1,.1)
        for pixels,index,t in ((a,1,.2),(a,2,.1),(a,True,.2),(a,2,float('nan')),(a.astype(float),2,.2),(a[:10],2,.2)):
            with self.assertRaises(ValueError):r.observe(pixels,index,t)
        self.assertEqual(len(r.measurements),1)

    def test_capacity_and_failed_run_provenance(self):
        r=PreviewRecording(10);r.MAX_MEASUREMENTS=1
        a=np.zeros((480,640),dtype=np.uint8);r.observe(a,1,.1)
        with self.assertRaises(ValueError):r.observe(a,2,.2)
        with tempfile.TemporaryDirectory() as tmp:
            result=r.save(tmp,False)
            self.assertFalse(result['completed_run'])
        self.assertEqual(PreviewRecording(10).save('unused',False)['samples'],0)
