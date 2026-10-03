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
from shapely.geometry import LineString, MultiPolygon
from shapely.ops import split, unary_union

from register import apply_geom, parts


class ReviewConformance(ValueError):
    """A repairable gap has no unique adjacent administrative unit."""


DEFAULT_FILES = {"registered_gpkg": "registered.gpkg", "qc_json": "qc.json",
                 "overlay_png": "overlay.png", "run_log": "run.log"}
DEFAULT_C = {"conformed_gpkg": "conformed.gpkg", "conformance_qc_json": "conformance_qc.json"}
AREA_TOLERANCE_M2 = 1e-3
AREA_SUM_TOLERANCE_M2 = 1e-2
SEAM_DRIFT_TOLERANCE_M = 1.0
MAX_INTERNAL_GAP_WIDTH_PT = 0.25
MIN_INTERNAL_GAP_ASPECT_RATIO = 10.0
MIN_INTERNAL_GAP_RECT_FILL_RATIO = 0.8


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


def _split_gap_midline(piece, rectangle, edge_lengths, adjacent, units_fit, max_width):
    if len(adjacent) != 2:
        return None
    short_edge = int(np.argmin(edge_lengths))
    opposite = (short_edge + 2) % 4
    coords = list(rectangle.exterior.coords)
    start = ((coords[short_edge][0] + coords[short_edge + 1][0]) / 2,
             (coords[short_edge][1] + coords[short_edge + 1][1]) / 2)
    end = ((coords[opposite][0] + coords[opposite + 1][0]) / 2,
           (coords[opposite][1] + coords[opposite + 1][1]) / 2)
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = np.hypot(dx, dy)
    if length == 0:
        return None
    dx, dy = dx / length, dy / length
    extension = 2 * max_width
    divider = LineString([(start[0] - dx * extension, start[1] - dy * extension),
                          (end[0] + dx * extension, end[1] + dy * extension)])
    halves = _pieces(split(piece, divider))
    if len(halves) != 2 or unary_union(halves).symmetric_difference(piece).area > AREA_TOLERANCE_M2:
        return None

    assignments = []
    for half in halves:
        contacts = [half.boundary.intersection(g.boundary).length
                    for g in units_fit.geometry]
        ranked = sorted(contacts, reverse=True)
        if not ranked or ranked[0] < 0.5 or (len(ranked) > 1 and
                                             ranked[1] >= 0.99 * ranked[0]):
            return None
        assignments.append(int(np.argmax(contacts)))
    if set(assignments) != set(adjacent):
        return None
    return list(zip(halves, assignments))


