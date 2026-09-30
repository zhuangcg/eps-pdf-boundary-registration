"""Run EPS/PDF administrative-vector extraction, naming, registration and delivery."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml
from PIL import Image
from shapely.geometry import Point
from shapely.ops import unary_union

from check_output_manifest import check
from deliver import ReviewConformance, _figure, filenames, write
from extract import ReviewExtraction, extract
from names import ReviewNames, attach, scan
from register import ReviewRegistration, apply_geom, load_reference, register
from scope import NoCommonBoundary, ReviewScope, matching_region, resolve
from source import inspect, sha256


def _reference_hash(path):
    if path.suffix.lower() != ".shp":
        return sha256(path)
    sidecars = [path.with_suffix(ext) for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg")]
    manifest = [(file.suffix.lower(), sha256(file)) for file in sidecars if file.is_file()]
    return hashlib.sha256(json.dumps(manifest).encode()).hexdigest()


def _fingerprint(config):
    data = {k: v for k, v in config.items() if k not in {"work_dir", "output_dir"}}
    data["source_sha256"] = sha256(Path(config["source_map"]))
    data["reference_sha256"] = _reference_hash(Path(config["reference_boundary"]))
    data["pipeline_code_sha256"] = hashlib.sha256(b"".join(
        path.read_bytes() for path in sorted(Path(__file__).parent.glob("*.py")))).hexdigest()
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _record_review(config, status, reason, details=None):
    work = Path(config["work_dir"])
    work.mkdir(parents=True, exist_ok=True)
    path = work / "review.json"
    path.write_text(json.dumps({"status": status, "reason": reason, **(details or {})},
                               ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"##VERDICT stage=run status={status} reason={reason}")
    print(f"review: {path}")
    return 2


def _scope_preview(census, reference, work):
    plt.rcParams.update({"font.family": "Helvetica", "font.size": 12,
                         "lines.linewidth": 1.5})
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), dpi=120)
    with Image.open(census["preview"]) as preview:
        axes[0].imshow(preview)
    gpd.GeoSeries([reference["source_geometry"]], crs=reference["output_crs"]).boundary.plot(
        ax=axes[1], color="#343A40", linewidth=1.5)
    for ax, title in zip(axes, ("Source sheet (page coordinates)", "Reference (geographic CRS)")):
        ax.set_title(title)
        ax.set_aspect("equal")
        ax.axis("off")
    path = work / "scope_comparison.png"
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return str(path)


def run(config):
    if config.get("workflow", {}).get("mode") not in {None, "single"}:
        raise ValueError("single-map run does not accept this workflow.mode")
    if config.get("names", {}).get("mode") is None:
        config.setdefault("names", {})["mode"] = (
            "required" if config["names"].get("require_map_annotation") is True else "auto")
    if config["names"]["mode"] not in {"auto", "required"}:
        raise ValueError("names.mode must be auto or required")
    if config.get("delivery", {}).get("mode", "R") not in {"R", "C"}:
        raise ValueError("delivery.mode must be R or C")
    out = Path(config["output_dir"])
    work = Path(config["work_dir"])
    if out.resolve() == work.resolve() or out.resolve() in work.resolve().parents:
        raise ValueError("work_dir must be outside output_dir")
    try:
        resolve(config)
    except NoCommonBoundary as exc:
        return _record_review(config, "NO_COMMON_BOUNDARY", str(exc))
    except ReviewScope as exc:
        if "conflicts" in str(exc):
            return _record_review(config, "REVIEW_SCOPE", str(exc))
        # Incomplete evidence can be resolved after extracting map-body labels.
    fingerprint = _fingerprint(config)
    if out.is_dir() and any(out.iterdir()):
        files, c_files = filenames(config)
        expected = set(files.values())
        if config.get("delivery", {}).get("mode", "R") == "C":
            expected.update(c_files.values())
        qc_path = out / files["qc_json"]
        if qc_path.is_file():
            prior = json.loads(qc_path.read_text(encoding="utf-8"))
            findings = check(out, expected, set())
            if prior.get("fingerprint") == fingerprint and all(ok for _, ok, _ in findings):
                print("##VERDICT stage=run status=cached_delivery")
                return 0
        raise FileExistsError(f"delivery directory already contains another or incomplete run: {out}")
    census = inspect(Path(config["source_map"]), work,
                     config.get("extraction", {}).get("bezier_tolerance_pt", 0.05),
                     config.get("source_page", 1))
    try:
        reference = load_reference(config)
    except ReviewScope as exc:
        return _record_review(config, "REVIEW_SCOPE", str(exc),
                              {"source_preview": census["preview"]})
    scope_details = {"source_preview": census["preview"],
                     "reference": reference["evidence"],
                     "scope_comparison": _scope_preview(census, reference, work)}
    try:
        extracted = extract(config)
    except ReviewExtraction as exc:
        return _record_review(config, "REVIEW_EXTRACTION", str(exc), scope_details)
    page = gpd.read_file(extracted["page_units_gpkg"], layer="page_units")
    labels = scan(census, config, page)
    in_map_words = [row["raw_text"] for row in labels["labels"] if any(
        geom.covers(Point(row["page_x_pt"], row["page_y_pt"])) for geom in page.geometry)]
    try:
        decision = resolve(config, ocr_words=in_map_words)
    except ReviewScope as exc:
        return _record_review(config, "REVIEW_SCOPE", str(exc), scope_details)
    except NoCommonBoundary as exc:
        return _record_review(config, "NO_COMMON_BOUNDARY", str(exc))
    if decision["source_scope"] == "same_extent":
        region = matching_region(config, reference["evidence"],
                                 [row["raw_text"] for row in labels["labels"]])
        decision["region_match"] = region
        if region["status"] == "review":
            return _record_review(config, "REVIEW_SCOPE",
                                  "no matching target-region label in source and reference; confirm their extent",
                                  scope_details)
    if config.get("delivery", {}).get("mode", "R") == "C" and decision["source_scope"] != "same_extent":
        raise ValueError("Mode C requires same_extent; use Mode R for a shared boundary arc")
    decision["reference"] = reference["evidence"]
    try:
        named, map_labels, name_qc = attach(page, labels, config, census,
                                           decision["admin_level"])
    except ReviewNames as exc:
        return _record_review(config, "REVIEW_NAMES", str(exc),
                              {**scope_details,
                               "name_review": str(work / "review_names.json")})
    try:
        registration = register(named, reference, decision["source_scope"], config)
    except ReviewRegistration as exc:
        return _record_review(config, "REVIEW_REGISTRATION", str(exc), scope_details)
    if registration["gate"]["status"] != "pass":
        fitted = named.copy()
        fitted["geometry"] = [apply_geom(geom, registration["matrix"])
                              for geom in named.geometry]
        fitted = fitted.set_crs(reference["fit_crs"])
        overlay = work / "review_registration.png"
        _figure(fitted, unary_union(fitted.geometry), reference["geometry"],
                registration, overlay)
        return _record_review(config, "REVIEW_REGISTRATION",
                              "; ".join(registration["gate"]["reasons"]),
                              {**scope_details, "candidate_overlay": str(overlay),
                               "metrics": registration["metrics"],
                               "gate": registration["gate"]})
    files, c_files = filenames(config)
    expected = set(files.values())
    if config.get("delivery", {}).get("mode", "R") == "C":
        expected.update(c_files.values())
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="delivery_", dir=out.parent) as stage:
        staged_config = {**config, "output_dir": stage}
        try:
            qc = write(staged_config, named, map_labels, name_qc, extracted, decision,
                       registration, reference, sha256(Path(config["source_map"])),
                       _reference_hash(Path(config["reference_boundary"])), fingerprint)
        except ReviewConformance as exc:
            fitted = named.copy()
            fitted["geometry"] = [apply_geom(geom, registration["matrix"])
                                  for geom in named.geometry]
            fitted = fitted.set_crs(reference["fit_crs"])
            overlay = work / "review_conformance.png"
            _figure(fitted, unary_union(fitted.geometry), reference["geometry"],
                    registration, overlay)
            return _record_review(config, "REVIEW_CONFORMANCE", str(exc),
                                  {**scope_details, "candidate_overlay": str(overlay)})
        findings = check(Path(stage), expected, set())
        bad = [(name, msg) for name, ok, msg in findings if not ok]
        if bad:
            raise ValueError(f"delivery manifest failed: {bad}")
        if out.is_dir():
            out.rmdir()  # only an empty directory reaches this point
        Path(stage).replace(out)
    print(f"method={extracted['method']} units={len(named)} names={name_qc['named_units']}/"
          f"{name_qc['total_units']} scope={decision['source_scope']}")
    print(f"median={registration['metrics']['median_m']:.2f} m "
          f"P90={registration['metrics']['p90_m']:.2f} m")
    print(f"delivery: {out}")
    print(f"##VERDICT stage=run status={qc['status']}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--intent", help="user's explicit level and source/reference relationship")
    args = ap.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if config.get("workflow", {}).get("mode") == "batch_hierarchical":
        if args.intent:
            ap.error("--intent is for one map; set defaults or case options in a batch manifest")
        from batch import run_batch
        return run_batch(config, args.config, run)
    if args.intent:
        config["user_intent"] = args.intent
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
