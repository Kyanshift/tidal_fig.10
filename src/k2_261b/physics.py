"""Explicit physical execution entry point; bookkeeping stays model agnostic."""
import json
import time
from pathlib import Path

import numpy as np

from .records import append_rows, create_run, finish_run, read_config, validate_run
from .tides import JacksonModel, integrate_bs


def integrate_dop853(model):
    from scipy.integrate import solve_ivp
    cfg = model.config["integration"]
    end, dt = cfg["end_time_year"], cfg["output_interval_year"]
    sign = 1 if end > 0 else -1
    times = np.append(np.arange(0., end, sign*dt), end)
    def engulfment(t, y):
        return y[0]*(1-y[1]) - model.radius(t)
    engulfment.terminal = True
    engulfment.direction = -1
    events = [engulfment] if sign > 0 else None
    sol = solve_ivp(model.rhs, (0., end), model.initial, method="DOP853", t_eval=times,
                    rtol=cfg["tolerance"], atol=cfg["tolerance"],
                    max_step=cfg["max_step_year"], events=events, dense_output=True)
    if not sol.success:
        raise RuntimeError(sol.message)
    rows = [model.row(t, y, "initial_state" if t == 0 else "") for t, y in zip(sol.t, sol.y.T)]
    reason = "integration_end"
    metrics = {"termination_reason": reason, "rhs_evaluations": sol.nfev}
    if sign > 0 and len(sol.t_events[0]):
        t = float(sol.t_events[0][0])
        if t > rows[-1]["t_year"]:
            rows.append(model.row(t, sol.sol(t), "stellar_engulfment"))
        reason = metrics["termination_reason"] = "stellar_engulfment"
        metrics["event_time_year"] = t
    return rows, metrics


def integrate_euler(model):
    """Explicit historical Euler comparison with corrected time labels.

    Historical script plots the post-step state at the pre-step time. This
    implementation labels each state with its actual time, and records the
    first engulfment state instead of omitting it.
    """
    cfg = model.config["integration"]
    end = cfg["end_time_year"]
    step = np.sign(end)*cfg["max_step_year"]
    t, y = 0., model.initial.copy()
    rows = [model.row(t, y, "initial_state")]
    while abs(t) < abs(end):
        h = np.sign(end)*min(abs(step), abs(end-t))
        y = y + h * model.rhs(t, y)
        t += h
        if y[0] <= 0 or not 0 <= y[1] < 1:
            return rows, {"termination_reason": "elliptic_domain_exit_before_next_output"}
        event = "stellar_engulfment" if end > 0 and y[0]*(1-y[1]) <= model.radius(t) else ""
        rows.append(model.row(t, y, event))
        if event:
            return rows, {"termination_reason": event, "event_bracket_year": [t-abs(step), t]}
    return rows, {"termination_reason": "integration_end"}


def execute(root, config_path):
    root = Path(root).resolve()
    config = read_config(config_path)
    integration = config["integration"]
    if integration["end_time_year"] == 0 or (integration["end_time_year"] > 0) != (integration["direction"] == "forward"):
        raise ValueError("End time must have the configured direction")
    if any(integration[key] <= 0 for key in ("max_step_year", "output_interval_year", "tolerance")):
        raise ValueError("Steps and tolerance must be positive")
    if config["model"]["implementation"] != "jackson2009_orbit_averaged":
        raise ValueError("Unsupported physical model")
    if config["model"]["tides"]["prescription"] != "jackson2009_constant_modified_Q":
        raise ValueError("Jackson execution requires the constant modified-Q prescription")
    if integration["integrator"] not in {"rebound_bs", "scipy_dop853", "legacy_euler"}:
        raise ValueError("Unsupported solver")
    run = create_run(root, config_path, "reproductions")
    started = time.perf_counter()
    try:
        # Execute against the immutable run inputs, never mutable live data.
        config = read_config(run / "config.yaml")
        model = JacksonModel(config, run / "inputs/files")
        solver = {"rebound_bs": integrate_bs, "scipy_dop853": integrate_dop853,
                  "legacy_euler": integrate_euler}[integration["integrator"]]
        rows, metrics = solver(model)
        append_rows(run, rows)
        metrics.update(wall_seconds=time.perf_counter()-started,
                       scientific_acceptance="pending_digitized_curve_and_model_review",
                       physical_mapping_verified=False, ensemble=config.get("sampling", {"kind": "central_only"}),
                       initial_da_dt_au_per_year=float(model.rhs(0, model.initial)[0]),
                       initial_de_dt_per_year=float(model.rhs(0, model.initial)[1]),
                       stellar_radius_at_epoch_Rsun=model.radius(0)/model.rsun,
                       radius_track_provenance="unverified_legacy_YY_track",
                       end_age_Gyr=model.age+rows[-1]["t_year"]/1e9)
        finish_run(run, "completed", metrics["termination_reason"], metrics)
        validate_run(run)
    except BaseException as exc:
        finish_run(run, "aborted" if isinstance(exc, KeyboardInterrupt) else "failed",
                   type(exc).__name__ + ": " + str(exc), {"wall_seconds": time.perf_counter()-started})
        raise
    return run
