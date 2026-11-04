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
import hashlib, json, os, sys, shutil, subprocess, time, uuid
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
                vtype = ("ui_image" if os.path.exists(
                            os.path.join(cdir, "processed", v, "portrait.png"))
                         else "sprite")
                unit_jobs.append({"id": f"{cid}/{v}", "type": vtype,
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

    # resolve placement into an explicit members list — the runner renders
    # what it's told instead of knowing the scene's cast
    layout = spec.get("layout", {})
    row_list = layout.get("rows", [{"id": "front", "y": 648}])
    rows = {r["id"]: r["y"] for r in row_list}
    row_ids = list(rows)
    spacing = layout.get("spacing_px", 170)
    briefs = {}
    for cid in spec["components"]:
        bp = os.path.join(ROOT, "pipeline", "components", cid, "brief.json")
        if os.path.exists(bp):
            briefs[cid] = json.load(open(bp))

    members, auto, first_sprite = [], 0, None
    for cid in spec["components"]:
        man, b = mans.get(cid), briefs.get(cid, {})
        if not man or man["type"] != "sprite" or b.get("prop"):
            continue
        if first_sprite is None:
            first_sprite = cid
        row = layout.get(f"{cid}_row", row_ids[0])
        x = layout.get(f"{cid}_x")
        if x is None:
            auto += 1
            x = 140 + auto * spacing
        poses = [p.get("name") if isinstance(p, dict) else p
                 for p in b.get("poses", ["idle"])]
        members.append({"id": cid, "kind": "sprite",
                        "dir": f"res://assets/components/{cid}",
                        "x": x, "row": row, "y": rows.get(row, 648),
                        "h_px": man.get("h_px", 384),
                        "walk": b.get("walk") or [p for p in poses if str(p).startswith("walk")],
                        "patrol": False})
    patroller = layout.get("patroller") or first_sprite
    for m in members:
        m["patrol"] = m["id"] == patroller

    # variants: "cast" deploy joins the scene (crew-style); "swap" stays library
    v_i = 0
    for cid, vids in variants.items():
        if briefs.get(cid, {}).get("deploy", "cast") == "swap":
            continue
        row = layout.get(f"{cid}_row", row_ids[-1])
        for v in vids:
            v_i += 1
            members.append({"id": f"{cid}/{v}", "kind": "variant",
                            "dir": f"res://assets/components/{cid}/{v}",
                            "x": 140 + (v_i + auto) * spacing, "row": row,
                            "y": rows.get(row, 560), "h_px": 360})

    # ui_images: grid-placed cards, or the dialogue portrait
    grid, cards = layout.get("grid", {}), layout.get("cards", [])
    cols = max(1, int(grid.get("cols", 3)))
    gx, gy = grid.get("origin", [24, 60])
    cw, ch, gap = grid.get("card_w", 300), grid.get("card_h", 500), grid.get("gap", 14)
    grid_w = cols * cw + (cols - 1) * gap
    for i, cid in enumerate(cards):
        if cid in mans and mans[cid]["type"] == "ui_image":
            # short last row: center it within the declared grid width
            row_i, n = i // cols, min(cols, len(cards) - (i // cols) * cols)
            cx = gx + (grid_w - (n * cw + (n - 1) * gap)) / 2 if grid.get("center") else gx
            members.append({"id": cid, "kind": "ui",
                            "dir": f"res://assets/components/{cid}",
                            "x": cx + (i % cols) * (cw + gap),
                            "y": gy + row_i * (ch + gap),
                            "w": cw, "h": ch})
    dialogue = layout.get("dialogue") or next(
        (c for c in spec["components"]
         if c in mans and mans[c]["type"] == "ui_image" and c not in cards), None)

    # glbs: emitted for provenance; runner reports placement not_implemented
    for cid in spec["components"]:
        if cid in mans and mans[cid]["type"] == "glb" and not briefs.get(cid, {}).get("prop"):
            row = layout.get(f"{cid}_row", row_ids[0])
            members.append({"id": cid, "kind": "glb",
                            "dir": f"res://assets/components/{cid}",
                            "glb": glbs.get(cid),
                            "x": layout.get(f"{cid}_x", 512),
                            "row": row, "y": rows.get(row, 648)})

    layers = []
    for cid, man in mans.items():
        if man["type"] == "parallax":
            # later (higher-factor) layers sit lower so hero layers stay visible;
            # brief y_off overrides the legacy 380 heuristic
            layers.append({"id": cid, "factor": man["factor"],
                           "min_visible_pct": man.get("min_visible_pct"),
                           "y_off": briefs.get(cid, {}).get(
                               "y_off", 380 if man["factor"] >= 0.5 else 0)})
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
                           "members": members, "dialogue": dialogue,
                           "layers": layers, "shots": spec["shots"],
                           "variants": variants, "glbs": glbs,
                           "shot_expect": spec.get("shot_expect", {}),
                           "action_shots": spec.get("action_shots", [])}}
    job_path = os.path.join(comp_dir, "jobs.json")
    atomic_json(job_path, job)
    # regenerate .import sidecars inside the publish lock so the runner
    # (which waits on .publish.lock) never reads unimported textures
    env = json.load(open(os.path.join(ROOT, "tools", "env.json")))
    godot_exe = env.get("godot")
    if godot_exe and os.path.exists(godot_exe):
        subprocess.run([godot_exe, "--path", GODOT, "--import", "--quit"],
                       capture_output=True, timeout=600)
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
