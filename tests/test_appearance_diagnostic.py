import unittest
from eye_tracker.appearance_diagnostic import StableCandidate,DiagnosticRecording,CHECK_TARGETS
from eye_tracker.appearance import CoarseAppearanceModel
import numpy as np

class DiagnosticTemporalTests(unittest.TestCase):
 def test_brief_wrong_candidate_never_survives_and_resets_previous(self):
  g=StableCandidate()
  for i in range(1,7):result=g.update('water',i,i*.08,i*.08+.01)
  self.assertEqual(result,'water')
  self.assertIsNone(g.update('help',7,.56,.57))
  self.assertIsNone(g.update('water',8,.64,.65))
 def test_stale_or_missing_input_immediately_clears_candidate(self):
  g=StableCandidate()
  for i in range(1,7):g.update('rest',i,i*.08,i*.08+.01)
  self.assertIsNone(g.update('rest',7,.56,.80))
  self.assertIsNone(g.update('rest',8,.64,.65))
  self.assertIsNone(g.update(None,9,.72,.73))
 def test_large_gap_cannot_earn_stability_and_duplicate_fails(self):
  g=StableCandidate()
  self.assertIsNone(g.update('more',1,1.,1.01))
  self.assertIsNone(g.update('more',2,2.,2.01))
  with self.assertRaises(ValueError):g.update('more',2,2.1,2.11)
  self.assertIsNone(g.key)
 def test_instructed_label_never_reaches_predictor_and_prediction_is_not_action(self):
  class FakeEngine:
   class baseline:
    @staticmethod
    def finish():return {'ready':True}
   def observe(self,pixels,index,copied,clock):
    return {'candidate':'help','stable_candidate':'help','processing_ms':1,'actions_enabled':False}
  recording=DiagnosticRecording(FakeEngine());im=np.zeros((480,640),np.uint8)
  recording.observe(im,1,12.1,12.2,10.,1)
  self.assertEqual(recording.rows[0]['instructed_target'],'rest')
  self.assertEqual(recording.rows[0]['stable_candidate'],'help')
  self.assertFalse(recording.rows[0]['actions_enabled'])
 def test_fixed_plan_covers_all_classes_once(self):
  self.assertEqual({n for n,_,_ in CHECK_TARGETS},set(CoarseAppearanceModel.LABELS))
  self.assertEqual(len(CHECK_TARGETS),6)
  self.assertEqual(CHECK_TARGETS[0][2],'session_reference')
  self.assertEqual(sum(n=='center' and visit=='new_check' for n,_,visit in CHECK_TARGETS),1)

class TranslationDiagnosticTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import sys
  from pathlib import Path
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/deps/opencv'))
  import cv2
  cls.cv=cv2
 def setUp(self):
  from eye_tracker.appearance_diagnostic import TranslationMatcher
  rng=np.random.default_rng(23)
  self.ref=self.cv.GaussianBlur(rng.integers(0,256,(480,640),dtype=np.uint8),(11,11),3)
  self.matcher=TranslationMatcher(self.ref,(160,100,360,300))
 def test_translation_and_current_eye_pixels(self):
  M=np.float32([[1,0,12],[0,1,-8]]);im=self.cv.warpAffine(self.ref,M,(640,480))
  patch,result=self.matcher.align(im)
  self.assertLess(np.linalg.norm(np.asarray(result['translation'])-[12,-8]),.5)
  x0,y0,x1,y1=self.matcher.crop
  self.assertLess(np.mean(np.abs(patch.astype(float)-self.ref[y0:y1,x0:x1])),2)
  changed=self.ref.copy();changed[160:240,170:350]=230
  patch,result=self.matcher.align(changed)
  self.assertLess(np.linalg.norm(result['translation']),.5)
  self.assertGreater(np.mean(np.abs(patch.astype(float)-self.ref[y0:y1,x0:x1])),15)
 def test_blank_or_unrelated_neighborhood_is_rejected(self):
  from eye_tracker.appearance import AlignmentFailure
  with self.assertRaises(AlignmentFailure):self.matcher.align(np.zeros_like(self.ref))
  rng=np.random.default_rng(24);unrelated=self.cv.GaussianBlur(rng.integers(0,256,self.ref.shape,dtype=np.uint8),(11,11),3)
  with self.assertRaises(AlignmentFailure):self.matcher.align(unrelated)

