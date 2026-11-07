"""Public build status only; never expose local package paths."""

import importlib.util
from pathlib import Path


def codec_compiled() -> bool:
    spec = importlib.util.find_spec("meta_sam_parser._mask_codec")
    return bool(spec and spec.origin and Path(spec.origin).suffix in {".so", ".pyd"})
