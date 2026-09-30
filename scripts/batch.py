"""Opt-in hierarchical batch delivery using the existing single-map Mode C run."""
from __future__ import annotations

import copy
import csv
import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.ops import unary_union

from deliver import AREA_TOLERANCE_M2, SEAM_DRIFT_TOLERANCE_M, filenames
from register import choose_fit_crs


def _path(base, value):
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _load_manifest(manifest, base):
    if not isinstance(manifest, dict):
        raise ValueError("batch manifest must be a mapping")
    if manifest.get("workflow", {}).get("mode") != "batch_hierarchical":
        raise ValueError("workflow.mode must be batch_hierarchical")
    parent = manifest.get("parent_reference")
    if not isinstance(parent, dict) or not parent.get("path") or not parent.get("id_field"):
        raise ValueError("parent_reference needs path and id_field")
    if not manifest.get("output_dir") or not manifest.get("work_dir"):
        raise ValueError("batch needs output_dir and work_dir")
    field = parent["id_field"]
    path = _path(base, parent["path"])
    if not path.is_file():
        raise ValueError(f"parent_reference does not exist: {path}")
    if path.suffix.lower() == ".gpkg" and not parent.get("layer"):
        layers = [name for name, geometry_type in pyogrio.list_layers(path)
                  if geometry_type is not None]
        if len(layers) != 1:
            raise ValueError(f"parent_reference layers={layers}; set layer")
    raw = gpd.read_file(path, layer=parent.get("layer"))
    if raw.empty or raw.crs is None or field not in raw or raw[field].isna().any():
        raise ValueError("parent_reference needs nonempty features, known CRS and non-null id_field")
    if any(g is None or g.is_empty or not g.is_valid or g.geom_type not in
           {"Polygon", "MultiPolygon"} for g in raw.geometry):
        raise ValueError("parent_reference contains null, empty, invalid or non-polygon geometry")
    fit_crs = choose_fit_crs(raw, parent.get("fit_crs"))
    raw_fit = raw.to_crs(fit_crs)
    if not raw_fit.geometry.is_valid.all():
        raise ValueError("parent_reference becomes invalid after projection")
    references = {str(key): group.geometry.union_all()
                  for key, group in raw_fit.groupby(field, dropna=False)}
    values = {str(value): value for value in raw[field].drop_duplicates()}
    for a, key_a in enumerate(references):
        for key_b in list(references)[a + 1:]:
            if references[key_a].intersection(references[key_b]).area > AREA_TOLERANCE_M2:
                raise ValueError(f"parent_reference cities overlap: {key_a}, {key_b}")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) < 2:
        raise ValueError("batch_hierarchical requires at least two cases")
    if any(not isinstance(case, dict) or "parent_id" not in case or
           "source_map" not in case for case in cases):
        raise ValueError("each case needs parent_id and source_map")
    ids = [str(case["parent_id"]) for case in cases]
    if any(key.strip() != key or key in {"", ".", ".."} or
           re.search(r'[<>:"/\\|?*]', key) for key in ids):
        raise ValueError("parent_id must be a safe single path component")
    if len(ids) != len(set(ids)):
        raise ValueError("cases contain duplicate parent_id")
    missing = sorted(set(ids) - references.keys())
    if missing:
        raise ValueError(f"parent_reference has no features for: {missing}")
    for case in cases:
        source = _path(base, case["source_map"])
        if not source.is_file() or source.suffix.lower() not in {".eps", ".pdf"}:
            raise ValueError(f"case source_map must be an existing EPS or PDF: {source}")
    return parent, path, field, references, values, fit_crs, cases


def _case_config(manifest, case, base, parent, parent_path, field, value, fit_crs, out, work):
    config = copy.deepcopy(manifest.get("defaults") or {})
    options = case.get("options") or {}
    if not isinstance(config, dict) or not isinstance(options, dict):
        raise ValueError("defaults and case options must be mappings")
    for key, option_value in options.items():
        if isinstance(option_value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **option_value}
        else:
            config[key] = copy.deepcopy(option_value)
    protected = {"source_map", "reference_boundary", "reference_layer", "source_page",
                 "output_dir", "work_dir"}
    if protected & (manifest.get("defaults") or {}).keys() or protected & options.keys():
        raise ValueError("batch source, reference, page and output paths belong in cases/parent_reference")
    if "scope_confirmation" in (manifest.get("defaults") or {}):
        raise ValueError("scope_confirmation must be recorded per case from the user's answer")
    key = str(case["parent_id"])
    config.update(source_map=str(_path(base, case["source_map"])),
                  reference_boundary=str(parent_path), reference_layer=parent.get("layer"),
                  source_page=case.get("page", 1), output_dir=str(out / "cities" / key),
                  work_dir=str(work / key), admin_level="district", source_scope="same_extent")
    config["reference"] = {**(config.get("reference") or {}), "fit_crs": str(fit_crs),
                           "id_field": field, "filter": {"field": field,
                                                          "value": value}}
    config["delivery"] = {**(config.get("delivery") or {}), "mode": "C"}
    return config