def _repair_internal_line_gaps(units_fit, reference, m_per_pt):
    max_width = m_per_pt * MAX_INTERNAL_GAP_WIDTH_PT
    interior = reference.buffer(-max_width)
    if interior.is_empty:
        return units_fit, {"status": "no_interior_area", "repaired_pieces": 0,
                           "repaired_area_km2": 0.0,
                           "width_limit_pt": MAX_INTERNAL_GAP_WIDTH_PT,
                           "max_width_m": max_width,
                           "minimum_aspect_ratio": MIN_INTERNAL_GAP_ASPECT_RATIO,
                           "minimum_rectangle_fill_ratio": MIN_INTERNAL_GAP_RECT_FILL_RATIO}, []

    uncovered = reference.difference(unary_union(units_fit.geometry))
    ids = list(units_fit.admin_id)
    owners = [[] for _ in ids]
    repairs = []
    for piece in _pieces(uncovered):
        rectangle = piece.minimum_rotated_rectangle
        edges = list(rectangle.exterior.coords)
        lengths = [np.hypot(edges[i + 1][0] - edges[i][0],
                            edges[i + 1][1] - edges[i][1]) for i in range(4)]
        width, length = min(lengths), max(lengths)
        aspect = length / width if width else float("inf")
        rect_fill = piece.area / rectangle.area if rectangle.area else 0
        if (not interior.covers(piece) or width <= 0 or width > max_width or
                aspect < MIN_INTERNAL_GAP_ASPECT_RATIO or
                rect_fill < MIN_INTERNAL_GAP_RECT_FILL_RATIO):
            continue
        contacts = [piece.boundary.intersection(g.boundary).length
                    for g in units_fit.geometry]
        ranked = sorted(contacts, reverse=True)
        if not ranked or ranked[0] < 0.5 or (len(ranked) > 1 and
                                             ranked[1] >= 0.99 * ranked[0]):
            adjacent = [i for i, contact in enumerate(contacts) if contact >= 0.5]
            split_repairs = _split_gap_midline(
                piece, rectangle, lengths, adjacent, units_fit, max_width)
            if split_repairs is None:
                raise ReviewConformance(
                    "Mode R found an internal line-like gap without a unique owner: "
                    f"area={piece.area:.3f} m2, width={width:.3f} m, "
                    f"length={length:.3f} m, bounds={tuple(round(v, 3) for v in piece.bounds)}, "
                    f"owner_contacts_m={ranked[:3]}")
            for half, ix in split_repairs:
                owners[ix].append(half)
                repairs.append({"admin_id": ids[ix],
                                "evidence_class": "midline_split_between_two_units",
                                "area_km2": half.area / 1e6, "width_m": width,
                                "length_m": length, "aspect_ratio": aspect,
                                "rectangle_fill_ratio": rect_fill, "geometry": half})
            continue
        ix = int(np.argmax(contacts))
        owners[ix].append(piece)
        repairs.append({"admin_id": ids[ix], "evidence_class": "unique_adjacent_contact",
                        "area_km2": piece.area / 1e6, "width_m": width,
                        "length_m": length, "aspect_ratio": aspect,
                        "rectangle_fill_ratio": rect_fill, "geometry": piece})

    if not repairs:
        return units_fit, {"status": "no_line_like_gaps", "repaired_pieces": 0,
                           "repaired_area_km2": 0.0,
                           "width_limit_pt": MAX_INTERNAL_GAP_WIDTH_PT,
                           "max_width_m": max_width,
                           "minimum_aspect_ratio": MIN_INTERNAL_GAP_ASPECT_RATIO,
                           "minimum_rectangle_fill_ratio": MIN_INTERNAL_GAP_RECT_FILL_RATIO}, []
    repaired = units_fit.copy()
    repaired["geometry"] = [
        unary_union([geom, *added])
        for geom, added in zip(units_fit.geometry, owners)]
    report = {"status": "repaired", "width_limit_pt": MAX_INTERNAL_GAP_WIDTH_PT,
              "max_width_m": max_width, "minimum_aspect_ratio": MIN_INTERNAL_GAP_ASPECT_RATIO,
              "minimum_rectangle_fill_ratio": MIN_INTERNAL_GAP_RECT_FILL_RATIO,
              "repaired_pieces": len(repairs),
              "repaired_area_km2": sum(row["area_km2"] for row in repairs),
              "assignment": "unique contact or midline split between two adjacent units",
              "caveat": "inferred closure; not evidence drawn on the source sheet"}
    return repaired, report, repairs


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
    mode = config.get("delivery", {}).get("mode", "R")
    gap_repair = {"status": "handled_by_mode_c" if mode == "C" else "not_applicable"}
    gap_rows = []
    if mode == "R" and scope["source_scope"] == "same_extent":
        units_fit, gap_repair, gap_rows = _repair_internal_line_gaps(
            units_fit, reference["geometry"], registration["stats"]["m_per_pt"])
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
    if gap_rows:
        gpd.GeoDataFrame(gap_rows, geometry="geometry", crs=fit_crs).to_crs(
            output_crs).to_file(gpkg, layer="internal_gap_repairs", driver="GPKG")
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
                       "internal_boundaries_independently_validated": False,
                       "internal_gap_repair": gap_repair},
        "status": "REGISTERED_WITH_QC" if name_qc["status"] not in {"incomplete", "not_checked"}
                  else "REGISTERED_REVIEW_NAMES",
    }
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
