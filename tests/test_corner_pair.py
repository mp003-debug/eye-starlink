import unittest
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/deps/opencv'))
import cv2
from eye_tracker.corner_pair import PairCornerMatcher
from eye_tracker.appearance import AlignmentFailure

class PairCornerTests(unittest.TestCase):
 def setUp(self):
  rng=np.random.default_rng(472)
  self.reference=cv2.GaussianBlur(rng.integers(0,256,(480,640),dtype=np.uint8),(7,7),1.5)
  self.m=PairCornerMatcher(self.reference,(140,100,364,324),[[164,200],[364,200]],'eye_support_v1')
 def moved(self,dx,dy):return cv2.warpAffine(self.reference,np.float32([[1,0,dx],[0,1,dy]]),(640,480))
 def test_setup_can_relocate_far_without_reusing_skin_template(self):
  px=self.moved(120,30);px[:170]=110;px[270:]=130
  self.m.acquire(px);patch,info=self.m.align(px)
  np.testing.assert_allclose(info['corner_centers'],[[284,230],[484,230]],atol=.5)
  self.assertEqual(info['alignment'],'paired_corners_v1')
 def test_blank_one_corner_and_unrelated_images_are_rejected(self):
  one=self.reference.copy();one[168:232,344:384]=127
  for px in (np.zeros_like(one),one,np.flipud(self.reference)):
   with self.assertRaises(AlignmentFailure):self.m.acquire(px)
 def test_two_complete_same_identity_pairs_are_ambiguous(self):
  px=self.reference.copy();px[328:392,144:184]=self.reference[168:232,144:184]
  px[328:392,344:384]=self.reference[168:232,344:384]
  with self.assertRaisesRegex(AlignmentFailure,'ambiguous'):self.m.acquire(px)
 def test_interaction_never_reacquires_outside_frozen_neighborhood(self):
  self.m.acquire(self.reference);old=self.m.origin_shift.copy()
  with self.assertRaises(AlignmentFailure):self.m.align(self.moved(120,0))
  np.testing.assert_array_equal(self.m.origin_shift,old)
 def test_complete_corners_do_not_allow_missing_feature_crop(self):
  with self.assertRaises(AlignmentFailure):self.m.acquire(self.moved(-145,0))
 def test_current_eye_texture_is_used_without_template_substitution(self):
  self.m.acquire(self.reference);px=self.reference.copy();px[195:216,220:310]=230
  patch,info=self.m.align(px);left,top,right,bottom=self.m.crop
  self.assertGreater(float(patch[195-top:216-top,220-left:310-left].mean()),225)

 def test_parallel_and_serial_matching_return_identical_current_pixels(self):
  serial=PairCornerMatcher(self.reference,self.m.box,self.m.corners,'eye_support_v1',parallel=False)
  for dx,dy in ((0,0),(12,-7),(120,30)):
   px=self.moved(dx,dy);a=self.m.acquire(px);b=serial.acquire(px)
   self.assertEqual(a,b)
   p1,m1=self.m.align(px);p2,m2=serial.align(px)
   np.testing.assert_array_equal(p1,p2);self.assertEqual(m1,m2)
  # A failed parallel attempt has finished both readers before the next frame.
  with self.assertRaises(AlignmentFailure):self.m.acquire(np.zeros_like(self.reference))
  self.m.acquire(self.reference)
