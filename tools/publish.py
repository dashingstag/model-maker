"""Publish processed component assets into the Godot project and write the
harness job file. Rule: godot/assets is a build artifact (always regenerated).

  python tools/publish.py <goal> [--unit-only] [--wait S]

- Default (mode "all"): every component must be `certified`, otherwise
  exits — composition only runs on certified inputs.
- --unit-only (mode "unit"): publishes `processed`/`certified` components
  for C3 unit renders (the step that leads to certification).
Locks: composition/<goal>.lock -> godot/.publish.lock -> each component
lock (sorted) around its swap. Staging happens outside godot/ so Godot
never imports half-copied trees.
"""
import hashlib, json, os, sys, shutil, time, uuid
from pipelib import FileLock, LockHeld, atomic_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT = os.path.join(ROOT, "godot")
STAGING = os.path.join(ROOT, ".publish_staging")
PUBLISHABLE = {"processed", "certified"}

def _rename(src, dst, tries=30):
    """os.rename with backoff — Windows refuses while a file is open."""
    for i in range(tries):
        try:
            os.rename(src, dst); return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.1 * (i + 1))

def pub_tree(src, dst):
    """Copy into staging (same volume, outside godot/), then swap by rename.
    Keeps existing .import sidecars so uid:// refs survive content swaps."""
    os.makedirs(STAGING, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    tmp, old = os.path.join(STAGING, f"new-{tag}"), os.path.join(STAGING, f"old-{tag}")
    shutil.copytree(src, tmp)
    if os.path.isdir(dst):
        for dp, _, files in os.walk(dst):
            for f in files:
                if f.endswith(".import"):
                    rel = os.path.relpath(os.path.join(dp, f), dst)
                    target = os.path.join(tmp, rel)
                    if os.path.exists(target[:-len(".import")]):
                        shutil.copyfile(os.path.join(dp, f), target)
        _rename(dst, old)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    _rename(tmp, dst)
    shutil.rmtree(old, ignore_errors=True)

def main(goal, unit_only, wait):
    comp_dir = os.path.join(ROOT, "pipeline", "composition", goal)
    spec = json.load(open(os.path.join(comp_dir, "spec.json")))
    assets = os.path.join(GODOT, "assets", "components")
    mans, skipped = {}, []
    for cid in spec["components"]:
        mp = os.path.join(ROOT, "pipeline", "components", cid, "manifest.json")
        man = json.load(open(mp)) if os.path.exists(mp) else {}
        if man.get("status") in PUBLISHABLE:
            mans[cid] = man
        else:
            skipped.append(f"{cid} ({man.get('status', 'no manifest')})")
    uncertified = [c for c, m in mans.items() if m["status"] != "certified"]
    if not unit_only and (skipped or uncertified):
        sys.exit("composition blocked — not certified: "
                 + ", ".join(skipped + [f"{c} (processed)" for c in uncertified])
                 + "\n  use --unit-only for C3 unit renders")

    unit_jobs, variants, glbs = [], {}, {}
    for cid in sorted(mans):
        man = mans[cid]
        cdir = os.path.join(ROOT, "pipeline", "components", cid)
        with FileLock(cdir + ".lock", owner=f"{goal}:publish", timeout=wait):
            pub_tree(os.path.join(cdir, "processed"), os.path.join(assets, cid))
        t = man["type"]
        if t == "sprite_variant":
            variants[cid] = man["variants"]
            for v in man["variants"]:
                unit_jobs.append({"id": f"{cid}/{v}", "type": "sprite",
                                  "assets": f"res://assets/components/{cid}/{v}",
                                  "out": os.path.join(cdir, "unit_render", v),
                                  "h_px": 360})
            continue
        uj = {"id": cid, "type": t, "assets": f"res://assets/components/{cid}",
              "out": os.path.join(cdir, "unit_render")}
        if t == "sprite":
            uj["h_px"] = man.get("h_px", 384)
        if t == "glb":
            uj["glb"] = man.get("glb", "pirate.glb")
            glbs[cid] = uj["glb"]
        unit_jobs.append(uj)

    layers = []
    for cid, man in mans.items():
        if man["type"] == "parallax":
            # later (higher-factor) layers sit lower so hero layers stay visible
            layers.append({"id": cid, "factor": man["factor"],
                           "min_visible_pct": man.get("min_visible_pct"),
                           "y_off": 380 if man["factor"] >= 0.5 else 0})
    layers.sort(key=lambda L: L["factor"])

    manifest_sha = {}
    for cid in mans:
        mp = os.path.join(ROOT, "pipeline", "components", cid, "manifest.json")
        manifest_sha[cid] = "sha256:" + hashlib.sha256(open(mp, "rb").read()).hexdigest()
    job = {"mode": "unit" if unit_only else "all", "out_dir": comp_dir,
           "provenance": {"manifests": manifest_sha, "goal": goal},
           "rig": spec["rig"], "unit_jobs": unit_jobs,
           "composition": {"components_dir": "res://assets/components",
                           "layout": spec.get("layout", {}),
                           "layers": layers, "shots": spec["shots"],
                           "variants": variants, "glbs": glbs,
                           "shot_expect": spec.get("shot_expect", {}),
                           "action_shots": spec.get("action_shots", [])}}
    job_path = os.path.join(comp_dir, "jobs.json")
    atomic_json(job_path, job)
    if skipped:
        print("not published:", ", ".join(skipped))
    print("published ->", assets)
    print("job ->", job_path)

if __name__ == "__main__":
    goal = sys.argv[1]
    comp_dir = os.path.join(ROOT, "pipeline", "composition", goal)
    wait = int(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 0
    locks = []
    try:
        # fixed order: goal -> project publish lock -> component locks
        locks.append(FileLock(comp_dir + ".lock",
                              owner=f"{goal}:publish", timeout=wait).acquire())
        locks.append(FileLock(os.path.join(GODOT, ".publish.lock"),
                              owner=f"{goal}:publish", timeout=wait).acquire())
        main(goal, "--unit-only" in sys.argv, wait)
    except LockHeld as e:
        sys.exit(str(e))
    finally:
        for l in reversed(locks):
            l.release()
