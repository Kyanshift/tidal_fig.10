"""Jackson et al. (2009), equations 1/2, in explicit au/Msun/year units.

Historical algorithm source: legacy/tidal/tidal.py (unchanged). This is a
low-e expansion, not a general high-e equilibrium-tide prescription.
"""
from dataclasses import dataclass
from pathlib import Path
import math
import warnings

import numpy as np


@dataclass
class JacksonModel:
    config: dict
    root: Path

    def __post_init__(self):
        c = self.config["constants"]
        self.G = c["G_SI"] * c["Msun_kg"] * c["year_seconds"]**2 / c["au_m"]**3
        i = self.config["initial_conditions"]
        self.ms = i["star_mass_Msun"]
        self.mp = i["planet_mass_Mjup"] * c["Mjup_kg"] / c["Msun_kg"]
        self.rp = i["planet_radius_Rjup"] * c["Rjup_m"] / c["au_m"]
        self.rsun = c["Rsun_m"] / c["au_m"]
        self.age = i["stellar_age_Gyr"]
        self.initial = np.array([i["a_au"], i["e"]], dtype=float)
        if (not np.all(np.isfinite(self.initial)) or self.initial[0] <= 0
                or not 0 <= self.initial[1] < 1
                or any(not math.isfinite(v) or v <= 0 for v in (self.G,self.ms,self.mp,self.rp,self.rsun))):
            raise ValueError("Initial state must have positive finite constants, masses/radii/a and 0<=e<1")
        tides = self.config["model"]["tides"]
        self.qs, self.qp = tides["q_prime_star"], tides["q_prime_planet"]
        if any(not math.isfinite(v) or v <= 0 for v in (self.qs,self.qp)):
            raise ValueError("Jackson denominators must be finite positive Q_prime values")
        self.track = np.loadtxt(self.root / self.config["model"]["stellar_radius"]["track"])
        if self.track.ndim != 2 or self.track.shape[1] != 2 or np.any(np.diff(self.track[:, 0]) <= 0):
            raise ValueError("Track must contain strictly increasing age and radius columns")
        if not np.all(np.isfinite(self.track)) or np.any(self.track[:, 1] <= 0):
            raise ValueError("Invalid stellar track")
        self.roche = self.config["model"]["roche_coefficient"] * self.rp * (self.ms / self.mp)**(1/3)

    def radius(self, t_year):
        # Deliberate legacy endpoint clamping, including ages below 1 Gyr.
        return float(np.interp(self.age + t_year / 1e9, self.track[:, 0], self.track[:, 1])) * self.rsun

    def contributions(self, t_year, y):
        a, e = y
        if not math.isfinite(a) or not math.isfinite(e) or a <= 0:
            raise ValueError("Nonfinite or nonpositive orbit in tidal RHS")
        A = math.sqrt(self.G * self.ms**3) * self.rp**5 / (self.qp * self.mp)
        B = math.sqrt(self.G / self.ms) * self.radius(t_year)**5 * self.mp / self.qs
        return (np.array([-a * 63/2 * A * e**2, -e * 63/4 * A]) * a**(-6.5),
                np.array([-a * 9/2 * B * (1 + 57/4 * e**2), -e * 225/16 * B]) * a**(-6.5))

    def rhs(self, t_year, y):
        planet, star = self.contributions(t_year, y)
        return planet + star

    def row(self, t_year, y, event=""):
        a, e = map(float, y)
        return dict(t_year=float(t_year), body="K2-261_b", a_au=a, e=e,
                    pericentre_au=a*(1-e), stellar_radius_au=self.radius(t_year),
                    roche_limit_au=self.roche, event=event)


