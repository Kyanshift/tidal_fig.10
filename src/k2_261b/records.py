"""Immutable experiment inputs and appendable, validated evolution records."""

from __future__ import annotations

import csv
import hashlib
import importlib
import importlib.metadata
import io
import json
import math
import platform
import re
import subprocess
import sys
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import yaml

COLUMNS = (
    "t_year", "body", "a_au", "e", "pericentre_au",
    "stellar_radius_au", "roche_limit_au", "event",
)
TERMINAL = {"completed", "failed", "aborted"}
CATEGORIES = {"reproductions", "sweeps", "architectures", "examples"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _atomic_text(path, text):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="")
    temporary.replace(path)


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return value


def read_config(path):
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int or config["schema_version"] != 1:
        raise ValueError("config.schema_version must be 1")
    experiment = config.get("experiment", {})
    if not isinstance(experiment.get("name"), str) or not experiment["name"].strip():
        raise ValueError("experiment.name is required")
    if experiment.get("kind") not in {"reproduction", "sensitivity", "architecture", "demonstration"}:
        raise ValueError("Invalid experiment.kind")
    if experiment.get("dataset_type") not in {"scientific", "synthetic"}:
        raise ValueError("dataset_type must be scientific or synthetic")
    if (experiment["kind"] == "demonstration") != (experiment["dataset_type"] == "synthetic"):
        raise ValueError("Only demonstration records may use synthetic data")
    seed = config.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if config.get("units") != {"length": "au", "mass": "Msun", "time": "yr"}:
        raise ValueError("Canonical units must be au, Msun, yr")
    if config.get("integration", {}).get("direction") not in {"forward", "backward"}:
        raise ValueError("integration.direction must be forward or backward")
    tides = config.get("model", {}).get("tides", {})
    for name in ("q_prime_star", "q_prime_planet"):
        if name in tides and tides[name] is not None:
            if _number(tides[name], name) <= 0:
                raise ValueError(f"{name} must be positive")
    inputs = config.get("inputs", [])
    if not isinstance(inputs, list) or not all(isinstance(p, str) for p in inputs):
        raise ValueError("inputs must be a list of project-relative paths")
    _json(config)  # Reject YAML timestamps, NaN and other nonportable values.
    return config


def _inside(root, relative):
    candidate = (root / relative).resolve()
    if Path(relative).is_absolute() or not candidate.is_relative_to(root):
        raise ValueError(f"Input must remain within project: {relative}")
    return candidate


def environment(root):
    packages = {}
    for name in ("rebound", "reboundx", "PyYAML", "numpy", "scipy", "astropy", "matplotlib"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    patch = root / "artifacts/reboundx-msvc.patch"
    commit_file = root / "artifacts/reboundx-upstream-commit.json"
    native_libraries = {}
    for name in ("rebound", "reboundx"):
        try:
            module = importlib.import_module(name)
            library = Path(module.__libpath__)
            native_libraries[name] = {
                "import_status": "passed", "path": str(library),
                "sha256": sha256(library), "version": module.__version__,
                "upstream_commit": module.__githash__,
            }
        except (ImportError, OSError, AttributeError) as exc:
            native_libraries[name] = {"import_status": "unavailable", "error": str(exc)}
    return {
        "python": sys.version, "executable": sys.executable,
        "platform": platform.platform(), "machine": platform.machine(),
        "packages": packages,
        "native_libraries": native_libraries,
        "reboundx_build": {
            "variant": "local_msvc_adaptation" if patch.exists() else "unspecified",
            "patch_sha256": sha256(patch) if patch.exists() else None,
            "upstream_record_sha256": sha256(commit_file) if commit_file.exists() else None,
        },
    }


def _git(root):
    def run(*args):
        try:
            p = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=15)
            return p.stdout.strip() if p.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    changes = run("status", "--porcelain", "--untracked-files=all")
    return {"commit": run("rev-parse", "HEAD"), "branch": run("branch", "--show-current"),
            "dirty": bool(changes) if changes is not None else None,
            "status_sha256": hashlib.sha256(changes.encode()).hexdigest() if changes is not None else None,
            "status_entry_count": len(changes.splitlines()) if changes else 0}


