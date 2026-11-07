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

try:
    from pixelmatch.contrib.PIL import pixelmatch as _pixelmatch
except ImportError:  # perceptual diff unavailable — raw channel fallback
    _pixelmatch = None


def diff(a_path, b_path, tol):
    a = Image.open(a_path).convert("RGBA")
    b = Image.open(b_path).convert("RGBA")
    if a.size != b.size:
        return {"changed": 1.0, "note": f"size {a.size} != {b.size}"}
    w, h = a.size
    if _pixelmatch:
        # OKLab perceptual distance + anti-aliased-pixel detection:
        # AA/font-rasterization noise no longer counts as drift.
        n = _pixelmatch(a, b, None, threshold=tol / 255.0,
                        diff_mask=True)
        return {"changed": n / (w * h)}
    d = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    px = d.load()
    changed = sum(
        1 for y in range(h) for x in range(w)
        if max(px[x, y]) > tol)
    return {"changed": changed / (w * h)}


def _dupes(path, names):
    """Groups of byte-identical shots — the decoy signature of an
    unresolved shot name capturing the same fallback frame."""
    import hashlib
    by_hash = {}
    for f in names:
        with open(os.path.join(path, f), "rb") as fh:
            by_hash.setdefault(hashlib.md5(fh.read()).hexdigest(),
                               []).append(f)
    return [g for g in by_hash.values() if len(g) > 1]


def main(goal, write, max_changed, tol, only):
    comp = os.path.join(ROOT, "pipeline", "composition", goal, "shots")
    gold = os.path.join(ROOT, "golden", goal)
    if write:
        os.makedirs(gold, exist_ok=True)
        names = sorted(f for f in os.listdir(comp) if f.endswith(".png"))
        for f in names:
            Image.open(os.path.join(comp, f)).save(
                os.path.join(gold, f))
        print(f"{goal}: blessed {len(names)} golden shots")
        for g in _dupes(comp, names):
            print(f"{goal}: WARNING byte-identical shots blessed: "
                  f"{', '.join(g)}")
        return
    names = only or sorted(
        f for f in os.listdir(gold) if f.endswith(".png"))
    report = {"goal": goal, "shots": {}}
    fresh = [f for f in names if os.path.exists(os.path.join(comp, f))]
    d = _dupes(comp, fresh)
    if d:
        report["dupes"] = d
    # a harness run that dies before writing shots leaves stale captures
    # that diff "clean" against old goldens — compare against jobs.json
    # (rewritten by every publish) so a failed run can never pass
    jobs = os.path.join(ROOT, "pipeline", "composition", goal, "jobs.json")
    jobs_t = os.path.getmtime(jobs) if os.path.exists(jobs) else 0
    worst = 0.0
    for name in names:
        gp, cp = os.path.join(gold, name), os.path.join(comp, name)
        if not os.path.exists(cp):
            report["shots"][name] = {"pass": None, "note": "no fresh shot"}
            continue
        if os.path.getmtime(cp) < jobs_t:
            report["shots"][name] = {
                "pass": None, "note": "stale shot (older than jobs.json)"}
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