class SessionBaselineTests(unittest.TestCase):
 def test_center_only_offset_is_frozen_and_preserves_new_direction_difference(self):
  from eye_tracker.appearance_diagnostic import SessionBaseline
  reference=np.full(1152,.4,np.float32);b=SessionBaseline(reference)
  for i in range(1,6):b.add(reference+.1,i)
  self.assertTrue(b.finish()['ready'])
  direction=reference+.1;direction[:100]+=.05
  expected=reference.copy();expected[:100]+=.05
  np.testing.assert_allclose(b.correct(direction),expected,atol=1e-6)
  with self.assertRaises(ValueError):b.add(reference,6)
  np.testing.assert_allclose(b.correct(direction),expected,atol=1e-6)
 def test_incomplete_or_excessive_setup_cannot_enable_reference(self):
  from eye_tracker.appearance_diagnostic import SessionBaseline
  ref=np.full(1152,.4,np.float32);b=SessionBaseline(ref);b.add(ref,1)
  self.assertFalse(b.finish()['ready'])
  with self.assertRaises(ValueError):b.correct(ref)
  b=SessionBaseline(ref)
  for i in range(1,6):b.add(ref+.3,i)
  self.assertFalse(b.finish()['ready'])
  with self.assertRaises(ValueError):b.correct(ref)
 def test_duplicate_frames_and_unstable_reference_are_rejected(self):
  from eye_tracker.appearance_diagnostic import SessionBaseline
  ref=np.full(1152,.4,np.float32);b=SessionBaseline(ref);b.add(ref,1)
  with self.assertRaises(ValueError):b.add(ref,1)
  b=SessionBaseline(ref)
  for i,v in enumerate((.05,.25,.45,.65,.85),1):b.add(np.full(1152,v),i)
  self.assertFalse(b.finish()['ready'])
 def test_reference_collection_never_scores_predictions(self):
  class Engine:
   def observe_reference(self,pixels,index,copied,eligible,clock):
    return dict(candidate=None,stable_candidate=None,actions_enabled=False,processing_ms=1,reference_sample=eligible)
   def observe(self,*a):raise AssertionError('classification during reference')
  r=DiagnosticRecording(Engine());r.observe(np.zeros((480,640),np.uint8),1,12.1,12.2,10.,0)
  self.assertFalse(r.rows[0]['scored']);self.assertTrue(r.rows[0]['reference_sample'])

class CornerRegistrationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):TranslationDiagnosticTests.setUpClass.__func__(cls)
 def setUp(self):TranslationDiagnosticTests.setUp(self)
 def test_corner_refinement_recovers_eye_motion_different_from_brow(self):
  from eye_tracker.appearance_diagnostic import CornerMatcher
  matcher=CornerMatcher(self.ref,(160,100,360,300),[[180,200],[340,200]])
  # Local eye band shifts vertically; coarse outer skin remains fixed.
  moved=self.cv.warpAffine(self.ref,np.float32([[1,0,0],[0,1,10]]),(640,480))
  current=self.ref.copy();current[150:260]=moved[150:260]
  patch,info=matcher.align(current)
  np.testing.assert_allclose(info['corner_centers'],[[180,210],[340,210]],atol=.6)
  x0,y0,x1,y1=matcher.crop
  self.assertLess(np.mean(np.abs(patch[:95].astype(float)-self.ref[y0:y0+95,x0:x1])),3)

