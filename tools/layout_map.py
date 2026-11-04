"""Layout map — render the resolved composition plan to a PNG.

  python tools/layout_map.py <goal>

Reads pipeline/composition/<goal>/jobs.json (publish's resolved members:
explicit x/y/h_px, patrol, layout.attach) + component manifest aspect,
draws labeled boxes on the 2x composition canvas ->
composition/<goal>/layout_map.png. Run after publish to eyeball the
plan before the harness spends GPU; overlaps/off-canvas jump out.
"""
import json
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _aspect(cid):
    mp = os.path.join(ROOT, "pipeline", "components", cid, "manifest.json")
    try:
        o = json.load(open(mp)).get("output", {})
        return o.get("w_px", 1) / max(o.get("h_px", 1), 1)
    except (OSError, ValueError):
        return 0.6


def main(goal):
    comp_dir = os.path.join(ROOT, "pipeline", "composition", goal)
    job = json.load(open(os.path.join(comp_dir, "jobs.json")))
    comp = job["composition"]
    W, H = 2560, 1440
    img = Image.new("RGB", (W, H), (22, 22, 30))
    dr = ImageDraw.Draw(img)
    for f in range(1, 10):  # parallax bands
        y = H // 2 - 400 + f * 90
        dr.line([0, y, W, y], fill=(30 + f * 3, 34, 40))
    members = comp.get("members", [])
    for m in members:
        kind = m.get("kind")
        if kind == "ui":
            w, h = m.get("w", 300), m.get("h", 400)
            x0, y0 = m.get("x", 0) - w // 2, m.get("y", 0) - h // 2
            dr.rectangle([x0, y0, x0 + w, y0 + h],
                         outline=(90, 160, 220), width=2)
            dr.text((x0 + 4, y0 + 4), m["id"], fill=(110, 190, 240))
        elif kind == "sprite":
            h = m.get("h_px", 384)
            w = int(h * _aspect(m["id"]))
            x, y = m["x"], m["y"]
            dr.rectangle([x - w // 2, y - h, x + w // 2, y],
                         outline=(210, 170, 60), width=2)
            dr.text((x - w // 2, y - h - 14), m["id"], fill=(230, 200, 90))
            if m.get("patrol") or "patrol" in comp.get("layout", {}):
                lay = comp.get("layout", {})
                rng = lay.get("patrol") or lay.get(m["id"] + "_patrol")
                if rng:
                    lo, hi = (rng["from_x"], rng["to_x"]) if isinstance(
                        rng, dict) else rng[:2]
                    dr.line([lo, y + 8, hi, y + 8], fill=(120, 210, 120),
                            width=3)
                    dr.text((lo, y + 14), "patrol", fill=(120, 210, 120))
        elif kind == "glb":
            x, y = m.get("x", W // 2), m.get("y", H // 2)
            dr.rectangle([x - 90, y - 200, x + 90, y],
                         outline=(200, 100, 220), width=2)
            dr.text((x - 86, y - 214), f"glb:{m['id']}", fill=(220, 130, 240))
    for p in comp.get("layout", {}).get("attach", []):
        host = next((m for m in members if m["id"] == p.get("to")), None)
        if host:
            ox, oy = p.get("offset", [0, 0])
            px, py = host["x"] + ox, host["y"] + oy
            dr.rectangle([px - 18, py - 18, px + 18, py + 18],
                         outline=(230, 110, 230))
            dr.text((px + 22, py - 8), p["prop"], fill=(230, 110, 230))
    shots = comp.get("shots", {})
    names = shots.keys() if isinstance(shots, dict) else shots
    dr.text((16, H - 28), "shots: " + ", ".join(names),
            fill=(120, 120, 140))
    out = os.path.join(comp_dir, "layout_map.png")
    img.save(out)
    print(f"{goal}: layout map -> {out}")


if __name__ == "__main__":
    main(sys.argv[1])
