"""Extract administrative faces from reviewed fills or a stroke network.

The output is in page points, without a CRS. Ambiguity stops for review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import fitz
import geopandas as gpd
import numpy as np
import yaml
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polygonize_full, unary_union

from pathio import closed_rings, signed_area, subpaths
from source import inspect


class ReviewExtraction(ValueError):
    """Extraction needs a person or vision-capable agent to choose a candidate."""


def _candidate_preview(census, work, key, candidates):
    """Colour candidate outlines on the original-page preview for human review."""
    path = work / f"review_extraction_{key}.png"
    with Image.open(census["preview"]) as original:
        canvas = original.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    sx, sy = canvas.width / census["page_pt"][0], canvas.height / census["page_pt"][1]
    palette = ["#e60000", "#0066ff", "#00a040", "#aa00aa", "#ff8800"]
    for index, (_, records) in enumerate(candidates):
        colour = palette[index % len(palette)]
        for row in records:
            geom = row["geometry"]
            for poly in (geom.geoms if isinstance(geom, MultiPolygon) else [geom]):
                pts = [(round(x * sx), round(y * sy)) for x, y in poly.exterior.coords]
                draw.line(pts, fill=colour, width=2, joint="curve")
    canvas.save(path)
    return str(path)


def _rgb(rows, field):
    if rows is None:
        return None
    try:
        colours = {tuple(map(int, row)) for row in rows}
    except (TypeError, ValueError) as exc:
        raise ValueError(f"extraction.{field} must contain RGB triplets") from exc
    if any(len(row) != 3 or any(v < 0 or v > 255 for v in row) for row in colours):
        raise ValueError(f"extraction.{field} must contain RGB triplets in 0..255")
    return colours


def _filled_geometry(rings):
    polys = []
    for ring in rings:
        poly = Polygon(ring)
        if not poly.is_valid:
            fixed = poly.buffer(0)
            if (not isinstance(fixed, Polygon) or not fixed.is_valid or
                abs(fixed.area - poly.area) > max(1e-8, 1e-8 * poly.area)):
                raise ValueError("invalid filled ring cannot be repaired without changing area")
            poly = fixed
        polys.append(poly)
    if not polys or any(p.is_empty for p in polys):
        raise ValueError("invalid or empty filled ring")
    order = sorted(range(len(polys)), key=lambda i: -polys[i].area)
    parents, depths = {}, {}
    for pos, i in enumerate(order):
        parent = next((j for j in reversed(order[:pos])
                       if polys[j].contains(polys[i].representative_point())), None)
        parents[i] = parent
        depths[i] = 0 if parent is None else depths[parent] + 1
    shells = []
    for i in order:
        if depths[i] % 2:
            continue
        holes = [polys[j].exterior.coords for j in order if parents[j] == i and depths[j] % 2]
        geom = Polygon(polys[i].exterior.coords, holes)
        if not geom.is_valid:
            raise ValueError("invalid shell/hole hierarchy")
        shells.append(geom)
    return unary_union(shells)


def _fill_units(drawings, keep, split, min_area, tol, page_area):
    by_colour = defaultdict(list)
    rejected, bands = [], []
    for idx, drawing in enumerate(drawings):
        fill = drawing.get("fill")
        if fill is None:
            continue
        rgb = tuple(round(255 * x) for x in fill[:3])
        rings = closed_rings(drawing["items"], tol)
        area = sum(abs(signed_area(ring)) for ring in rings)
        if area < min_area:
            rejected.append({"drawing": idx, "rgb": rgb, "area_pt2": area,
                             "reason": "below area threshold"})
            continue
        try:
            geom = _filled_geometry(rings)
        except ValueError as exc:
            if keep is not None and rgb in keep:
                raise ReviewExtraction(f"drawing {idx} in selected fill {rgb}: {exc}") from exc
            rejected.append({"drawing": idx, "rgb": rgb, "reason": str(exc)})
            continue
        if geom.area < min_area or (keep is None and geom.area > 0.85 * page_area):
            rejected.append({"drawing": idx, "rgb": rgb, "area_pt2": float(geom.area),
                             "reason": "below area threshold or page background"})
            continue
        solidity = geom.area / geom.convex_hull.area
        if geom.area >= max(100, 0.002 * page_area) and solidity < 0.1:
            bands.append({"drawing": idx, "rgb": rgb, "geometry": geom,
                          "solidity": float(solidity)})
            rejected.append({"drawing": idx, "rgb": rgb, "reason": "boundary band candidate",
                             "solidity": float(solidity)})
            continue
        if keep is not None and rgb not in keep:
            rejected.append({"drawing": idx, "rgb": rgb, "reason": "unselected fill"})
            continue
        by_colour[rgb].append((idx, geom))
    if keep is not None and set(by_colour) | {b["rgb"] for b in bands if b["rgb"] in keep} != keep:
        raise ReviewExtraction(f"selected fills missing polygons: {sorted(keep - set(by_colour))}")
    records = []
    for rgb, members in sorted(by_colour.items()):
        if keep is not None and rgb not in split and len(members) > 1:
            for pos, (_, first) in enumerate(members):
                for _, second in members[pos + 1:]:
                    shared = first.boundary.intersection(second.boundary).length
                    if shared > 1e-6 and first.intersection(second).area < 1e-6:
                        raise ReviewExtraction(
                            f"adjacent selected fill paths share colour {rgb}; "
                            "review whether split_colours_rgb should include it")
        # Separate drawing paths can share an edge and colour; unioning them erases the unit boundary.
        merged = unary_union([geom for _, geom in members])
        parts = ([part for _, geom in members for part in
                  (geom.geoms if isinstance(geom, MultiPolygon) else [geom])]
                 if keep is None or rgb in split else
                 (list(merged.geoms) if isinstance(merged, MultiPolygon) else [merged]))
        if keep is None or rgb in split:
            large = [p for p in parts if p.area >= min_area]
            small = [p for p in parts if p.area < min_area]
            if keep is not None and rgb in split and len(large) < 2:
                raise ReviewExtraction(f"split fill {rgb} has fewer than two substantial parts")
            if small and len(large) > 1:
                raise ReviewExtraction(
                    f"small islands in fill {rgb} have multiple possible parent units; "
                    "review the source drawings instead of assigning by distance")
            for piece in small:
                if large:
                    large[0] = large[0].union(piece)
            units = large
        else:
            units = [merged]
        for unit in units:
            records.append({"source_style": "fill:" + ",".join(map(str, rgb)),
                            "source_drawings": ",".join(str(i) for i, geom in members
                                                        if geom.intersection(unit).area > 0),
                            "area_pt2": float(unit.area), "geometry": unit})
    return records, rejected, sum(len(v) for v in by_colour.values()), bands


def _style(drawing):
    colour = drawing.get("color")
    if colour is None:
        return None
    return (tuple(round(255 * x) for x in colour[:3]),
            round(float(drawing.get("width") or 0), 3), str(drawing.get("dashes") or ""))


def _bridges(lines, tolerance):
    if tolerance <= 0:
        return [], []
    ends = []
    for line in lines:
        if not line.is_ring:
            ends.extend([tuple(line.coords[0]), tuple(line.coords[-1])])
    if len(ends) < 2:
        return [], []
    points = np.asarray(ends)
    groups = cKDTree(points).query_ball_point(points, tolerance)
    links, log, used = [], [], set()
    for i, nearby in enumerate(groups):
        neighbors = [j for j in nearby if j != i and
                     1e-8 < np.linalg.norm(points[i] - points[j]) <= tolerance]
        if len(neighbors) > 1:
            raise ReviewExtraction("more than two line endpoints meet within snap_tolerance_pt")
        if not neighbors or i in used:
            continue
        j = neighbors[0]
        reverse = [k for k in groups[j] if k != j and
                   1e-8 < np.linalg.norm(points[j] - points[k]) <= tolerance]
        if reverse != [i]:
            raise ReviewExtraction("ambiguous endpoint bridge")
        used.update((i, j))
        links.append(LineString([points[i], points[j]]))
        log.append({"from": points[i].tolist(), "to": points[j].tolist(),
                    "length_pt": float(np.linalg.norm(points[i] - points[j]))})
    return links, log


def _stroke_units(drawings, styles, min_area, tol, snap_tolerance):
    lines, ids, rejected = [], [], []
    for idx, drawing in enumerate(drawings):
        style = _style(drawing)
        if style is None:
            continue
        if style not in styles:
            rejected.append({"drawing": idx, "style": str(style), "reason": "unselected stroke"})
            continue
        for points in subpaths(drawing["items"], tol):
            if len(points) >= 2:
                line = LineString(points)
                if line.length > 1e-9:
                    lines.append(line)
                    ids.append(idx)
    if not lines:
        return [], rejected, 0, []
    bridges, bridge_log = _bridges(lines, snap_tolerance)
    polygons, dangles, cuts, invalid = polygonize_full(unary_union([*lines, *bridges]))
    faces = [p for p in polygons.geoms if p.area >= min_area and p.is_valid]
    if not faces:
        raise ReviewExtraction(f"selected strokes do not close administrative faces; "
                               f"dangles={len(dangles.geoms)}, cuts={len(cuts.geoms)}")
    records = [{"source_style": "stroke:" + ";".join(map(str, sorted(styles))),
                "source_drawings": ",".join(map(str, sorted(set(ids)))),
                "area_pt2": float(p.area), "geometry": p} for p in faces]
    return records, rejected, len(set(ids)), bridge_log


def extract(config: dict) -> dict:
    extraction = config.get("extraction", {})
    method = extraction.get("method", "auto")
    if method not in {"auto", "fill", "line"}:
        raise ValueError("extraction.method must be auto, fill, or line")
    keep = _rgb(extraction.get("keep_colours_rgb"), "keep_colours_rgb")
    split = _rgb(extraction.get("split_colours_rgb", []), "split_colours_rgb") or set()
    if keep is not None and not split <= keep:
        raise ValueError("split_colours_rgb must be in keep_colours_rgb")
    work = Path(config["work_dir"])
    tol = float(extraction.get("bezier_tolerance_pt", 0.05))
    census = inspect(Path(config["source_map"]), work, tol, config.get("source_page", 1))
    min_area = float(extraction.get("min_fill_area_pt2") or
                     max(20.0, census["page_pt"][0] * census["page_pt"][1] * 0.001))
    expected = extraction.get("expected_admin_polygon_count")
    snap = float(extraction.get("snap_tolerance_pt") or 0)
    if tol <= 0 or min_area <= 0 or snap < 0:
        raise ValueError("flatten/area thresholds must be positive; snap tolerance nonnegative")
    stroke_rules = extraction.get("keep_strokes")
    stamp = {"version": 4, "pdf_sha256": census["stamp"]["pdf_sha256"],
             "page_index": census["page_index"],
             "method": method, "keep_colours_rgb": sorted(map(list, keep)) if keep is not None else None,
             "split_colours_rgb": sorted(map(list, split)), "keep_strokes": stroke_rules,
             "min_fill_area_pt2": min_area, "expected_admin_polygon_count": expected,
             "flatten_tolerance_pt": tol, "snap_tolerance_pt": snap}
    key = hashlib.sha256(json.dumps(stamp, sort_keys=True).encode()).hexdigest()[:12]
    stage = work / f"extraction_{key}"
    report_path, gpkg_path = stage / "extraction.json", stage / "page_units.gpkg"
    if report_path.is_file() and gpkg_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("stamp") == stamp:
            return report
    if stage.exists() and any(stage.iterdir()):
        raise FileExistsError(f"incomplete extraction at {stage}; inspect it before retrying")
    with fitz.open(census["pdf"]) as doc:
        drawings = doc[census["page_index"]].get_drawings()
    page_area = census["page_pt"][0] * census["page_pt"][1]
    fill_result = None
    if method != "line" and census["filled_drawings"]:
        fill_result = _fill_units(drawings, keep, split, min_area, tol, page_area)
        records, rejected, accepted, bands = fill_result
        selected_bands = [b for b in bands if keep is None or b["rgb"] in keep]
        if selected_bands and not records and len(selected_bands) == 1:
            band = selected_bands[0]["geometry"]
            if isinstance(band, Polygon) and len(band.interiors) == 1:
                inner = Polygon(band.interiors[0])
                records.append({"source_style": "band_inner", "source_drawings":
                                str(selected_bands[0]["drawing"]),
                                "area_pt2": float(inner.area), "geometry": inner})
                accepted = 1
                fill_result = records, rejected, accepted, bands
        if selected_bands and (not records or records[0]["source_style"] != "band_inner"):
            preview = _candidate_preview(census, work, key,
                                         [("fill", records), ("band", [
                                             {"geometry": b["geometry"]} for b in selected_bands])])
            raise ReviewExtraction(f"filled band and administrative faces need review; inspect {preview}")
    if method == "fill" and (not fill_result or not fill_result[0]):
        raise ReviewExtraction("no credible filled administrative polygons")
    line_result = None
    if method != "fill" and census["stroked_drawings"]:
        available = {_style(d) for d in drawings if _style(d) is not None}
        if stroke_rules is not None:
            styles = {(tuple(row["rgb"]), round(float(row["width_pt"]), 3),
                       str(row.get("dashes") or "")) for row in stroke_rules}
            if not styles <= available:
                raise ReviewExtraction("reviewed stroke style is absent from the source")
            line_result = _stroke_units(drawings, styles, min_area, tol, snap)
        elif method == "line" or (method == "auto" and keep is None) or not fill_result or not fill_result[0]:
            candidates = []
            for style in available:
                try:
                    result = _stroke_units(drawings, {style}, min_area, tol,
                                           snap if method == "line" else 0)
                except ReviewExtraction:
                    continue
                if result[0]:
                    candidates.append((style, result))
            if len(candidates) == 1:
                line_result = candidates[0][1]
            elif len(candidates) > 1:
                review = work / f"review_extraction_{key}.json"
                preview = _candidate_preview(census, work, key,
                                             [(str(s), result[0]) for s, result in candidates])
                review.write_text(json.dumps({"reason": "multiple closed stroke networks",
                                              "preview": preview,
                                              "candidates": [{"style": str(s), "units": len(r[0])}
                                                             for s, r in candidates]},
                                             ensure_ascii=False, indent=2), encoding="utf-8")
                raise ReviewExtraction(f"multiple plausible stroke networks; inspect {review}")
    if method == "auto" and fill_result and fill_result[0] and line_result and line_result[0]:
        filled = unary_union([r["geometry"] for r in fill_result[0]])
        outlined = unary_union([r["geometry"] for r in line_result[0]])
        if keep is None and outlined.buffer(1e-6).covers(filled) and outlined.area > 3 * filled.area:
            fill_result = None  # an interior decorative fill inside the stroked partition
        else:
            preview = _candidate_preview(census, work, key,
                                         [("fill", fill_result[0]), ("line", line_result[0])])
            raise ReviewExtraction(f"both fill and stroke networks are plausible; "
                                   f"inspect {preview} and choose extraction.method")
    chosen = (line_result if method == "line" else fill_result if fill_result and fill_result[0]
              else line_result)
    if not chosen or not chosen[0]:
        raise ReviewExtraction("no credible administrative faces in filled paths or strokes")
    used_method = "line" if chosen is line_result else "fill"
    if method == "auto" and used_method == "line" and (
        len(chosen[0]) > 30 or
        unary_union([r["geometry"] for r in chosen[0]]).area < 0.15 * page_area
    ):
        preview = _candidate_preview(census, work, key, [("line", chosen[0])])
        raise ReviewExtraction(f"stroke network needs administrative review; inspect {preview}")
    if method == "auto" and keep is None and used_method == "fill" and (
        census["filled_drawings"] > 50 or census["embedded_images"]
    ):
        review = work / f"review_extraction_{key}.json"
        review.write_text(json.dumps({"reason": "mixed map needs reviewed fills",
                                      "colours": census["colours"][:30]},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
        raise ReviewExtraction(f"mixed fills; choose keep_colours_rgb using {review}")
    if used_method == "fill":
        records, rejected, accepted, bands = chosen
        bridges = []
    else:
        records, rejected, accepted, bridges = chosen
        bands = []
    records.sort(key=lambda row: (-row["area_pt2"], row["geometry"].bounds))
    if expected is not None and len(records) != int(expected):
        raise ReviewExtraction(f"extracted {len(records)} units, expected {expected}; review method/styles")
    for i, row in enumerate(records, 1):
        row["admin_id"] = f"A{i:03d}"
    frame = gpd.GeoDataFrame(records, geometry="geometry")
    if any(not geom.is_valid or geom.is_empty for geom in frame.geometry):
        raise ReviewExtraction("invalid administrative geometry")
    union = unary_union(frame.geometry)
    overlap = float(sum(frame.geometry.area) - union.area)
    if overlap > max(1e-6, 0.001 * union.area):
        raise ReviewExtraction(f"administrative faces overlap by {overlap:.3f} page pt²")
    stage.mkdir(parents=True, exist_ok=True)
    frame.to_file(gpkg_path, layer="page_units", driver="GPKG")
    (stage / "reject_log.json").write_text(json.dumps(rejected, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    report = {"stamp": stamp, "method": used_method, "admin_units": len(frame),
              "accepted_drawings": accepted, "rejected_drawings": len(rejected),
              "bridges": bridges, "overlap_area_pt2": overlap,
              "boundary_source": ("band_inner" if used_method == "fill" and
                                  records[0]["source_style"] == "band_inner" else
                                  "administrative_fill" if used_method == "fill" else "stroke"),
              "excluded_band_drawings": [b["drawing"] for b in bands
                                         if records[0]["source_style"] != "band_inner"],
              "inner_edge_drawing": (int(records[0]["source_drawings"])
                                     if records[0]["source_style"] == "band_inner" else None),
              "page_units_gpkg": str(gpkg_path), "reject_log": str(stage / "reject_log.json"),
              "units": frame.drop(columns="geometry").to_dict(orient="records")}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    try:
        report = extract(config)
    except ReviewExtraction as exc:
        print(f"##VERDICT stage=extract status=review reason={exc}")
        return 2
    print(f"method={report['method']} admin units={report['admin_units']} "
          f"from {report['accepted_drawings']} paths")
    print(report["page_units_gpkg"])
    print("##VERDICT stage=extract status=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
