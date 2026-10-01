"""REBOUNDx CTL diagnostics against its local C source and Jackson rates.

No universal Q-prime/lag conversion is asserted. Lags use explicit local
low-e calibrations: circular stellar da, and pseudo-synchronous planetary
de at e->0. Spin and Love numbers are diagnostic assumptions.
"""
import math
import time

import numpy as np

from .records import append_rows, create_run, finish_run, read_config, validate_run
from .tides import JacksonModel


def pseudo_sync_ratio(e):
    return (1+7.5*e**2+5.625*e**4+.3125*e**6)/((1+3*e**2+.375*e**4)*(1-e**2)**1.5)


def ctl_average(model, e, lags, loves, spins, which="both", samples=16384):
    """Quadrature of dissipative acceleration in vendor CTL C source.

    Uses exact two-body reduced specific energy/angular momentum and averages
    with dt/dE. Conservative static tide is intentionally excluded here.
    """
    a = model.initial[0]
    mu = model.G*(model.ms+model.mp)
    n = math.sqrt(mu/a**3)
    E = np.arange(samples)*2*math.pi/samples
    c,s = np.cos(E),np.sin(E)
    w = 1-e*c
    r = np.column_stack([a*(c-e),a*math.sqrt(1-e**2)*s])
    v = np.column_stack([-a*n*s/w,a*n*math.sqrt(1-e**2)*c/w])
    r2 = np.sum(r*r,axis=1)
    rv = np.sum(r*v,axis=1)
    vt = v-r*(rv/r2)[:,None]
    acc = np.zeros_like(r)
    for index,ratio,radius,body in [(0,model.mp/model.ms,model.radius(0),"star"),
                                  (1,model.ms/model.mp,model.rp,"planet")]:
        if which not in {"both",body}:
            continue
        omega_cross_r = spins[index]*np.column_stack([-r[:,1],r[:,0]])
        coef = -3*mu*ratio*loves[index]*radius**5 / r2**4
        acc += (coef*lags[index])[:,None] * (3*r*(rv/r2)[:,None]+vt-omega_cross_r)
    energy=-mu/(2*a)
    h=math.sqrt(mu*a*(1-e**2))
    denergy=np.sum(v*acc,axis=1)
    dh=r[:,0]*acc[:,1]-r[:,1]*acc[:,0]
    da=2*a*a/mu*denergy
    de=(h*h*denergy+2*energy*h*dh)/(e*mu*mu)
    return np.array([np.mean(da*w),np.mean(de*w)])


def nbody_probe(model, e, lags, loves, spins, which="both", amplification=1., periods=64, tidal=True, epsilon=1e-10):
    import rebound
    import reboundx
    sim=rebound.Simulation()
    sim.G=model.G
    sim.integrator="ias15"
    sim.integrator.epsilon=epsilon
    sim.add(m=model.ms,r=model.radius(0))
    sim.add(m=model.mp,a=model.initial[0],e=e,r=model.rp,inc=0,Omega=0,omega=0,M=0)
    sim.move_to_com()
    rebx=None
    if tidal:
        rebx=reboundx.Extras(sim)
        rebx.add_force(rebx.load_force("tides_constant_time_lag"))
        for index,body in [(0,"star"),(1,"planet")]:
            if which in {"both",body}:
                p=sim.particles[index]
                p.params["tctl_k2"]=loves[index]
                p.params["tctl_tau"]=lags[index]*amplification
                p.params["OmegaMag"]=spins[index]
    energy0=sim.energy()+(rebx.tides_constant_time_lag_potential() if tidal else 0)
    L0=sim.angular_momentum().z
    period=sim.particles[1].orbit(primary=sim.particles[0]).P
    times=np.arange(periods+1)*period
    states=[]
    energy_errors=[]
    L_errors=[]
    for t in times:
        sim.integrate(float(t))
        orbit=sim.particles[1].orbit(primary=sim.particles[0])
        states.append([orbit.a,orbit.e])
        energy=sim.energy()+(rebx.tides_constant_time_lag_potential() if tidal else 0)
        energy_errors.append((energy-energy0)/abs(energy0))
        L_errors.append((sim.angular_momentum().z-L0)/abs(L0))
    return times,np.array(states),dict(max_energy_relative_error=float(max(abs(np.array(energy_errors)))),
        max_orbital_L_relative_change=float(max(abs(np.array(L_errors)))),
        energy_final_relative_change=float(energy_errors[-1]),L_final_relative_change=float(L_errors[-1]),
        period_year=float(period))


