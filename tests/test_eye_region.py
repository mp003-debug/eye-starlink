import unittest
import numpy as np
from eye_tracker.eye_region import EyeRegionLocator, normalize_boxes, display_crop

class EyeRegionTests(unittest.TestCase):
    def setUp(self):
        self.pixels=np.zeros((480,640),dtype=np.uint8)
        self.left=(70,170,200,300); self.right=(440,170,570,300)

    def locator(self, series):
        rows=iter(series)
        return EyeRegionLocator(lambda pixels,hint:next(rows))

    def test_confirmation_following_and_immediate_loss_do_not_hold_stale_box(self):
        shifted=(80,174,210,304)
        loc=self.locator([[self.left,self.right],[shifted],[shifted],[],[shifted],[shifted]])
        rows=[loc.update(self.pixels,i+1,i*.1) for i in range(6)]
        self.assertEqual([r['state'] for r in rows],['confirming','located','located','searching','confirming','located'])
        self.assertIsNone(rows[3]['box']); self.assertIsNone(rows[3]['crop'])
        self.assertEqual(rows[1]['track_id'],1);self.assertEqual(rows[5]['track_id'],2)
        self.assertEqual(rows[1]['box'],shifted)
        self.assertTrue(all(not r['gaze_validated'] for r in rows))

    def test_long_gap_reconfirms_and_cannot_directly_jump_to_other_eye(self):
        loc=self.locator([[self.left],[self.left],[self.right],[self.right],[self.right]])
        self.assertEqual(loc.update(self.pixels,1,0)['state'],'confirming')
        self.assertEqual(loc.update(self.pixels,2,.1)['state'],'located')
        self.assertEqual(loc.update(self.pixels,3,.2)['state'],'searching')
        self.assertEqual(loc.update(self.pixels,4,.8)['state'],'confirming')
        self.assertEqual(loc.update(self.pixels,5,.9)['track_id'],2)

    def test_no_eye_frames_and_invalid_identity_never_create_location(self):
        loc=self.locator([[],[]])
        self.assertIsNone(loc.update(self.pixels,1,1)['box'])
        for index,t in [(1,2),(2,1),(2,float('nan'))]:
            with self.assertRaises(ValueError):loc.update(self.pixels,index,t)
        with self.assertRaises(ValueError):loc.update(self.pixels.astype(float),2,2)
        self.assertEqual(loc.update(self.pixels,2,2)['state'],'searching')

    def test_duplicate_suppression_bounds_and_clipped_display_crop(self):
        boxes=normalize_boxes([self.left,(72,172,198,298),self.right,(-5,0,100,100),(1,2,3,4),(1,2,float('nan'),100)])
        self.assertEqual(boxes,[self.left,self.right])
        for b in [(0,0,90,90),(530,370,640,480)]:
            x0,y0,x1,y1=display_crop(b)
            self.assertTrue(0<=x0<x1<=640 and 0<=y0<y1<=480)
            self.assertEqual(x1-x0,y1-y0)
