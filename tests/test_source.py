"""A small check that path census and cache reuse survive a real PDF round trip."""
import sys
import tempfile
import unittest
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from source import inspect  # noqa: E402


class SourceInspectionTest(unittest.TestCase):
    def test_census_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "map.pdf"
            with fitz.open() as doc:
                page = doc.new_page(width=200, height=100)
                page.draw_rect(fitz.Rect(20, 20, 180, 80),
                               fill=(220 / 255, 233 / 255, 174 / 255))
                page.insert_text((25, 18), "Map")
                doc.save(pdf)
            first = inspect(pdf, root / "work")
            self.assertGreater(first["vector_drawings"], 0)
            self.assertEqual(first["native_words"], 1)
            self.assertIn([220, 233, 174], [row["rgb"] for row in first["colours"]])
            self.assertEqual(first, inspect(pdf, root / "work"))


if __name__ == "__main__":
    unittest.main()
