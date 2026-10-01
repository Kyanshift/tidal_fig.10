"""Behavioral checks for recording integrity; no astrophysical simulation."""

import csv
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from k2_261b.records import COLUMNS, append_rows, create_run, finish_run, read_config, sha256, validate_run


class RecordsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        (self.root / "data/track.txt").write_text("1 2\n", encoding="utf-8")
        (self.root / "src").mkdir()
        (self.root / "src/model.py").write_text("MODEL_VERSION = 1\n", encoding="utf-8")
        self.config = {
            "schema_version": 1,
            "experiment": {"name": "test", "kind": "sensitivity", "dataset_type": "scientific"},
            "seed": 42, "units": {"length": "au", "mass": "Msun", "time": "yr"},
            "model": {"tides": {"q_prime_star": 1e6, "q_prime_planet": 3e4}},
            "integration": {"direction": "forward"}, "inputs": ["data/track.txt"],
        }
        self.path = self.root / "config.yaml"
        self.save()

    def save(self):
        self.path.write_text(yaml.safe_dump(self.config), encoding="utf-8")

    def row(self, time=0, **overrides):
        result = {"t_year": time, "body": "b", "a_au": 0.1, "e": 0.4,
                  "pericentre_au": 0.06, "stellar_radius_au": 0.01,
                  "roche_limit_au": 0.02, "event": ""}
        result.update(overrides)
        return result

    def test_snapshots_survive_changes_to_originals(self):
        run = create_run(self.root, self.path)
        (self.root / "data/track.txt").write_text("changed", encoding="utf-8")
        self.config["seed"] = 99
        self.save()
        self.assertEqual(read_config(run / "config.yaml")["seed"], 42)
        self.assertEqual((run / "inputs/files/data/track.txt").read_text(), "1 2\n")
        self.assertEqual(validate_run(run)["status"], "planned")
        metadata = json.loads((run / "metadata.json").read_text())
        self.assertEqual(metadata["code_snapshot"]["files"][0]["path"], "src/model.py")

    def test_snapshot_creation_failure_leaves_a_failure_record(self):
        with patch("k2_261b.records.zipfile.ZipFile", side_effect=OSError("storage_failure")):
            with self.assertRaisesRegex(OSError, "storage_failure"):
                create_run(self.root, self.path)
        run = self.root / "results/sweeps/run_000001"
        self.assertTrue(all((run / name).is_file() for name in ["config.yaml", "metadata.json", "evolution.csv", "summary.json"]))
        summary = json.loads((run / "summary.json").read_text())
        self.assertEqual(summary["status"], "failed")
        self.assertIn("storage_failure", summary["termination_reason"])
        with self.assertRaisesRegex(ValueError, "initialization incomplete"):
            validate_run(run)

    def test_snapshot_corruption_is_detected_before_write(self):
        run = create_run(self.root, self.path)
        (run / "inputs/files/data/track.txt").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Input snapshot modified"):
            append_rows(run, [self.row()])
        self.assertFalse((run / ".write.lock").exists())

    def test_configuration_is_immutable(self):
        run = create_run(self.root, self.path)
        with (run / "config.yaml").open("a") as handle:
            handle.write("changed: true\n")
        with self.assertRaisesRegex(ValueError, "Config snapshot"):
            validate_run(run)

    def test_lifecycle_and_terminal_write_protection(self):
        run = create_run(self.root, self.path)
        append_rows(run, [self.row(), self.row(1)])
        self.assertEqual(validate_run(run)["status"], "running")
        finish_run(run, "completed", "integration_end", {"acceptance_passed": False})
        self.assertEqual(validate_run(run)["row_count"], 2)
        with self.assertRaisesRegex(ValueError, "Terminal"):
            append_rows(run, [self.row(2)])
        with self.assertRaisesRegex(ValueError, "already terminal"):
            finish_run(run, "failed", "second_end")

    def test_invalid_batch_does_not_partially_append(self):
        run = create_run(self.root, self.path)
        append_rows(run, [self.row()])
        before = sha256(run / "evolution.csv")
        for invalid in [self.row(2, e=float("nan")), self.row(2, pericentre_au=0.03), self.row(0)]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                append_rows(run, [self.row(1), invalid])
            self.assertEqual(sha256(run / "evolution.csv"), before)
        self.assertEqual(validate_run(run)["row_count"], 1)

    def test_empty_run_cannot_be_completed_but_can_be_aborted(self):
        run = create_run(self.root, self.path)
        with self.assertRaisesRegex(ValueError, "without evolution"):
            finish_run(run, "completed", "empty")
        finish_run(run, "aborted", "cancelled_before_execution")
        self.assertEqual(validate_run(run)["status"], "aborted")

    def test_backward_and_multibody_records(self):
        self.config["integration"]["direction"] = "backward"
        self.save()
        run = create_run(self.root, self.path)
        append_rows(run, [self.row(0), self.row(0, body="c"), self.row(-1)])
        self.assertEqual(validate_run(run)["row_count"], 3)

    def test_ejection_and_nonfinite_metrics(self):
        run = create_run(self.root, self.path)
        append_rows(run, [self.row(0, a_au=-1, e=1.2, pericentre_au=0.2, event="ejection")])
        with self.assertRaises(ValueError):
            finish_run(run, "completed", "ejected", {"invalid": float("inf")})
        self.assertEqual(validate_run(run)["status"], "running")

    def test_id_allocation_concurrent_and_no_overwrite(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            runs = list(pool.map(lambda _: create_run(self.root, self.path), range(8)))
        self.assertEqual(len({p.name for p in runs}), 8)
        self.assertTrue(all(validate_run(p)["valid"] for p in runs))

    def test_input_path_escape_rejected_before_allocation(self):
        self.config["inputs"] = ["../outside.txt"]
        self.save()
        with self.assertRaisesRegex(ValueError, "within project"):
            create_run(self.root, self.path)
        self.assertFalse((self.root / "results").exists())

    def test_synthetic_results_cannot_enter_scientific_categories(self):
        self.config["experiment"].update(kind="demonstration", dataset_type="synthetic")
        self.save()
        with self.assertRaisesRegex(ValueError, "Synthetic"):
            create_run(self.root, self.path, "sweeps")
        self.assertEqual(validate_run(create_run(self.root, self.path, "examples"))["dataset_type"], "synthetic")

    def test_corrupt_row_count_and_header_are_detected(self):
        run = create_run(self.root, self.path)
        append_rows(run, [self.row()])
        with (run / "evolution.csv").open("a", newline="") as handle:
            csv.DictWriter(handle, fieldnames=COLUMNS).writerow(self.row(1))
        with self.assertRaisesRegex(ValueError, "row_count"):
            validate_run(run)
        (run / "evolution.csv").write_text("bad,header\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "CSV header"):
            validate_run(run)


class ProjectInputsTest(unittest.TestCase):
    def test_truth_sources_and_scientific_values(self):
        root = Path(__file__).resolve().parents[1]
        truth = yaml.safe_load((root / "configs/parameters/paper_truth.yaml").read_text(encoding="utf-8"))
        for source in truth["sources"].values():
            self.assertTrue((root / source["path"]).is_file())
        for value in truth["adopted_observations"].values():
            self.assertIn(value["source"], truth["sources"])
            self.assertGreaterEqual(value["uncertainty"]["minus"], 0)
            self.assertGreaterEqual(value["uncertainty"]["plus"], 0)
        baseline = read_config(root / "configs/reproductions/fig10_baseline.yaml")
        self.assertEqual(baseline["initial_conditions"]["star_mass_Msun"], truth["adopted_observations"]["star_mass"]["value"])
        design = yaml.safe_load((root / "configs/sweeps/tidal_quality_factors.yaml").read_text(encoding="utf-8"))
        self.assertEqual(set(design["mandatory_factors"]), {"model.tides.q_prime_star", "model.tides.q_prime_planet"})
        self.assertFalse(truth["quality_factor_conventions"]["operational_fig10_mapping"]["reboundx_time_lag_conversion_enabled"])


if __name__ == "__main__":
    unittest.main()
