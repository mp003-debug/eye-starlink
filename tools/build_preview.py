"""Build Chinese setup-view labels as pixels; do not redistribute system fonts."""
import argparse
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from eye_tracker.preview import PreviewRenderer, TEMPLATE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=Path("assets/fonts/noto_sans_cjk_sc.otf"))
    parser.add_argument("--eye-region",action="store_true")
    args = parser.parse_args()
    fonts = {n: ImageFont.truetype(str(args.font), n) for n in (12, 13, 14, 26)}
    image = Image.new("RGB", (640, 480), "#eef5f2")
    draw = ImageDraw.Draw(image)
    draw.text((20, 13), "眼语 / 眼区定位" if args.eye_region else "眼语 / 相机调试", font=fonts[26], fill="#164e4b")
    draw.text((20, 49), "自然坐姿 · 寻找眼区 · 尚未校准视线" if args.eye_region else "真实采集 640×480 · GRAY8 · 画面用于调焦和曝光检查", font=fonts[12], fill="#59716d")
    draw.rounded_rectangle((460, 18, 620, 43), radius=12, fill="#dbeae2")
    draw.text((474, 22), "调试模式 · 尚未眼控", font=fonts[12], fill="#456957")
    draw.text((20, 80), "相机全图 / 青框为当前眼区放大范围" if args.eye_region else "相机全图 / 黄色框为右侧放大范围", font=fonts[12], fill="#365a56")
    draw.text((424, 80), "眼区放大 / 丢失时留空" if args.eye_region else "中心放大 / 不是眼部识别", font=fonts[12], fill="#365a56")
    draw.rectangle((20, 104, 403, 391), fill="#172c30")
    draw.rectangle((424, 104, 615, 295), fill="#172c30")
    draw.rounded_rectangle((420, 304, 620, 444), radius=8, fill="white")
    for y, label in ((310, "帧数"), (338, "速率"), (366, "均值")):
        draw.text((430, y + 2), label, font=fonts[12], fill="#54746e")
    draw.text((20, 398), "灰度分布：左暗 → 右亮", font=fonts[12], fill="#54746e")
    draw.text((430, 426), "高亮像素占比（≥253）", font=fonts[12], fill="#54746e")
    draw.text((20, 454), "请自然坐好；当前只找眼区，不输出视线、不触发按钮或语音。" if args.eye_region else "调焦请使用文字或刻度；当前不输出视线、不触发按钮或语音。", font=fonts[13], fill="#486761")
    TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    destination = TEMPLATE.with_name("eye_region_template.png") if args.eye_region else TEMPLATE
    image.save(destination)
    # An explicitly synthetic checkerboard proves panel alignment offline.
    yy, xx = np.indices((480, 640))
    pixels = np.where((xx // 24 + yy // 24) % 2, 200, 40).astype(np.uint8)
    preview, _ = PreviewRenderer(destination).frame(pixels, 123, 10)
    ImageDraw.Draw(preview).text((24, 112), "OFFLINE SYNTHETIC PATTERN", fill="red")
    out = ROOT / ("build/previews/eye_region_setup.png" if args.eye_region else "build/previews/camera_setup.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    preview.save(out)
    print(out)


if __name__ == "__main__":
    main()
