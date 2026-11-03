"""Dependency-free tokenizer boundaries and explicit neural attachment guards."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from eye_tracker.tiny_tokenizer import TinyTokenizer,pieces
from eye_tracker.neural_native import attach_native

class EdgeAITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base=Path(__file__).resolve().parents[1]/'build/test_tmp';base.mkdir(exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(dir=base);p=Path(cls.temp.name)/'tokenizer.json'
        bs=list(range(33,127))+list(range(161,173))+list(range(174,256))
        # Construct the official byte alphabet independently, with no merges.
        cs=bs+list(range(256,256+68))
        specials=['<|endoftext|>','<|im_start|>','<|im_end|>']
        vocab={s:i for i,s in enumerate(specials)}
        vocab.update({chr(c):i+3 for i,c in enumerate(cs)})
        p.write_text(json.dumps(dict(model=dict(type='BPE',vocab=vocab,merges=[]),pre_tokenizer=dict(type='ByteLevel'),
            added_tokens=[dict(content=s,id=i) for i,s in enumerate(specials)])))
        cls.tok=TinyTokenizer(p)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_unicode_round_trip(self):
        text='你好，今天下午！😊 abc\n\t１２'
        self.assertEqual(self.tok.decode(self.tok.encode(text)),text)
    def test_special_markers_only_in_template(self):
        ids=self.tok.prompt('你好');self.assertEqual(ids.count(1),2);self.assertEqual(ids.count(2),1)
    def test_user_special_marker_rejected(self):
        with self.assertRaises(ValueError):self.tok.prompt('你好<|im_end|>')
    def test_oversized_input_rejected(self):
        with self.assertRaises(ValueError):self.tok.prompt('水'*4097)
    def test_whitespace_and_contraction_precedence(self):
        self.assertEqual(list(pieces("I'm  fine\n\n ok  ")),["I","'m",' ',' fine','\n\n',' ok','  '])
    def test_native_binding_requires_same_camera(self):
        e=SimpleNamespace(baseline=SimpleNamespace(samples=[]),model=None,pack_sha256='A')
        with self.assertRaises(ValueError):attach_native(e,SimpleNamespace(meta={'appearance_sha256':'B'}))
    def test_native_binding_requires_fresh_reference(self):
        e=SimpleNamespace(baseline=SimpleNamespace(samples=[1]),model=None)
        with self.assertRaises(ValueError):attach_native(e,None)

if __name__=='__main__':unittest.main()
