"""Regression checks for scope, filled bands, and ambiguous registration."""
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import fitz
import geopandas as gpd
from shapely import affinity
from shapely.geometry import Polygon, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extract import ReviewExtraction, extract  # noqa: E402
from deliver import ReviewConformance, _conform  # noqa: E402
from register import load_reference, register  # noqa: E402
from run import _reference_hash, run  # noqa: E402
from scope import ReviewScope, resolve  # noqa: E402


class BoundaryGuardsTest(unittest.TestCase):
    def test_scope_confirmation_and_multilayer_reference(self):
        intent = "提取广东省地级市边界，使用广东省级边界作为参考；图面与参考同范围"
        self.assertEqual(resolve({"source_map": "map.pdf", "admin_level": "city",
                                  "source_scope": "same_extent", "user_intent": intent})
                         ["admin_level"], "city")
        mismatch = {"source_map": "map.pdf", "admin_level": "district",
                    "source_scope": "same_extent"}
        with self.assertRaises(ReviewScope):
            resolve(mismatch, ocr_words=["南湖街道", "东门街道"])
        mismatch["scope_review"] = {"admin_level_conflict":
                                    "district fill faces reviewed; street labels are secondary"}
        self.assertEqual(resolve(mismatch, ocr_words=["南湖街道", "东门街道"])
                         ["hints"]["admin_level_conflict_reviewed"],
                         mismatch["scope_review"]["admin_level_conflict"])
        config = {"source_map": "map.pdf", "admin_level": "city", "source_scope": "auto",
                  "scope_confirmation": "用户确认图面与参考同范围"}
        self.assertEqual(resolve(config)["source_scope"], "same_extent")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reference.gpkg"
            frame = gpd.GeoDataFrame(geometry=[box(0, 0, 10, 10)], crs="EPSG:3857")
            frame.to_file(path, layer="first", driver="GPKG")
            frame.to_file(path, layer="second", driver="GPKG")
            with self.assertRaises(ReviewScope):
                load_reference({"reference_boundary": str(path)})
            selected = load_reference({"reference_boundary": str(path),
                                       "reference_layer": "second"})
            self.assertEqual(selected["evidence"]["layer"], "second")
            invalid = Path(tmp) / "invalid.gpkg"
            gpd.GeoDataFrame(geometry=[Polygon([(0, 0), (2, 2), (0, 2),
                                                (2, 0)])], crs="EPSG:3857").to_file(
                invalid, driver="GPKG")
            with self.assertRaisesRegex(ReviewScope, "repair changes area"):
                load_reference({"reference_boundary": str(invalid)})
            shp = Path(tmp) / "boundary.shp"
            shp.write_bytes(b"geometry")
            prj = shp.with_suffix(".prj")
            prj.write_text("CRS A", encoding="utf-8")
            before = _reference_hash(shp)
            prj.write_text("CRS B", encoding="utf-8")
            self.assertNotEqual(before, _reference_hash(shp))

    def test_band_inner_ring_and_open_band_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ring = root / "ring.pdf"
            with fitz.open() as doc:
                page = doc.new_page(width=200, height=200)
                shape = page.new_shape()
                shape.draw_rect(fitz.Rect(20, 20, 180, 180))
                shape.draw_rect(fitz.Rect(24, 24, 176, 176))
                shape.finish(color=None, fill=(0.5, 0.4, 0.3), even_odd=True)
                shape.commit()
                doc.save(ring)
            config = {"source_map": str(ring), "work_dir": str(root / "ring_work"),
                      "extraction": {"method": "fill", "min_fill_area_pt2": 20}}
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="'crs' was not provided")
                result = extract(config)
            self.assertEqual(result["boundary_source"], "band_inner")
            self.assertAlmostEqual(gpd.read_file(result["page_units_gpkg"]).area.iloc[0], 152**2)

            ribbon = root / "ribbon.pdf"
            with fitz.open() as doc:
                page = doc.new_page(width=240, height=200)
                shape = page.new_shape()
                shape.draw_polyline([(20, 20), (22, 20), (22, 175), (218, 175),
                                     (218, 20), (220, 20), (220, 177), (20, 177),
                                     (20, 20)])
                shape.finish(color=None, fill=(0.5, 0.4, 0.3), closePath=True)
                shape.commit()
                doc.save(ribbon)
            config["source_map"] = str(ribbon)
            config["work_dir"] = str(root / "ribbon_work")
            with self.assertRaises(ReviewExtraction):
                extract(config)
            self.assertEqual(len(list((root / "ribbon_work").glob("review_extraction_*.png"))), 1)

    def test_reviewed_fill_excludes_adjacent_band(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "map.pdf"
            with fitz.open() as doc:
                page = doc.new_page(width=240, height=200)
                page.draw_rect(fitz.Rect(25, 25, 215, 170), color=None,
                               fill=(0.2, 0.7, 0.4))
                shape = page.new_shape()
                shape.draw_polyline([(20, 20), (22, 20), (22, 175), (218, 175),
                                     (218, 20), (220, 20), (220, 177), (20, 177),
                                     (20, 20)])
                shape.finish(color=None, fill=(0.5, 0.4, 0.3), closePath=True)
                shape.commit()
                doc.save(pdf)
            config = {"source_map": str(pdf), "work_dir": str(root / "review"),
                      "extraction": {"method": "fill", "min_fill_area_pt2": 20}}
            with self.assertRaises(ReviewExtraction):
                extract(config)
            config["work_dir"] = str(root / "work")
            config["extraction"]["keep_colours_rgb"] = [[51, 178, 102]]
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="'crs' was not provided")
                result = extract(config)
            self.assertEqual(result["admin_units"], 1)
            self.assertEqual(result["boundary_source"], "administrative_fill")
            self.assertEqual(result["excluded_band_drawings"], [1])

    def test_small_island_with_two_possible_parent_faces_needs_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "islands.pdf"
            with fitz.open() as doc:
                page = doc.new_page(width=220, height=160)
                shape = page.new_shape()
                for rect in (fitz.Rect(20, 20, 70, 90),
                             fitz.Rect(140, 20, 190, 90),
                             fitz.Rect(105, 110, 110, 115)):
                    shape.draw_rect(rect)
                shape.finish(color=None, fill=(0.2, 0.7, 0.4))
                shape.commit()
                doc.save(pdf)
            config = {"source_map": str(pdf), "work_dir": str(root / "work"),
                      "extraction": {"method": "fill", "min_fill_area_pt2": 100}}
            with self.assertRaisesRegex(ReviewExtraction, "multiple possible parent units"):
                extract(config)
            self.assertFalse(list((root / "work").glob("extraction_*/page_units.gpkg")))

    def test_whole_extent_and_orientation_gate(self):
        shape = Polygon([(0, 0), (100, 0), (100, 30), (60, 30),
                         (60, 80), (0, 80)])
        source = gpd.GeoDataFrame(geometry=[shape])
        right = affinity.affine_transform(shape, [10, 0, 0, 10, 1000, 2000])
        reference = {"geometry": right, "fit_crs": "EPSG:3857",
                     "output_crs": "EPSG:3857"}
        good = register(source, reference, "same_extent", {})
        self.assertEqual(good["gate"]["status"], "pass")
        reference["geometry"] = box(1000, 2000, 2000, 2800)
        wrong = register(source, reference, "same_extent", {})
        self.assertEqual(wrong["gate"]["status"], "review")
        source = gpd.GeoDataFrame(geometry=[box(0, 0, 100, 80)])
        symmetric = register(source, reference, "same_extent", {})
        self.assertIn("multiple distinct credible transforms", symmetric["gate"]["reasons"])

    def test_mode_c_does_not_guess_owner_of_uncovered_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            units = gpd.GeoDataFrame({"admin_id": ["A1", "A2"]},
                                     geometry=[box(0, 0, 4, 10), box(6, 0, 10, 10)],
                                     crs="EPSG:3857")
            with self.assertRaisesRegex(ReviewConformance, "no unique"):
                _conform(units, box(0, 0, 10, 10), units.crs, Path(tmp),
                         {"conformed_gpkg": "conformed.gpkg"})
            self.assertFalse((Path(tmp) / "conformed.gpkg").exists())

    def test_wrong_reference_stops_before_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "map.pdf"
            with fitz.open() as doc:
                page = doc.new_page(width=200, height=200)
                shape = page.new_shape()
                shape.draw_polyline([(20, 20), (120, 20), (120, 50),
                                     (80, 50), (80, 100), (20, 100), (20, 20)])
                shape.finish(color=None, fill=(0.2, 0.7, 0.4), closePath=True)
                shape.commit()
                doc.save(pdf)
            reference = root / "wrong.gpkg"
            gpd.GeoDataFrame(geometry=[box(1000, 2000, 2000, 2800)],
                             crs="EPSG:3857").to_file(reference, driver="GPKG")
            config = {"source_map": str(pdf), "reference_boundary": str(reference),
                      "admin_level": "city", "source_scope": "same_extent",
                      "work_dir": str(root / "work"), "output_dir": str(root / "output"),
                      "names": {"mode": "auto"}, "delivery": {"mode": "R"},
                      "extraction": {"method": "fill", "min_fill_area_pt2": 20}}
            self.assertEqual(run(config), 2)
            self.assertIn('"status": "REVIEW_SCOPE"',
                          (root / "work" / "review.json").read_text(encoding="utf-8"))
            config["scope_confirmation"] = "用户确认图面与参考同范围"
            self.assertEqual(run(config), 2)
            self.assertFalse((root / "output").exists())
            self.assertTrue((root / "work" / "scope_comparison.png").is_file())
            self.assertTrue((root / "work" / "review_registration.png").is_file())


if __name__ == "__main__":
    unittest.main()
