"""Verify the installed library, including the Windows-adapted step wrappers."""
import ctypes
import math
import unittest

import rebound
import reboundx


def simulation():
    sim = rebound.Simulation()
    sim.add(m=1)
    sim.add(m=1e-3, a=1, e=0.1)
    sim.move_to_com()
    return sim


def state(sim):
    return tuple(getattr(p, key) for p in sim.particles for key in ("x", "y", "z", "vx", "vy", "vz"))


class TestMSVCAdaptation(unittest.TestCase):
    def test_ias15_and_kepler_steps(self):
        for name in ("ias15", "kepler"):
            with self.subTest(operator=name):
                sim = simulation()
                reference = simulation()
                reference.integrate(0.1)
                sim.integrator = "none"
                old_state = sim.integrator.state
                old_dt = sim.dt
                rebx = reboundx.Extras(sim)
                op = rebx.load_operator(name)
                op.step_function(ctypes.byref(sim), ctypes.byref(op), 0.1)
                sim.process_messages()
                for actual, expected in zip(state(sim), state(reference)):
                    self.assertAlmostEqual(actual, expected, delta=1e-13)
                self.assertEqual(sim.t, 0)
                self.assertEqual(sim.dt, old_dt)
                self.assertEqual(sim.integrator, "none")
                self.assertEqual(sim.integrator.state, old_state)

    def test_jump_and_interaction_steps(self):
        sim = simulation()
        sim.add(m=1e-3, a=1.7, e=0.2)
        sim.move_to_com()
        sim.integrator = "none"
        rebx = reboundx.Extras(sim)
        before = state(sim)
        jump = rebx.load_operator("jump")
        jump.step_function(ctypes.byref(sim), ctypes.byref(jump), 0.1)
        # Jacobi coordinates have no jump term.
        for actual, expected in zip(state(sim), before):
            self.assertAlmostEqual(actual, expected, delta=1e-14)
        interaction = rebx.load_operator("interaction")
        interaction.step_function(ctypes.byref(sim), ctypes.byref(interaction), 0.1)
        sim.process_messages()
        self.assertTrue(all(math.isfinite(value) for value in state(sim)))
        self.assertGreater(max(abs(a-b) for a, b in zip(state(sim), before)), 1e-7)
        self.assertEqual(sim.integrator, "none")

    def test_gr_full_and_spline(self):
        sim = simulation()
        rebx = reboundx.Extras(sim)
        gr = rebx.load_force("gr_full")
        gr.params["c"] = 1e4
        rebx.add_force(gr)
        sim.integrate(10)
        self.assertTrue(all(math.isfinite(value) for value in state(sim)))
        spline = reboundx.Interpolator(rebx, [0, 1, 2, 3], [1, 3, 5, 7], "spline")
        self.assertAlmostEqual(spline.interpolate(rebx, 1.5), 4, delta=1e-14)

    def test_seeded_stochastic_forces(self):
        results = []
        seeds = []
        for _ in range(2):
            sim = simulation()
            sim.rand_seed = 42
            rebx = reboundx.Extras(sim)
            force = rebx.load_force("stochastic_forces")
            rebx.add_force(force)
            sim.particles[1].params["kappa"] = 1e-5
            sim.integrate(1)
            results.append(state(sim))
            seeds.append(sim.rand_seed)
        self.assertEqual(results[0], results[1])
        self.assertEqual(seeds[0], seeds[1])
        self.assertNotEqual(seeds[0], 42)


if __name__ == "__main__":
    print("REBOUND:", rebound.__version__)
    print("REBOUNDx:", reboundx.__version__)
    print("Upstream commit:", reboundx.__githash__)
    print("Installed DLL:", reboundx.__libpath__)
    unittest.main(verbosity=2)
