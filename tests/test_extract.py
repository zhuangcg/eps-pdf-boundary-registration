"""A reused fill colour must split into separate administrative units."""
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import fitz
import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from extract import extract  # noqa: E402


class ExtractionTest(unittest.TestCase):
    def test_reviewed_colours_and_reused_colour(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "map.pdf"
            a = (220 / 255, 233 / 255, 174 / 255)
            b = (250 / 255, 209 / 255, 227 / 255)
            with fitz.open() as doc:
                page = doc.new_page(width=200, height=200)
                for rect, colour in [((10, 10, 70, 70), a),
                                     ((90, 10, 150, 70), a),
                                     ((10, 90, 80, 150), b)]:
                    page.draw_rect(fitz.Rect(rect), color=None, fill=colour)
                doc.save(pdf)
            config = {"source_map": str(pdf), "work_dir": str(root / "work"),
                      "extraction": {"keep_colours_rgb": [[220, 233, 174], [250, 209, 227]],
                                     "split_colours_rgb": [[220, 233, 174]],
                                     "min_fill_area_pt2": 20,
                                     "expected_admin_polygon_count": 3}}
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="'crs' was not provided")
                report = extract(config)
            frame = gpd.read_file(report["page_units_gpkg"])
            self.assertEqual(len(frame), 3)
            self.assertEqual(sorted(round(a) for a in frame.area), [3600, 3600, 4200])
            self.assertEqual(len(set(frame.source_drawings)), 3)
            self.assertEqual(report, extract(config))


if __name__ == "__main__":
    unittest.main()
