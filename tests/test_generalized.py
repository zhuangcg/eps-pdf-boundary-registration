"""Small EPS checks for fill/line routing, missing names, and early refusal."""
import sys
import json
import tempfile
import unittest
import warnings
from pathlib import Path

import geopandas as gpd
import pyogrio
import fitz
from shapely.geometry import Polygon, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extract import ReviewExtraction, extract  # noqa: E402
from run import run  # noqa: E402
from scope import NoCommonBoundary, ReviewScope, resolve  # noqa: E402
from source import inspect  # noqa: E402
from names import scan  # noqa: E402


HEADER = "%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 200 200\n"
LEFT = "newpath 20 40 moveto 100 40 lineto 100 160 lineto 20 160 lineto closepath "
RIGHT = "newpath 100 40 moveto 180 40 lineto 180 160 lineto 100 160 lineto closepath "


def eps(root, body):
    path = root / "map.eps"
    path.write_text(HEADER + body + "\nshowpage\n", encoding="ascii")
    return path


class GeneralizedWorkflowTest(unittest.TestCase):
    def test_native_title_only_still_triggers_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "map.pdf"
            with fitz.open() as doc:
                page = doc.new_page(width=200, height=200)
                page.insert_text((10, 15), "Old title")
                page.draw_rect(fitz.Rect(20, 40, 180, 160), color=(0, 0, 0))
                doc.save(pdf)
            census = inspect(pdf, root / "work")
            frame = gpd.GeoDataFrame(geometry=[box(20, 40, 180, 160)])
            found = scan(census, {"work_dir": str(root / "work"),
                                  "admin_level": "district"}, frame)
            self.assertNotEqual(found["status"], "native")
            self.assertTrue(any(row["raw_text"] == "Old" for row in found["labels"]))
            self.assertEqual(found, scan(census, {"work_dir": str(root / "work"),
                                                  "admin_level": "district"}, frame))

    def test_pure_fill_and_mixed_strokes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = eps(root, "0.7 0.8 0.2 setrgbcolor\n" + LEFT + "fill\n" + RIGHT + "fill")
            config = {"source_map": str(source), "work_dir": str(root / "fill"),
                      "extraction": {"method": "auto", "min_fill_area_pt2": 20}}
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="'crs' was not provided")
                result = extract(config)
            self.assertEqual((result["method"], result["admin_units"]), ("fill", 2))
            config["work_dir"] = str(root / "review_same_colour")
            config["extraction"]["keep_colours_rgb"] = [[179, 204, 51]]
            with self.assertRaises(ReviewExtraction):
                extract(config)
            del config["extraction"]["keep_colours_rgb"]

            source = eps(root, "0 0.5 1 setrgbcolor\n"
                         "newpath 110 50 moveto 130 50 lineto 130 70 lineto 110 70 lineto closepath fill\n"
                         "0 0 0 setrgbcolor 1 setlinewidth\n" + LEFT + "stroke\n" + RIGHT +
                         "stroke\n0.6 0.6 0.6 setrgbcolor newpath 0 100 moveto 200 100 lineto stroke")
            config["work_dir"] = str(root / "mixed")
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="'crs' was not provided")
                result = extract(config)
            self.assertEqual((result["method"], result["admin_units"]), ("line", 2))

    def test_gap_and_multiple_stroke_networks_need_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = eps(root, "0 0 0 setrgbcolor 1 setlinewidth\n"
                         "newpath 20 40 moveto 180 40 lineto 180 160 lineto 20 160 lineto "
                         "20 40.4 lineto stroke")
            config = {"source_map": str(source), "work_dir": str(root / "gap"),
                      "extraction": {"method": "line", "min_fill_area_pt2": 20}}
            with self.assertRaises(ReviewExtraction):
                extract(config)
            config["extraction"]["snap_tolerance_pt"] = 0.5
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="'crs' was not provided")
                closed = extract(config)
            self.assertEqual(closed["admin_units"], 1)
            self.assertEqual(len(closed["bridges"]), 1)

            source = eps(root, "0 0 0 setrgbcolor\n" + LEFT + "stroke\n"
                         "0 0 1 setrgbcolor\n" + RIGHT + "stroke")
            config = {"source_map": str(source), "work_dir": str(root / "ambiguous"),
                      "extraction": {"method": "auto", "min_fill_area_pt2": 20}}
            with self.assertRaises(ReviewExtraction):
                extract(config)
            self.assertEqual(len(list((root / "ambiguous").glob("review_extraction_*.png"))), 1)

    def test_no_common_boundary_stops_before_source_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {"source_map": str(root / "missing.eps"),
                      "reference_boundary": str(root / "missing.gpkg"),
                      "admin_level": "city", "source_scope": "no_common_boundary",
                      "work_dir": str(root / "work"), "output_dir": str(root / "output"),
                      "names": {"mode": "auto"}, "delivery": {"mode": "R"}}
            with self.assertRaises(NoCommonBoundary):
                resolve(config)
            self.assertEqual(run(config), 2)
            self.assertFalse((root / "output").exists())
            config["source_scope"] = "auto"
            config["user_intent"] = "内陆城市边界只有国界参考，没有共同边界"
            self.assertEqual(run(config), 2)
            self.assertFalse((root / "output").exists())
            with self.assertRaises(ReviewScope):
                resolve({"source_map": "map.eps", "admin_level": "district",
                         "source_scope": "same_extent", "user_intent": "提取街道边界"},
                        ocr_words=["南湖街道", "东门街道"])

    def test_country_outline_with_unlabelled_internal_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            right = ("newpath 100 40 moveto 180 40 lineto 180 100 lineto "
                     "160 100 lineto 160 160 lineto 100 160 lineto closepath ")
            source = eps(root, "0 0 0 setrgbcolor 1 setlinewidth\n" +
                         LEFT + "stroke\n" + right + "stroke")
            reference = root / "country.gpkg"
            outline = Polygon([(1200, 2400), (2800, 2400), (2800, 3000),
                               (2600, 3000), (2600, 3600), (1200, 3600)])
            gpd.GeoDataFrame({"id": [1]}, geometry=[outline],
                             crs="EPSG:32649").to_file(reference, layer="boundary", driver="GPKG")
            config = {"source_map": str(source), "reference_boundary": str(reference),
                      "reference_layer": "boundary", "admin_level": "city",
                      "source_scope": "same_extent",
                      "scope_confirmation": "用户确认图面与参考同范围",
                      "work_dir": str(root / "work"),
                      "output_dir": str(root / "output"), "reference": {"fit_crs": "EPSG:32649"},
                      "delivery": {"mode": "R"}, "names": {"mode": "auto"},
                      "extraction": {"method": "auto", "min_fill_area_pt2": 20}}
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="'crs' was not provided")
                self.assertEqual(run(config), 0)
            delivered = gpd.read_file(root / "output" / "registered.gpkg",
                                      layer="administrative_units")
            self.assertEqual(len(delivered), 2)
            self.assertTrue(delivered.admin_name.isna().all())
            qc = json.loads((root / "output" / "qc.json").read_text(encoding="utf-8"))
            self.assertEqual(qc["registration"]["gate"]["status"], "pass")
            self.assertEqual(qc["decision"]["reference"]["crs"], "EPSG:32649")
            self.assertEqual(qc["extraction"]["boundary_source"], "stroke")
            self.assertEqual(qc["names"]["status"], "no_labels_found")
            self.assertIn("未发现图面名称", qc["names"]["message"])
            self.assertNotIn("map_labels", pyogrio.list_layers(
                root / "output" / "registered.gpkg")[:, 0])
            self.assertEqual(run(config), 0)  # verified delivery cache
            config["delivery"]["mode"] = "C"
            config["output_dir"] = str(root / "conformed_output")
            self.assertEqual(run(config), 0)
            self.assertTrue((root / "conformed_output" / "conformed.gpkg").is_file())
            config["delivery"]["mode"] = "R"
            config["names"]["mode"] = "required"
            config["output_dir"] = str(root / "required_output")
            self.assertEqual(run(config), 2)
            self.assertFalse((root / "required_output").exists())
            review = json.loads((root / "work" / "review_names.json").read_text(
                encoding="utf-8"))
            self.assertEqual(len(review["unresolved"]), 2)
            self.assertTrue(all(Path(row["crop"]).is_file() for row in review["unresolved"]))
            self.assertEqual(json.loads((root / "work" / "review.json").read_text(
                encoding="utf-8"))["status"], "REVIEW_NAMES")


if __name__ == "__main__":
    unittest.main()
