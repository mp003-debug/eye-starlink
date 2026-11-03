import unittest
from dataclasses import replace
import math
import numpy as np
from eye_tracker.calibration import Context, Observation, CalibrationPoint, AffineCalibration
from eye_tracker.demo import synthetic_observation, FIT_TARGETS, CHECK_TARGETS


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.context=Context('test','fixed','simulated')
        self.fit=[CalibrationPoint(synthetic_observation('f'+str(i),p,self.context),p) for i,p in enumerate(FIT_TARGETS)]
        self.checks=[CalibrationPoint(synthetic_observation('c'+str(i),p,self.context),p) for i,p in enumerate(CHECK_TARGETS)]

    def test_affine_predicts_unused_point_and_signed_features(self):
        model=AffineCalibration.fit(self.fit,self.checks)
        obs=synthetic_observation('unused',(.35,.65),self.context)
        self.assertLess(obs.feature()[0],0)
        np.testing.assert_allclose(model.project(obs),(.35,.65),atol=1e-10)
        self.assertFalse(model.metrics['optical_acceptance'])

    def test_common_pixel_translation_cancels_algebraically(self):
        a=synthetic_observation('a',(.35,.6),self.context)
        b=synthetic_observation('b',(.35,.6),self.context,shift=(20,-10))
        self.assertEqual(a.feature(),b.feature())

    def test_reused_frame_rejected(self):
        checks=list(self.checks)
        checks[0]=replace(checks[0],observation=replace(checks[0].observation,frame_id='f0'))
        with self.assertRaisesRegex(ValueError,'leakage'):AffineCalibration.fit(self.fit,checks)

    def test_independent_failure_does_not_refit(self):
        checks=[replace(p,observation=replace(p.observation,pupil=(p.observation.pupil[0]+8,p.observation.pupil[1]))) for p in self.checks]
        with self.assertRaises(ValueError):AffineCalibration.fit(self.fit,checks)

    def test_degenerate_features_rejected(self):
        points=[replace(p,observation=replace(p.observation,pupil=(160+i,120+i))) for i,p in enumerate(self.fit)]
        with self.assertRaises(ValueError):AffineCalibration.fit(points,self.checks)

    def test_context_and_roi_changes_rejected(self):
        model=AffineCalibration.fit(self.fit,self.checks)
        obs=self.checks[0].observation
        for changed in (replace(obs,context=Context('test','moved','simulated')),replace(obs,roi_size=(640,480)),
                        replace(obs,context=Context('test','fixed','live'))):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):model.project(changed)

    def test_no_extrapolation_or_clipping(self):
        model=AffineCalibration.fit(self.fit,self.checks)
        with self.assertRaisesRegex(ValueError,'region'):
            model.project(synthetic_observation('out',(.98,.5),self.context))

    def test_nonfinite_coordinates_and_thresholds_rejected(self):
        for value in (float('nan'),float('inf')):
            with self.assertRaises(ValueError):replace(self.fit[0].observation,pupil=(value,20)).feature()
            with self.assertRaises(ValueError):AffineCalibration.fit(self.fit,self.checks,max_check_error=value)

    def test_mixed_sessions_and_missing_targets_rejected(self):
        checks=[replace(p,observation=replace(p.observation,context=Context('other','fixed','simulated'))) for p in self.checks]
        with self.assertRaises(ValueError):AffineCalibration.fit(self.fit,checks)
        with self.assertRaises(ValueError):AffineCalibration.fit(self.fit[:4],self.checks)


if __name__=='__main__':unittest.main()
