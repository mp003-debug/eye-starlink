import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

from eye_tracker.trial_telemetry import BoundedTrialTelemetry, read_process_resources


class BoundedTrialTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.wall = 100.
        self.cpu = 20.
        self.t = BoundedTrialTelemetry(
            proc_root=self.tmp.name, resource_clock=lambda: self.wall,
            process_clock=lambda: self.cpu)
        self.pixels = np.full((480, 640), 37, np.uint8)

    def row(self, index, copied, valid=True, **extra):
        row = dict(frame_index=index, copied_monotonic=copied,
                   evaluated_monotonic=copied+.1,
                   candidate='water', stable_candidate='water' if valid else None,
                   reason='tracking' if valid else 'unknown',
                   processing_ms=80., copy_to_result_ms=100.)
        row.update(extra)
        return row

    def record(self, index, copied, valid=True, action=None, **extra):
        self.wall = 100.+copied
        self.cpu = 20.+.25*copied
        row = self.row(index, copied, valid, **extra)
        self.t.observe(self.pixels, row, action)
        return row

    def test_long_run_keeps_all_counters_and_bounds_retained_data(self):
        selected = 0
        for i in range(2600):
            action = SimpleNamespace(key='water') if i % 137 == 0 else None
            selected += action is not None
            last = self.record(i+1, i/10., valid=i % 20 < 10, action=action)
        last['presented_monotonic'] = 999.
        report = self.t.summary()
        self.assertEqual(report['total_frames'], 2600)
        self.assertEqual(report['total_selections'], selected)
        self.assertEqual(report['valid_frames'], 1300)
        self.assertEqual(report['invalid_frames'], 1300)
        self.assertEqual(sum(report['reason_counts'].values()), 2600)
        self.assertEqual(report['processing']['count'], 2600)
        self.assertAlmostEqual(report['processing']['sum_ms'], 2600*80.)
        self.assertEqual(report['processing']['mean_ms'], 80.)
        self.assertEqual(report['processing']['max_ms'], 80.)
        self.assertEqual(len(self.t.rows), 1800)
        self.assertEqual(self.t.rows[0]['frame_index'], 801)
        self.assertIs(self.t.rows[-1], last)
        self.assertEqual(self.t.rows[-1]['presented_monotonic'], 999.)
        self.assertEqual(len(self.t.audit), 120)
        self.assertEqual(len(self.t.audit_metadata), 120)
        self.assertEqual(report['retention']['rows_discarded'], 800)
        self.assertGreater(report['retention']['audit_discarded'], 0)
        self.assertEqual(report['retention']['audit_pixels_bytes_retained'], 120*320*240)
        self.assertEqual(report['retention']['audit_pixels_bytes_total'],
                         report['retention']['audit_samples_total']*320*240)
        self.assertAlmostEqual(report['max_inter_frame_gap_seconds'], .1)
        json.dumps(report, allow_nan=False)

    def test_periodic_only_audit_is_sparse_and_does_not_alias_dma_buffer(self):
        for i in range(301):
            self.record(i+1, i/10.)
        self.assertEqual([i for i, _ in self.t.audit], [1, 101, 201, 301])
        self.assertEqual([m['elapsed'] for m in self.t.audit_metadata], [0., 10., 20., 30.])
        self.pixels.fill(99)
        self.assertEqual(int(self.t.audit[0][1][0, 0]), 37)
        self.assertEqual(self.t.audit[0][1].shape, (240, 320))
        self.assertFalse(np.shares_memory(self.t.audit[0][1], self.pixels))

    def test_selection_and_validity_events_never_sample_faster_than_one_hz(self):
        for i in range(33):
            self.record(i+1, i/10., valid=i % 2 == 0, action=SimpleNamespace(key='help'))
        report = self.t.summary()
        self.assertEqual(report['total_selections'], 33)
        self.assertEqual(report['selection_counts'], {'help': 33})
        self.assertEqual(report['validity_transitions'], 32)
        self.assertEqual(report['retention']['audit_samples_total'], 4)
        times = [item['elapsed'] for item in self.t.audit_metadata]
        self.assertTrue(all(b-a >= 1 for a, b in zip(times, times[1:])))
        self.assertEqual(report['retention']['audit_rate_limited_frames'], 29)

    def test_validity_transition_is_sampled_without_an_action(self):
        self.record(1, 0.)
        self.record(2, 1.1, valid=False)
        self.record(3, 2.2)
        self.assertEqual(len(self.t.audit), 3)
        self.assertEqual(self.t.audit_metadata[1]['triggers'], ['validity_changed'])
        self.assertEqual(self.t.summary()['total_selections'], 0)

    def test_valid_is_current_stable_region_not_just_non_null_stable(self):
        self.record(1, 0.)
        self.record(2, 1., candidate='help', stable_candidate='water')
        self.record(3, 2., candidate=None, stable_candidate=None)
        self.record(4, 3., candidate='unknown', stable_candidate='unknown')
        report = self.t.summary()
        self.assertEqual(report['valid_frames'], 1)
        self.assertEqual(report['invalid_frames'], 3)

    def test_resources_are_ten_second_samples_with_single_core_cpu_and_endpoint(self):
        for i in range(1201):
            self.record(i+1, float(i))
        self.record(1202, 1200.5)
        report = self.t.summary()
        self.assertEqual(len(report['resources']), 122)
        self.assertIsNone(report['resources'][0]['cpu_percent_single_core'])
        self.assertAlmostEqual(report['resources'][1]['cpu_percent_single_core'], 25.)
        self.assertAlmostEqual(report['resource_end']['cpu_percent_single_core'], 25.)
        self.assertEqual(report['resource_start']['elapsed'], 0.)
        self.assertEqual(report['resource_end']['elapsed'], 1200.5)
        self.assertTrue(all(value is None for value in report['resource_end']['memory_kib'].values()))
        count = report['retention']['resource_samples_total']
        self.assertEqual(self.t.summary()['retention']['resource_samples_total'], count)

    def test_resource_and_reason_limits_hold_even_beyond_planned_duration(self):
        for i in range(150):
            self.record(i+1, i*10., reason='different_reason_'+str(i))
        report = self.t.summary()
        self.assertEqual(len(report['resources']), 128)
        self.assertEqual(report['retention']['resources_discarded'], 22)
        self.assertEqual(report['resource_start']['elapsed'], 0.)
        self.assertEqual(sum(report['reason_counts'].values()), 150)
        self.assertLessEqual(len(report['reason_counts']), 64)
        self.assertGreater(report['reason_counts']['__other__'], 0)

    def test_missing_invalid_metrics_and_empty_recording_are_json_safe(self):
        empty = self.t.summary()
        self.assertEqual(empty['total_frames'], 0)
        self.assertIsNone(empty['resource_start'])
        self.assertIsNone(empty['processing']['mean_ms'])
        self.record(1, 0., processing_ms=float('nan'), copy_to_result_ms=-1)
        self.record(2, 1., processing_ms=None, copy_to_result_ms=float('inf'))
        self.record(3, 4., processing_ms=42., copy_to_result_ms=48.)
        report = self.t.summary()
        self.assertEqual(report['processing']['count'], 1)
        self.assertEqual(report['processing']['missing_or_invalid'], 2)
        self.assertEqual(report['processing']['mean_ms'], 42.)
        self.assertEqual(report['max_inter_frame_gap_seconds'], 3.)
        self.assertNotIn('p95', json.dumps(report).lower())
        json.dumps(empty, allow_nan=False)
        json.dumps(report, allow_nan=False)

    def test_duplicate_or_nonfinite_frame_identity_does_not_count(self):
        self.record(1, 1.)
        for index, stamp in ((1, 2.), (2, 1.), (2, float('nan')), (True, 2.)):
            with self.assertRaises(ValueError):
                self.t.observe(self.pixels, self.row(index, stamp), None)
        self.assertEqual(self.t.total_frames, 1)


class ProcessResourceTests(unittest.TestCase):
    def test_reads_proc_kib_fields_and_ignores_other_units_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'self').mkdir()
            (root/'self'/'status').write_text(
                'Name: python\nVmRSS:\t1234 kB\nVmHWM: 2345 kB\n', encoding='ascii')
            (root/'meminfo').write_text(
                'MemAvailable: 4567 kB\nCmaFree: 8192 kB\nCmaTotal: 16384 kB\n', encoding='ascii')
            values = read_process_resources(root)
            self.assertEqual(values, dict(VmRSS=1234, VmHWM=2345, MemAvailable=4567,
                                          CmaFree=8192, CmaTotal=16384))
            (root/'meminfo').write_text(
                'MemAvailable: nan kB\nCmaFree: -1 kB\nCmaTotal: 999 MB\n', encoding='ascii')
            values = read_process_resources(root)
            self.assertIsNone(values['MemAvailable'])
            self.assertIsNone(values['CmaFree'])
            self.assertIsNone(values['CmaTotal'])
            self.assertEqual(values['VmRSS'], 1234)

    def test_missing_proc_files_are_null_without_platform_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(all(value is None for value in read_process_resources(tmp).values()))


if __name__ == '__main__':
    unittest.main()

