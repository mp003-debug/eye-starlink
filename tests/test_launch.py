"""Launch-boundary tests: no real hardware or classifier success is simulated as evidence."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from eye_tracker import launch


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.profile = dict(version=1, model='private/model.npz', evidence='private/check',
                            duration_seconds=1200, audible=True)
        for name, relative in [('bit','build/fpga/eye_tracker.bit'),
                               ('hwh','build/fpga/eye_tracker.hwh'), ('model','private/model.npz')]:
            p=self.root/relative; p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(name.encode())
            self.profile['expected_'+name+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        for relative in ('private/check/runtime_manifest.json','private/check/diagnostic.json','build/fpga/result.json'):
            p=self.root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
        self.path=self.root/'profile.json'
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.profile),encoding='utf-8')

    def plan(self):
        with patch.object(launch,'verify_artifacts',return_value={'fixture_only':True}):
            return launch.prepare_launch(self.path,self.root)

    def test_reposition_is_explicit_and_preserves_wireless_opt_in(self):
        with patch.object(launch,'verify_artifacts',return_value={}):
            self.assertNotIn('--reposition-assist',launch.prepare_launch(self.path,self.root)['board_arguments'])
            p=launch.prepare_launch(self.path,self.root,reposition_assist=True)
            self.assertIn('--reposition-assist',p['board_arguments']);self.assertFalse(p['uart_enabled'])
            for mode in ('log','live'):
                p=launch.prepare_launch(self.path,self.root,eye_events=mode,reposition_assist=True)
                self.assertTrue(p['uart_enabled']);self.assertIn('--reposition-assist',p['board_arguments'])

    def test_daily_tools_require_explicit_flag_complete_features_and_support_wireless_opt_in(self):
        from eye_tracker.phrases import QUICK_KEYS
        for name in ['assets/speech/'+n for n in ['manifest.json']+[k+'.wav' for k in QUICK_KEYS]]+['assets/music/playlist.json','assets/photos/album.json','assets/typing/pinyin.json','assets/typing/glyphs.npz']:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture')
        with patch.object(launch,'verify_artifacts',return_value={'audio_ip_version':'0x00020000'}):
            self.assertNotIn('--daily-tools',launch.prepare_launch(self.path,self.root)['board_arguments'])
            p=launch.prepare_launch(self.path,self.root,music=True,quick_phrases=True,emotion_cards=True,daily_tools=True)
            self.assertIn('--daily-tools',p['board_arguments']);self.assertFalse(p['uart_enabled'])
            with self.assertRaises(ValueError):launch.prepare_launch(self.path,self.root,daily_tools=True)
            for mode in ('log','live'):
                p=launch.prepare_launch(self.path,self.root,music=True,quick_phrases=True,emotion_cards=True,daily_tools=True,eye_events=mode)
                self.assertTrue(p['uart_enabled']);self.assertIn('--daily-tools',p['board_arguments'])

    def test_stale_artifact_or_model_cannot_launch(self):
        for name,relative in [('bit','build/fpga/eye_tracker.bit'),('hwh','build/fpga/eye_tracker.hwh'),('model','private/model.npz')]:
            p=self.root/relative; original=p.read_bytes();p.write_bytes(b'wrong version')
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
                self.plan()
            p.write_bytes(original)

    def test_profile_cannot_enable_hidden_wireless_or_scripted_controls(self):
        for field in ('event_test','uart_enabled','trial_auto_controls'):
            self.profile[field]=True;self.write()
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'exactly'):
                self.plan()
            del self.profile[field]

    def test_no_unbounded_or_nonfinite_duration(self):
        for value in (True,0,9,1201,float('inf'),float('nan'),'60'):
            self.profile['duration_seconds']=value;self.write()
            with self.subTest(value=value),self.assertRaises(ValueError):self.plan()

    def test_demo_window_requires_cli_opt_in_and_keeps_profile_and_wireless_defaults(self):
        self.profile['duration_seconds']=2400;self.write()
        original=self.path.read_bytes()
        with self.assertRaises(ValueError):self.plan()
        with patch.object(launch,'verify_artifacts',return_value={}):
            plan=launch.prepare_launch(self.path,self.root,demo_window=True)
        self.assertIn('--demo-window',plan['board_arguments'])
        self.assertIn('2400',plan['board_arguments'])
        self.assertTrue(plan['demo_window']);self.assertFalse(plan['uart_enabled'])
        self.assertEqual(original,self.path.read_bytes())
        self.profile['duration_seconds']=3600;self.write()
        with self.assertRaises(ValueError):self.plan()
        with patch.object(launch,'verify_artifacts',return_value={}):
            hour=launch.prepare_launch(self.path,self.root,demo_window=True)
        self.assertIn('3600',hour['board_arguments'])
        self.assertFalse(hour['uart_enabled'])
        self.profile['duration_seconds']=3601;self.write()
        with self.assertRaises(ValueError):launch.load_profile(self.path,self.root,demo_window=True)

    def test_wrong_boolean_and_duplicate_json_are_rejected(self):
        self.profile['audible']='false';self.write()
        with self.assertRaises(ValueError):self.plan()
        self.profile['audible']=False;self.write()
        raw=self.path.read_text();self.path.write_text(raw[:-1]+',"audible":true}')
        with self.assertRaisesRegex(ValueError,'duplicate'):self.plan()

    def test_paths_cannot_escape_project(self):
        for value in ('../outside.npz','C:/outside.npz','/outside.npz','\\\\server\\share\\m.npz','private/../../outside.npz'):
            self.profile['model']=value;self.write()
            with self.subTest(value=value),self.assertRaises(ValueError):self.plan()

    def test_missing_independent_evidence_is_not_accepted(self):
        (self.root/'private/check/diagnostic.json').unlink()
        with self.assertRaisesRegex(ValueError,'required file missing'):self.plan()

    def test_unique_output_and_checks_do_not_create_files(self):
        first=self.plan();second=self.plan()
        self.assertNotEqual(first['output'],second['output'])
        self.assertFalse((self.root/'data').exists())
        self.assertFalse(first['positive_evidence_validated'])
        self.assertFalse(first['fresh_center_reference_verified'])
        self.assertFalse(first['uart_enabled'])
        self.assertIn('--trial-evidence',first['board_arguments'])
        self.assertNotIn('--event-test',first['board_arguments'])
        self.assertNotIn('--trial-auto-controls',first['board_arguments'])

    def test_offline_check_never_invokes_board(self):
        with patch.object(launch,'verify_artifacts',return_value={}),patch.object(launch,'_invoke_board') as invoke,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(launch.main(['--profile',str(self.path),'--check-only'],self.root),0)
        invoke.assert_not_called()
        self.assertFalse((self.root/'data').exists())

    def test_failed_board_gate_does_not_forge_run_or_success(self):
        with patch.object(launch,'verify_artifacts',return_value={}),patch.object(launch,'_invoke_board',side_effect=ValueError('independent check rejected')),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError,'independent check rejected'):
                launch.main(['--profile',str(self.path)],self.root)
        self.assertFalse((self.root/'data').exists())

    def test_board_exit_code_and_actual_result_are_preserved(self):
        def board_stub(arguments):
            p=Path(arguments[arguments.index('--output')+1]);p.mkdir(parents=True)
            (p/'result.json').write_text('{"completed":false}')
            return 1
        with patch.object(launch,'verify_artifacts',return_value={}),patch.object(launch,'_invoke_board',side_effect=board_stub),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(launch.main(['--profile',str(self.path)],self.root),1)
        output=next((self.root/'data/private/runs').iterdir())
        self.assertFalse(json.loads((output/'result.json').read_text())['completed'])
        self.assertIn('launch plan only',json.loads((output/'launch_profile.json').read_text())['scope'])

    def test_import_has_no_numpy_pynq_or_board_dependency(self):
        code="import sys; import eye_tracker.launch; assert 'pynq' not in sys.modules; assert 'eye_tracker.board' not in sys.modules; assert 'numpy' not in sys.modules"
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_music_opt_in_requires_audible_profile_and_matching_build(self):
        playlist=self.root/'assets/music/playlist.json'
        playlist.parent.mkdir(parents=True);playlist.write_text('{"version":1,"tracks":[]}')
        with patch.object(launch,'verify_artifacts',return_value={'audio_ip_version':'0x00010000'}):
            self.assertNotIn('--music',launch.prepare_launch(self.path,self.root)['board_arguments'])
            with self.assertRaisesRegex(ValueError,'audio IP v2'):
                launch.prepare_launch(self.path,self.root,music=True)
        with patch.object(launch,'verify_artifacts',return_value={'audio_ip_version':'0x00020000'}):
            plan=launch.prepare_launch(self.path,self.root,music=True)
            self.assertTrue(plan['music_enabled']);self.assertIn('--music',plan['board_arguments'])
            self.assertFalse(plan['uart_enabled'])
            self.profile['audible']=False;self.write()
            with self.assertRaisesRegex(ValueError,'audible profile'):
                launch.prepare_launch(self.path,self.root,music=True)

    def test_quick_phrases_explicit_flag_required_with_new_ip_and_assets(self):
        from eye_tracker.phrases import QUICK_KEYS
        folder=self.root/'assets/speech';folder.mkdir(parents=True)
        for name in ['manifest.json']+[key+'.wav' for key in QUICK_KEYS]:(folder/name).write_bytes(b'fixture')
        with patch.object(launch,'verify_artifacts',return_value={'audio_ip_version':'0x00010000'}):
            self.assertNotIn('--quick-phrases',launch.prepare_launch(self.path,self.root)['board_arguments'])
            with self.assertRaisesRegex(ValueError,'audio IP v2'):
                launch.prepare_launch(self.path,self.root,quick_phrases=True)
        with patch.object(launch,'verify_artifacts',return_value={'audio_ip_version':'0x00020000'}):
            plan=launch.prepare_launch(self.path,self.root,quick_phrases=True)
            self.assertTrue(plan['quick_phrases_enabled']);self.assertFalse(plan['music_enabled'])
            self.assertFalse(plan['uart_enabled']);self.assertIn('--quick-phrases',plan['board_arguments'])
            (folder/'toilet.wav').unlink()
            with self.assertRaisesRegex(ValueError,'required file missing'):
                launch.prepare_launch(self.path,self.root,quick_phrases=True)
            self.profile['audible']=False;self.write()
            with self.assertRaisesRegex(ValueError,'audible'):
                launch.prepare_launch(self.path,self.root,quick_phrases=True)

    def test_emotion_cards_require_explicit_local_feature_combination(self):
        from eye_tracker.phrases import QUICK_KEYS
        folder=self.root/'assets/speech';folder.mkdir(parents=True)
        for name in ['manifest.json']+[key+'.wav' for key in QUICK_KEYS]:(folder/name).write_bytes(b'fixture')
        music=self.root/'assets/music';music.mkdir();(music/'playlist.json').write_text('{}')
        with patch.object(launch,'verify_artifacts',return_value={'audio_ip_version':'0x00020000'}):
            self.assertNotIn('--emotion-cards',launch.prepare_launch(self.path,self.root)['board_arguments'])
            p=launch.prepare_launch(self.path,self.root,music=True,quick_phrases=True,emotion_cards=True)
            self.assertIn('--emotion-cards',p['board_arguments'])
            self.assertTrue(p['emotion_cards_enabled']);self.assertFalse(p['uart_enabled'])
            for mode in ('log','live'):
                p=launch.prepare_launch(self.path,self.root,music=True,quick_phrases=True,emotion_cards=True,eye_events=mode)
                self.assertTrue(p['uart_enabled'])
            for args in ({},{'music':True},{'quick_phrases':True}):
                with self.assertRaisesRegex(ValueError,'emotion cards require'):
                    launch.prepare_launch(self.path,self.root,emotion_cards=True,**args)
