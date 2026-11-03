"""Stage 0: decompose a goal brief into component folders.

  python tools/scaffold.py briefs/<goal>.brief.json

- Resolves @<kind>/<name> refs against shared/ and models.json
- Skips components already certified in the library (reuse-first)
- Creates pipeline/components/<id>/ with a brief.json slice per uncertified
  component, and pipeline/composition/<goal>/
"""
import json, os, sys
from pipelib import FileLock, LockHeld, atomic_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPES = {"sprite", "sprite_variant", "ui_image", "parallax", "glb"}
# fields compared when deciding whether a certified component satisfies a
# new brief's request (requested ⊆ certified)
CONSTRAINT_KEYS = ("type", "h_px", "pivot", "anims", "poses", "tri_budget",
                   "factor", "collision", "method", "of")
LOCK_WAIT = 30  # seconds to wait for a component lock before reporting held


def constraint_mismatch(man, req):
    """None if the certified manifest satisfies the requested constraints."""
    cert = man.get("constraints") or man
    for k in CONSTRAINT_KEYS:
        if k in req and k in cert and req[k] != cert[k]:
            return f"{k}: brief wants {req[k]!r}, certified has {cert[k]!r}"
    return None

def load(p):
    return json.load(open(os.path.join(ROOT, p)))

def resolve_ref(ref):
    """@<kind>/<name> -> shared/<kind>/<name>.json contents"""
    kind, name = ref[1:].split("/", 1)
    return load(f"shared/{kind}/{name}.json")

def main(brief_path):
    brief = load(brief_path)
    goal = brief["goal"]

    style = resolve_ref(brief["style"])
    palette = resolve_ref(brief["palette"])
    rig = resolve_ref(brief["composition"]["lighting_rig"])
    models = load("models.json")

    errors = []
    for c in brief["components"]:
        if c["type"] not in TYPES:
            errors.append(f"{c['id']}: unknown type {c['type']}")
    for key in ("checkpoints", "controlnets", "matting"):
        if key not in models:
            errors.append(f"models.json missing {key}")
    if errors:
        sys.exit("scaffold gate FAILED:\n  " + "\n  ".join(errors))

    created, reused, held, conflicts = [], [], [], []
    for c in brief["components"]:
        cid = c["id"]
        cdir = os.path.join(ROOT, "pipeline", "components", cid)
        try:
            lock = FileLock(cdir + ".lock", owner=f"{goal}:scaffold",
                            timeout=LOCK_WAIT).acquire()
        except LockHeld as e:
            held.append(f"{cid} (owner: {e.owner})")
            continue
        try:
            mpath = os.path.join(cdir, "manifest.json")
            if os.path.exists(mpath):
                man = json.load(open(mpath))
                if man.get("status") == "certified":
                    bad = constraint_mismatch(man, c)
                    if bad is None:
                        reused.append(cid)
                        continue
                    conflicts.append(f"{cid}: {bad} — request a new id or --recertify")
                    continue
            # uncertified: check whether another goal already claimed it
            bpath = os.path.join(cdir, "brief.json")
            if os.path.exists(bpath):
                prior = json.load(open(bpath)).get("goal")
                if prior and prior != goal:
                    held.append(f"{cid} (claimed by goal '{prior}')")
                    continue
            for sub in ("candidates", "accepted", "processed", "unit_render"):
                os.makedirs(os.path.join(cdir, sub), exist_ok=True)
            slice_ = dict(c)
            slice_["goal"] = goal
            slice_["style"] = style
            slice_["palette"] = palette
            atomic_json(bpath, slice_)
            created.append(cid)
        finally:
            lock.release()

    comp_dir = os.path.join(ROOT, "pipeline", "composition", goal)
    os.makedirs(comp_dir, exist_ok=True)
    with FileLock(comp_dir + ".lock", owner=f"{goal}:scaffold",
                  timeout=LOCK_WAIT):
        atomic_json(os.path.join(comp_dir, "spec.json"),
                    {"goal": goal, "rig": rig,
                     "shots": brief["composition"]["shots"],
                     "layout": brief["composition"].get("layout", {}),
                     "components": [c["id"] for c in brief["components"]]})

    print(f"goal={goal}  created={created}  reused(certified)={reused}")
    if held or conflicts:
        for h in held: print("  held:", h)
        for x in conflicts: print("  conflict:", x)
        sys.exit(1)

if __name__ == "__main__":
    main(sys.argv[1])
