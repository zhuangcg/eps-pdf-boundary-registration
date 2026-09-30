"""Write Mode R and optional same-extent Mode C from one global transform."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union

from register import apply_geom, parts


class ReviewConformance(ValueError):
    """Mode C cannot assign reference-only area without a clear sheet edge."""


DEFAULT_FILES = {"registered_gpkg": "registered.gpkg", "qc_json": "qc.json",
                 "overlay_png": "overlay.png", "run_log": "run.log"}
DEFAULT_C = {"conformed_gpkg": "conformed.gpkg", "conformance_qc_json": "conformance_qc.json"}
AREA_TOLERANCE_M2 = 1e-3
AREA_SUM_TOLERANCE_M2 = 1e-2
SEAM_DRIFT_TOLERANCE_M = 1.0


def filenames(config):
    delivery = config.get("delivery", {})
    return {**DEFAULT_FILES, **(delivery.get("files") or {})}, {
        **DEFAULT_C, **(delivery.get("conformed_files") or {})}


def _figure(units, source, reference, registration, out):
    plt.rcParams.update({"font.family": "Helvetica", "font.size": 12,
                         "lines.linewidth": 1.5})
    fig, ax = plt.subplots(figsize=(10, 7), dpi=150)
    reference_style = {"color": "#343A40", "linewidth": 2.0, "linestyle": "-"}
    source_style = {"color": "#D55E00", "linewidth": 2.0, "linestyle": "-"}
    units_style = {"color": "#0072B2", "linewidth": 1.5, "linestyle": "-"}
    gpd.GeoSeries([reference]).boundary.plot(ax=ax, **reference_style)
    gpd.GeoSeries([source]).boundary.plot(ax=ax, **source_style)
    units.boundary.plot(ax=ax, **units_style)
    metrics = registration["metrics"]
    line = (f"median {metrics['median_m']:.1f} m  P90 {metrics['p90_m']:.1f} m"
            + (f"  shared arc {metrics['shared_arc_km']:.2f} km"
               if "shared_arc_km" in metrics else ""))
    ax.set_title(line)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def _pieces(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return list(geom.geoms)
    return [p for part in geom.geoms for p in _pieces(part)]


def _conform(units_fit, reference, output_crs, out, paths):
    ids = list(units_fit.admin_id)
    ref = reference
    clipped = [g.intersection(ref) for g in units_fit.geometry]
    uncovered = ref.difference(unary_union(clipped))
    owners = {key: [] for key in ids}
    added_rows = []
    for piece in _pieces(uncovered):
        shared = [piece.boundary.intersection(g.boundary).length for g in clipped]
        ranked = sorted(shared, reverse=True)
        if not ranked or ranked[0] < 0.5 or (len(ranked) > 1 and
                                             ranked[1] >= 0.99 * ranked[0]):
            raise ReviewConformance(
                "Mode C reference-only area has no unique sheet-supported owner")
        ix = int(np.argmax(shared))
        evidence = ("reference_outline_not_on_sheet"
                    if piece.boundary.intersection(ref.boundary).length >= 1
                    else "drawing_seam_closure")
        owners[ids[ix]].append(piece)
        added_rows.append({"admin_id": ids[ix], "evidence_class": evidence,
                           "area_km2": piece.area / 1e6, "geometry": piece})
    combined = [unary_union([clipped[i], *owners[key]]) for i, key in enumerate(ids)]
    final = [None] * len(combined)
    for i in sorted(range(len(combined)), key=lambda j: -combined[j].area):
        taken = [g for g in final if g is not None]
        final[i] = combined[i].difference(unary_union(taken)) if taken else combined[i]
    union = unary_union(final)
    overlap = sum(final[i].intersection(final[j]).area
                  for i in range(len(final)) for j in range(i + 1, len(final)))
    seams = unary_union([final[i].boundary.intersection(final[j].boundary)
                         for i in range(len(final)) for j in range(i + 1, len(final))])
    original_lines = unary_union([g.boundary for g in clipped])
    drift = seams.difference(original_lines.buffer(0.05, cap_style=2)).length
    checks = {
        "symmetric_difference_m2": union.symmetric_difference(ref).area,
        "outside_m2": union.difference(ref).area,
        "uncovered_m2": ref.difference(union).area,
        "pairwise_overlap_m2": overlap,
        "area_sum_difference_m2": sum(g.area for g in final) - ref.area,
        "internal_seam_drift_m": drift,
        "invalid_geometries": sum(not g.is_valid for g in final),
    }
    passed = (all(abs(checks[k]) <= AREA_TOLERANCE_M2 for k in
                  ("symmetric_difference_m2", "outside_m2", "uncovered_m2",
                   "pairwise_overlap_m2")) and
              abs(checks["area_sum_difference_m2"]) <= AREA_SUM_TOLERANCE_M2 and
              drift < SEAM_DRIFT_TOLERANCE_M and checks["invalid_geometries"] == 0)
    if not passed:
        raise ReviewConformance(f"Mode C geometric assertions failed: {checks}")
    conform = units_fit.copy()
    conform["geometry"] = final
    conform["area_km2"] = [g.area / 1e6 for g in final]
    conform["added_area_km2"] = [sum(p.area for p in owners[key]) / 1e6 for key in ids]
    gpkg = out / paths["conformed_gpkg"]
    conform.to_crs(output_crs).to_file(gpkg, layer="conformed_units", driver="GPKG")
    gpd.GeoDataFrame({"feature": ["conformed_outline"]}, geometry=[union],
                     crs=units_fit.crs).to_crs(output_crs).to_file(
                         gpkg, layer="conformed_outline", driver="GPKG")
    if added_rows:
        gpd.GeoDataFrame(added_rows, geometry="geometry", crs=units_fit.crs).to_crs(
            output_crs).to_file(gpkg, layer="added_without_sheet_evidence", driver="GPKG")
    report = {"all_assertions_pass": passed, "assertions": checks,
              "added_pieces": len(added_rows), "added_total_km2": sum(
                  row["area_km2"] for row in added_rows),
              "dropped_total_km2": sum(g.difference(ref).area for g in units_fit.geometry) / 1e6,
              "caveat": "reference supplies the outer boundary; added area lacks sheet evidence"}
    (out / paths["conformance_qc_json"]).write_text(json.dumps(
        report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def write(config, page_units, label_points, name_qc, extraction, scope, registration,
          reference, source_hash, reference_hash, fingerprint):
    out = Path(config["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise FileExistsError(f"delivery directory is not empty: {out}")
    files, c_files = filenames(config)
    matrix = registration["matrix"]
    fit_crs, output_crs = reference["fit_crs"], reference["output_crs"]
    units_fit = page_units.copy()
    units_fit["geometry"] = [apply_geom(g, matrix) for g in page_units.geometry]
    units_fit = units_fit.set_crs(fit_crs)
    units_fit["admin_level"] = scope["admin_level"]
    units_fit["area_km2"] = units_fit.geometry.area / 1e6
    source = unary_union(units_fit.geometry)
    gpkg = out / files["registered_gpkg"]
    units_fit.to_crs(output_crs).to_file(gpkg, layer="administrative_units", driver="GPKG")
    gpd.GeoDataFrame({"feature": ["registered_outline"]}, geometry=[source],
                     crs=fit_crs).to_crs(output_crs).to_file(
                         gpkg, layer="registered_outline", driver="GPKG")
    gpd.GeoDataFrame({"feature": ["reference_outline"]}, geometry=[reference["geometry"]],
                     crs=fit_crs).to_crs(output_crs).to_file(
                         gpkg, layer="reference_outline", driver="GPKG")
    if label_points is not None and len(label_points):
        labels_fit = label_points.copy()
        labels_fit["geometry"] = [apply_geom(g, matrix) for g in labels_fit.geometry]
        labels_fit = labels_fit.set_crs(fit_crs)
        labels_fit.to_crs(output_crs).to_file(gpkg, layer="map_labels", driver="GPKG")
    scale = registration["stats"]["m_per_pt"]
    scale_check = abs(registration["stats"]["scale_denominator"] -
                      scale * 72 / 25.4 * 1000) < 1e-6
    if not scale_check or not all(units_fit.geometry.is_valid):
        raise ValueError("scale identity or output geometry validity failed")
    qc = {
        "fingerprint": fingerprint, "created_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {"source_map": str(config["source_map"]),
                   "source_page": config.get("source_page", 1),
                   "source_sha256": source_hash,
                   "reference_boundary": str(config["reference_boundary"]),
                   "reference_sha256": reference_hash},
        "decision": scope, "extraction": {"method": extraction["method"],
                                          "admin_units": extraction["admin_units"],
                                          "bridges": extraction["bridges"],
                                          "overlap_area_pt2": extraction["overlap_area_pt2"],
                                          "boundary_source": extraction["boundary_source"],
                                          "excluded_band_drawings": extraction["excluded_band_drawings"],
                                          "inner_edge_drawing": extraction["inner_edge_drawing"]},
        "names": name_qc, "registration": {
            "model": registration["model"], "matrix_page_to_fit": matrix.tolist(),
            "fit_crs": registration["fit_crs"], "output_crs": registration["output_crs"],
            "scale": registration["stats"], "metrics": registration["metrics"],
            "gate": registration["gate"],
            "selection": registration["selection"],
            "iterations": len(registration["history"])},
        "validation": {"scale_identity": scale_check,
                       "invalid_geometries": int(sum(not g.is_valid for g in units_fit.geometry)),
                       "internal_boundaries_independently_validated": False},
        "status": "REGISTERED_WITH_QC" if name_qc["status"] not in {"incomplete", "not_checked"}
                  else "REGISTERED_REVIEW_NAMES",
    }
    mode = config.get("delivery", {}).get("mode", "R")
    if mode == "C":
        if scope["source_scope"] != "same_extent":
            raise ValueError("Mode C requires same_extent")
        qc["conformance"] = _conform(units_fit, reference["geometry"], output_crs, out, c_files)
    (out / files["qc_json"]).write_text(json.dumps(qc, ensure_ascii=False, indent=2,
                                                   default=float), encoding="utf-8")
    _figure(units_fit, source, reference["geometry"], registration, out / files["overlay_png"])
    delivered = gpd.read_file(gpkg, layer="administrative_units")
    if len(delivered) != len(page_units) or delivered.crs != output_crs:
        raise ValueError("delivered GPKG failed independent readback")
    lines = [
        "## EPS registration run",
        f"- Source: {config['source_map']}",
        f"- Source page: {config.get('source_page', 1)}",
        f"- Reference: {config['reference_boundary']}",
        f"- Level: {scope['admin_level']} ({scope['evidence']['admin_level']})",
        f"- Relationship: {scope['source_scope']} ({scope['evidence']['source_scope']})",
        f"- Extraction: {extraction['method']}, {len(delivered)} units",
        f"- Names: {name_qc['named_units']}/{name_qc['total_units']} ({name_qc['status']})",
        *([f"- Name review: {name_qc['message']}"] if name_qc.get("message") else []),
        f"- Fit CRS: {registration['fit_crs']}; delivered CRS: {registration['output_crs']}",
        f"- Scale: {scale:.5f} m/pt (1:{registration['stats']['scale_denominator']:.0f})",
        f"- Outline median/P90: {registration['metrics']['median_m']:.2f}/"
        f"{registration['metrics']['p90_m']:.2f} m",
        "- Internal unit boundaries have no independent same-level reference validation.",
        f"- Status: {qc['status']}",
    ]
    (out / files["run_log"]).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return qc