def execute_ctl(root,config_path):
    run=create_run(root,config_path,"reproductions")
    start=time.perf_counter()
    try:
        config=read_config(run/"config.yaml")
        if config["model"]["implementation"] != "reboundx_tides_constant_time_lag_diagnostic":
            raise ValueError("CTL diagnostics require their dedicated physical configuration")
        m=JacksonModel(config,run/"inputs/files")
        d=config["diagnostic"]
        n=math.sqrt(m.G*(m.ms+m.mp)/m.initial[0]**3)
        loves=d["love_numbers"]
        lags=d["lags_year"]
        rows=[]
        metrics={"quadrature":[],"nbody":[],"no_dissipation":[]}
        for e in d["eccentricity_grid"]:
            spins=[0.,n*pseudo_sync_ratio(e)]
            planet,star=m.contributions(0,[m.initial[0],e])
            for which,reference in [("star",star),("planet",planet),("both",star+planet)]:
                average=ctl_average(m,e,lags,loves,spins,which,samples=d.get("quadrature_samples",16384))
                metrics["quadrature"].append(dict(e=e,body=which,ctl_da_dt_au_year=float(average[0]),ctl_de_dt_year=float(average[1]),
                    jackson_da_dt_au_year=float(reference[0]),jackson_de_dt_year=float(reference[1]),
                    da_ratio=float(average[0]/reference[0]),de_ratio=float(average[1]/reference[1])))
        e=m.initial[1]
        spins=[0.,n*pseudo_sync_ratio(e)]
        for which in ["star","planet","both"]:
            times,control,conservation=nbody_probe(m,e,lags,loves,spins,which,amplification=0,periods=d["periods"],epsilon=config["integration"]["tolerance"])
            metrics["no_dissipation"].append(dict(kind="static_tide_tau_zero",body=which,**conservation))
            for j,(t,y) in enumerate(zip(times,control)):
                row=m.row(t,y,"ctl_tau_zero_control" if j==0 else "")
                row["stellar_radius_au"]=m.radius(0)
                row["body"]="control_"+which
                rows.append(row)
            for boost in d["amplifications"]:
                ts,states,budget=nbody_probe(m,e,lags,loves,spins,which,amplification=boost,periods=d["periods"],epsilon=config["integration"]["tolerance"])
                measured=np.polyfit(ts,states-control,1)[0]/boost
                expected=ctl_average(m,e,lags,loves,spins,which,samples=d.get("quadrature_samples",16384))
                metrics["nbody"].append(dict(body=which,amplification=boost,measured_da_dt_au_year=float(measured[0]),
                    measured_de_dt_year=float(measured[1]),relative_error=(measured/expected-1).tolist(),**budget))
                for j,(t,y) in enumerate(zip(ts,states)):
                    row=m.row(t,y,"amplified_ctl_diagnostic" if j==0 else "")
                    row["stellar_radius_au"]=m.radius(0)
                    row["body"]=f"ctl_{which}_{boost:g}"
                    rows.append(row)
        for e in [.42,.85]:
            ts,states,budget=nbody_probe(m,e,lags,loves,spins,tidal=False,periods=d["periods"],epsilon=config["integration"]["tolerance"])
            metrics["no_dissipation"].append(dict(kind="Newtonian",e=e,**budget))
            for j,(t,y) in enumerate(zip(ts,states)):
                row=m.row(t,y,"newtonian_control" if j==0 else "")
                row["stellar_radius_au"]=m.radius(0)
                row["body"]=f"newtonian_{e:g}"
                rows.append(row)
        metrics.update(wall_seconds=time.perf_counter()-start,physical_mapping_verified=False,
            conclusion="CTL_and_Jackson_not_equivalent_even_after_local_low_e_calibrations",
            amplification_note="Artificial diagnostic lag scaling to resolve tiny orbital drift; not physical Figure10 trajectories",
            budget_note="Fixed aligned spins act as angular momentum reservoirs; orbital L alone need not be conserved with dissipation")
        append_rows(run,rows)
        finish_run(run,"completed","short_CTL_mapping_diagnostic",metrics)
        validate_run(run)
    except BaseException as exc:
        finish_run(run,"failed",type(exc).__name__+": "+str(exc),{"wall_seconds":time.perf_counter()-start})
        raise
    return run
