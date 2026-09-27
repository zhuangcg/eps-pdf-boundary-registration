"""Scope and naming gates follow the generalized contract."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect_environment.py"


class WorkflowGuardsTest(unittest.TestCase):
    def test_scope_and_name_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "map.eps"
            reference = root / "city.gpkg"
            source.touch()
            reference.touch()
            config_path = root / "run.yaml"
            config = {
                "source_map": str(source),
                "reference_boundary": str(reference),
                "admin_level": "street",
                "source_scope": "partial_parent",
                "output_dir": str(root / "output"),
                "work_dir": str(root / "work"),
                "reference": {"fit_crs": "EPSG:32649"},
                "names": {"require_map_annotation": True},
                "delivery": {"mode": "R"},
            }

            def run():
                config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
                return subprocess.run(
                    [sys.executable, str(SCRIPT), "--config", str(config_path)],
                    capture_output=True, text=True,
                )

            self.assertEqual(run().returncode, 0)
            config["delivery"]["mode"] = "C"
            self.assertIn("same-extent reference", run().stdout)
            config["source_scope"] = "same_extent"
            self.assertEqual(run().returncode, 0)
            config["names"]["require_map_annotation"] = False
            self.assertEqual(run().returncode, 0)
            config["names"]["mode"] = "unknown"
            self.assertIn("names.mode", run().stdout)


if __name__ == "__main__":
    unittest.main()
