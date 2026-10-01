"""Local CLI for experiment bookkeeping, with an explicitly synthetic demo."""

import argparse
import json
from pathlib import Path

from .records import append_rows, create_run, environment, finish_run, list_runs, read_rows, validate_run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="Snapshot a configuration and allocate a planned run")
    create.add_argument("--config", type=Path, required=True)
    create.add_argument("--category", choices=["reproductions", "sweeps", "architectures"], default="sweeps")
    simulate = sub.add_parser("simulate", help="Execute an explicitly configured physical solver in a new run")
    simulate.add_argument("--config", type=Path, required=True)
    ctl = sub.add_parser("ctl-check", help="Recorded local REBOUNDx CTL/Jackson mapping diagnostic")
    ctl.add_argument("--config", type=Path, required=True)
    append = sub.add_parser("append", help="Append validated CSV output supplied by a future simulator")
    append.add_argument("--run", type=Path, required=True)
    append.add_argument("--csv", type=Path, required=True)
    finish = sub.add_parser("finish")
    finish.add_argument("--run", type=Path, required=True)
    finish.add_argument("--status", choices=["completed", "failed", "aborted"], required=True)
    finish.add_argument("--reason", required=True)
    finish.add_argument("--metrics", type=Path)
    check = sub.add_parser("validate")
    check.add_argument("--run", type=Path, required=True)
    sub.add_parser("list")
    sub.add_parser("doctor")
    sub.add_parser("demo", help="Create a SYNTHETIC record, never a scientific simulation")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "ctl-check":
            from .ctl import execute_ctl
            config = args.config if args.config.is_absolute() else root / args.config
            run = execute_ctl(root, config)
            output = {"run_path": str(run), **validate_run(run)}
        elif args.command == "simulate":
            from .physics import execute
            config = args.config if args.config.is_absolute() else root / args.config
            run = execute(root, config)
            output = {"run_path": str(run), **validate_run(run)}
        elif args.command == "create":
            config = args.config if args.config.is_absolute() else root / args.config
            output = {"run_path": str(create_run(root, config, args.category)), "status": "planned"}
        elif args.command == "append":
            append_rows(args.run, read_rows(args.csv))
            output = validate_run(args.run)
        elif args.command == "finish":
            metrics = json.loads(args.metrics.read_text(encoding="utf-8-sig")) if args.metrics else None
            finish_run(args.run, args.status, args.reason, metrics)
            output = validate_run(args.run)
        elif args.command == "validate":
            output = validate_run(args.run)
        elif args.command == "list":
            output = list_runs(root)
        elif args.command == "doctor":
            output = environment(root)
            import rebound
            import reboundx
            sim = rebound.Simulation()
            sim.add(m=1)
            sim.add(m=1e-6, a=1)
            rebx = reboundx.Extras(sim)
            force = rebx.load_force("tides_constant_time_lag")
            output["runtime_check"] = {"imports": "passed", "effect_load": force.name.decode(),
                                       "reboundx_upstream_commit": reboundx.__githash__}
        else:
            run = create_run(root, root / "configs/examples/recording_demo.yaml", "examples")
            append_rows(run, [{"t_year": t, "body": "synthetic_planet", "a_au": a, "e": e,
                               "pericentre_au": a * (1 - e), "stellar_radius_au": "",
                               "roche_limit_au": "", "event": "synthetic_demo"}
                              for t, a, e in [(0, 0.1, 0.4), (1, 0.099, 0.39), (2, 0.098, 0.38)]])
            finish_run(run, "completed", "synthetic_recording_demo_only", {"scientific_claim": None})
            output = {"run_path": str(run), **validate_run(run)}
        print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, OSError, ImportError, KeyError, TypeError, RuntimeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
