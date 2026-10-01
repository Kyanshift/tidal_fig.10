"""Recorded, bounded Figure 10 central-curve suite and approximate ensemble."""
import argparse
import copy
import csv
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from k2_261b.physics import execute
from k2_261b.records import read_rows, validate_run, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ensemble",type=int,default=0)
    parser.add_argument("--budget-seconds",type=float,default=180.)
    parser.add_argument("--label",default="fig10_stage1")
    parser.add_argument("--analyze",type=Path,help="Regenerate derived analysis only from an existing suite manifest")
    args = parser.parse_args()
    if args.analyze:
        analyze(args.analyze,json.loads((args.analyze/"runs.json").read_text()))
        return
    if not 0 <= args.ensemble <= 64:
        parser.error("Stage 1 ensemble budget is 0..64 paired samples")
    output = ROOT / "results/reproductions" / args.label
    output.mkdir(exist_ok=False)
    (output / "configs").mkdir()
    started = time.perf_counter()
    manifest = []
    def run(name, cfg):
        if time.perf_counter()-started > args.budget_seconds:
            raise RuntimeError("Suite wall budget exceeded before next run")
        cfg["experiment"]["name"] = name
        cfg["inputs"] += ["data/processed/fig10/central_curves.csv", "data/processed/fig10/digitization.json"]
        path = output / "configs" / (name+".yaml")
        path.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding="utf-8")
        result = execute(ROOT,path)
        manifest.append(dict(name=name,run=str(result.relative_to(ROOT)),config_sha256=sha256(result/"config.yaml")))
        (output/"runs.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
        print(name, result.name, flush=True)
        return result
    bases = {d:yaml.safe_load((ROOT/f"configs/reproductions/fig10_bs_{d}.yaml").read_text()) for d in ["backward","forward"]}
    for direction,base in bases.items():
        for solver in ["rebound_bs","scipy_dop853"]:
            cfg=copy.deepcopy(base)
            cfg["integration"]["integrator"]=solver
            run(f"legacy_{direction}_{solver}",cfg)
            cfg=copy.deepcopy(cfg)
            cfg["integration"].update(tolerance=1e-12,max_step_year=2.5e5,output_interval_year=2.5e5)
            run(f"legacy_{direction}_{solver}_fine",cfg)
        cfg=copy.deepcopy(base)
        cfg["initial_conditions"]["star_mass_Msun"]=1.104
        cfg["initial_conditions"]["note"]="Published Table 2/3 central values, operational Q-prime interpretation."
        cfg["model"]["tides"]["q_prime_planet"]=30000
        cfg["model"]["tides"]["mapping_status"]="provisional_interpretation_of_published_unprimed_Q"
        run(f"published_{direction}_rebound_bs",cfg)
        cfg=copy.deepcopy(base)
        cfg["integration"].update(integrator="legacy_euler",max_step_year=1e5,output_interval_year=1e5)
        run(f"legacy_{direction}_euler",cfg)
    # Approximate independent Gaussian marginals from the legacy script,
    # deliberately distinct from the missing true joint posterior.
    rng=np.random.default_rng(261001)
    for index in range(args.ensemble):
        while True:
            values = dict(zip(["star_mass_Msun","planet_mass_Mjup","planet_radius_Rjup","a_au","e","stellar_age_Gyr"],
                              rng.normal([1.101,.179,.840,.10376,.42,8.51],[.015,.020,.011,.0005,.03,.6])))
            if all(values[k]>0 for k in ["star_mass_Msun","planet_mass_Mjup","planet_radius_Rjup","a_au"]) and 0<values["e"]<1 and 1<values["stellar_age_Gyr"]<9.5:
                break
        for direction,base in bases.items():
            cfg=copy.deepcopy(base)
            cfg["initial_conditions"].update({k:float(v) for k,v in values.items()})
            age=float(values["stellar_age_Gyr"])
            cfg["integration"]["end_time_year"]=(.1-age)*1e9 if direction=="backward" else (9.8-age)*1e9
            cfg["seed"]=261001+index
            cfg["sampling"]={"kind":"approximate_independent_legacy_gaussian_marginals","draw_seed":261001,"sample_index":index,
                             "covariance":"unavailable_not_reconstructed","radius_policy":"common_unscaled_legacy_track; sampled_star_radius_unused",
                             "truncation":"positive_masses_radii_a; 0<e<1; 1<age<9.5", "source":"legacy/tidal/tidal.py"}
            run(f"approx_{index:03d}_{direction}",cfg)
    analyze(output,manifest)
    print(json.dumps(dict(output=str(output),wall_seconds=time.perf_counter()-started,runs=len(manifest)),indent=2))


def analyze(output, manifest):
    cache=ROOT/"tmp/matplotlib"
    cache.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR",str(cache))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    def load(item):
        run=ROOT/item["run"]
        validate_run(run)
        cfg=yaml.safe_load((run/"config.yaml").read_text())
        data=read_rows(run/"evolution.csv")
        age=cfg["initial_conditions"]["stellar_age_Gyr"]
        array=np.array([[age+float(r["t_year"])/1e9,*[float(r[k]) for k in ["a_au","e","pericentre_au","roche_limit_au","stellar_radius_au"]]] for r in data])
        array=array[np.argsort(array[:,0])]
        return array,json.loads((run/"summary.json").read_text())
    loaded={item["name"]:load(item) for item in manifest}
    central=np.vstack([loaded["legacy_backward_rebound_bs"][0][:-1],loaded["legacy_forward_rebound_bs"][0]])
    published=np.vstack([loaded["published_backward_rebound_bs"][0][:-1],loaded["published_forward_rebound_bs"][0]])
    fieldcols={"a_au":1,"e":2,"pericentre_au":3,"roche_limit_au":4,"stellar_radius_au":5}
    centre_run=ROOT/next(item["run"] for item in manifest if item["name"]=="legacy_backward_rebound_bs")
    point_source=centre_run/"inputs/files/data/processed/fig10/central_curves.csv"
    with point_source.open() as handle:
        points=list(csv.DictReader(handle))
    centre_config=yaml.safe_load((centre_run/"config.yaml").read_text())
    t=centre_config["acceptance"]["numerical_fig10_tolerance"]
    tolerances={f:t["e_absolute" if f=="e" else f+"_absolute"] for f in fieldcols}
    compare={}
    for field,col in fieldcols.items():
        target=np.array([[float(p["age_Gyr"]),float(p["value"])] for p in points if p["observable"]==field and float(p["age_Gyr"])<=9.2])
        residual=np.interp(target[:,0],central[:,0],central[:,col])-target[:,1]
        compare[field]=dict(count=len(target),max_absolute=float(abs(residual).max()),rms=float(np.sqrt(np.mean(residual**2))),
                            tolerance=tolerances[field],passed=bool(abs(residual).max()<=tolerances[field]))
    numerical={}
    for direction in ["backward","forward"]:
        base,summary=loaded[f"legacy_{direction}_rebound_bs"]
        for suffix in ["scipy_dop853","rebound_bs_fine","scipy_dop853_fine","euler"]:
            other,other_summary=loaded[f"legacy_{direction}_{suffix}"]
            lo=max(base[0,0],other[0,0]); hi=min(base[-1,0],other[-1,0])
            # Convergence comparisons at common interior 1-Myr times;
            # final event times are compared separately.
            x=np.arange(lo,hi-1e-3,.001)
            numerical[f"{direction}_{suffix}"]={field:float(abs(np.interp(x,base[:,0],base[:,col])-np.interp(x,other[:,0],other[:,col])).max()) for field,col in fieldcols.items()}
            if direction=="forward":
                numerical[f"{direction}_{suffix}"]["engulfment_time_difference_year"]=abs(summary["metrics"]["end_age_Gyr"]-other_summary["metrics"]["end_age_Gyr"])*1e9
    fig,(ax1,ax2)=plt.subplots(2,1,figsize=(9,9),sharex=True,layout="constrained")
    for name,(data,_) in loaded.items():
        if name.startswith("approx_"):
            ax1.plot(data[:,0],data[:,2],color=".35",alpha=.15,lw=.6)
            ax2.plot(data[:,0],data[:,1],color=".35",alpha=.15,lw=.6)
            ax2.plot(data[:,0],data[:,3],color="royalblue",alpha=.15,lw=.6)
            ax2.plot(data[:,0],data[:,4],color="crimson",alpha=.08,lw=.4)
    ax1.plot(central[:,0],central[:,2],color="#9a8700",lw=2,label="Legacy denominators: REBOUND BS")
    ax1.plot(published[:,0],published[:,2],color="#c45a1a",lw=1.4,ls="--",label="Published values: operational Q' mapping")
    ax1.scatter([8.51],[.42],color="crimson",s=22,zorder=5)
    ax2.scatter([8.51],[.10376],color="crimson",s=22,zorder=5)
    colors={"e":"black","a_au":"black","pericentre_au":"royalblue","roche_limit_au":"crimson","stellar_radius_au":"forestgreen"}
    for field,col in fieldcols.items():
        ax=ax1 if field=="e" else ax2
        if field!="e":
            ax.plot(central[:,0],central[:,col],color=colors[field],lw=1.8,label=field)
        pts=[p for p in points if p["observable"]==field and float(p["age_Gyr"])<=9.2]
        ax.scatter([float(p["age_Gyr"]) for p in pts],[float(p["value"]) for p in pts],s=9,facecolors="none",edgecolors=colors[field],alpha=.7,label="Published raster samples" if field=="e" else None)
    # Plot stellar track to its supplied end beyond planet termination.
    track=np.loadtxt(centre_run/"inputs/files/data/raw/stellar_tracks/CL002_14_Rs.txt")
    ax2.plot(track[:,0],track[:,1]*695700000/149597870700,color="forestgreen",lw=1.8)
    for ax in [ax1,ax2]:
        ax.axvline(8.51,color=".5",ls=":",lw=1)
        ax.set_xlim(.1,10.)
        ax.grid(alpha=.15)
        ax.legend(fontsize=8,loc="upper right" if ax==ax1 else "upper left")
    ax1.set_ylim(0,1); ax1.set_ylabel("Eccentricity")
    ax2.set_ylim(0,.25); ax2.set_ylabel("Distance [au]"); ax2.set_xlabel("Stellar age [Gyr]")
    n=sum(name.startswith("approx_") for name in loaded)//2
    fig.suptitle(f"K2-261 b / EPIC 201498078 - Figure 10 central-curve check\nJackson (2009) averaged equations; approximate ensemble n={n}; CTL mapping unverified",fontsize=12)
    fig.savefig(output/"fig10_comparison.png",dpi=180)
    fig.savefig(output/"fig10_comparison.svg")
    plt.close(fig)
    past={field:float(np.interp(1.,central[:,0],central[:,col])) for field,col in fieldcols.items()}
    past["pericentre_over_roche"]=past["pericentre_au"]/past["roche_limit_au"]
    numerical_passed=all(v["a_au"]<1e-5 and v["e"]<2e-5 and v.get("engulfment_time_difference_year",0)<100 for k,v in numerical.items() if "euler" not in k)
    report=dict(numerical_comparison=numerical,numerical_checks_passed=numerical_passed,
                numerical_tolerances={"a_au":1e-5,"e":2e-5,"event_year":100,"note":"includes output interpolation; Euler is historical comparison only"},
                digitized_central_comparison=compare,at_age_1_Gyr=past,
                engulfment=loaded["legacy_forward_rebound_bs"][1]["metrics"],
                published_engulfment=loaded["published_forward_rebound_bs"][1]["metrics"],
                central_raster_acceptance=all(p["passed"] for p in compare.values()),
                exact_joint_posterior_reproduction=False,full_REBOUNDx_physical_equivalence=False,
                ensemble_count=n,run_manifest_sha256=sha256(output/"runs.json"),
                analysis_script_sha256=sha256(Path(__file__)),digitized_snapshot_sha256=sha256(point_source),
                comparison_notes="Colour-mask calibration; tolerances apply 0.2..9.2 Gyr, near-singular endpoint visual only; convergence values include linear output interpolation.")
    (output/"comparison.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