def create_run(root, config_path, category="sweeps"):
    root = Path(root).resolve()
    config_path = Path(config_path).resolve()
    config = read_config(config_path)
    if category not in CATEGORIES:
        raise ValueError("Invalid category")
    if (category == "examples") != (config["experiment"]["dataset_type"] == "synthetic"):
        raise ValueError("Synthetic records belong in examples; scientific records belong elsewhere")
    # Preflight all inputs before allocating an experiment ID.
    inputs = [(relative, _inside(root, relative)) for relative in config.get("inputs", [])]
    if any(not path.is_file() for _, path in inputs):
        raise ValueError("Every configured input must exist and be a regular file")
    parent = root / "results" / category
    parent.mkdir(parents=True, exist_ok=True)
    existing = [int(p.name[4:]) for p in parent.iterdir() if re.fullmatch(r"run_\d{6,}", p.name)]
    number = max(existing, default=0) + 1
    while True:
        run = parent / f"run_{number:06d}"
        try:
            run.mkdir()  # Atomic ID reservation across concurrent creators.
            break
        except FileExistsError:
            number += 1
    snapshot = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    (run / "config.yaml").write_text(snapshot, encoding="utf-8")
    _write_rows(run / "evolution.csv", [])
    summary = {
        "schema_version": 1, "run_id": run.name, "status": "planned",
        "dataset_type": config["experiment"]["dataset_type"], "row_count": 0,
        "started_at_utc": None, "finished_at_utc": None,
        "termination_reason": None, "metrics": {},
    }
    _atomic_text(run / "summary.json", _json(summary))
    metadata = {
        "schema_version": 1, "run_id": run.name, "category": category,
        "created_at_utc": utc_now(), "project_timezone": "Europe/Berlin",
        "project_root_at_creation": str(root), "seed": config["seed"],
        "source_config_path": str(config_path), "source_config_sha256": sha256(config_path),
        "config_snapshot_sha256": sha256(run / "config.yaml"),
        "git": _git(root), "environment": environment(root),
        "inputs": [], "code_snapshot": None, "initialization_status": "initializing",
        "argv": sys.argv,
    }
    _atomic_text(run / "metadata.json", _json(metadata))
    try:
        input_records = []
        for relative, source in inputs:
            destination = run / "inputs" / "files" / source.relative_to(root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            input_records.append({"source_path": relative, "snapshot_path": destination.relative_to(run).as_posix(),
                                  "sha256": sha256(destination), "bytes": destination.stat().st_size})
        code_files = sorted({p for pattern in ("src/**/*.py", "scripts/*.py", "scripts/*.ps1",
                                               "requirements/*.txt", "pyproject.toml") for p in root.glob(pattern) if p.is_file()})
        code_path = run / "inputs" / "code.zip"
        code_path.parent.mkdir(parents=True, exist_ok=True)
        code_manifest = []
        with zipfile.ZipFile(code_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in code_files:
                data = path.read_bytes()
                name = path.relative_to(root).as_posix()
                archive.writestr(name, data)
                code_manifest.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
        metadata.update({
            "inputs": input_records, "code_snapshot": {
                "path": "inputs/code.zip", "sha256": sha256(code_path), "files": code_manifest,
            },
            "initialization_status": "complete",
        })
        _atomic_text(run / "metadata.json", _json(metadata))
    except Exception as exc:
        metadata.update(initialization_status="failed", initialization_error=str(exc))
        _atomic_text(run / "metadata.json", _json(metadata))
        summary.update(status="failed", finished_at_utc=utc_now(), termination_reason=f"initialization_error: {exc}")
        _atomic_text(run / "summary.json", _json(summary))
        raise
    return run


def _write_rows(path, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    _atomic_text(path, buffer.getvalue())


def read_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(COLUMNS):
            raise ValueError(f"CSV header must be {','.join(COLUMNS)}")
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError("Malformed CSV row")
    return rows


def _validate_rows(rows, direction):
    previous = {}
    for row in rows:
        if (set(row) != set(COLUMNS) or not isinstance(row["body"], str)
                or not row["body"].strip() or not isinstance(row["event"], str)):
            raise ValueError("Every row needs the complete columns and a body name")
        numbers = {}
        for name in COLUMNS:
            if name in {"body", "event"}:
                continue
            if row[name] in ("", None) and name in {"stellar_radius_au", "roche_limit_au"}:
                continue
            try:
                if isinstance(row[name], bool):
                    raise ValueError("Boolean is not an orbital value")
                numbers[name] = _number(float(row[name]), name)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid numerical cell: {name}") from exc
        a, e, q = (numbers[k] for k in ("a_au", "e", "pericentre_au"))
        bound = a > 0 and 0 <= e < 1
        unbound = a < 0 and e > 1 and row["event"] == "ejection"
        if not (bound or unbound) or q <= 0:
            raise ValueError("Invalid orbit: unbound rows require a<0, e>1 and event=ejection")
        if not math.isclose(q, a * (1 - e), rel_tol=1e-8, abs_tol=1e-12):
            raise ValueError("pericentre_au must equal a_au*(1-e)")
        if any(numbers.get(k, 0) < 0 for k in ("stellar_radius_au", "roche_limit_au")):
            raise ValueError("Radii cannot be negative")
        body, t = row["body"], numbers["t_year"]
        if body in previous:
            if (direction == "forward" and t <= previous[body]) or (direction == "backward" and t >= previous[body]):
                raise ValueError("Times must be strictly monotonic per body in integration.direction")
        previous[body] = t


def validate_run(run):
    run = Path(run).resolve()
    config = read_config(run / "config.yaml")
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    if metadata.get("initialization_status") != "complete":
        raise ValueError("Run initialization incomplete; preserve the failure record and allocate a new run")
    if sha256(run / "config.yaml") != metadata["config_snapshot_sha256"]:
        raise ValueError("Config snapshot has been modified")
    if metadata["seed"] != config["seed"] or summary["dataset_type"] != config["experiment"]["dataset_type"]:
        raise ValueError("Config/metadata/summary provenance mismatch")
    if metadata["run_id"] != run.name or summary["run_id"] != run.name:
        raise ValueError("Run ID mismatch")
    for item in metadata["inputs"] + [metadata["code_snapshot"]]:
        path = _inside(run, item.get("snapshot_path", item.get("path")))
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Input snapshot modified: {path.name}")
    rows = read_rows(run / "evolution.csv")
    _validate_rows(rows, config["integration"]["direction"])
    if summary["row_count"] != len(rows):
        raise ValueError("Summary row_count does not match evolution.csv")
    if summary["status"] not in TERMINAL | {"planned", "running"}:
        raise ValueError("Invalid run status")
    if summary["status"] == "completed" and not rows:
        raise ValueError("Completed runs need at least one evolution row")
    _json(summary)
    return {"valid": True, "run_id": run.name, "status": summary["status"],
            "dataset_type": summary["dataset_type"], "row_count": len(rows)}


@contextmanager
def _locked(run):
    lock = run / ".write.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError("Another writer holds .write.lock; inspect before recovering a stale lock") from exc
    try:
        with handle:
            handle.write(str(__import__("os").getpid()))
        yield
    finally:
        lock.unlink()


def append_rows(run, new_rows):
    run = Path(run).resolve()
    if not new_rows:
        raise ValueError("No rows to append")
    with _locked(run):
        validate_run(run)
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        if summary["status"] in TERMINAL:
            raise ValueError("Terminal runs are immutable; allocate a new run")
        config = read_config(run / "config.yaml")
        rows = read_rows(run / "evolution.csv") + list(new_rows)
        _validate_rows(rows, config["integration"]["direction"])
        _write_rows(run / "evolution.csv", rows)
        summary.update(status="running", row_count=len(rows),
                       started_at_utc=summary["started_at_utc"] or utc_now())
        _atomic_text(run / "summary.json", _json(summary))


def finish_run(run, status, reason, metrics=None):
    run = Path(run).resolve()
    if status not in TERMINAL or not reason.strip():
        raise ValueError("A terminal status and termination reason are required")
    if metrics is not None and not isinstance(metrics, dict):
        raise ValueError("metrics must be a JSON object")
    with _locked(run):
        result = validate_run(run)
        if result["status"] in TERMINAL:
            raise ValueError("Run is already terminal")
        if status == "completed" and result["row_count"] == 0:
            raise ValueError("Cannot complete a run without evolution rows")
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        summary.update(status=status, finished_at_utc=utc_now(), termination_reason=reason, metrics=metrics or {})
        encoded = _json(summary)
        _atomic_text(run / "summary.json", encoded)


def list_runs(root):
    return [{"path": path.parent.relative_to(root).as_posix(),
             **json.loads(path.read_text(encoding="utf-8"))}
            for path in sorted((Path(root) / "results").glob("*/run_*/summary.json"))]