class CornerEdgeTests(CornerRegistrationTests):
 def _near_edge(self,dx):
  from eye_tracker.appearance_diagnostic import CornerMatcher
  matcher=CornerMatcher(self.ref,(160,100,360,300),[[180,200],[340,200]])
  matcher.origin_shift=np.array([-100.,0.],np.float32)
  current=self.cv.warpAffine(self.ref,np.float32([[1,0,dx],[0,1,0]]),(640,480))
  return matcher,current
 def test_complete_eye_survives_clipped_search_margin(self):
  # True left corner x=44, full feature crop x=4. Only search margin is outside.
  matcher,current=self._near_edge(-136)
  patch,info=matcher.align(current)
  np.testing.assert_allclose(info['corner_centers'],[[44,200],[204,200]],atol=.6)
  x0,y0,x1,y1=matcher.crop
  self.assertLess(np.mean(np.abs(patch.astype(float)-self.ref[y0:y1,x0:x1])),2)
 def test_unobserved_final_feature_crop_still_rejected(self):
  from eye_tracker.appearance import AlignmentFailure
  matcher,current=self._near_edge(-144)
  with self.assertRaisesRegex(AlignmentFailure,'eye_crop_outside_frame'):matcher.align(current)
 def test_corner_cannot_match_in_padded_or_blank_edge(self):
  from eye_tracker.appearance import AlignmentFailure
  matcher,current=self._near_edge(-136)
  current[164:235,:68]=0
  with self.assertRaises(AlignmentFailure):matcher.align(current)
 def test_refined_crop_not_unused_coarse_crop_controls_visibility(self):
  # Coarse skin suggests dx=-144 (its crop would be off-screen), while eye
  # is observed at dx=-136. The final complete eye may still be evaluated.
  matcher,current=self._near_edge(-136)
  matcher._locate=lambda pixels:(np.array([-144.,0.]),{'translation':[-144.,0.],'neighborhood_score':.99})
  patch,info=matcher.align(current)
  np.testing.assert_allclose(info['corner_centers'],[[44,200],[204,200]],atol=.6)

class SetupRelocationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):TranslationDiagnosticTests.setUpClass.__func__(cls)
 def setUp(self):TranslationDiagnosticTests.setUp(self)
 def test_explicit_setup_relocates_without_expanding_inference_window(self):
  M=np.float32([[1,0,100],[0,1,16]]);im=self.cv.warpAffine(self.ref,M,(640,480))
  from eye_tracker.appearance import AlignmentFailure
  with self.assertRaises(AlignmentFailure):self.matcher.align(im)
  relocation=self.matcher.acquire(im)
  np.testing.assert_allclose(relocation['origin_shift'],[100,16],atol=1)
  _,metrics=self.matcher.align(im)
  np.testing.assert_allclose(metrics['translation'],[100,16],atol=.6)
  with self.assertRaises(AlignmentFailure):self.matcher.align(self.ref)
 def test_duplicate_eye_neighborhood_cannot_relocate_automatically(self):
  from eye_tracker.appearance import AlignmentFailure
  repeated=np.zeros_like(self.ref);repeated[100:300,160:360]=self.ref[100:300,160:360];repeated[100:300,400:600]=self.ref[100:300,160:360]
  with self.assertRaises(AlignmentFailure):self.matcher.acquire(repeated)


class BoundedCornerPeakTests(CornerRegistrationTests):
 def test_cut_off_strong_peak_is_bracketed_once_without_changing_feature(self):
  from eye_tracker.appearance_diagnostic import CornerMatcher
  matcher=CornerMatcher(self.ref,(160,100,360,300),[[180,200],[340,200]])
  matcher._locate=lambda pixels:(np.zeros(2),{'translation':[0,0],'neighborhood_score':1.})
  current=self.cv.warpAffine(self.ref,np.float32([[1,0,0],[0,1,29]]),(640,480))
  patch,result=matcher.align(current)
  self.assertEqual(result['corner_boundary_retry'],[True,True])
  np.testing.assert_allclose(result['corner_centers'],[[180,229],[340,229]],atol=.6)
  x0,y0,x1,y1=matcher.crop
  self.assertLess(np.mean(np.abs(patch.astype(float)-self.ref[y0:y1,x0:x1])),2)
 def test_peak_beyond_bounded_retry_and_blank_are_still_rejected(self):
  from eye_tracker.appearance_diagnostic import CornerMatcher
  from eye_tracker.appearance import AlignmentFailure
  matcher=CornerMatcher(self.ref,(160,100,360,300),[[180,200],[340,200]])
  matcher._locate=lambda pixels:(np.zeros(2),{'translation':[0,0],'neighborhood_score':1.})
  for pixels in (self.cv.warpAffine(self.ref,np.float32([[1,0,0],[0,1,42]]),(640,480)),np.zeros_like(self.ref)):
   with self.assertRaises(AlignmentFailure):matcher.align(pixels)


class AnatomicalFeatureCropTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):TranslationDiagnosticTests.setUpClass.__func__(cls)
 def setUp(self):TranslationDiagnosticTests.setUp(self)
 def test_visible_eye_support_survives_missing_distant_skin(self):
  from eye_tracker.appearance_diagnostic import CornerMatcher
  from eye_tracker.appearance import AlignmentFailure
  legacy=CornerMatcher(self.ref,(160,100,360,300),[[180,200],[340,200]])
  compact=CornerMatcher(self.ref,(160,100,360,300),[[180,200],[340,200]],'eye_support_v1')
  # Both corners and the newly defined full feature area are observed.
  for matcher in (legacy,compact):matcher.origin_shift=np.array([-120.,0.])
  current=self.cv.warpAffine(self.ref,np.float32([[1,0,-144],[0,1,0]]),(640,480))
  with self.assertRaisesRegex(AlignmentFailure,'eye_crop_outside_frame'):legacy.align(current)
  patch,info=compact.align(current)
  x0,y0,x1,y1=compact.crop
  np.testing.assert_allclose(info['corner_centers'],[[36,200],[196,200]],atol=.6)
  self.assertLess(np.mean(np.abs(patch.astype(float)-self.ref[y0:y1,x0:x1])),2)
 def test_missing_required_support_is_still_rejected(self):
  from eye_tracker.appearance_diagnostic import CornerMatcher
  from eye_tracker.appearance import AlignmentFailure
  matcher=CornerMatcher(self.ref,(160,100,360,300),[[180,200],[340,200]],'eye_support_v1')
  matcher.origin_shift=np.array([-144.,0.])
  current=self.cv.warpAffine(self.ref,np.float32([[1,0,-168],[0,1,0]]),(640,480))
  with self.assertRaises(AlignmentFailure):matcher.align(current)
 def test_unknown_crop_cannot_silently_use_different_features(self):
  from eye_tracker.appearance_diagnostic import CornerMatcher
  with self.assertRaisesRegex(ValueError,'unknown_feature_crop_mode'):
   CornerMatcher(self.ref,(160,100,360,300),[[180,200],[340,200]],'unregistered')

class CurrentSessionPackTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):TranslationDiagnosticTests.setUpClass.__func__(cls)
 def setUp(self):TranslationDiagnosticTests.setUp(self)
 def test_single_visit_needs_explicit_current_fit_and_cannot_enable(self):
  import tempfile,json
  from pathlib import Path
  from eye_tracker.appearance_diagnostic import AppearanceDiagnostic
  from eye_tracker.appearance import CoarseAppearanceModel
  meta=dict(alignment='corners_and_session_reference',diagnostic_only=True,strict_training_passed=True,
      feature_crop_mode='eye_support_v1',template_visit_count=1,training_protocol='current_session_25',
      training_ids=['frame'+str(i)for i in range(25)],training_counts={k:5 for k in CoarseAppearanceModel.LABELS})
  def write(path,metadata):
   np.savez_compressed(path,reference=self.ref,box=np.array([160,100,360,300]),corners=np.array([[180,200],[340,200]]),
       metadata=np.array(json.dumps(metadata)),**{'template_'+k:np.full((1,1152),.5,np.float32)for k in CoarseAppearanceModel.LABELS})
  with tempfile.TemporaryDirectory()as folder:
   path=Path(folder)/'pack.npz';write(path,meta);engine=AppearanceDiagnostic(path)
   self.assertFalse(engine.model.enabled);self.assertIsNone(engine.baseline.offset)
   for key in ('training_protocol','training_ids','training_counts','strict_training_passed'):
    changed=dict(meta);changed.pop(key);write(path,changed)
    with self.assertRaises(ValueError):AppearanceDiagnostic(path)
   changed=dict(meta,template_visit_count=2);write(path,changed)
   with self.assertRaises(ValueError):AppearanceDiagnostic(path)
