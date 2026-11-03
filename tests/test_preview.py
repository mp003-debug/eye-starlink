import unittest
import numpy as np
from eye_tracker.preview import PreviewRenderer, frame_statistics
from eye_tracker.framebuffer import DISPLAY, encode_frame


class PreviewTests(unittest.TestCase):
    def test_image_layout_keeps_real_pixels_and_center_magnification(self):
        pixels=np.full((480,640),31,dtype=np.uint8)
        pixels[176:304,256:384]=187
        renderer=PreviewRenderer()
        image, stats=renderer.frame(pixels,10,1.0)
        self.assertEqual(image.size,(640,480))
        self.assertEqual(image.getpixel((30,114)),(31,31,31))
        self.assertEqual(image.getpixel((500,180)),(187,187,187))
        self.assertEqual(stats['bright_percent'],0)
        raw,_=renderer.rgb565(pixels,10,1.0)
        self.assertEqual(len(raw),DISPLAY.size_bytes)
        self.assertEqual(raw,encode_frame(np.asarray(image)))

    def test_clipping_and_invalid_camera_data_are_not_silently_accepted(self):
        pixels=np.zeros((480,640),dtype=np.uint8);pixels[:,320:]=255
        stats=frame_statistics(pixels)
        self.assertEqual(stats['bright_percent'],50)
        self.assertEqual(stats['dark_percent'],50)
        self.assertEqual(stats['mean'],127.5)
        for bad in (pixels.astype(np.float32),pixels[:200],pixels[:,:,None]):
            with self.assertRaises(ValueError):frame_statistics(bad)
        renderer=PreviewRenderer()
        for index,elapsed in ((0,1),(1,0),(1,float('nan'))):
            with self.assertRaises(ValueError):renderer.frame(pixels,index,elapsed)

    def test_board_legacy_bitmap_font_without_getbbox(self):
        renderer=PreviewRenderer()
        modern=renderer.font
        class LegacyFont:
            def getsize(self, text):
                box=modern.getbbox(text)
                return (box[2]-box[0],box[3])
            def getmask(self, text, *args, **kwargs):
                return modern.getmask(text,*args,**kwargs)
        renderer.font=LegacyFont()
        image,_=renderer.frame(np.zeros((480,640),dtype=np.uint8),1,1)
        self.assertEqual(image.size,(640,480))

    def test_fast_regions_match_reference_full_canvas_on_textured_frames(self):
        renderer=PreviewRenderer()
        pixels=np.random.default_rng(20261021).integers(0,256,(480,640),dtype=np.uint8)
        for index,elapsed in ((1,.2),(120,15),(9999,1000)):
            image,stats=renderer.frame(pixels,index,elapsed)
            raw,faststats=renderer.rgb565(pixels,index,elapsed)
            self.assertEqual(raw,encode_frame(np.asarray(image)))
            self.assertEqual(stats,faststats)

    def test_eye_region_uses_current_pixels_and_blanks_immediately_on_loss(self):
        pixels=np.full((480,640),31,dtype=np.uint8)
        pixels[100:260,40:200]=170
        renderer=PreviewRenderer()
        for region,expected in (({"state":"located","crop":(40,100,200,260)},170),
                                ({"state":"searching","crop":None},0)):
            renderer.set_region(region)
            image,stats=renderer.frame(pixels,1,1)
            raw,faststats=renderer.rgb565(pixels,1,1)
            self.assertEqual(image.getpixel((500,180)),(expected,)*3)
            self.assertEqual(raw,encode_frame(np.asarray(image)))
            self.assertEqual(stats,faststats)
        for bad in ({"state":"confirming","crop":(0,0,128,128)},
                    {"state":"located","crop":(-1,0,127,128)},
                    {"state":"located","crop":None}):
            with self.assertRaises(ValueError):renderer.set_region(bad)
