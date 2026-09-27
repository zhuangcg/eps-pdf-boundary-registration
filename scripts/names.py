"""Read map labels once, then attach only map-backed names to page polygons."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import fitz
import geopandas as gpd
from shapely.geometry import Point


def _label_key(census, dpi, frame):
    geometry = hashlib.sha256(b"".join(g.wkb for g in frame.geometry)).hexdigest()[:12]
    raw = f"{census['stamp']['pdf_sha256']}:{dpi}:{geometry}:rapidocr-subprocess-v3"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def scan(census: dict, config: dict, frame: gpd.GeoDataFrame) -> dict:
    work = Path(config["work_dir"])
    dpi = int(config.get("names", {}).get("outlined_text_ocr_dpi", 300))
    if dpi < 72 or dpi > 600:
        raise ValueError("names.outlined_text_ocr_dpi must be in 72..600")
    key = _label_key(census, dpi, frame)
    path = work / f"labels_{key}.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    with fitz.open(census["pdf"]) as doc:
        page = doc[0]
        words = page.get_text("words")
        native = [{"raw_text": str(w[4]), "confidence": 1.0, "source": "native_text",
                   "page_box": [float(w[0]), float(w[1]), float(w[2]), float(w[3])],
                   "page_x_pt": float((w[0] + w[2]) / 2),
                   "page_y_pt": float((w[1] + w[3]) / 2)} for w in words]
        level = config.get("admin_level", "auto")
        levels = [level] if level not in (None, "auto") else [
            "street", "district", "city", "province", "country"]
        covered = {i for row in native
                   if any(_candidate(row["raw_text"], candidate) for candidate in levels)
                   for i, geom in enumerate(frame.geometry)
                   if geom.covers(Point(row["page_x_pt"], row["page_y_pt"]))}
        if len(covered) == len(frame):
            result = {"status": "native", "dpi": None, "labels": native,
                      "source_sha256": census["stamp"]["pdf_sha256"]}
        else:
            command = [sys.executable, str(Path(__file__).with_name("ocr_page.py")),
                       str(census["pdf"]), str(dpi)]
            attempt = subprocess.run(command, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace")
            if attempt.returncode:
                result = {"status": "ocr_unavailable", "dpi": dpi, "labels": native,
                          "source_sha256": census["stamp"]["pdf_sha256"],
                          "error": attempt.stderr[-1000:]}
            else:
                result = {"status": "native+ocr" if native else "ocr", "dpi": dpi,
                          "labels": [*native, *json.loads(attempt.stdout)],
                          "source_sha256": census["stamp"]["pdf_sha256"]}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _candidate(text: str, level: str) -> bool:
    text = text.strip()
    patterns = {
        "street": r"^[\u4e00-\u9fff]{1,8}街道$",
        "district": r"^[\u4e00-\u9fff]{1,8}(?:区|县|新区)$",
        "city": r"^[\u4e00-\u9fff]{1,8}市$",
        "province": r"^[\u4e00-\u9fff]{1,8}(?:省|自治区)$",
        "country": r"^[\u4e00-\u9fff]{1,10}(?:国|共和国)$",
    }
    return bool(re.fullmatch(patterns.get(level, r"(?!)"), text))


def _crop(pdf: Path, work: Path, admin_id: str, point: tuple[float, float], box=None) -> Path:
    folder = work / "name_crops"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{admin_id}.png"
    if not path.is_file():
        with fitz.open(pdf) as doc:
            page = doc[0]
            x, y = point
            clip = (fitz.Rect(box) if box else fitz.Rect(x - 45, y - 22, x + 45, y + 22)) & page.rect
            page.get_pixmap(dpi=250, clip=clip, alpha=False).save(path)
    return path


def attach(frame: gpd.GeoDataFrame, scan_result: dict, config: dict, census: dict,
           admin_level: str) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame | None, dict]:
    """Return named page polygons, accepted label points, and a naming QC record."""
    frame = frame.copy()
    labels = scan_result["labels"]
    reviewed = config.get("names", {}).get("reviewed_labels", [])
    if config.get("names", {}).get("mode", "auto") == "required" and not (labels or reviewed):
        raise ValueError("names.mode=required but the page contains no readable labels")
    assigned: dict[str, list[dict]] = defaultdict(list)
    for row in labels:
        if not _candidate(row["raw_text"], admin_level):
            continue
        point = Point(row["page_x_pt"], row["page_y_pt"])
        hits = frame[frame.geometry.covers(point)]
        if len(hits) == 1:
            assigned[str(hits.iloc[0]["admin_id"])].append(row)
    review_by_id = {}
    for row in reviewed:
        admin_id = str(row["admin_id"])
        match = frame[frame.admin_id == admin_id]
        if len(match) != 1:
            raise ValueError(f"reviewed label references unknown admin_id {admin_id}")
        point = tuple(map(float, row["page_pt"]))
        if not match.geometry.iloc[0].buffer(1).covers(Point(point)):
            raise ValueError(f"reviewed label for {admin_id} is outside its polygon")
        if not row.get("name") or not row.get("evidence"):
            raise ValueError("reviewed_labels require name, page_pt and evidence")
        review_by_id[admin_id] = {**row, "crop": str(_crop(
            Path(census["pdf"]), Path(config["work_dir"]), admin_id, point,
            row.get("crop_box_pt")))}
    name_rows, label_rows = [], []
    for _, feature in frame.iterrows():
        admin_id = str(feature.admin_id)
        hit = assigned.get(admin_id, [])
        review = review_by_id.get(admin_id)
        if review:
            name, status, source = review["name"], "reviewed", "visual_crop"
            label_rows.append({"admin_id": admin_id, "raw_text": review.get("raw_text", ""),
                               "accepted_text": name, "source": source,
                               "evidence": review["evidence"], "crop": review["crop"],
                               "confidence": None, "geometry": Point(*review["page_pt"])})
        elif len({row["raw_text"] for row in hit}) == 1 and hit:
            row = max(hit, key=lambda r: r["confidence"])
            name, status, source = row["raw_text"], "accepted", row["source"]
            label_rows.append({"admin_id": admin_id, "raw_text": row["raw_text"],
                               "accepted_text": name, "source": source, "evidence": "page annotation",
                               "crop": None, "confidence": row["confidence"],
                               "geometry": Point(row["page_x_pt"], row["page_y_pt"])})
        elif hit:
            name, status, source = None, "conflict", None
        else:
            name, status, source = None, ("ocr_unavailable" if scan_result["status"] ==
                                          "ocr_unavailable" else "not_found"), None
        name_rows.append((name, status, source))
    frame["admin_name"] = [r[0] for r in name_rows]
    frame["name_status"] = [r[1] for r in name_rows]
    frame["name_source"] = [r[2] for r in name_rows]
    label_frame = (gpd.GeoDataFrame(label_rows, geometry="geometry") if label_rows else None)
    named = int(frame.admin_name.notna().sum())
    qc = {"scan_status": scan_result["status"], "raw_label_count": len(labels),
          "named_units": named, "total_units": len(frame),
          "status": "complete" if named == len(frame) else
                    "not_checked" if scan_result["status"] == "ocr_unavailable" else
                    "no_labels_found" if not labels and not reviewed else
                    "incomplete",
          "unresolved_admin_ids": list(frame.loc[frame.admin_name.isna(), "admin_id"])}
    if qc["status"] == "no_labels_found":
        qc["message"] = "未发现图面名称 / no map names found"
    elif qc["status"] == "not_checked":
        qc["message"] = "OCR 未完成，图面名称尚未核查 / map names not checked"
    if config.get("names", {}).get("mode", "auto") == "required" and named != len(frame):
        raise ValueError(f"names.mode=required: only {named}/{len(frame)} map-backed names")
    return frame, label_frame, qc
