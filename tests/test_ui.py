import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from eye_tracker.calibration import Context
from eye_tracker.interaction import DwellController, GazeSample, MAIN_TARGETS, MORE_TARGETS,ALL_TARGETS,PAGE_TARGETS
from eye_tracker.render import Renderer, feedback_message
from eye_tracker.framebuffer import DISPLAY, encode_frame
from eye_tracker.ui import BoardRenderer, ASSET, card_box
from eye_tracker.ui_test import InteractionTest, PHASES, run_on_board


class BoardUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer=BoardRenderer()

    def test_complete_acceptance_sequence_uses_the_real_controller(self):
        scenario=InteractionTest()
        for now in range(0,30000,50):
            scenario.step(now)
            if scenario.done:break
        result=scenario.result()
        self.assertTrue(result['scenario_completed'])
        self.assertEqual(len(result['phase_checks']),len(PHASES))
        self.assertTrue(all(check['passed'] for check in result['phase_checks']))
        self.assertEqual([a['key'] for a in result['actions']],['water','water','rest','more','back','help'])
        self.assertTrue(all(a['source']=='simulated' for a in result['actions']))
        self.assertFalse(result['camera_enabled'])
        self.assertFalse(result['audio_enabled'])
        self.assertFalse(result['real_gaze_validated'])
        self.assertGreater(result['missing_input_ticks'],0)

    def test_stalled_input_does_not_get_synthetic_catchup_actions(self):
        scenario=InteractionTest()
        scenario.step(0);scenario.step(800);scenario.step(950)
        scenario.step(3000)
        self.assertEqual(scenario.actions,[])
        self.assertEqual(scenario.controller.progress,0)
        with self.assertRaisesRegex(RuntimeError,'water_once'):
            scenario.step(3200)
        self.assertFalse(scenario.result()['scenario_completed'])

    def test_pixels_match_authoritative_artwork_for_all_cards_and_sources(self):
        font=Path('assets/fonts/noto_sans_cjk_sc.otf')
        if not font.is_file():self.skipTest('offline artwork reference requires the build font')
        reference=Renderer(font)
        for source in ('simulated','replay','live'):
            c=DwellController(Context('test','geometry',source),'test-only')
            for target in ALL_TARGETS:
                if target.key.startswith('tool_slot_'):continue  # Dynamic pages have dedicated atlas/interaction checks.
                c.page=next(page for page,targets in PAGE_TARGETS.items() if target in targets)
                if c.page=='emotion_display':c.emotion_key='emotion_happy'
                for state in ('idle','progress','locked','locked_idle'):
                    with self.subTest(source=source,target=target.key,state=state):
                        c.target_key=target.key if state in ('progress','locked') else None
                        c.progress=.6 if state=='progress' else 0
                        c.locks={target.key} if state.startswith('locked') else set()
                        c.cursor=None;c.reason='tracking'
                        message=feedback_message(source,target.key)
                        expected=encode_frame(np.asarray(reference.frame(c,message=message)))
                        self.assertEqual(self.renderer.rgb565(c,target.key),expected)

    def test_rendering_does_not_change_controller_and_handles_cursor_edges(self):
        c=DwellController(Context('test','geometry','simulated'),'test-only')
        for point in ((0,0),(1,1),(0,1),(1,0),(.25,.375)):
            c.cursor=point
            before=repr(vars(c))
            frame=self.renderer.rgb565(c)
            self.assertEqual(len(frame),DISPLAY.size_bytes)
            self.assertEqual(repr(vars(c)),before)

    def test_progress_never_rounds_up_or_displays_completion_early(self):
        c=DwellController(Context('test','geometry','simulated'),'test-only')
        c.target_key='water'
        c.progress=.999
        almost=self.renderer.rgb565(c)
        c.progress=.95
        self.assertEqual(almost,self.renderer.rgb565(c))
        c.progress=1
        self.assertNotEqual(almost,self.renderer.rgb565(c))

    def test_selected_button_stays_visibly_locked_after_lost_input(self):
        c=DwellController(Context('test','geometry','simulated'),'test-only')
        for seq,t in enumerate(range(0,1050,50)):
            c.feed(GazeSample(c.context,'test-only',seq,t,'valid',(.25,.37)),t)
        c.feed(GazeSample(c.context,'test-only',30,1100,'lost'),1100)
        frame=np.frombuffer(self.renderer.rgb565(c),dtype='<u2').reshape(480,640)
        l,t,r,b=card_box(MAIN_TARGETS[0])
        np.testing.assert_array_equal(frame[t:b,l:r],self.renderer.tiles['water_locked_idle'])

    def test_mismatched_geometry_or_malformed_tile_is_rejected(self):
        with np.load(ASSET,allow_pickle=False) as saved:
            arrays={name:saved[name] for name in saved.files}
        temp_root=Path(__file__).resolve().parents[1]/'build/test_tmp'
        temp_root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as folder:
            path=Path(folder)/'bad.npz'
            wrong=dict(arrays)
            meta=json.loads(arrays['metadata'].tobytes())
            meta['targets'][0]['rect'][0]=.1
            wrong['metadata']=np.frombuffer(json.dumps(meta).encode(),dtype=np.uint8)
            np.savez_compressed(path,**wrong)
            with self.assertRaisesRegex(ValueError,'geometry'):BoardRenderer(path)
            wrong=dict(arrays);wrong['water_active']=wrong['water_active'][:3]
            np.savez_compressed(path,**wrong)
            with self.assertRaisesRegex(ValueError,'tile'):BoardRenderer(path)

    def test_wrong_dwell_label_cannot_be_used(self):
        c=DwellController(Context('test','geometry','simulated'),'test-only',dwell_ms=800)
        with self.assertRaisesRegex(ValueError,'dwell'):self.renderer.rgb565(c)

    def test_startup_reference_pixels_match_and_never_show_selectable_cards(self):
        font=Path('assets/fonts/noto_sans_cjk_sc.otf')
        if not font.is_file():self.skipTest('offline artwork reference requires build font')
        reference=Renderer(font)
        for count in range(6):
            for failed in (False,True):
                self.assertEqual(self.renderer.setup_frame(count,failed),
                    encode_frame(np.asarray(reference.setup_frame(count,failed))))
        for count in (-1,6,True,1.5):
            with self.assertRaises(ValueError):self.renderer.setup_frame(count)

    def test_guidance_text_fits_compiled_message_region(self):
        from PIL import ImageFont
        from eye_tracker.render import EXTRA_MESSAGES
        font=Path('assets/fonts/noto_sans_cjk_sc.otf')
        if not font.is_file():self.skipTest('build font needed')
        face=ImageFont.truetype(str(font),14)
        for key,text in EXTRA_MESSAGES.items():
            if key.startswith('guide_'):
                with self.subTest(key=key):
                    self.assertLessEqual(face.getlength(text),548)
                    self.assertIn('message_live_'+key,self.renderer.tiles)

    def test_display_failure_preserves_incomplete_trace_and_propagates(self):
        class FailedDisplay:
            def present(self,frame):raise TimeoutError('display slot stuck')
        temp_root=Path(__file__).resolve().parents[1]/'build/test_tmp'
        temp_root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as folder:
            with self.assertRaisesRegex(TimeoutError,'slot stuck'):
                run_on_board(FailedDisplay(),self.renderer,Path(folder),now=lambda:0,sleep=lambda _:None)
            result=json.loads((Path(folder)/'interaction_trace.json').read_text())
            self.assertFalse(result['scenario_completed'])
            self.assertEqual(result['actions'],[])
