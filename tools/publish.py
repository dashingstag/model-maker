"""Publish processed component assets into the Godot project and write the
harness job file. Rule: godot/assets is a build artifact (always regenerated).

  python tools/publish.py <goal>
"""
import json, os, sys, shutil, subprocess
from pipelib import FileLock, LockHeld, atomic_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT = os.path.join(ROOT, "godot")
ENV = json.load(open(os.path.join(ROOT, "tools", "env.json")))
GEXE = ENV["godot"]

def pub_tree(src, dst):
    """Atomic-ish swap: build beside dst, then two renames.
    Readers may see dst absent for microseconds — never a torn tree."""
    tmp, old = dst + ".new", dst + ".old"
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    shutil.copytree(src, tmp)
    if os.path.isdir(dst):
        if os.path.isdir(old):
            shutil.rmtree(old)
        os.rename(dst, old)
    os.rename(tmp, dst)
    shutil.rmtree(old, ignore_errors=True)

def main(goal):
    comp_dir = os.path.join(ROOT, "pipeline", "composition", goal)
    spec = json.load(open(os.path.join(comp_dir, "spec.json")))
    rig = spec["rig"]
    assets = os.path.join(GODOT, "assets", "components")
    unit_jobs = []

    for cid in spec["components"]:
        cdir = os.path.join(ROOT, "pipeline", "components", cid)
        man_path = os.path.join(cdir, "manifest.json")
        if not os.path.exists(man_path):
            print(f"SKIP {cid}: no manifest"); continue
        man = json.load(open(man_path))
        t = man["type"]
        if t == "sprite_variant":
            for v in man["variants"]:
                pub_tree(os.path.join(cdir, "processed", v),
                         os.path.join(assets, "crew", v))
            continue
        dst = os.path.join(assets, cid)
        pub_tree(os.path.join(cdir, "processed"), dst)
        uj = {"id": cid, "type": t,
              "assets": f"res://assets/components/{cid}",
              "out": os.path.join(cdir, "unit_render")}
        if t == "sprite":
            uj["h_px"] = man.get("h_px", 384)
        unit_jobs.append(uj)

    layers = []
    for cid in spec["components"]:
        mpath = os.path.join(ROOT, "pipeline", "components", cid, "manifest.json")
        if not os.path.exists(mpath): continue
        man = json.load(open(mpath))
        if man["type"] == "parallax":
            # later (higher-factor) layers sit lower so hero layers stay visible
            y_off = 380 if man["factor"] >= 0.5 else 0
            layers.append({"id": cid, "factor": man["factor"],
                           "min_visible_pct": man.get("min_visible_pct"),
                           "y_off": y_off})
    layers.sort(key=lambda L: L["factor"])

    job = {"mode": "all", "out_dir": comp_dir, "rig": rig,
           "unit_jobs": unit_jobs,
           "composition": {"components_dir": "res://assets/components",
                           "layout": spec.get("layout", {}),
                           "layers": layers, "shots": spec["shots"],
                           "shot_expect": spec.get("shot_expect", {}),
                           "action_shots": spec.get("action_shots", [])}}
    job_path = os.path.join(comp_dir, "jobs.json")
    atomic_json(job_path, job)
    print("published ->", assets)
    print("job ->", job_path)

if __name__ == "__main__":
    goal = sys.argv[1]
    comp_dir = os.path.join(ROOT, "pipeline", "composition", goal)
    wait = int(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 0
    locks = []
    try:
        # order: goal lock first, then project publish lock (deadlock-free
        # single ordering — the only multi-holder in the pipeline)
        locks.append(FileLock(comp_dir + ".lock",
                              owner=f"{goal}:publish", timeout=wait).acquire())
        locks.append(FileLock(os.path.join(GODOT, ".publish.lock"),
                              owner=f"{goal}:publish", timeout=wait).acquire())
        main(goal)
    except LockHeld as e:
        sys.exit(str(e))
    finally:
        for l in reversed(locks):
            l.release()
