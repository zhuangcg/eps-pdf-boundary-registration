"""Batch publication checks use tiny real GPKGs and no registration mock geometry."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import fitz
from shapely import affinity
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from batch import run_batch  # noqa: E402
from register import load_reference  # noqa: E402
from run import main, run  # noqa: E402


class BatchTest(unittest.TestCase):
    def test_run_cli_dispatches_batch_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "batch.yaml"
            manifest.write_text("workflow:\n  mode: batch_hierarchical\n", encoding="utf-8")
            with patch("batch.run_batch", return_value=7) as dispatch, patch.object(
                sys, "argv", ["run.py", "--config", str(manifest)]
            ):
                self.assertEqual(main(), 7)
            dispatch.assert_called_once()
            with patch.object(sys, "argv", ["run.py", "--config", str(manifest),
                                            "--intent", "same extent"]):
                with self.assertRaises(SystemExit):
                    main()

    def test_reference_filter_keeps_one_identity_with_split_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cities.gpkg"
            gpd.GeoDataFrame({"code": [1, 1, 2], "name": ["A", "A", "B"]},
                             geometry=[box(0, 0, 1, 1), box(2, 0, 3, 1),
                                       box(3, 0, 4, 1)], crs="EPSG:3857").to_file(
                                           path, layer="city", driver="GPKG")
            config = {"reference_boundary": str(path), "reference_layer": "city",
                      "reference": {"fit_crs": "EPSG:3857", "id_field": "code",
                                    "filter": {"field": "code", "value": 1}}}
            selected = load_reference(config)
            self.assertEqual(selected["selection"]["features"], 2)
            self.assertAlmostEqual(selected["geometry"].area, 2)
            config["reference"]["filter"]["value"] = 4
            with self.assertRaisesRegex(ValueError, "matched no features"):
                load_reference(config)
            config["reference"]["filter"] = {"field": "name", "value": "A"}
            self.assertEqual(load_reference(config)["selection"]["features"], 2)
            del config["reference"]["id_field"]
            with self.assertRaisesRegex(ValueError, "need reference.id_field"):
                load_reference(config)
            config["reference"]["filter"] = {"field": "missing", "value": "A"}
            with self.assertRaisesRegex(ValueError, "field is absent"):
                load_reference(config)

    @staticmethod
    def _fake_city(config, gap=False, overlap=False):
        out = Path(config["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        if (out / "conformed.gpkg").exists():
            return 0
        key = int(config["reference"]["filter"]["value"])
        x = (key - 1) * 100
        boundary = box(x, 0, x + 100, 100)
        units = [box(x - (1 if overlap and key == 2 else 0), 0, x + 50, 100),
                 box(x + 50, 0, x + (99 if gap and key == 2 else 100), 100)]
        gpd.GeoDataFrame({"admin_id": ["A001", "A002"]}, geometry=units,
                         crs="EPSG:3857").to_file(out / "conformed.gpkg",
                                                   layer="conformed_units", driver="GPKG")
        gpd.GeoDataFrame({"feature": ["reference"]}, geometry=[boundary],
                         crs="EPSG:3857").to_file(out / "registered.gpkg",
                                                   layer="reference_outline", driver="GPKG")
        return 0

    def _manifest(self, root, count=2):
        refs = root / "reference.gpkg"
        gpd.GeoDataFrame({"code": [1, 2, 3]},
                         geometry=[box(i * 100, 0, (i + 1) * 100, 100)
                                   for i in range(3)], crs="EPSG:3857").to_file(
                                       refs, layer="city", driver="GPKG")
        for i in range(count):
            (root / f"map{i + 1}.pdf").touch()
        return {"workflow": {"mode": "batch_hierarchical"},
                "parent_reference": {"path": str(refs), "layer": "city",
                                     "id_field": "code", "fit_crs": "EPSG:3857"},
                "output_dir": str(root / "output"), "work_dir": str(root / "work"),
                "cases": [{"source_map": str(root / f"map{i + 1}.pdf"),
                           "parent_id": str(i + 1)} for i in range(count)]}

    def test_subset_preview_and_full_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root)
            self.assertEqual(run_batch(manifest, root / "batch.yaml", self._fake_city), 0)
            self.assertTrue((root / "output" / "batch_preview.gpkg").is_file())
            self.assertFalse((root / "output" / "province_conformed.gpkg").exists())
            preview = gpd.read_file(root / "output" / "batch_preview.gpkg",
                                    layer="district_units")
            self.assertEqual(set(preview.parent_id), {"1", "2"})
            manifest["cases"].append({"source_map": str(root / "map3.pdf"), "parent_id": "3"})
            (root / "map3.pdf").touch()
            self.assertEqual(run_batch(manifest, root / "batch.yaml", self._fake_city), 0)
            self.assertTrue((root / "output" / "province_conformed.gpkg").is_file())

    def test_gap_and_duplicate_case_block_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root)
            manifest["cases"][1]["parent_id"] = "1"
            with self.assertRaisesRegex(ValueError, "duplicate parent_id"):
                run_batch(manifest, root / "batch.yaml", self._fake_city)
            manifest["cases"][1]["parent_id"] = "2"
            self.assertEqual(run_batch(manifest, root / "batch.yaml",
                                       lambda config: self._fake_city(config, gap=True)), 2)
            self.assertFalse((root / "output" / "batch_preview.gpkg").exists())
            report = json.loads((root / "output" / "province_qc.json").read_text())
            self.assertGreater(report["checks"]["uncovered_m2"], 0)

    def test_cross_city_overlap_blocks_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root)
            self.assertEqual(run_batch(manifest, root / "batch.yaml",
                                       lambda config: self._fake_city(config, overlap=True)), 2)
            self.assertFalse((root / "output" / "batch_preview.gpkg").exists())
            report = json.loads((root / "output" / "province_qc.json").read_text())
            self.assertGreater(report["checks"]["district_overlap_m2"], 0)

    def test_city_review_blocks_batch_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root)
            self.assertEqual(run_batch(manifest, root / "batch.yaml", lambda _: 2), 2)
            self.assertFalse((root / "output" / "province_conformed.gpkg").exists())
            self.assertFalse((root / "output" / "batch_preview.gpkg").exists())
            review = json.loads((root / "work" / "batch_review.json").read_text())
            self.assertEqual(review["status"], "city_review")

    def test_batch_parent_id_is_not_scope_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self._manifest(root)
            seen = []
            def capture(config):
                seen.append(config)
                return 2
            self.assertEqual(run_batch(manifest, root / "batch.yaml", capture), 2)
            self.assertNotIn("scope_confirmation", seen[0])
            manifest["defaults"] = {"scope_confirmation": "same extent"}
            with self.assertRaisesRegex(ValueError, "per case"):
                run_batch(manifest, root / "batch.yaml", capture)

    def test_mixed_eps_pdf_real_city_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            refs = root / "cities.gpkg"
            outline = box(0, 0, 160, 120).difference(box(140, 80, 160, 120))
            gpd.GeoDataFrame({"code": [1, 2]},
                             geometry=[outline, affinity.translate(outline, xoff=160)],
                             crs="EPSG:3857").to_file(refs, layer="city", driver="GPKG")
            eps = root / "city1.eps"
            eps.write_text("%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 200 200\n"
                           "0.7 0.8 0.2 setrgbcolor\n"
                           "newpath 20 40 moveto 100 40 lineto 100 160 lineto 20 160 lineto closepath fill\n"
                           "newpath 100 40 moveto 180 40 lineto 180 120 lineto 160 120 lineto "
                           "160 160 lineto 100 160 lineto closepath fill\n"
                           "showpage\n", encoding="ascii")
            pdf = root / "city2.pdf"
            with fitz.open() as doc:
                doc.new_page(width=200, height=200)
                page = doc.new_page(width=200, height=200)
                for rect in (fitz.Rect(20, 40, 100, 160),
                             fitz.Rect(100, 40, 160, 80),
                             fitz.Rect(100, 80, 180, 160)):
                    page.draw_rect(rect, color=None, fill=(0.7, 0.8, 0.2))
                doc.save(pdf)
            manifest = {"workflow": {"mode": "batch_hierarchical"},
                        "parent_reference": {"path": str(refs), "layer": "city",
                                             "id_field": "code", "fit_crs": "EPSG:3857"},
                        "output_dir": str(root / "out"), "work_dir": str(root / "work"),
                        "defaults": {"extraction": {"method": "fill", "min_fill_area_pt2": 20},
                                     "names": {"mode": "auto"}},
                        "cases": [{"source_map": str(eps), "parent_id": "1",
                                   "options": {"scope_confirmation": "user confirms same_extent for city 1"}},
                                  {"source_map": str(pdf), "parent_id": "2", "page": 2,
                                   "options": {"scope_confirmation": "user confirms same_extent for city 2"}}]}
            code = run_batch(manifest, root / "batch.yaml", run)
            self.assertEqual(code, 0, (root / "work" / "2" / "review.json").read_text(
                encoding="utf-8") if code and (root / "work" / "2" / "review.json").exists()
                else "")
            self.assertTrue((root / "out" / "province_conformed.gpkg").exists())
            for key in ("1", "2"):
                self.assertTrue((root / "out" / "cities" / key / "registered.gpkg").exists())
                self.assertTrue((root / "out" / "cities" / key / "conformed.gpkg").exists())


if __name__ == "__main__":
    unittest.main()
