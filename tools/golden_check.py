"""Golden diff — compare fresh composition shots to golden/<goal>/.

  python tools/golden_check.py <goal> [--write] [--max-changed 0.02]
                                      [--tol 24] [--shots a,b]

Per-shot metric: fraction of pixels whose per-channel abs diff exceeds
--tol. A shot passes when changed_px fraction <= --max-changed. Text/ui
shots churn legitimately (font rasterization) — exclude via --shots or
raise --max-changed per goal. --write blesses the current shots into
golden/<goal>/ (use after verified changes, not to silence regressions).
"""
import json
import os
import sys

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def diff(a_path, b_path, tol):
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    if a.size != b.size:
        return {"changed": 1.0, "note": f"size {a.size} != {b.size}"}
    d = ImageChops.difference(a, b)
    w, h = d.size
    px = d.load()
    changed = sum(
        1 for y in range(h) for x in range(w)
        if max(px[x, y]) > tol)
    return {"changed": changed / (w * h)}


def main(goal, write, max_changed, tol, only):
    comp = os.path.join(ROOT, "pipeline", "composition", goal, "shots")
    gold = os.path.join(ROOT, "golden", goal)
    if write:
        os.makedirs(gold, exist_ok=True)
        n = 0
        for f in sorted(os.listdir(comp)):
            if f.endswith(".png"):
                Image.open(os.path.join(comp, f)).save(
                    os.path.join(gold, f))
                n += 1
        print(f"{goal}: blessed {n} golden shots")
        return
    names = only or sorted(
        f for f in os.listdir(gold) if f.endswith(".png"))
    report = {"goal": goal, "shots": {}}
    worst = 0.0
    for name in names:
        gp, cp = os.path.join(gold, name), os.path.join(comp, name)
        if not os.path.exists(cp):
            report["shots"][name] = {"pass": None, "note": "no fresh shot"}
            continue
        r = diff(cp, gp, tol)
        r["pass"] = r.get("changed", 1.0) <= max_changed
        worst = max(worst, r.get("changed", 0.0))
        report["shots"][name] = r
    report["pass"] = all(s.get("pass") is not False
                         for s in report["shots"].values())
    report["worst_changed"] = round(worst, 4)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["pass"] else 1)


if __name__ == "__main__":
    only = (sys.argv[sys.argv.index("--shots") + 1].split(",")
            if "--shots" in sys.argv else None)
    only = [n if n.endswith(".png") else n + ".png" for n in only] if only else None
    main(sys.argv[1], "--write" in sys.argv,
         float(sys.argv[sys.argv.index("--max-changed") + 1])
         if "--max-changed" in sys.argv else 0.02,
         int(sys.argv[sys.argv.index("--tol") + 1])
         if "--tol" in sys.argv else 24,
         only)
