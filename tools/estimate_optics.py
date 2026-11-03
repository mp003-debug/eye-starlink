"""Paraxial lens sampling estimates. No camera, illumination or gaze validation."""
import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def positive_finite(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("expected a positive finite number")
    return result


def estimate(focal_mm, distance_mm, target_mm, pitch_mm, capture, sensor):
    if distance_mm <= focal_mm:
        raise ValueError("object distance must exceed focal length")
    magnification = focal_mm / (distance_mm - focal_mm)
    return {
        "focal_length_mm": focal_mm,
        "object_distance_mm": distance_mm,
        "magnification": magnification,
        "capture_field_width_mm": capture[0] * pitch_mm / magnification,
        "capture_field_height_mm": capture[1] * pitch_mm / magnification,
        "sensor_full_field_width_mm": sensor[0] * pitch_mm / magnification,
        "pixels_per_object_mm": magnification / pitch_mm,
        "target_diameters": [
            {"diameter_mm": diameter, "diameter_pixels": diameter * magnification / pitch_mm}
            for diameter in target_mm
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focal-lengths-mm", type=positive_finite, nargs="+", default=[2.8, 8.0, 12.0])
    parser.add_argument("--distances-mm", type=positive_finite, nargs="+", default=[300.0, 350.0, 400.0, 450.0])
    parser.add_argument("--target-diameters-mm", type=positive_finite, nargs="+", default=[3.0, 4.0, 5.0])
    parser.add_argument("--output", type=Path, default=Path("build/optics/estimate.json"))
    args = parser.parse_args()
    config = json.loads((ROOT / "config/hardware.json").read_text(encoding="utf-8"))
    pitch_mm = positive_finite(config["sensor_pixel_pitch_um"]) / 1000.0
    capture = config["capture_image"]
    sensor = config["sensor_image"]
    for shape in (capture, sensor):
        if len(shape) != 2 or any(type(v) is not int or v <= 0 for v in shape):
            parser.error("sensor and capture geometry must contain two positive integers")
    if any(c > s for c, s in zip(capture, sensor)):
        parser.error("capture cannot exceed the sensor in this crop-only model")
    output = (ROOT / args.output).resolve()
    try:
        output.relative_to(ROOT)
    except ValueError:
        parser.error("output must remain within the project root")
    try:
        rows = [
            estimate(focal, distance, args.target_diameters_mm, pitch_mm, capture, sensor)
            for focal in args.focal_lengths_mm for distance in args.distances_mm
        ]
    except ValueError as exc:
        parser.error(str(exc))
    report = {
        "model": "paraxial_thin_lens",
        "measured": False,
        "board_tested": False,
        "gaze_accuracy_validated": False,
        "pixel_pitch_um": config["sensor_pixel_pitch_um"],
        "capture_pixels": capture,
        "sensor_pixels": sensor,
        "assumptions": [
            "m = f / (u - f); object distance u approximates the distance to the front principal plane",
            "1:1 sensor sampling, central crop, no binning or digital resampling",
            "example target diameters are not measured user pupil diameters",
            "no lens distortion, principal-plane offset, blur, aperture or corneal-refraction model",
            "field of view is not a validated head-motion range",
        ],
        "rows": rows,
        "sources": [
            "https://www.onsemi.com/download/data-sheet/pdf/mt9v034-d.pdf",
            "https://www.edmundoptics.com/knowledge-center/application-notes/imaging/understanding-focal-length-and-field-of-view/",
        ],
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized, encoding="utf-8")
    print("Calculated only; no measured eye data. Saved: " + str(output))
    for row in rows:
        print("f={:.1f} mm, u={:.0f} mm: field={:.1f} x {:.1f} mm, {:.3f} pixels/mm".format(
            row["focal_length_mm"], row["object_distance_mm"],
            row["capture_field_width_mm"], row["capture_field_height_mm"], row["pixels_per_object_mm"]))


if __name__ == "__main__":
    main()
