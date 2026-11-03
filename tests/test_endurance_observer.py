import importlib.util,unittest
from pathlib import Path
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location('endurance_observer',Path(__file__).resolve().parents[1]/'tools/check_upgrade_endurance.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class Player:
    def __init__(self):
        self.state='playing';self.offset=0;self.index=0;self.calls=0
        self.library=SimpleNamespace(tracks=[dict(id='track',frames=16)])
    def poll(self):self.calls+=1;self.offset=16;self.state='ended';return 7

class ObserverTests(unittest.TestCase):
    def test_delegates_once_and_records_complete_track_once(self):
        observer=module.Observer(clock=lambda:0)
        player=module.observed_player(Player,observer)()
        self.assertEqual(player.poll(),7);player.poll()
        self.assertEqual(player.calls,2)
        ends=[e for e in observer.events if e['event']=='natural_end']
        self.assertEqual(len(ends),1);self.assertTrue(ends[0]['sample_count_matches'])
    def test_original_fault_propagates_without_false_completion(self):
        class Failed(Player):
            def poll(self):raise RuntimeError('underrun')
        observer=module.Observer(clock=lambda:0);player=module.observed_player(Failed,observer)()
        with self.assertRaisesRegex(RuntimeError,'underrun'):player.poll()
        self.assertEqual(observer.events,[])
    def test_mismatched_completion_is_marked_and_history_bounded(self):
        observer=module.Observer(clock=lambda:0);player=Player();player.state='ended'
        for _ in range(300):observer.observe(player,'playing')
        self.assertEqual(len(observer.events),256)
        self.assertFalse(observer.events[-1]['sample_count_matches'])
        self.assertEqual(observer.events.summary()['counts']['natural_end'],300)
