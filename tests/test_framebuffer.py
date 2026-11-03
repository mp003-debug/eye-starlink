import unittest
import numpy as np
from eye_tracker.framebuffer import CAPTURE,DISPLAY,FrameLayout,pack_rgb565,unpack_rgb565,encode_frame

class FramebufferTests(unittest.TestCase):
    def test_primary_colors_byte_order(self):
        rgb=np.array([[[255,0,0],[0,255,0],[0,0,255],[255,255,255],[0,0,0]]],dtype=np.uint8)
        words=pack_rgb565(rgb)
        self.assertEqual(words.tolist(),[[0xF800,0x07E0,0x001F,0xFFFF,0]])
        self.assertEqual(words.tobytes(),bytes.fromhex('00f8e0071f00ffff0000'))
        np.testing.assert_array_equal(unpack_rgb565(words),rgb)

    def test_quantization_bound_and_not_bgr(self):
        rng=np.random.default_rng(42)
        rgb=rng.integers(0,256,(80,640,3),dtype=np.uint8)
        restored=unpack_rgb565(pack_rgb565(rgb))
        errors=np.abs(restored.astype(np.int16)-rgb.astype(np.int16))
        self.assertTrue(np.all(errors.max(axis=(0,1))<=np.array([7,3,7])))

    def test_all_words_round_trip(self):
        words=np.arange(65536,dtype=np.uint16).reshape(256,256)
        np.testing.assert_array_equal(pack_rgb565(unpack_rgb565(words)),words)

    def test_separate_dma_row_sizes(self):
        self.assertEqual((CAPTURE.hsize_bytes,CAPTURE.size_bytes),(640,307200))
        self.assertEqual((DISPLAY.hsize_bytes,DISPLAY.size_bytes),(1280,614400))
        with self.assertRaises(ValueError):encode_frame(np.zeros((480,640,3),dtype=np.uint8),CAPTURE)

    def test_padding_and_reject_wrong_frame(self):
        layout=FrameLayout(3,2,'RGB565_LE',8)
        data=encode_frame(np.full((2,3,3),255,dtype=np.uint8),layout)
        self.assertEqual(data,bytes.fromhex('ffffffffffff0000')*2)
        with self.assertRaises(ValueError):FrameLayout(640,480,'RGB565_LE',640)
        with self.assertRaises(ValueError):FrameLayout(3,2,'RGB565_LE',6)
        with self.assertRaises(ValueError):encode_frame(np.zeros((2,3,3),dtype=np.uint8))
        with self.assertRaises(ValueError):pack_rgb565(np.zeros((2,3,3),dtype=np.float32))
