"""One global page-to-reference transform for complete or shared-arc outlines."""
from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
from pyproj import CRS, Transformer
from scipy.spatial import cKDTree
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union


class ReviewRegistration(ValueError):
    """No unique, defensible global alignment was found."""


def parts(geom):
    return list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]


def exterior(geom):
    return Polygon(max(parts(geom), key=lambda p: p.area).exterior)


def sample_ring(coords, spacing):
    a = np.asarray(coords, dtype=float)
    if np.allclose(a[0], a[-1]):
        a = a[:-1]
    a = np.concatenate([a, a[:1]])
    seg = np.linalg.norm(np.diff(a, axis=0), axis=1)
    keep = np.concatenate([[True], seg[:-1] > 1e-12])
    a = np.concatenate([a[:-1][keep], a[:1]])
    seg = np.linalg.norm(np.diff(a, axis=0), axis=1)
    cumulative = np.r_[0.0, np.cumsum(seg)]
    count = max(8, int(round(cumulative[-1] / spacing)))
    distances = np.linspace(0, cumulative[-1], count, endpoint=False)
    return np.column_stack([np.interp(distances, cumulative, a[:, k]) for k in (0, 1)])


def sample_outer(geom, spacing):
    return sample_ring(exterior(geom).exterior.coords, spacing)


def apply_points(points, matrix):
    return np.asarray(points) @ matrix[:2, :2].T + matrix[:2, 2]


def apply_geom(geom, matrix):
    m = matrix
    return affinity.affine_transform(geom, [m[0, 0], m[0, 1], m[1, 0], m[1, 1],
                                            m[0, 2], m[1, 2]])


def similarity(src, dst, allow_reflection=True):
    a, b = src - src.mean(0), dst - dst.mean(0)
    u, singular, vt = np.linalg.svd(b.T @ a / len(a))
    sign = 1.0 if allow_reflection else np.sign(np.linalg.det(u @ vt))
    r = u @ np.diag([1.0, sign]) @ vt
    scale = (singular * [1.0, sign]).sum() / np.mean(np.sum(a * a, axis=1))
    m = np.eye(3)
    m[:2, :2] = scale * r
    m[:2, 2] = dst.mean(0) - m[:2, :2] @ src.mean(0)
    return m


def affine_fit(src, dst):
    x = np.column_stack([src, np.ones(len(src))])
    coef, *_ = np.linalg.lstsq(x, dst, rcond=None)
    m = np.eye(3)
    m[:2, :2] = coef[:2].T
    m[:2, 2] = coef[2]
    return m


def scale_stats(matrix):
    linear = matrix[:2, :2]
    sx, sy = np.linalg.norm(linear[:, 0]), np.linalg.norm(linear[:, 1])
    return {"m_per_pt": float((sx + sy) / 2),
            "scale_denominator": float((sx + sy) / 2 * 72 / 25.4 * 1000),
            "anisotropy": float(abs(sx - sy) / max(sx, sy)),
            "reflection": bool(np.linalg.det(linear) < 0)}


def choose_fit_crs(reference, configured):
    if configured and configured != "auto":
        crs = CRS.from_user_input(configured)
        if not crs.is_projected or not all(axis.unit_name.lower() in
                                            {"metre", "meter", "metres", "meters"}
                                            for axis in crs.axis_info[:2]):
            raise ValueError("reference.fit_crs must be projected in metres")
        return crs
    geo = reference.to_crs(4326)
    bounds = geo.total_bounds
    centre = geo.geometry.union_all().centroid
    if bounds[2] - bounds[0] < 6 and -80 < centre.y < 84:
        estimated = geo.estimate_utm_crs()
        if estimated:
            return CRS.from_user_input(estimated)
    return CRS.from_proj4(f"+proj=aeqd +lat_0={centre.y:.8f} +lon_0={centre.x:.8f} "
                          "+datum=WGS84 +units=m +no_defs")


def load_reference(config):
    path = config["reference_boundary"]
    layer = config.get("reference_layer")
    raw = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if raw.crs is None or raw.empty:
        raise ValueError("reference boundary needs a known CRS and nonempty geometry")
    geom = raw.geometry.union_all()
    if not geom.is_valid:
        geom = geom.buffer(0)
    if geom.is_empty or geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("reference must contain polygon geometry")
    fit_crs = choose_fit_crs(raw, config.get("reference", {}).get("fit_crs"))
    fit_geom = gpd.GeoSeries([geom], crs=raw.crs).to_crs(fit_crs).iloc[0]
    return {"geometry": fit_geom, "source_geometry": geom,
            "fit_crs": fit_crs, "output_crs": raw.crs}