class ReboundBS:
    """Pure orbit-averaged ODE, with no fictitious N-body particles."""
    def __init__(self, model, t=0., y=None, tolerance=None):
        import rebound
        self.model = model
        self.sim = rebound.Simulation()
        self.sim.G = model.G
        self.sim.integrator = "BS"
        tol = tolerance or model.config["integration"]["tolerance"]
        self.sim.integrator.eps_abs = tol
        self.sim.integrator.eps_rel = tol
        self.sim.t = t
        sign = 1 if model.config["integration"]["direction"] == "forward" else -1
        step = model.config["integration"]["max_step_year"]
        self.sim.dt = sign * min(step, 1e5)
        self.sim.integrator.max_dt = step
        self.ode = self.sim.create_ode(length=2, needs_nbody=False)
        self.error = None
        def derivatives(ode, ydot, state, time):
            # ctypes does not propagate callback exceptions. Capture explicitly.
            try:
                value = model.rhs(time, [state[0], state[1]])
                ydot[0], ydot[1] = value
            except Exception as exc:
                self.error = exc
                ydot[0] = ydot[1] = 0.
        self.ode.derivatives = derivatives
        state = model.initial if y is None else y
        self.ode.y[0], self.ode.y[1] = map(float, state)

    def advance(self, t):
        # Expected when the accuracy-controlled solver hits our scientific cap.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Maximum stepsize reached during ODE integration.", category=RuntimeWarning)
            self.sim.integrate(float(t), exact_finish_time=1)
        if self.error is not None:
            raise RuntimeError(f"ODE callback failed: {self.error}") from self.error
        y = np.array([self.ode.y[0], self.ode.y[1]])
        if not np.all(np.isfinite(y)) or y[0] <= 0 or not 0 <= y[1] < 1:
            raise ValueError("Orbit left the finite elliptic domain")
        return y


def integrate_bs(model):
    """Output on fixed grid; localize forward engulfment by fresh BS solves.

    Roche crossing is diagnostic, not a disruption simulation. Continuing past
    it is an explicit idealized legacy comparison. Engulfment is q <= R_star.
    """
    cfg = model.config["integration"]
    end, interval = cfg["end_time_year"], cfg["output_interval_year"]
    sign = 1 if end > 0 else -1
    solver = ReboundBS(model)
    rows = [model.row(0, model.initial, "initial_state")]
    old_t, old_y = 0., model.initial.copy()
    roche_crossings = []
    last_gap = old_y[0]*(1-old_y[1]) - model.roche
    while abs(old_t) < abs(end):
        derivative = model.rhs(old_t, old_y)
        # Prevent a BS trial from traversing the singular a=0 region before
        # detecting q=Rstar. Shorten output and trial steps near rapid decay.
        decay_step = 0.01 * old_y[0] / max(abs(derivative[0]), 1e-100)
        step = min(interval, cfg["max_step_year"], decay_step, abs(end-old_t))
        t = old_t + sign * step
        solver.sim.integrator.max_dt = step
        solver.sim.dt = sign * min(abs(solver.sim.dt), step)
        y = solver.advance(t)
        q = y[0]*(1-y[1])
        if sign > 0 and q <= model.radius(t):
            lo, hi = old_t, float(t)
            while hi - lo > cfg["event_tolerance_year"]:
                mid = (lo + hi)/2
                trial = ReboundBS(model, old_t, old_y).advance(mid)
                if trial[0]*(1-trial[1]) > model.radius(mid):
                    lo = mid
                else:
                    hi = mid
            final = ReboundBS(model, old_t, old_y).advance(hi)
            rows.append(model.row(hi, final, "stellar_engulfment"))
            return rows, dict(termination_reason="stellar_engulfment", event_bracket_year=[lo, hi],
                             roche_crossings=roche_crossings)
        gap = q - model.roche
        event = ""
        if gap * last_gap < 0:
            event = "roche_crossing_diagnostic"
            roche_crossings.append(dict(bracket_year=sorted([old_t, float(t)]),
                                        policy="continue_idealized_paper_model"))
        rows.append(model.row(t, y, event))
        old_t, old_y, last_gap = float(t), y, gap
    return rows, dict(termination_reason="integration_end", roche_crossings=roche_crossings)


def reference_solution(model, times, tolerance=1e-11):
    """Independent DOP853 solution evaluated at the BS output times."""
    from scipy.integrate import solve_ivp
    sol = solve_ivp(model.rhs, (0., float(times[-1])), model.initial, method="DOP853",
                    t_eval=times, rtol=tolerance, atol=tolerance,
                    max_step=model.config["integration"]["max_step_year"])
    if not sol.success or sol.y.shape[1] != len(times):
        raise RuntimeError(sol.message)
    return sol.y.T
