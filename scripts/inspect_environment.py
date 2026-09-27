"""Check dependencies and, when supplied, fail early on an impossible run config."""
import argparse
from importlib.util import find_spec
from pathlib import Path
import shutil
import sys

REQUIRED_PACKAGES = [
    "numpy",
    "scipy",
    "geopandas",
    "shapely",
    "pyproj",
    "matplotlib",
    "PIL",                # Pillow: ambiguous-candidate preview
    "fitz",               # PyMuPDF: converted EPS vectors and page text
    "yaml",               # run configuration and manifest
]
OPTIONAL_PACKAGES = ["rapidocr_onnxruntime"]

EXECUTABLES = ["gswin64c", "gs"]

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--config", type=Path, help="YAML run configuration to validate")
a = ap.parse_args()

print(f"Python: {sys.version}")
print("\nRequired Python packages:")
for name in REQUIRED_PACKAGES:
    print(f"  {name:15s} {'OK' if find_spec(name) else 'MISSING'}")

print("\nConditional packages (OCR for outlined map text):")
for name in OPTIONAL_PACKAGES:
    print(f"  {name:20s} {'OK' if find_spec(name) else 'MISSING'}")

print("\nExecutables:")
for name in EXECUTABLES:
    path = shutil.which(name)
    print(f"  {name:15s} {path or 'NOT FOUND'}")

if a.config:
    import yaml

    config = yaml.safe_load(a.config.read_text(encoding="utf-8"))
    errors = []
    scope = config.get("source_scope")
    mode = config.get("delivery", {}).get("mode")
    if scope not in {None, "auto", "same_extent", "partial_parent", "shared_boundary", "no_common_boundary"}:
        errors.append("source_scope must be auto, same_extent, shared_boundary, or no_common_boundary")
    if mode not in {"R", "C"}:
        errors.append("delivery.mode must be R or C")
    if scope in {"partial_parent", "shared_boundary", "no_common_boundary"} and mode == "C":
        errors.append("Mode C needs a same-extent reference; a parent city is insufficient")
    if config.get("names", {}).get("mode", "auto") not in {"auto", "required"}:
        errors.append("names.mode must be auto or required")
    if config.get("extraction", {}).get("method", "auto") not in {"auto", "fill", "line"}:
        errors.append("extraction.method must be auto, fill, or line")
    out = Path(config.get("output_dir", ".")).resolve()
    work = Path(config.get("work_dir", ".")).resolve()
    if work == out or out in work.parents:
        errors.append("work_dir must be outside output_dir")
    for field in ("source_map", "reference_boundary"):
        if not Path(config.get(field, "")).is_file():
            errors.append(f"{field} does not exist")
    if str(config.get("source_map", "")).lower().endswith(".eps") and not (
        shutil.which("gswin64c") or shutil.which("gs")
    ):
        errors.append("Ghostscript is required for EPS vector conversion")
    print("\nConfiguration:", "PASS" if not errors else "FAIL")
    for error in errors:
        print("  " + error)
    if errors:
        sys.exit(1)

if any(find_spec(name) is None for name in REQUIRED_PACKAGES):
    sys.exit(1)
