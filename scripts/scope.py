"""Resolve administrative level and geometric relationship before registration."""
from __future__ import annotations

import re
from pathlib import Path


class ReviewScope(ValueError):
    """Prompt and source evidence do not establish a unique run type."""


class NoCommonBoundary(ValueError):
    """A containing reference outline cannot locate an interior source by itself."""


LEVEL_WORDS = {
    "street": r"街道|乡镇|street|township",
    "district": r"区级|区界|各区|区划|district|borough",
    "city": r"地级市|城市边界|市级|市界|市边界|各市|city|cities",
    "province": r"省级|省界|各省|province|state",
    "country": r"国家边界|国界|各国|country|nation",
}


def matching_region(config, reference_evidence, page_words=()):
    """A matching place label is a scope clue, never geometric proof."""
    if config.get("scope_confirmation"):
        return {"status": "user_confirmed", "match": None}
    source_text = " ".join([Path(config["source_map"]).stem,
                            str(config.get("user_intent") or ""), *map(str, page_words)]).lower()
    reference_text = " ".join([Path(config["reference_boundary"]).stem,
                               *(name for values in reference_evidence["name_samples"].values()
                                 for name in values)]).lower()
    chinese = re.findall(r"[\u4e00-\u9fff]{2,8}?(?:省|市|县|区)", reference_text)
    english = re.findall(r"[a-z]{5,}", reference_text)
    generic = {"行政区", "中心区", "市辖区", "城区", "地图", "boundary", "reference",
               "district", "province", "cities", "county", "shapefile"}
    match = next((word for word in [*chinese, *english]
                  if word not in generic and word in source_text), None)
    return {"status": "matched_label" if match else "review", "match": match}


def _intent_level(text):
    target = re.search(r"(?:提取|生成|输出|获取|制作)\s*([^，,；;。]+)", text)
    if target:
        text = target.group(1)
    else:
        text = re.split(r"(?:参考|对照)", text, maxsplit=1)[0]
    matches = [key for key, pattern in LEVEL_WORDS.items()
               if re.search(pattern, text, re.IGNORECASE)]
    return matches[0] if matches else None  # the target is the finest mentioned level


def _intent_scope(text):
    if re.search(r"无共同边界|不接壤|内陆城市|内部城市|no.common.boundary|interior.city", text, re.I):
        return "no_common_boundary"
    if re.search(r"共线|接壤|沿.*[市国]界|shared.arc|shared.boundary", text, re.I):
        return "shared_boundary"
    if re.search(r"同范围|完整.*[市国].*图|全国.*图|全市.*图|same.extent|whole.country", text, re.I):
        return "same_extent"
    return None


def _body_level(words):
    text = [str(w).strip() for w in words]
    counts = {
        "street": sum(w.endswith(("街道", "镇", "乡")) for w in text),
        "district": sum(w.endswith(("区", "县")) and len(w) <= 9 for w in text),
        "city": sum(w.endswith("市") and len(w) <= 9 for w in text),
        "province": sum(w.endswith(("省", "自治区")) for w in text),
    }
    ranked = sorted(counts.items(), key=lambda row: -row[1])
    return ranked[0][0] if ranked[0][1] >= 2 and ranked[0][1] > ranked[1][1] else None


def resolve(config: dict, native_words=(), ocr_words=()) -> dict:
    """Prompt/config win; filename and body labels are hints, never silent overrides."""
    intent = str(config.get("user_intent") or "")
    confirmation = config.get("scope_confirmation")
    review = config.get("scope_review") or {}
    if not isinstance(review, dict):
        raise ValueError("scope_review must be a mapping")
    level_review = review.get("admin_level_conflict")
    if level_review is not None and (not isinstance(level_review, str) or
                                     not level_review.strip()):
        raise ValueError("scope_review.admin_level_conflict must explain the map evidence")
    if confirmation is not None and (not isinstance(confirmation, str) or not confirmation.strip()):
        raise ValueError("scope_confirmation must be a nonempty record of the user's answer")
    level = config.get("admin_level", "auto")
    if level not in {None, "auto", *LEVEL_WORDS}:
        raise ValueError("admin_level must be auto, street, district, city, province, or country")
    scope = config.get("source_scope", "auto")
    if scope == "partial_parent":
        scope = "shared_boundary"
    if scope not in {"auto", "same_extent", "shared_boundary", "no_common_boundary"}:
        raise ValueError("source_scope must be auto, same_extent, shared_boundary, or no_common_boundary")
    prompt_level, prompt_scope = _intent_level(intent), _intent_scope(intent)
    confirmed_scope = _intent_scope(confirmation) if confirmation else None
    if confirmation and not confirmed_scope:
        raise ReviewScope("scope_confirmation must state same_extent, shared_boundary, or no_common_boundary")
    if prompt_scope and confirmed_scope and prompt_scope != confirmed_scope:
        raise ReviewScope("scope_confirmation conflicts with user_intent")
    filename = Path(config.get("source_map", "")).stem
    hints = {"filename": filename, "filename_level": _intent_level(filename),
             "body_level": _body_level([*native_words, *ocr_words]),
             "prompt_level": prompt_level, "prompt_scope": prompt_scope,
             "confirmed_scope": confirmed_scope}
    if level not in (None, "auto") and prompt_level and level != prompt_level:
        raise ReviewScope(f"admin_level={level} conflicts with user_intent={prompt_level}")
    if scope != "auto" and prompt_scope and scope != prompt_scope:
        raise ReviewScope(f"source_scope={scope} conflicts with user_intent={prompt_scope}")
    if scope != "auto" and confirmed_scope and scope != confirmed_scope:
        raise ReviewScope(f"source_scope={scope} conflicts with scope_confirmation={confirmed_scope}")
    if hints["body_level"] and (level not in (None, "auto") or prompt_level):
        declared = level if level not in (None, "auto") else prompt_level
        if declared != hints["body_level"]:
            if not level_review:
                raise ReviewScope(f"declared admin_level={declared} conflicts with map-body labels={hints['body_level']}")
            hints["admin_level_conflict_reviewed"] = level_review
    level = level if level not in (None, "auto") else (prompt_level or hints["body_level"]
                                                      or hints["filename_level"])
    scope = scope if scope != "auto" else (confirmed_scope or prompt_scope)
    if scope == "no_common_boundary":
        raise NoCommonBoundary(
            "源图与参考范围没有共同边界；仅凭上级边界无法定位内部城市，请提供共同边界或其他定位依据")
    if not level or not scope:
        raise ReviewScope(f"administrative level or boundary relationship uncertain; hints={hints}")
    evidence = {
        "admin_level": "config" if config.get("admin_level", "auto") not in (None, "auto")
                       else "user_intent" if prompt_level else "map_body_labels" if hints["body_level"]
                       else "filename",
        "source_scope": "scope_confirmation" if confirmed_scope else
                        "config" if config.get("source_scope", "auto") != "auto"
                        else "user_intent",
    }
    result = {"admin_level": level, "source_scope": scope,
              "evidence": evidence, "hints": hints,
              "scope_confirmation": confirmation}
    return result