def _global_qc(cities, fit_crs):
    district_rows, city_rows, adjacency = [], [], []
    references, delivered = {}, {}
    for key, config in cities.items():
        out = Path(config["output_dir"])
        files, conformed = filenames(config)
        units = gpd.read_file(out / conformed["conformed_gpkg"], layer="conformed_units")
        ref = gpd.read_file(out / files["registered_gpkg"], layer="reference_outline")
        if units.empty or len(ref) != 1:
            raise ValueError(f"{key}: missing conformed units or reference outline")
        units["parent_id"] = key
        ref["parent_id"] = key
        district_rows.append(units)
        city_rows.append(ref[["parent_id", "geometry"]])
        references[key] = ref.to_crs(fit_crs).geometry.iloc[0]
        delivered[key] = units.to_crs(fit_crs).geometry.union_all()
    districts = gpd.GeoDataFrame(pd.concat(district_rows, ignore_index=True),
                                 geometry="geometry", crs=district_rows[0].crs)
    city_units = gpd.GeoDataFrame(pd.concat(city_rows, ignore_index=True),
                                  geometry="geometry", crs=city_rows[0].crs)
    geoms = list(districts.to_crs(fit_crs).geometry)
    ref_union = unary_union(list(references.values()))
    unit_union = unary_union(geoms)
    city_coverage = {key: delivered[key].symmetric_difference(references[key]).area
                     for key in cities}
    checks = {
        "symmetric_difference_m2": unit_union.symmetric_difference(ref_union).area,
        "uncovered_m2": ref_union.difference(unit_union).area,
        "outside_m2": unit_union.difference(ref_union).area,
        "district_overlap_m2": sum(g.area for g in geoms) - unit_union.area,
        "invalid_geometries": sum(not g.is_valid for g in geoms),
        "city_coverage_m2": city_coverage,
    }
    keys = list(cities)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            shared = references[a].boundary.intersection(references[b].boundary)
            if shared.length <= 0:
                continue  # point-touching cities are not adjacent along a segment
            border_a = delivered[a].boundary.intersection(shared)
            border_b = delivered[b].boundary.intersection(shared)
            mismatch = (shared.symmetric_difference(border_a).length +
                        shared.symmetric_difference(border_b).length +
                        border_a.symmetric_difference(border_b).length)
            pair_ref = references[a].union(references[b])
            pair_out = delivered[a].union(delivered[b])
            row = {"city_a": a, "city_b": b, "shared_length_km": shared.length / 1000,
                   "mismatch_length_m": mismatch,
                   "gap_area_m2": pair_ref.difference(pair_out).area,
                   "overlap_area_m2": delivered[a].intersection(delivered[b]).area}
            row["status"] = "pass" if (mismatch < SEAM_DRIFT_TOLERANCE_M and
                row["gap_area_m2"] <= AREA_TOLERANCE_M2 and
                row["overlap_area_m2"] <= AREA_TOLERANCE_M2) else "fail"
            adjacency.append(row)
    passed = (checks["invalid_geometries"] == 0 and
              all(checks[k] <= AREA_TOLERANCE_M2 for k in
                  ("symmetric_difference_m2", "uncovered_m2", "outside_m2",
                   "district_overlap_m2")) and
              all(area <= AREA_TOLERANCE_M2 for area in city_coverage.values()) and
              all(row["status"] == "pass" for row in adjacency))
    return districts, city_units, checks, adjacency, passed


def run_batch(manifest, config_path, run_case):
    base = Path(config_path).resolve().parent
    parent, parent_path, field, references, values, fit_crs, cases = _load_manifest(manifest, base)
    out, work = _path(base, manifest["output_dir"]), _path(base, manifest["work_dir"])
    if out == work or out in work.parents or work in out.parents:
        raise ValueError("batch output_dir and work_dir must be separate")
    cities = {}
    for case in cases:
        key = str(case["parent_id"])
        config = _case_config(manifest, case, base, parent, parent_path, field,
                              values[key], fit_crs, out, work)
        cities[key] = config
        try:
            code = run_case(config)
        except Exception as exc:
            work.mkdir(parents=True, exist_ok=True)
            (work / "batch_review.json").write_text(json.dumps(
                {"status": "city_failed", "parent_id": key, "reason": str(exc)},
                ensure_ascii=False, indent=2), encoding="utf-8")
            raise
        if code != 0:
            work.mkdir(parents=True, exist_ok=True)
            (work / "batch_review.json").write_text(json.dumps(
                {"status": "city_review", "parent_id": key, "exit_code": code},
                ensure_ascii=False, indent=2), encoding="utf-8")
            return code
    districts, city_units, checks, adjacency, passed = _global_qc(cities, fit_crs)
    complete = set(cities) == set(references)
    out.mkdir(parents=True, exist_ok=True)
    report = {"status": "fail" if not passed else "pass" if complete else "preview",
              "complete": complete,
              "fit_crs": str(fit_crs), "checks": checks,
              "area_tolerance_m2": AREA_TOLERANCE_M2,
              "length_tolerance_m": SEAM_DRIFT_TOLERANCE_M,
              "missing_parent_ids": sorted(set(references) - set(cities))}
    filename = "province_conformed.gpkg" if complete else "batch_preview.gpkg"
    target = out / filename
    if passed and target.exists():
        raise FileExistsError(f"batch delivery already exists: {target}")
    (out / "province_qc.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    with (out / "city_adjacency_qc.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["city_a", "city_b", "shared_length_km",
                                                  "mismatch_length_m", "gap_area_m2",
                                                  "overlap_area_m2", "status"])
        writer.writeheader()
        writer.writerows(adjacency)
    if not passed:
        print("##VERDICT stage=batch status=fail; province output withheld")
        return 2
    tmp = work / "batch_delivery.gpkg"
    if tmp.exists():
        raise FileExistsError(f"incomplete batch delivery at {tmp}; inspect before retrying")
    work.mkdir(parents=True, exist_ok=True)
    districts.to_file(tmp, layer="district_units", driver="GPKG")
    city_units.to_file(tmp, layer="city_units", driver="GPKG")
    gpd.GeoDataFrame({"feature": ["outline"]}, geometry=[city_units.geometry.union_all()],
                     crs=city_units.crs).to_file(
                         tmp, layer="province_outline" if complete else "batch_outline",
                         driver="GPKG")
    tmp.replace(target)
    print(f"##VERDICT stage=batch status={'pass' if complete else 'preview'} delivery={target}")
    return 0
