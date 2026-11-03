"""Synthetic local-input/navigation checks; not real-eye acceptance."""
import hashlib,json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from eye_tracker.album import PhotoLibrary,PHOTO_BOX,PHOTO_BYTES
from eye_tracker.composer import PinyinLexicon,Composer,Favorites,MAX_TEXT
from eye_tracker.daily_tools import DailyTools,SLOT_KEYS,validate_options
from eye_tracker.interaction import DwellController,GazeSample,MAIN_TARGETS
from eye_tracker.calibration import Context
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from import_photos import import_photo

def fixture(path=None):
    lex=PinyinLexicon(ROOT/'assets/typing/pinyin.json')
    return DailyTools(PhotoLibrary(ROOT/'assets/photos'),Composer(lex,Favorites(lex,path)))

class ComposerTests(unittest.TestCase):
    def setUp(self):self.d=fixture();self.c=self.d.composer
    def test_pinyin_commits_one_character_then_resets_syllable(self):
        for py,ch in [('ni','你'),('hao','好'),('lv','绿')]:
            for letter in py:self.assertTrue(self.c.letter(letter))
            self.assertTrue(self.c.candidate(self.c.lexicon.candidates(py).index(ch)))
            self.assertEqual(self.c.pinyin,'')
        self.assertEqual(self.c.text,'你好绿')
        self.assertEqual(self.c.lexicon.candidates('shui')[0],'水')
    def test_limits_invalid_characters_erase_and_clear(self):
        for _ in range(6):self.assertTrue(self.c.letter('a'))
        self.assertFalse(self.c.letter('b'));self.c.text='我'*64
        self.assertFalse(self.c.append('好'));self.c.erase();self.assertEqual(len(self.c.pinyin),5)
        self.c.pinyin='';self.c.erase();self.assertEqual(len(self.c.text),63)
        with self.assertRaises(ValueError):self.c.append('A')
        self.c.clear();self.assertEqual((self.c.text,self.c.pinyin),('',''))
    def test_full_body_does_not_consume_pending_candidate(self):
        self.c.text='我'*64;self.c.pinyin='ni';self.assertFalse(self.c.candidate(0));self.assertEqual(self.c.pinyin,'ni')
    def test_saved_phrases_survive_reload_duplicate_and_capacity(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'favorites.json';f=Favorites(self.c.lexicon,p)
            self.assertEqual(f.save('你好'),'saved');self.assertEqual(f.save('你好'),'already_saved')
            for i in range(11):f.save('我'+str(i))
            self.assertEqual(f.save('好'),'full');self.assertEqual(len(Favorites(self.c.lexicon,p).items),12)
            f.delete(0);self.assertEqual(len(Favorites(self.c.lexicon,p).items),11)
    def test_save_failure_keeps_previous_disk_and_memory_and_draft(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'favorites.json';d=fixture(p);d.composer.text='你好';d.composer.favorites.save('好');before=p.read_bytes()
            d.state='present'
            with patch.object(Path,'replace',side_effect=OSError('full')):d.select(1)
            self.assertEqual(p.read_bytes(),before);self.assertEqual(d.composer.favorites.items,['好']);self.assertEqual(d.composer.text,'你好')
            self.assertIn('未成功',d.notice);self.assertFalse(p.with_suffix('.json.pending').exists())
    def test_malformed_saved_data_and_dictionary_fail_before_hardware(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.json'
            for data in ([],{'version':1,'items':['不允许A']},{'version':1,'items':['我','我']}):
                p.write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaises(ValueError):Favorites(self.c.lexicon,p)
            for data in ([],{'version':1,'syllables':{'ni':'你你'}},{'version':1,'syllables':{'NI':'你'}}):
                p.write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaises(ValueError):PinyinLexicon(p)
    def test_load_delete_and_clear_require_explicit_confirmation(self):
        d=self.d;d.composer.text='你好';d.composer.favorites.save('谢谢');d.state='favorites';d.select(0)
        d.select(1);self.assertEqual(d.state,'load_confirm');d.select(1);self.assertEqual(d.composer.text,'你好')
        d.select(1);d.select(0);self.assertEqual(d.composer.text,'谢谢')
        d.state='favorites';d.select(0);d.select(2);d.select(1);self.assertEqual(d.composer.favorites.items,['谢谢'])
        d.select(2);d.select(0);self.assertEqual(d.composer.favorites.items,[]);self.assertEqual(d.composer.text,'谢谢')
        d.state='edit';d.select(2);d.select(1);self.assertEqual(d.composer.text,'谢谢');d.select(2);d.select(0);self.assertEqual(d.composer.text,'')
    def test_candidate_and_favorite_odd_pagination_wraps_without_skipping(self):
        d=self.d;d.composer.pinyin='ni';d.state='candidates';n=len(d.candidate_choices());seen=[]
        for _ in range((n+1)//2):
            seen.extend(c.value for c in d.view().choices[:2] if c and c.command=='candidate');d.select(2)
        self.assertEqual(seen,list(range(len(d.composer.candidates()))));self.assertEqual(d.candidate_offset,0)
        for s in ('你','好','我'):d.composer.favorites.save(s)
        d.state='favorites';d.select(2);self.assertEqual(d.view().choices[0].value,2);self.assertIsNone(d.view().choices[1]);d.select(2);self.assertEqual(d.favorite_offset,0)
    def test_empty_candidates_and_empty_draft_do_not_expose_invalid_actions(self):
        self.d.state='candidates';self.assertEqual(self.d.view().choices[:3],(None,None,None))
        self.d.state='present';self.assertEqual(self.d.view().choices[:2],(None,None))
    def test_draft_survives_navigation_and_reposition_without_automatic_show(self):
        self.c.text='想你';self.c.pinyin='hao';self.d.open('album');self.d.reset_navigation()
        self.assertEqual((self.c.text,self.c.pinyin),('想你','hao'));self.assertEqual(self.d.state,'compose');self.assertEqual(self.d.display_text,'')

class DailyNavigationTests(unittest.TestCase):
    def setUp(self):
        self.d=fixture();self.c=DwellController(Context('test','four','live'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=self.d);self.seq=0;self.time=0
    def feed(self,point,n=15,status='valid'):
        result=[]
        for _ in range(n):
            self.seq+=1;self.time+=100;a=self.c.feed(GazeSample(self.c.context,'checked',self.seq,self.time,status,point),self.time)
            if a:result.append(a)
        return result
    def choose(self,key):
        self.feed((.5,.55),5);target=next(t for t in self.c.targets if t.key==key);l,t,r,b=target.rect
        out=self.feed(((l+r)/2,(t+b)/2));self.assertEqual([a.key for a in out],[key]);return out[0]
    def slot(self,i):return self.choose('help' if self.d.view().choices[i].command=='help' else SLOT_KEYS[i])
    def enter_typing(self):self.choose('more');self.choose('communication_open');self.choose('typing_open')
    def letter(self,letter):
        if self.d.state=='suggestions':self.slot(2)
        if self.d.state=='candidates':self.slot(3)
        while True:
            index=next(i for i,c in enumerate(self.d.view().choices[:3]) if c and letter in c.value)
            leaf=len(self.d.view().choices[index].value)==1;self.slot(index)
            if leaf:break
    def test_grouped_gaze_sequence_composes_displays_saves_and_returns(self):
        self.enter_typing();self.slot(0);self.slot(1)
        for py,ch in [('ni','你'),('hao','好')]:
            for letter in py:self.letter(letter)
            self.assertEqual(self.d.state,'candidates')
            while ch not in [c.label for c in self.d.view().choices[:2] if c]:self.slot(2)
            self.slot(next(i for i,c in enumerate(self.d.view().choices[:2]) if c and c.label==ch))
        self.assertEqual(self.d.composer.text,'你好');self.slot(3);self.slot(2);self.slot(1)
        self.assertEqual(self.d.composer.favorites.items,['你好']);self.slot(0);self.assertEqual(self.d.view().body,'你好')
        self.assertEqual(self.slot(2).phrase,'请来帮助我');self.slot(3);self.slot(3);self.slot(3);self.slot(3)
        self.assertEqual(self.c.page,'daily_communication');self.assertNotIn('你好',repr(self.d.last_event))
    def test_same_slot_and_invalid_input_cannot_repeat_letters(self):
        self.enter_typing();self.slot(0);self.slot(1);self.slot(0);self.slot(0);self.slot(0)
        self.assertEqual(self.d.composer.pinyin,'a');self.assertEqual(self.feed((.25,.38),40),[])
        self.feed(None,5,'closed');self.assertEqual(self.feed((.25,.38),20),[])
        self.feed((.5,.55),4);self.assertEqual(self.feed((.25,.38),9),[])
        self.assertEqual(len(self.feed((.25,.38),3)),1);self.assertEqual(self.d.composer.pinyin,'')
        self.assertEqual(self.d.composer.text,self.d.composer.lexicon.candidates('a')[0])
    def test_photo_view_has_only_return_and_cannot_switch_by_looking_at_picture(self):
        self.choose('more');self.choose('leisure_open');self.choose('album_open');self.slot(1);self.slot(2)
        self.assertEqual(self.d.photo_index,1);self.assertEqual([t.key for t in self.c.targets],['tool_slot_3'])
        for p in ((.25,.38),(.75,.38),(.25,.7)):self.assertEqual(self.feed(p,30),[])
        self.slot(3);self.assertEqual(self.d.state,'album');self.assertEqual(self.feed((.75,.7),30),[])
        self.slot(1);self.assertEqual(self.d.photo_index,2)
    def test_pause_cancel_lost_and_invalid_reference_do_not_commit_text(self):
        self.enter_typing();self.d.state='candidates';self.d.composer.pinyin='ni'
        self.feed((.5,.55),5);self.feed((.25,.38),8);self.feed(None,2,'lost');self.assertEqual(self.feed((.25,.38),8),[])
        self.c.pause(self.time);self.assertEqual(self.feed((.25,.38),30),[]);self.c.resume(self.time)
        self.c.invalidate_calibration();self.assertEqual(self.feed((.25,.38),30),[]);self.assertEqual(self.d.composer.text,'')
    def test_feature_requires_explicit_complete_local_enable(self):
        validate_options(True,True,True,True,True)
        for flags in ((False,True,True,False),(True,False,True,False),(True,True,False,False)):
            with self.assertRaises(ValueError):validate_options(True,*flags)

class AlbumAndDisplayTests(unittest.TestCase):
    def test_three_assets_are_hash_checked_and_cache_one_immutable_frame(self):
        lib=PhotoLibrary(ROOT/'assets/photos');self.assertEqual(len(lib.photos),3)
        one=lib.frame(0);self.assertIs(one,lib.frame(0));self.assertEqual(one.nbytes,PHOTO_BYTES);self.assertFalse(one.flags.writeable)
        two=lib.frame(1);self.assertFalse(np.array_equal(one,two));self.assertIsNot(one,lib.frame(0))
    def test_import_replace_path_and_hash_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'source.png';Image.new('RGB',(200,100),'red').save(p)
            import_photo(p,'test','照片',root)
            with self.assertRaises(ValueError):import_photo(p,'test','照片',root)
            with self.assertRaises(ValueError):import_photo(p,'../bad','照片',root)
            import_photo(p,'test','新照片',root,replace=True)
            folder=root/'assets/photos';self.assertEqual(PhotoLibrary(folder).photos[0]['title'],'新照片')
            raw=folder/'test.rgb565';raw.write_bytes(bytes(PHOTO_BYTES))
            with self.assertRaises(ValueError):PhotoLibrary(folder)
    def test_atlas_pages_render_bounded_and_dynamic_text_changes_pixels(self):
        from eye_tracker.ui import BoardRenderer
        d=fixture();c=DwellController(Context('test','four','live'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d);c.page='local_tools'
        r=BoardRenderer();r.bind_daily_tools(d);frames=[]
        d.composer.text='你好，谢谢！';d.composer.favorites.save('我想喝水');d.favorite_index=0;d.display_text='我'*32
        for state in ('album','photo_view','compose','keyboard','candidates','more','edit','symbols','clear_confirm','present','display','favorites','favorite','delete_confirm','load_confirm'):
            d.state=state;before=repr(vars(d));raw=r.rgb565(c,'guide_ready');self.assertEqual(len(raw),614400);self.assertEqual(before,repr(vars(d)));frames.append(raw)
        self.assertGreater(len(set(frames)),12)
        d.state='photo_view';words=np.frombuffer(r.rgb565(c),dtype='<u2').reshape(480,640);l,t,rr,b=PHOTO_BOX
        np.testing.assert_array_equal(words[t:t+100,l:rr],d.album.frame(0)[:100])
        with self.assertRaisesRegex(ValueError,'unbuilt'):r.daily_renderer.atlas.require('🦋')
    def test_atlas_rejects_dictionary_mismatch_and_no_binding(self):
        from eye_tracker.text_ui import GlyphAtlas
        with self.assertRaises(ValueError):GlyphAtlas(ROOT/'assets/typing/glyphs.npz','wrong')

    def test_dynamic_labels_have_readable_contrast_and_help_uses_same_card_layout(self):
        from eye_tracker.ui import BoardRenderer
        d=fixture();d.state='present';d.composer.text='你好'
        c=DwellController(Context('test','four','live'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d);c.page='local_tools'
        r=BoardRenderer();r.bind_daily_tools(d)
        for active in (None,'tool_slot_0','help'):
            c.target_key=active;c.progress=.6
            words=np.frombuffer(r.rgb565(c),dtype='<u2').reshape(480,640)
            for y in (167,321):
                area=words[y:y+32,70:270];dark=((area>>11)&31)<16
                self.assertGreater(np.count_nonzero(dark),200)

    def test_live_dwell_updates_reuse_bounded_text_cache_and_keep_progress_and_cursor(self):
        from eye_tracker.ui import BoardRenderer,progress_box
        d=fixture();c=DwellController(Context('test','four','live'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d);c.page='local_tools'
        r=BoardRenderer();r.bind_daily_tools(d);d.open('album');r.rgb565(c,'guide_ready')
        built=r.daily_renderer.cache_builds
        with patch.object(r.daily_renderer.atlas,'draw',side_effect=AssertionError('per-frame text rasterization')):
            c.target_key='tool_slot_0';c.progress=.5;c.cursor=(.2625,.38)
            raw=r.rgb565(c,'guide_ready');words=np.frombuffer(raw,dtype='<u2').reshape(480,640)
            l,t,rr,b=progress_box(MAIN_TARGETS[0]);np.testing.assert_array_equal(words[t:b,l:rr],r.tiles['local_album_progress_10'])
            c.progress=.8;self.assertNotEqual(raw,r.rgb565(c,'guide_page_release'))
            x,y=int(c.cursor[0]*640),int(c.cursor[1]*480);self.assertEqual(words[y,x],r.tiles['cursor'][15,15])
        self.assertEqual(r.daily_renderer.cache_builds,built)
        d.select(1);r.rgb565(c,'guide_ready');self.assertEqual(r.daily_renderer.cache_builds,built+1)
        self.assertLess(sum(a.nbytes for a in {id(a):a for a in r.daily_renderer.cache.values()}.values()),1500000)

    def test_cached_dynamic_pixels_match_fresh_build_after_navigation(self):
        from eye_tracker.ui import BoardRenderer
        d=fixture();c=DwellController(Context('test','four','live'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d);c.page='local_tools'
        r=BoardRenderer();r.bind_daily_tools(d)
        for state in ('compose','album','photo_view','keyboard','present','display'):
            d.state=state;d.composer.text='你好';d.display_text='我想喝水';c.target_key='tool_slot_3';c.progress=.55
            cached=r.rgb565(c,'guide_ready');r.daily_renderer._key=None
            self.assertEqual(cached,r.rgb565(c,'guide_ready'))

    def test_photo_return_caption_is_centered_on_original_gaze_anchor(self):
        from eye_tracker.ui import BoardRenderer
        from eye_tracker.fixation import POINTS
        d=fixture();d.state='photo_view';c=DwellController(Context('test','four','live'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d);c.page='local_tools'
        r=BoardRenderer();r.bind_daily_tools(d)
        words=np.frombuffer(r.rgb565(c),dtype='<u2').reshape(480,640)
        x,y=[round(v*s) for v,s in zip(POINTS['more'],(640,480))]
        self.assertEqual((x,y),(472,336))
        center=words[y-14:y+16,x-58:x+58]
        self.assertGreater(np.count_nonzero(((center>>11)&31)<16),400)
        self.assertEqual(c.targets[0].rect,MAIN_TARGETS[3].rect)
