"""Build the installed, unmodified SAM codec with mypyc. No inference/network calls.

Only build tooling is required (mypy, setuptools and a C compiler). The resulting
extensions need neither mypy nor setuptools at runtime. The installed parser's
original source and license remain in place.
"""

import argparse
import importlib.metadata
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SMOKE = r"""
import importlib.abc, importlib.util, sys
from pathlib import Path
class NoBuildDependencies(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mypy', 'mypyc', 'setuptools'}:
            raise ImportError('build dependency requested at runtime')
sys.meta_path.insert(0, NoBuildDependencies())
from meta_sam_parser import _mask_codec as compiled
from meta_sam_parser._types import SegmentationMask
assert Path(compiled.__file__).suffix in {'.so', '.pyd'}
spec = importlib.util.spec_from_file_location('meta_sam_parser.reference_codec', Path(compiled.__file__).with_name('_mask_codec.py'))
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
for width, height in [(1,1), (7,9), (64,64)]:
    for variant in range(4):
        raster = bytes((x+y+variant) % 2 if variant < 2 else int(x > width//3 and y > height//3)
                       for y in range(height) for x in range(width))
        wire = reference._encode_raster(raster, width, height)
        mask = SegmentationMask('one_bit', wire, width, height)
        assert reference.decode_mask_to_raster(mask) == compiled.decode_mask_to_raster(mask) == raster
        for invalid in [wire[:-1], wire+'!', '!', '~bad']:
            bad = SegmentationMask('one_bit', invalid, width, height)
            outcomes=[]
            for decoder in [reference.decode_mask_to_raster, compiled.decode_mask_to_raster]:
                try: outcomes.append(('ok', decoder(bad)))
                except Exception as exc: outcomes.append(('error', type(exc).__name__))
            assert outcomes[0] == outcomes[1], outcomes
print('Compiled SAM codec matches reference; no build dependency imported at runtime.')
"""


def build(install: bool) -> None:
    if importlib.metadata.version("meta-sam-parser") != "0.1.0":
        raise RuntimeError("SAM codec compilation is verified for meta-sam-parser 0.1.0 only")
    spec = importlib.util.find_spec("meta_sam_parser")
    if spec is None or spec.origin is None:
        raise RuntimeError("Install the frozen project dependencies first")
    package = Path(spec.origin).parent
    if shutil.which("cc") is None:
        raise RuntimeError("A C compiler is required for the build stage")
    with tempfile.TemporaryDirectory(prefix="apprentice-codec-build-") as name:
        workspace = Path(name)
        shutil.copytree(
            package,
            workspace / "meta_sam_parser",
            ignore=shutil.ignore_patterns("*.so", "*.pyd", "__pycache__"),
        )
        (workspace / "setup.py").write_text(
            "from setuptools import setup\nfrom mypyc.build import mypycify\n"
            "setup(name='apprentice-sam-codec-build', ext_modules=mypycify(['meta_sam_parser/_mask_codec.py']))\n"
        )
        subprocess.run(
            [sys.executable, "setup.py", "build_ext", "--inplace"], cwd=workspace, check=True
        )
        subprocess.run([sys.executable, "-c", SMOKE], cwd=workspace, check=True)
        artifacts = list((workspace / "meta_sam_parser").glob("*.so")) + list(
            (workspace / "meta_sam_parser").glob("*.pyd")
        )
        if not artifacts:
            raise RuntimeError("SAM codec build produced no extensions")
        if install:
            for artifact in artifacts:
                shutil.copy2(artifact, package / artifact.name)
        print(json.dumps({"compiled": True, "installed": install, "extensions": len(artifacts)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install compiled extensions into this Python environment",
    )
    args = parser.parse_args()
    build(args.install)


if __name__ == "__main__":
    main()
