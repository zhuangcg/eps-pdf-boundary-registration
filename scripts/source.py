"""Inspect one EPS/PDF sheet once: vector paths, fill-colour census, and preview.

This is a pre-extraction stage. It does not guess which colours are administrative
polygons; an agent reviews work/census.json and the preview before setting a keep rule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import fitz
import yaml

from pathio import closed_rings, signed_area, subpaths


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_pdf(source: Path, work: Path) -> Path:
    if source.suffix.lower() == ".pdf":
        return source
    if source.suffix.lower() != ".eps":
        raise ValueError("source inspection currently supports EPS or PDF")
    gs = shutil.which("gswin64c") or shutil.which("gs")
    if not gs:
        raise RuntimeError("Ghostscript is required to preserve EPS vectors")
    stamp = work / "conversion.json"
    key = {"input_sha256": sha256(source), "converter": str(gs),
           "flags": ["-dSAFER", "-dEPSCrop", "-sDEVICE=pdfwrite"]}
    target = work / ("source_" + hashlib.sha256(
        json.dumps(key, sort_keys=True).encode()).hexdigest()[:12] + ".pdf")
    if target.is_file() and stamp.is_file() and json.loads(
        stamp.read_text(encoding="utf-8")
    ) == key:
        return target
    cmd = [gs, "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dEPSCrop",
           "-sDEVICE=pdfwrite", f"-sOutputFile={target}", str(source)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f"Ghostscript failed ({result.returncode}): "
                           f"{result.stderr.decode(errors='replace')[-2000:]}")
    with fitz.open(target) as doc:
        if len(doc) != 1:
            raise ValueError(f"expected one map page, got {len(doc)}")
        if not doc[0].get_drawings():
            raise ValueError("converted PDF has no vector drawings")
    stamp.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def inspect(source: Path, work: Path, tol_pt: float = 0.05) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    pdf = as_pdf(source, work)
    stamp = {"source_sha256": sha256(source), "pdf_sha256": sha256(pdf),
             "flatten_tolerance_pt": tol_pt, "census_version": 2}
    output = work / "census.json"
    preview = work / "preview.png"
    if output.is_file() and preview.is_file():
        cached = json.loads(output.read_text(encoding="utf-8"))
        if cached.get("stamp") == stamp:
            return cached

    with fitz.open(pdf) as doc:
        if len(doc) != 1:
            raise ValueError(f"expected one map page, got {len(doc)}")
        page = doc[0]
        drawings = page.get_drawings()
        if not drawings:
            raise ValueError("no vector drawings; use raster georeferencing instead")
        colours: dict[tuple[int, int, int], dict] = {}
        strokes: dict[tuple, dict] = {}
        filled = 0
        for drawing in drawings:
            fill = drawing.get("fill")
            if fill is not None:
                filled += 1
                colour = tuple(round(255 * x) for x in fill[:3])
                record = colours.setdefault(colour, {"rgb": list(colour), "paths": 0,
                                                      "sum_abs_ring_area_pt2": 0.0})
                record["paths"] += 1
                record["sum_abs_ring_area_pt2"] += sum(
                    abs(signed_area(ring)) for ring in closed_rings(drawing["items"], tol_pt))
            stroke = drawing.get("color")
            if stroke is not None:
                rgb = tuple(round(255 * x) for x in stroke[:3])
                width = round(float(drawing.get("width") or 0), 3)
                dashes = str(drawing.get("dashes") or "")
                key = (rgb, width, dashes)
                record = strokes.setdefault(key, {"rgb": list(rgb), "width_pt": width,
                                                  "dashes": dashes, "paths": 0,
                                                  "closed_subpaths": 0, "open_subpaths": 0})
                record["paths"] += 1
                for points in subpaths(drawing["items"], tol_pt):
                    if len(points) > 2 and abs(points[0][0] - points[-1][0]) + abs(points[0][1] - points[-1][1]) < 1e-5:
                        record["closed_subpaths"] += 1
                    else:
                        record["open_subpaths"] += 1
        page.get_pixmap(matrix=fitz.Matrix(96 / 72, 96 / 72)).save(preview)
        result = {
            "stamp": stamp,
            "page_pt": [float(page.rect.width), float(page.rect.height)],
            "vector_drawings": len(drawings),
            "filled_drawings": filled,
            "stroked_drawings": sum(row["paths"] for row in strokes.values()),
            "native_words": len(page.get_text("words")),
            "embedded_images": len(page.get_images(full=True)),
            "colours": sorted(colours.values(),
                              key=lambda row: -row["sum_abs_ring_area_pt2"]),
            "strokes": sorted(strokes.values(), key=lambda row: -row["paths"]),
            "preview": str(preview),
            "pdf": str(pdf),
        }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    source, work = Path(config["source_map"]), Path(config["work_dir"])
    tol = config.get("extraction", {}).get("bezier_tolerance_pt", 0.05)
    result = inspect(source, work, tol)
    print(f"vector drawings={result['vector_drawings']} filled={result['filled_drawings']} "
          f"stroked={result['stroked_drawings']} "
          f"native words={result['native_words']}")
    for row in result["colours"][:18]:
        print(f"  {row['rgb']} paths={row['paths']} "
          f"area={row['sum_abs_ring_area_pt2']:.1f} pt²")
    for row in result["strokes"][:8]:
        print(f"  stroke {row['rgb']} width={row['width_pt']} paths={row['paths']} "
              f"closed={row['closed_subpaths']}")
    print(f"census: {work / 'census.json'}")
    print(f"preview: {work / 'preview.png'}")
    print("##VERDICT stage=inspect status=pass; review fill and stroke candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
