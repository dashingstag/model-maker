"""Drop-in check — validate dist/<goal>/ against a bare Godot project.

  python tools/dropin_check.py <goal>

Copies godot/assets/ + dist/<goal>/scene.tscn into a temp project with
a minimal project.godot, runs scene_probe to instance the scene and
snap a frame. Proves the package works standalone — no reliance on the
source project's .godot caches or pipeline paths. Temp dir is removed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = json.load(open(os.path.join(ROOT, "tools", "env.json")))


def main(goal):
    dist = os.path.join(ROOT, "dist", goal)
    tscn = os.path.join(dist, "scene.tscn")
    if not os.path.exists(tscn):
        sys.exit(f"{goal}: no scene.tscn — run export_scene.py first")
    with tempfile.TemporaryDirectory(prefix="dropin_") as tmp:
        open(os.path.join(tmp, "project.godot"), "w").write(
            '[application]\nconfig/name="dropin_check"\n'
            'run/main_scene="res://scene.tscn"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
        shutil.copytree(os.path.join(ROOT, "godot", "assets"),
                        os.path.join(tmp, "assets"))
        shutil.copyfile(tscn, os.path.join(tmp, "scene.tscn"))
        os.makedirs(os.path.join(tmp, "scripts"))
        shutil.copyfile(os.path.join(ROOT, "godot", "scripts",
                                   "scene_probe.gd"),
                        os.path.join(tmp, "scripts", "scene_probe.gd"))
        # import pass first — a fresh project has no .godot/ cache and
        # the copied .import sidecars point at it; same step publish runs
        subprocess.run([ENV["godot"], "--path", tmp, "--import"],
                       capture_output=True, text=True, timeout=300)
        snap = os.path.join(tmp, "dropin.png")
        r = subprocess.run(
            [ENV["godot"], "--path", tmp, "-s",
             "res://scripts/scene_probe.gd", "--",
             os.path.abspath(os.path.join(tmp, "scene.tscn")), snap],
            capture_output=True, text=True, timeout=300)
        out = r.stdout + r.stderr
        keep = os.path.join(dist, "dropin_probe.png")
        ok = (os.path.exists(snap)
              and "Parse Error" not in out and "Failed loading" not in out)
        if ok:
            shutil.copyfile(snap, keep)
        print(out[-1200:])
        print(f"{goal}: drop-in {'PASS -> ' + keep if ok else 'FAIL'}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1])
