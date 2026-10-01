import copy
import math
from pathlib import Path
import sys
import unittest

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from k2_261b.tides import JacksonModel, ReboundBS, integrate_bs, reference_solution
from k2_261b.physics import integrate_dop853
from k2_261b.ctl import ctl_average, nbody_probe, pseudo_sync_ratio


class TidesTests(unittest.TestCase):
    def setUp(self):
        self.config = yaml.safe_load((ROOT / "configs/reproductions/fig10_bs_forward.yaml").read_text())
        self.model = JacksonModel(self.config, ROOT)

    def test_si_equations_and_year_conversion(self):
        c, i = self.config["constants"], self.config["initial_conditions"]
        a, e = i["a_au"]*c["au_m"], i["e"]
        ms, mp = i["star_mass_Msun"]*c["Msun_kg"], i["planet_mass_Mjup"]*c["Mjup_kg"]
        rp, rs = i["planet_radius_Rjup"]*c["Rjup_m"], self.model.radius(0)*c["au_m"]
        A = math.sqrt(c["G_SI"]*ms**3)*rp**5/(32000*mp)
        B = math.sqrt(c["G_SI"]/ms)*rs**5*mp/1e6
        expected = [-a*(63/2*A*e**2+9/2*B*(1+57/4*e**2))*a**(-6.5)*c["year_seconds"]/c["au_m"],
                    -e*(63/4*A+225/16*B)*a**(-6.5)*c["year_seconds"]]
        np.testing.assert_allclose(self.model.rhs(0,self.model.initial), expected, rtol=2e-14)

    def test_planet_only_integral_and_circular_limit(self):
        cfg = copy.deepcopy(self.config)
        cfg["model"]["tides"]["q_prime_star"] = 1e100
        m = JacksonModel(cfg, ROOT)
        final = ReboundBS(m).advance(3e8)
        invariant = lambda y: math.log(y[0])-y[1]**2
        self.assertLess(abs(invariant(final)-invariant(m.initial)), 2e-10)
        np.testing.assert_allclose(m.rhs(0,[.1,0]),[0,0],atol=1e-100)

    def test_bs_and_independent_solver_both_directions(self):
        for end in [-2e8,2e8]:
            cfg = copy.deepcopy(self.config)
            cfg["integration"]["direction"] = "forward" if end>0 else "backward"
            m = JacksonModel(cfg, ROOT)
            times = np.linspace(0,end,21)
            solver = ReboundBS(m)
            actual = np.array([solver.advance(t) for t in times])
            np.testing.assert_allclose(actual, reference_solution(m,times), rtol=1e-8, atol=2e-10)

    def test_track_clamping_and_epoch(self):
        self.assertAlmostEqual(self.model.radius(-9e9),self.model.track[0,1]*self.model.rsun)
        self.assertAlmostEqual(self.model.radius(9e9),self.model.track[-1,1]*self.model.rsun)
        self.assertAlmostEqual(self.model.age+(-7.51e9)/1e9,1.)

    def test_invalid_initial_physics_is_rejected(self):
        for field,value in [("e",1.1),("planet_mass_Mjup",0),("a_au",float("nan"))]:
            cfg=copy.deepcopy(self.config)
            cfg["initial_conditions"][field]=value
            with self.assertRaises(ValueError):
                JacksonModel(cfg,ROOT)

    def test_engulfment_matches_independent_event(self):
        rows, metrics = integrate_bs(self.model)
        reference, _ = integrate_dop853(self.model)
        self.assertEqual(rows[-1]["event"],"stellar_engulfment")
        self.assertLess(abs(rows[-1]["t_year"]-reference[-1]["t_year"]),100.)
        self.assertLess(metrics["event_bracket_year"][1]-metrics["event_bracket_year"][0],10.)

    def test_ctl_local_limits_show_stellar_mismatch(self):
        m=self.model
        n=math.sqrt(m.G*(m.ms+m.mp)/m.initial[0]**3)
        loves=[.028,.37]
        lags=[.75/(loves[0]*n*m.qs),1.5/(loves[1]*n*m.qp)]
        e=.001
        spins=[0.,n*pseudo_sync_ratio(e)]
        planet,star=m.contributions(0,[m.initial[0],e])
        ratio=ctl_average(m,e,lags,loves,spins,"planet")/planet
        np.testing.assert_allclose(ratio,[1,1],atol=.001)
        ratio=ctl_average(m,e,lags,loves,spins,"star")/star
        self.assertAlmostEqual(ratio[0],1.,delta=.001)
        self.assertAlmostEqual(ratio[1],1.44,delta=.001)

    def test_reboundx_rates_against_source_quadrature(self):
        m=self.model
        n=math.sqrt(m.G*(m.ms+m.mp)/m.initial[0]**3)
        loves=[.028,.37]
        lags=[.75/(loves[0]*n*m.qs),1.5/(loves[1]*n*m.qp)]
        spins=[0.,n*pseudo_sync_ratio(.42)]
        ts,control,budget=nbody_probe(m,.42,lags,loves,spins,amplification=0)
        self.assertLess(budget["max_energy_relative_error"],1e-11)
        self.assertLess(budget["max_orbital_L_relative_change"],1e-11)
        ts,states,budget=nbody_probe(m,.42,lags,loves,spins,amplification=1e4)
        measured=np.polyfit(ts,states-control,1)[0]/1e4
        expected=ctl_average(m,.42,lags,loves,spins)
        np.testing.assert_allclose(measured,expected,rtol=5e-5)
        self.assertLess(budget["energy_final_relative_change"],0)


if __name__ == "__main__":
    unittest.main()
