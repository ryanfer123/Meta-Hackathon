"""Compare compiled and reference SAM decoding on generated masks; no model calls."""

import argparse
import hashlib
import importlib.util
import json
import statistics
import time
from pathlib import Path

from meta_sam_parser import _mask_codec as compiled
from meta_sam_parser._types import SegmentationMask


def benchmark(repeats: int) -> list[dict[str, object]]:
    if Path(compiled.__file__).suffix not in {".so", ".pyd"}:
        raise RuntimeError("Run scripts/build_sam_codec.py --install first")
    spec = importlib.util.spec_from_file_location(
        "meta_sam_parser.benchmark_reference",
        Path(compiled.__file__).with_name("_mask_codec.py"),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("The original licensed codec source must remain installed")
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    rows = []
    for width, height in [(64, 64), (640, 360)]:
        raster = bytes(
            int(width // 4 <= x < 3 * width // 4 and height // 4 <= y < 3 * height // 4)
            for y in range(height)
            for x in range(width)
        )
        mask = SegmentationMask(
            "one_bit", reference._encode_raster(raster, width, height), width, height
        )
        timings = {}
        for name, decoder in [("reference", reference), ("compiled", compiled)]:
            samples = []
            for _ in range(repeats):
                started = time.perf_counter()
                decoded = decoder.decode_mask_to_raster(mask)
                samples.append(time.perf_counter() - started)
                if bytes(decoded) != raster:
                    raise RuntimeError("Decoded pixels differ from the generated source")
            timings[name] = statistics.median(samples)
        rows.append(
            {
                "source": "generated rectangular mask",
                "width": width,
                "height": height,
                "repeats": repeats,
                "reference_median_s": timings["reference"],
                "compiled_median_s": timings["compiled"],
                "speedup": timings["reference"] / timings["compiled"],
                "same_pixels": True,
                "raster_sha256": hashlib.sha256(raster).hexdigest(),
                "scope": "Local codec only; not hosted or end-to-end latency",
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 20:
        parser.error("--repeats must be between 1 and 20")
    output = json.dumps(benchmark(args.repeats), indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
