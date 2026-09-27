"""Phase L: assert the delivery directory matches the output contract.

Fails (exit 1) when the directory holds a file the contract does not list, lacks one it
does, leaves process residue behind, or repeats a layer across two vector files. Run it as
the last step of every delivery.

    python check_output_manifest.py <out_dir> --config run.yaml
    python check_output_manifest.py <out_dir> --mode R
    python check_output_manifest.py <out_dir> --mode C
    python check_output_manifest.py <out_dir> --files registered.gpkg qc.json ...
    python check_output_manifest.py --self-test
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

# The contract, by name. A delivery is a handful of files; if it needs more, the extras
# are either duplicates of something already here or process residue.
CONTRACT = {
    "R": {"registered.gpkg", "qc.json", "overlay.png", "run.log"},
    "C": {"conformed.gpkg", "conformance_qc.json"},
}
RESIDUE_PATTERNS = [
    "*_run[0-9]*", "*_run*.log", "*.log.*", "preview*", "*.tmp", "*~",
    ".ipynb_checkpoints", "__pycache__", "*.cpg", "*.sbn", "*.sbx", "*.quicksheet",
]
# <name>_v2.ext / <name>_final.ext / <name>(2).ext - the shapes reruns leave behind
RESIDUE_RE = re.compile(r"(?:_v\d+|_final|_old|_backup|\(\d+\))\.[A-Za-z0-9]+$")


def _layers_of(path: Path) -> set[str]:
    """Read the layers from GPKG metadata; unreadable files fail the contract."""
    with closing(sqlite3.connect(path)) as db:
        if db.execute("PRAGMA application_id").fetchone()[0] != 0x47504B47:
            raise ValueError("not a GeoPackage")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        layers = {row[0] for row in db.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'")}
        if not layers or any(not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (layer,)
        ).fetchone() for layer in layers):
            raise ValueError("no readable feature layers")
        return layers


def check(out_dir: Path, expected: set[str], allow: set[str]) -> list[tuple[str, bool, str]]:
    findings: list[tuple[str, bool, str]] = []
    present = {p.name for p in out_dir.iterdir() if p.is_file()}
    dirs = {p.name for p in out_dir.iterdir() if p.is_dir()}

    missing = sorted(expected - present)
    extra = sorted(present - expected - allow)
    findings.append(("every contracted file is present", not missing,
                     "missing: " + ", ".join(missing) if missing else
                     f"{len(expected)} files"))
    findings.append(("no unlisted file in the delivery", not extra,
                     "unlisted: " + ", ".join(extra) if extra else "nothing extra"))

    residue = sorted(n for n in present
                     if any(fnmatch.fnmatch(n, pat) for pat in RESIDUE_PATTERNS)
                     or RESIDUE_RE.search(n))
    findings.append(("no process residue", not residue,
                     "residue: " + ", ".join(residue) if residue else "clean"))

    for d in sorted(dirs):
        findings.append((f"no subdirectory '{d}' in delivery", False,
                         "put working artefacts beside the delivery directory in work/"))

    # A vector file is redundant when every layer it holds already ships in another file.
    # Two deliverables sharing one reference layer is fine; a whole file for that layer is
    # the duplication that bites, because the two copies can drift apart.
    layers_of, unreadable = {}, []
    for name in sorted(present):
        if not name.endswith(".gpkg"):
            continue
        try:
            got = _layers_of(out_dir / name)
        except (sqlite3.DatabaseError, OSError, ValueError) as exc:
            unreadable.append(f"{name}: {exc}")
            continue
        layers_of[name] = got

    detail = ("unreadable: " + ", ".join(unreadable) + "; ") if unreadable else ""
    dupes = [f"{n} (all its layers also present in "
             f"{', '.join(sorted(o for o in layers_of if o != n and layers_of[n] <= layers_of[o]))})"
             for n in sorted(layers_of)
             if any(n != o and layers_of[n] <= layers_of[o] for o in layers_of)]
    findings.append(("no vector file whose layers already ship elsewhere", not dupes and not unreadable,
                     detail + (f"{len(layers_of)} vector files, "
                               f"{len(set().union(*layers_of.values())) if layers_of else 0} distinct layers"
                               if not dupes else "redundant: " + "; ".join(dupes))))

    return findings


def self_test() -> int:
    """Use real GPKGs to check the file and layer rules."""
    import geopandas as gpd
    from shapely.geometry import Point

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        frame = gpd.GeoDataFrame({"id": [1]}, geometry=[Point(0, 0)], crs="EPSG:3857")
        frame.to_file(d / "registered.gpkg", layer="reference_city_outline", driver="GPKG")
        frame.to_file(d / "reference_city_outline.gpkg", layer="reference_city_outline", driver="GPKG")
        for name in ["qc.json", "overlay.png", "run.log", "qc.csv", "apply_export_run2.log"]:
            (d / name).write_text("x", encoding="utf-8")
        (d / "notes.txt.tmp").write_text("x", encoding="utf-8")
        findings = check(d, CONTRACT["R"], set())
        print("\n".join(f"  {'FAIL' if not ok else 'ok  '} {name}: {msg}"
                        for name, ok, msg in findings))
        caught = {name for name, ok, _ in findings if not ok}
        passed = {"no unlisted file in the delivery", "no process residue",
                  "no vector file whose layers already ship elsewhere"} <= caught
        print("\nSELF-TEST PASS (expected violations caught)" if passed else "\nSELF-TEST FAIL")
        return 0 if passed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out_dir", nargs="?", type=Path)
    ap.add_argument("--mode", choices=["R", "C"], default="R",
                    help="R registers only; C additionally delivers the conformed variant")
    ap.add_argument("--files", nargs="*", help="override the contract with exact filenames")
    ap.add_argument("--config", type=Path, help="read delivery filenames and mode from YAML")
    ap.add_argument("--allow", nargs="*", default=[],
                    help="extra filenames explicitly permitted")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        return self_test()
    if a.out_dir is None:
        ap.error("out_dir is required unless --self-test")

    if a.config:
        import yaml
        from deliver import DEFAULT_C, DEFAULT_FILES
        delivery = yaml.safe_load(a.config.read_text(encoding="utf-8"))["delivery"]
        if delivery["mode"] not in {"R", "C"}:
            ap.error("delivery.mode must be R or C")
        filenames = list({**DEFAULT_FILES, **(delivery.get("files") or {})}.values())
        if delivery["mode"] == "C":
            filenames += list({**DEFAULT_C, **(delivery.get("conformed_files") or {})}.values())
        expected = set(filenames)
        if len(expected) != len(filenames):
            ap.error("delivery filenames must be unique")
    else:
        expected = set(a.files) if a.files else set(CONTRACT["R"] | (CONTRACT["C"] if a.mode == "C" else set()))
    findings = check(a.out_dir, expected, set(a.allow))
    ok_all = True
    for name, ok, msg in findings:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  {msg}")
        ok_all &= ok
    if not ok_all:
        print("\nContract violated. Either delete the offending file or record why the "
              "contract must grow - do not leave the directory as it is.")
    print("\nALL CHECKS PASS" if ok_all else "MANIFEST FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
