import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
from eye_tracker.session_calibration import FIT_TARGETS, candidate_bytes, save_candidate
from eye_tracker.appearance_diagnostic import AppearanceDiagnostic

class SessionCalibrationTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(34)
        reference=rng.integers(0,256,(480,640),dtype=np.uint8)
        self.features={}; samples=[]
        for step,(key,point,visit) in enumerate(FIT_TARGETS):
            for slot in range(5):
                index=step*5+slot
                pixels=reference.copy(); pixels[0,0]=index
                self.features[index]=np.full(1152,.15+.16*max(step-1,0),np.float32)
                meta=dict(step=step,slot=slot,target=key,target_normalized=list(point),visit=visit,
                          requested_after_present_s=2.+slot*.8,copied_after_present_s=2.05+slot*.8,
                          frame_index=index+1)
                samples.append((meta,pixels))
        engine=SimpleNamespace(reference=reference,box=(160,100,360,300),
            anchor=SimpleNamespace(corners=np.array([[180,200],[340,200]])),
            baseline=SimpleNamespace(summary={'ready':True},ids=set(range(1,6)),correct=lambda x:x),
            geometry_id='known-eye',pack_sha256='b'*64,
            metadata=dict(alignment='corners_and_session_reference',feature_crop_mode='eye_support_v1',
                          diagnostic_only=True,strict_training_passed=True),
            feature=Mock(side_effect=lambda pixels:(self.features[int(pixels[0,0])],{})))
        self.recording=SimpleNamespace(engine=engine,plan=FIT_TARGETS,samples=samples)

    def test_fitting_excludes_reference_and_never_enables_or_updates_source(self):
        data,meta=candidate_bytes(self.recording,'a'*64)
        self.assertEqual(len(meta['training_ids']),25)
        self.assertFalse(set(meta['training_ids']) & set(meta['session_reference_ids']))
        self.assertEqual(self.recording.engine.feature.call_count,25)
        self.assertEqual(self.recording.engine.pack_sha256,'b'*64)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'model.npz';p.write_bytes(data);engine=AppearanceDiagnostic(p)
            self.assertFalse(engine.model.enabled);self.assertIsNone(engine.baseline.offset)
            self.assertTrue(meta['strict_training_passed']);self.assertFalse(meta['calibration_passed'])
            self.assertFalse(meta['actions_enabled'])

    def test_incomplete_or_unaccepted_reference_and_duplicate_image_fail(self):
        self.recording.engine.baseline.summary={'ready':False}
        with self.assertRaisesRegex(ValueError,'fresh_center'):candidate_bytes(self.recording,'a'*64)
        self.recording.engine.baseline.summary={'ready':True}
        self.recording.engine.baseline.ids.remove(3)
        with self.assertRaisesRegex(ValueError,'unaccepted_center'):candidate_bytes(self.recording,'a'*64)
        self.recording.engine.baseline.ids.add(3)
        old=self.recording.samples[9]
        self.recording.samples[9]=(old[0],self.recording.samples[8][1])
        with self.assertRaisesRegex(ValueError,'duplicate'):candidate_bytes(self.recording,'a'*64)
        self.recording.samples.pop()
        with self.assertRaisesRegex(ValueError,'thirty'):candidate_bytes(self.recording,'a'*64)

    def test_check_labels_or_early_captures_cannot_be_used_as_fit(self):
        self.recording.plan=[(k,p,'new_check')for k,p,v in FIT_TARGETS]
        with self.assertRaisesRegex(ValueError,'fit_plan'):candidate_bytes(self.recording,'a'*64)
        self.recording.plan=FIT_TARGETS
        self.recording.samples[8][0]['requested_after_present_s']=1.9
        with self.assertRaisesRegex(ValueError,'provenance'):candidate_bytes(self.recording,'a'*64)

    def test_cross_class_and_alignment_failures_do_not_make_a_candidate(self):
        self.features[10]=self.features[20].copy()
        with self.assertRaisesRegex(ValueError,'cross_class'):candidate_bytes(self.recording,'a'*64)
        self.recording.engine.feature.side_effect=ValueError('corner_pair_not_matched')
        with self.assertRaisesRegex(ValueError,'corner_pair'):candidate_bytes(self.recording,'a'*64)

    def test_save_requires_completed_capture_and_never_overwrites_an_old_model(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'capture';(out/'targets').mkdir(parents=True)
            manifest=out/'targets/manifest.json'
            entries=[{'sha256':hashlib.sha256(p.tobytes()).hexdigest()}for _,p in self.recording.samples]
            manifest.write_text(json.dumps(dict(completed_run=False,samples_detail=entries)))
            with self.assertRaisesRegex(ValueError,'completed_fit'):save_candidate(self.recording,out,root)
            self.assertFalse((out/'session_calibration').exists())
            manifest.write_text(json.dumps(dict(completed_run=True,samples_detail=entries)))
            source=root/'src/eye_tracker';source.mkdir(parents=True)
            for n in ('appearance.py','appearance_diagnostic.py','corner_pair.py','session_calibration.py'):
                (source/n).write_text('# fixture')
            result=save_candidate(self.recording,out,root)
            self.assertFalse(result['independent_check_passed'])
            original=(out/'session_calibration/model.npz').read_bytes()
            with self.assertRaises(FileExistsError):save_candidate(self.recording,out,root)
            self.assertEqual(original,(out/'session_calibration/model.npz').read_bytes())
