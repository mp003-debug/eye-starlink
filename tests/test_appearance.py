import unittest
import numpy as np
from eye_tracker.appearance import CoarseAppearanceModel,appearance_feature

class AppearanceModelTests(unittest.TestCase):
 def examples(self):
  result=[]
  for i,label in enumerate(CoarseAppearanceModel.LABELS):
   for j in range(5):
    a=np.zeros(1152,np.float32);a[i*200:(i+1)*200]=.8+j*.001
    result.append(dict(frame_id=label+str(j),target=label,visit='first',feature=a))
  return result
 def test_training_alone_never_enables_and_geometry_change_rejects(self):
  data=self.examples();m=CoarseAppearanceModel.fit(data,'one')
  self.assertFalse(m.enabled)
  self.assertIsNone(m.propose(data[0]['feature'],'two')['target'])
  self.assertIsNone(m.propose(np.full(1152,.5,np.float32),'one')['target'])
 def test_check_leakage_is_rejected_and_disables_previous_result(self):
  data=self.examples();m=CoarseAppearanceModel.fit(data,'one')
  with self.assertRaises(ValueError):m.validate(data,'one')
  self.assertFalse(m.enabled)
 def test_wrong_accepted_check_blocks_even_when_majority_is_correct(self):
  data=self.examples();m=CoarseAppearanceModel.fit(data,'one')
  checks=[dict(x,frame_id='check_'+x['frame_id']) for x in data]
  checks += [dict(frame_id='closed'+str(i),target='invalid',feature=np.full(1152,.5,np.float32)) for i in range(5)]
  self.assertTrue(m.validate(checks,'one')['passed'])
  checks[0]['feature']=data[5]['feature']
  self.assertFalse(m.validate(checks,'one')['passed']);self.assertFalse(m.enabled)
 def test_missing_or_ambiguous_target_cannot_create_model(self):
  data=self.examples()
  with self.assertRaises(ValueError):CoarseAppearanceModel.fit(data[5:],'one')
  for x in data:x['feature']=np.zeros(1152,np.float32)
  with self.assertRaises(ValueError):CoarseAppearanceModel.fit(data,'one')
 def test_single_outlier_is_not_forced_into_target(self):
  data=self.examples();data[0]['feature']=np.full(1152,.5,np.float32)
  m=CoarseAppearanceModel.fit(data,'one')
  self.assertIsNone(m.propose(data[0]['feature'],'one')['target'])
  self.assertEqual(m.training_support['center'][0]['retained'],4)
 def test_training_cross_class_error_is_not_hidden_by_majority(self):
  data=self.examples();data[0]['feature']=data[5]['feature'].copy()
  with self.assertRaisesRegex(ValueError,'cross_class_training_error'):
   CoarseAppearanceModel.fit(data,'one')
 def test_invalid_feature_is_not_silently_repaired(self):
  data=self.examples();m=CoarseAppearanceModel.fit(data,'one')
  for a in [np.zeros(1151),np.full(1152,float('nan')),np.full(1152,2.)]:
   with self.assertRaises(ValueError):m.propose(a,'one')


class EyeAnchorTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import sys
  from pathlib import Path
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/deps/opencv'))
  import cv2
  cls.cv=cv2
 def setUp(self):
  from eye_tracker.appearance import EyeAnchor
  rng=np.random.default_rng(17)
  self.ref=self.cv.GaussianBlur(rng.integers(0,256,(480,640),dtype=np.uint8),(5,5),0)
  self.anchor=EyeAnchor(self.ref,(160,100,360,300))
 def test_known_translation_aligns_current_pixels_without_drift(self):
  M=np.float32([[1,0,12],[0,1,-7]])
  current=self.cv.warpAffine(self.ref,M,(640,480))
  patch,result=self.anchor.align(current)
  self.assertLess(np.linalg.norm(np.asarray(result['delta_pixels'])-[12,-7]),.3)
  x0,y0,x1,y1=self.anchor.crop
  self.assertLess(np.mean(np.abs(patch.astype(float)-self.ref[y0:y1,x0:x1])),2)
  _,again=self.anchor.align(self.ref)
  self.assertLess(np.linalg.norm(again['delta_pixels']),.1)
 def test_eye_band_change_does_not_become_head_motion_or_stale_eye_pixels(self):
  current=self.ref.copy();current[160:240,170:360]=230
  patch,result=self.anchor.align(current)
  self.assertLess(np.linalg.norm(result['delta_pixels']),.5)
  x0,y0,x1,y1=self.anchor.crop
  self.assertGreater(np.mean(np.abs(patch.astype(float)-self.ref[y0:y1,x0:x1])),15)
  self.assertFalse(result['eye_open_validated'])
 def test_textureless_or_wrong_geometry_fails_closed(self):
  from eye_tracker.appearance import AlignmentFailure
  with self.assertRaises(AlignmentFailure):self.anchor.align(np.zeros((480,640),np.uint8))
  with self.assertRaises(AlignmentFailure):self.anchor.align(np.zeros((240,320),np.uint8))

 def test_distant_moving_texture_does_not_drive_eye_alignment(self):
  current=self.ref.copy();current[:70,:]=np.roll(current[:70,:],17,axis=1);current[330:,:]=np.roll(current[330:,:],-14,axis=1)
  patch,result=self.anchor.align(current)
  self.assertLess(np.linalg.norm(result['delta_pixels']),.5)
 def test_small_anisotropic_face_motion_aligns_but_excessive_shear_rejects(self):
  from eye_tracker.appearance import AlignmentFailure
  M=np.float32([[1.02,.025,-10],[-.01,.98,6]])
  current=self.cv.warpAffine(self.ref,M,(640,480));patch,result=self.anchor.align(current)
  x0,y0,x1,y1=self.anchor.crop
  self.assertLess(np.mean(np.abs(patch.astype(float)-self.ref[y0:y1,x0:x1])),6)
  bad=self.cv.warpAffine(self.ref,np.float32([[1,.3,-60],[0,1,0]]),(640,480))
  with self.assertRaises(AlignmentFailure):self.anchor.align(bad)


class DiscriminativeMetricTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import sys
  from pathlib import Path
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/deps/opencv'))
 def test_training_metric_never_enables_actions_or_consumes_check_examples(self):
  data=AppearanceModelTests().examples()
  model=CoarseAppearanceModel.fit(data,'geometry',discriminative=True)
  self.assertFalse(model.enabled)
  frozen=model.metric_weights.copy()
  self.assertTrue(all(model.propose(x['feature'],'geometry')['target']==x['target'] for x in data))
  with self.assertRaisesRegex(ValueError,'check_leakage'):
   model.validate(data,'geometry')
  np.testing.assert_array_equal(model.metric_weights,frozen)
  self.assertFalse(model.enabled)
 def test_weighted_fit_keeps_cross_class_conflict_block(self):
  data=AppearanceModelTests().examples();data[0]['feature']=data[5]['feature'].copy()
  with self.assertRaisesRegex(ValueError,'cross_class_training_error'):
   CoarseAppearanceModel.fit(data,'geometry',discriminative=True)
 def test_invalid_or_mutable_external_weights_cannot_change_decisions(self):
  for weights in (np.zeros(1152),np.ones(1151),np.full(1152,np.nan),np.full(1152,2.),np.r_[100.,np.ones(1151)]):
   with self.assertRaises(ValueError):CoarseAppearanceModel({},[],'g',weights)
  weights=np.ones(1152,np.float32);m=CoarseAppearanceModel({},[],'g',weights);weights[:]=0
  np.testing.assert_array_equal(m.metric_weights,np.ones(1152))
  with self.assertRaises(ValueError):m.metric_weights[0]=0
 def test_weight_training_is_order_independent_and_distinguishes_informative_pixels(self):
  data=AppearanceModelTests().examples()
  w=CoarseAppearanceModel.training_weights(data)
  np.testing.assert_allclose(w,CoarseAppearanceModel.training_weights(list(reversed(data))),atol=2e-6)
  self.assertGreater(float(w[:900].mean()),float(w[1050:].mean()))
  self.assertGreater(float(w.min()),0)
 def test_weighted_novelty_gate_rejects_unseen_patterns_and_changed_geometry(self):
  data=AppearanceModelTests().examples();m=CoarseAppearanceModel.fit(data,'g',discriminative=True)
  self.assertIsNone(m.propose(np.full(1152,.5,np.float32),'g')['target'])
  self.assertIsNone(m.propose(data[0]['feature'],'changed')['target'])
 def test_default_uniform_metric_matches_explicit_uniform_model(self):
  data=AppearanceModelTests().examples();m=CoarseAppearanceModel.fit(data,'g')
  other=CoarseAppearanceModel(m.templates,m.training_ids,'g',np.ones(1152))
  for x in data:self.assertEqual(m.propose(x['feature'],'g'),other.propose(x['feature'],'g'))
