"""Vision gate — the named-executor step. Persists every verdict.

  python tools/vision.py sheet   <cid>            # contact sheet -> reports/contact/<cid>.png
  python tools/vision.py checklist <cid>          # print the checklist to review
  python tools/vision.py record  <cid> --verdict pass|fail|needs_human
                                 --actor "<who>" [--check "item=pass|fail" ...]
                                 [--flag "<text>" ...] [--note "<text>"]
  python tools/vision.py certify <cid>            # manifest -> certified (gated)

Checklist = brief must_have/must_not + per-type items. `record` writes
unit_render/vision.json atomically; `certify` refuses unless vision passed
(or a manifest waiver exists) and every manifest gate is true.
"""
import argparse, glob, json, os, sys, time
from pipelib import FileLock, atomic_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPE_CHECKS = {
    "sprite": ["on-model across all poses (same face/outfit/props)",
               "no halo or fringe against the lit backdrop",
               "feet pivot sits on the ground line",
               "normal-map lighting reads correctly in lit.png"],
    "sprite_variant": ["recolor confined to the declared regions",
                       "skin/face/hat untouched", "each variant distinct",
                       "family resemblance to base"],
    "ui_image": ["subject centered and uncropped", "readable at dialogue size"],
    "parallax": ["no characters or text in the layer",
                 "colors stay in palette under the rig"],
    "glb": ["materials not washed out", "animations play without clipping",
            "within tri budget"],
}

def cdir(cid):
    return os.path.join(ROOT, "pipeline", "components", cid)

def checklist(cid):
    b = json.load(open(os.path.join(cdir(cid), "brief.json")))
    items = list(TYPE_CHECKS.get(b["type"], []))
    items += [f"has: {x}" for x in b.get("must_have", [])]
    items += [f"absent: {x}" for x in b.get("must_not", [])]
    return items

def sheet(cid):
    from PIL import Image
    d = cdir(cid)
    pats = ["processed/*.png", "processed/*/sprite_*.png", "unit_render/*.png",
            "unit_render/*/*.png"]
    files = [f for p in pats for f in sorted(glob.glob(os.path.join(d, p)))
             if not f.endswith("_n.png")]
    if not files:
        sys.exit(f"{cid}: nothing to review")
    ims = []
    for f in files:
        im = Image.open(f).convert("RGBA")
        im.thumbnail((360, 360))
        ims.append(im)
    w = sum(i.width for i in ims) + 8 * len(ims)
    h = max(i.height for i in ims)
    cols = max(1, min(len(ims), 6))
    rows = (len(ims) + cols - 1) // cols
    cw = max(i.width for i in ims) + 8
    out = Image.new("RGBA", (cols * cw, rows * (h + 8)), (46, 46, 58, 255))
    for k, im in enumerate(ims):
        out.alpha_composite(im, ((k % cols) * cw, (k // cols) * (h + 8)))
    os.makedirs(os.path.join(ROOT, "reports", "contact"), exist_ok=True)
    path = os.path.join(ROOT, "reports", "contact", f"{cid}.png")
    out.save(path)
    print(path)
    for f in files:
        print("  ", os.path.relpath(f, d))

def record(cid, a):
    d = cdir(cid)
    checks = {}
    for c in a.check or []:
        k, _, v = c.rpartition("=")
        checks[k] = v
    missing = [i for i in checklist(cid) if i not in checks]
    if a.verdict == "pass" and missing:
        sys.exit(f"{cid}: pass requires every checklist item; missing: {missing}")
    if a.verdict == "pass" and any(v != "pass" for v in checks.values()):
        sys.exit(f"{cid}: pass with failing checks — use fail/needs_human")
    files = sorted(os.path.relpath(f, d).replace("\\", "/")
                   for f in glob.glob(os.path.join(d, "unit_render", "**", "*.png"),
                                      recursive=True))
    os.makedirs(os.path.join(d, "unit_render"), exist_ok=True)
    rec = {"verdict": a.verdict, "actor": a.actor, "ts": time.time(),
           "checks": checks, "flags": a.flag or [], "note": a.note,
           "reviewed_files": files}
    with FileLock(d + ".lock", owner=f"vision:{a.actor}", timeout=30):
        atomic_json(os.path.join(d, "unit_render", "vision.json"), rec)
        mp = os.path.join(d, "manifest.json")
        if a.verdict != "pass" and os.path.exists(mp):
            m = json.load(open(mp))
            # fail demotes to processed (loop to earliest broken stage);
            # needs_human blocks until a person decides
            m["status"] = "needs_human" if a.verdict == "needs_human" else "processed"
            m.setdefault("history", []).append(
                {"rev": m.get("rev"), "ts": time.time(), "status": m["status"],
                 "reason": a.note or "; ".join(a.flag or [])})
            atomic_json(mp, m)
    print(f"{cid}: vision {a.verdict} by {a.actor}")

def certify(cid):
    d = cdir(cid)
    with FileLock(d + ".lock", owner="vision:certify", timeout=30):
        mp = os.path.join(d, "manifest.json")
        m = json.load(open(mp))
        vp = os.path.join(d, "unit_render", "vision.json")
        v = json.load(open(vp)) if os.path.exists(vp) else {}
        if v.get("verdict") != "pass" and not m.get("waiver"):
            sys.exit(f"{cid}: cannot certify — vision verdict '{v.get('verdict')}'")
        bad = [g for g, ok in m.get("gate", {}).items() if ok is False]
        if bad and not m.get("waiver"):
            sys.exit(f"{cid}: cannot certify — failing gates {bad}")
        m["status"] = "certified"
        m["certified"] = {"ts": time.time(), "by": v.get("actor")}
        atomic_json(mp, m)
    print(f"{cid}: certified (rev {m.get('rev')})")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sheet", "checklist", "record", "certify"])
    ap.add_argument("cid")
    ap.add_argument("--verdict", choices=["pass", "fail", "needs_human"])
    ap.add_argument("--actor", default="human")
    ap.add_argument("--check", action="append")
    ap.add_argument("--flag", action="append")
    ap.add_argument("--note")
    a = ap.parse_args()
    if a.cmd == "sheet": sheet(a.cid)
    elif a.cmd == "checklist": print("\n".join(checklist(a.cid)))
    elif a.cmd == "record":
        if not a.verdict: sys.exit("--verdict required")
        record(a.cid, a)
    else: certify(a.cid)