def _distance_summary(a, b):
    return {"median_m": float(np.median(a)), "p75_m": float(np.percentile(a, 75)),
            "p90_m": float(np.percentile(a, 90)), "p95_m": float(np.percentile(a, 95)),
            "max_m": float(np.max(a)), "reverse_median_m": float(np.median(b)),
            "reverse_p90_m": float(np.percentile(b, 90))}


def _icp(src, ref_dense, init, trim=0.8, iterations=80, mask=None):
    tree = cKDTree(ref_dense)
    matrix = init.copy()
    history = []
    for i in range(iterations):
        distances, idx = tree.query(apply_points(src, matrix))
        eligible = np.arange(len(src)) if mask is None else np.flatnonzero(mask)
        if len(eligible) < 12:
            raise ReviewRegistration("too few matched outline samples")
        keep = eligible[np.argsort(distances[eligible])[:max(12, int(len(eligible) * trim))]]
        updated = similarity(src[keep], ref_dense[idx[keep]])
        change = np.max(np.abs(updated - matrix))
        matrix = updated
        history.append(float(np.median(distances[keep])))
        if change < 1e-7:
            break
    return matrix, history


def _matrix(rotation_deg, reflection, scale, source_centre, target_centre):
    theta = math.radians(rotation_deg)
    rot = np.array([[math.cos(theta), -math.sin(theta)],
                    [math.sin(theta), math.cos(theta)]])
    flip = np.diag([(-1 if reflection in ("x", "xy") else 1),
                    (-1 if reflection in ("y", "xy") else 1)])
    m = np.eye(3)
    m[:2, :2] = scale * rot @ flip
    m[:2, 2] = target_centre - m[:2, :2] @ source_centre
    return m


def _complete(source, reference, config):
    src_geom, ref_geom = exterior(source), exterior(reference)
    scale = math.sqrt(ref_geom.area / src_geom.area)
    src = sample_outer(src_geom, max(0.3, src_geom.length / 2500))
    ref = sample_outer(ref_geom, max(30, ref_geom.length / 2500))
    dense = sample_outer(ref_geom, max(15, ref_geom.length / 5000))
    tree = cKDTree(dense)
    ranked = []
    for reflection in ("none", "x", "y", "xy"):
        for rotation in (0, 90, 180, 270):
            initial = _matrix(rotation, reflection, scale, src.mean(0), ref.mean(0))
            transformed = apply_points(src, initial)
            forward = tree.query(transformed)[0]
            reverse = cKDTree(transformed).query(ref)[0]
            ranked.append((float(np.median(forward) + np.median(reverse)),
                           reflection, rotation, initial))
    ranked.sort(key=lambda row: row[0])
    tried = []
    for score, reflection, rotation, initial in ranked[:4]:
        matrix, history = _icp(src, dense, initial)
        transformed = apply_points(src, matrix)
        forward = tree.query(transformed)[0]
        reverse = cKDTree(transformed).query(ref)[0]
        tried.append({"matrix": matrix, "model": "similarity", "reflection": reflection,
                      "rotation_deg": rotation, "coarse_score_m": score,
                      "fit_score_m": float(np.median(forward) + np.median(reverse)),
                      "history": history})
    tried.sort(key=lambda row: row["fit_score_m"])
    best = tried[0]
    tree = cKDTree(dense)
    d, idx = tree.query(apply_points(src, best["matrix"]))
    keep = np.argsort(d)[:max(12, int(0.8 * len(d)))]
    affine = affine_fit(src[keep], dense[idx[keep]])
    d_aff = tree.query(apply_points(src, affine))[0]
    gain = 1 - np.median(d_aff) / max(np.median(d), 1e-9)
    if gain > config.get("model_selection", {}).get("escalate_to_affine_if_median_gain_gt", 0.2):
        if scale_stats(affine)["anisotropy"] < 0.05:
            best = {**best, "matrix": affine, "model": "affine"}
    best["affine_median_gain"] = float(gain)
    best["coarse_candidates"] = [{"score_m": x[0], "reflection": x[1],
                                  "rotation_deg": x[2]} for x in ranked]
    return best


def _longest_circular(mask):
    n = len(mask)
    if not mask.any():
        return np.array([], dtype=int)
    if mask.all():
        return np.arange(n)
    doubled = np.r_[mask, mask]
    best, start = 0, 0
    i = 0
    while i < 2 * n:
        if doubled[i]:
            j = i
            while j < 2 * n and doubled[j]:
                j += 1
            if i < n and min(j - i, n) > best:
                best, start = min(j - i, n), i
            i = j
        else:
            i += 1
    return (start + np.arange(best)) % n


