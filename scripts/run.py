"""Run EPS/PDF administrative-vector extraction, naming, registration and delivery."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fitz
import geopandas as gpd
import yaml
from shapely.geometry import Point

from check_output_manifest import check
from deliver import DEFAULT_C, DEFAULT_FILES, filenames, write
from extract import ReviewExtraction, extract
from names import attach, scan
from register import ReviewRegistration, load_reference, register
from scope import NoCommonBoundary, ReviewScope, resolve
from source import inspect, sha256


def _fingerprint(config):
    data = {k: v for k, v in config.items() if k not in {"work_dir", "output_dir"}}
    data["source_sha256"] = sha256(Path(config["source_map"]))
    data["reference_sha256"] = sha256(Path(config["reference_boundary"]))
    data["pipeline_code_sha256"] = hashlib.sha256(b"".join(
        path.read_bytes() for path in sorted(Path(__file__).parent.glob("*.py")))).hexdigest()
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _record_review(config, status, reason):
    work = Path(config["work_dir"])
    work.mkdir(parents=True, exist_ok=True)
    path = work / "review.json"
    path.write_text(json.dumps({"status": status, "reason": reason}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"##VERDICT stage=run status={status} reason={reason}")
    print(f"review: {path}")
    return 2


def run(config):
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
                     config.get("extraction", {}).get("bezier_tolerance_pt", 0.05))
    try:
        extracted = extract(config)
    except ReviewExtraction as exc:
        return _record_review(config, "REVIEW_EXTRACTION", str(exc))
    page = gpd.read_file(extracted["page_units_gpkg"], layer="page_units")
    labels = scan(census, config, page)
    in_map_words = [row["raw_text"] for row in labels["labels"] if any(
        geom.covers(Point(row["page_x_pt"], row["page_y_pt"])) for geom in page.geometry)]
    try:
        decision = resolve(config, ocr_words=in_map_words)
    except ReviewScope as exc:
        return _record_review(config, "REVIEW_SCOPE", str(exc))
    except NoCommonBoundary as exc:
        return _record_review(config, "NO_COMMON_BOUNDARY", str(exc))
    if config.get("delivery", {}).get("mode", "R") == "C" and decision["source_scope"] != "same_extent":
        raise ValueError("Mode C requires same_extent; use Mode R for a shared boundary arc")
    named, map_labels, name_qc = attach(page, labels, config, census, decision["admin_level"])
    reference = load_reference(config)
    try:
        registration = register(named, reference, decision["source_scope"], config)
    except ReviewRegistration as exc:
        return _record_review(config, "REVIEW_REGISTRATION", str(exc))
    qc = write(config, named, map_labels, name_qc, extracted, decision, registration,
               reference, sha256(Path(config["source_map"])),
               sha256(Path(config["reference_boundary"])), fingerprint)
    files, c_files = filenames(config)
    expected = set(files.values())
    if config.get("delivery", {}).get("mode", "R") == "C":
        expected.update(c_files.values())
    findings = check(out, expected, set())
    bad = [(name, msg) for name, ok, msg in findings if not ok]
    if bad:
        raise ValueError(f"delivery manifest failed: {bad}")
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
    if args.intent:
        config["user_intent"] = args.intent
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