def _landmark_seed(config, fit_crs):
    marks = config.get("landmarks") or []
    if len(marks) < 2:
        return None
    src = np.asarray([row["page_pt"] for row in marks[:2]], dtype=float)
    to_fit = Transformer.from_crs(4326, fit_crs, always_xy=True)
    dst = np.asarray([to_fit.transform(*row["lonlat"]) for row in marks[:2]])
    if np.linalg.norm(src[0] - src[1]) < 1:
        raise ValueError("landmarks are too close in page coordinates")
    flip = np.eye(3)
    flip[1, 1] = -1
    return similarity(apply_points(src, flip), dst, allow_reflection=False) @ flip


def _shared(source, reference, config, fit_crs):
    src_geom, ref_geom = exterior(source), exterior(reference)
    seed = _landmark_seed(config, fit_crs)
    if seed is None:
        raise ReviewRegistration(
            "shared boundary needs two verified landmark seeds or a same-level reference; "
            "do not infer an arbitrary coast match")
    estimated_scale = scale_stats(seed)["m_per_pt"]
    src = sample_outer(src_geom, max(0.2, 60 / estimated_scale))
    dense = sample_outer(ref_geom, 25)
    tree = cKDTree(dense)
    matrix = seed.copy()
    history = []
    for gate in (400.0, 250.0, 150.0):
        for _ in range(100):
            transformed = apply_points(src, matrix)
            d, idx = tree.query(transformed)
            mutual = cKDTree(transformed).query(dense)[1][idx] == np.arange(len(src))
            eligible = np.flatnonzero((d < gate) & mutual)
            if len(eligible) < 30:
                break
            keep = eligible[np.argsort(d[eligible])[:max(30, int(0.8 * len(eligible)))]]
            updated = similarity(src[keep], dense[idx[keep]])
            change = np.max(np.abs(updated - matrix))
            matrix = updated
            history.append(float(np.median(d[keep])))
            if change < 1e-7:
                break
    transformed = apply_points(src, matrix)
    d = tree.query(transformed)[0]
    section = _longest_circular(d < 150)
    if len(section) < 30 or np.median(d[section]) > 100:
        raise ReviewRegistration("no credible continuous shared boundary arc after landmark seed")
    ref_section = dense[tree.query(transformed[section])[1]]
    sec_length = float(np.linalg.norm(np.diff(transformed[section], axis=0), axis=1).sum())
    if sec_length < 1000:
        raise ReviewRegistration("matched boundary arc is too short to establish placement")
    return {"matrix": matrix, "model": "similarity", "history": history,
            "source_samples": src, "section_indices": section,
            "section_length_m": sec_length, "section_fraction": len(section) / len(src),
            "fit_score_m": float(np.median(d[section])),
            "landmark_seed": seed.tolist()}


def register(page_units, reference, scope, config):
    source = unary_union(page_units.geometry)
    if not source.is_valid:
        raise ReviewRegistration("source administrative union is invalid")
    ref_geom = reference["geometry"]
    if scope == "same_extent":
        chosen = _complete(source, ref_geom, config)
    elif scope == "shared_boundary":
        chosen = _shared(source, ref_geom, config, reference["fit_crs"])
    else:
        raise ReviewRegistration("no shared boundary; cannot register")
    matrix = np.asarray(chosen["matrix"])
    transformed = apply_geom(source, matrix)
    if not transformed.is_valid:
        raise ReviewRegistration("global transform produced invalid geometry")
    sample = (chosen["source_samples"][chosen["section_indices"]]
              if scope == "shared_boundary" else sample_outer(exterior(source),
              max(0.3, exterior(source).length / 2500)))
    mapped = apply_points(sample, matrix)
    ref_dense = sample_outer(exterior(ref_geom), 25)
    forward = cKDTree(ref_dense).query(mapped)[0]
    if scope == "same_extent":
        reverse = cKDTree(sample_outer(exterior(transformed), 25)).query(
            sample_outer(exterior(ref_geom), 60))[0]
    else:
        near = cKDTree(mapped).query(ref_dense)[0]
        reverse = near[near < 150]
        if len(reverse) < 10:
            raise ReviewRegistration("too few reverse matches on shared arc")
    metrics = _distance_summary(forward, reverse)
    if scope == "same_extent":
        metrics["symmetric_difference_km2"] = float(
            transformed.symmetric_difference(ref_geom).area / 1e6)
        metrics["iou"] = float(transformed.intersection(ref_geom).area /
                               transformed.union(ref_geom).area)
    else:
        metrics["shared_arc_km"] = chosen["section_length_m"] / 1000
        metrics["shared_fraction"] = chosen["section_fraction"]
        metrics["unconstrained_fraction"] = 1 - chosen["section_fraction"]
    return {"matrix": matrix, "model": chosen["model"], "fit_crs": str(reference["fit_crs"]),
            "output_crs": str(reference["output_crs"]), "stats": scale_stats(matrix),
            "metrics": metrics, "history": chosen["history"],
            "selection": {k: v for k, v in chosen.items()
                          if k not in {"matrix", "history", "source_samples", "section_indices"}}}
