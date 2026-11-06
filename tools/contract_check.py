"""Contract check — the executable half of brief must_have/must_not.

  python tools/contract_check.py <cid>

must_have/must_not are certification gates, not prompt text (WORKFLOW.md).
The mechanically verifiable subset is declared in brief.json:

    "contract": {
      "palette_check": ["ribbon_red", ...],   # palette color names:
          # sprite -> must cover >= PALETTE_MIN opaque px across
          #   processed/ sprites (catches wrong colorways — a teal disk
          #   where crimson silk was briefed)
          # glb    -> must appear within material baseColorFactors or
          #   embedded texture pixels (sampled)
      "aspect_min": 1.5, "aspect_max": 4.0,   # h/w of the subject:
          # sprite -> opaque bbox on the largest-area processed sprite
          # glb    -> POSITION accessor min/max model AABB
          # (catches shape swaps — round medallion vs vertical staff)
      "glb": {
        "bones": ["hand.r", ...],   # joint names in the skin
        "anims": ["idle", ...],     # clip names
        "nodes": ["blade_tip", ...],# node names (sockets/markers)
        "textures_min": 1           # embedded images
      }
    }

Semantic checks the contract cannot express (pose intent, "wings",
hands holding props) still require the vision gate's human/actor
review — this tool does not claim to replace them.

Writes unit_render/contract.json atomically; `vision.py certify`
refuses when pass is false. Exit 0 on all-pass, 1 otherwise.
"""
import glob
import io
import json
import os
import struct
import sys

from pipelib import atomic_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PALETTE_MIN = 0.002      # opaque-pixel fraction a declared color needs
PALETTE_TOL = 48         # max per-channel abs diff counting as a match
ASPECT_PAD = 0.04        # bbox margin for antialiased edges
TEX_SAMPLE = 64          # stride sample of embedded texture pixels


def _hex_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def _palette(brief, cid, want):
    cols = dict(brief.get("palette", {}).get("colors", {}))
    if not cols:
        name = brief.get("palette", {}).get("name", "")
        p = os.path.join(ROOT, "shared", "palettes", name + ".json")
        if os.path.exists(p):
            cols = json.load(open(p)).get("colors", {})
    missing = [c for c in want if c not in cols]
    if missing:
        sys.exit(f"{cid}: palette_check names not in palette: {missing}")
    return cols


def _match(r, g, b, rgb):
    return (abs(r - rgb[0]) <= PALETTE_TOL and abs(g - rgb[1]) <= PALETTE_TOL
            and abs(b - rgb[2]) <= PALETTE_TOL)


def _sprite_metrics(d, targets):
    """Opaque-bbox aspect of the largest-area sprite + per-target opaque
    coverage fraction, unioned over processed/ sprites."""
    from PIL import Image
    files = sorted(f for p in ("processed/*.png", "processed/*/*.png")
                   for f in glob.glob(os.path.join(d, p))
                   if not f.endswith("_n.png"))
    best_area, best_aspect, opaque_tot = -1, None, 0
    hit = {t: 0 for t in targets}
    for f in files:
        im = Image.open(f).convert("RGBA")
        px, (w, h) = im.load(), im.size
        mn_x, mn_y, mx_x, mx_y, opq = w, h, -1, -1, 0
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if a < 32:
                    continue
                opq += 1
                mn_x = min(mn_x, x); mx_x = max(mx_x, x)
                mn_y = min(mn_y, y); mx_y = max(mx_y, y)
                for t, rgb in targets.items():
                    if _match(r, g, b, rgb):
                        hit[t] += 1
        if opq:
            opaque_tot += opq
            bw, bh = mx_x - mn_x + 1, mx_y - mn_y + 1
            if bw * bh > best_area:
                best_area, best_aspect = bw * bh, bh / float(bw)
    cov = {t: (hit[t] / opaque_tot if opaque_tot else 0.0)
           for t in targets}
    return best_aspect, cov, files


def _glb(path):
    with open(path, "rb") as f:
        magic, _ver, _ln = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:
            return None, b""
        clen, ctype = struct.unpack("<II", f.read(8))
        g = json.loads(f.read(clen))
        bin_ = b""
        if f.read(1):                       # second chunk may not exist
            f.seek(-1, 1)
            hdr = f.read(8)
            if len(hdr) == 8:
                blen, _bt = struct.unpack("<II", hdr)
                bin_ = f.read(blen)
    return g, bin_


def _glb_metrics(d, targets):
    glbs = glob.glob(os.path.join(d, "export", "*.glb"))
    if not glbs:
        return None, None
    g, bin_ = _glb(glbs[0])
    names = {n.get("name", "") for n in g.get("nodes", [])}
    joints = set()
    for sk in g.get("skins", []):
        joints |= {g["nodes"][j].get("name", "") for j in sk.get("joints", [])}
    anims = {a.get("name", "") for a in g.get("animations", [])}
    # model AABB from POSITION accessor min/max (meters)
    mn, mx = [1e9] * 3, [-1e9] * 3
    for m in g.get("meshes", []):
        for pr in m.get("primitives", []):
            acc = g["accessors"][pr["attributes"]["POSITION"]]
            for i in range(3):
                mn[i] = min(mn[i], acc["min"][i])
                mx[i] = max(mx[i], acc["max"][i])
    aspect = ((mx[1] - mn[1]) / max(1e-6, mx[0] - mn[0])
              if mn[0] < 1e8 else None)
    # palette candidates: baseColorFactors + sampled embedded texture px
    cov = {t: 0.0 for t in targets}
    for t, rgb in targets.items():
        for m in g.get("materials", []):
            cf = m.get("pbrMetallicRoughness", {}) \
                .get("baseColorFactor", [1, 1, 1, 1])
            c8 = tuple(int(round(v * 255)) for v in cf[:3])
            if _match(*c8, rgb):
                cov[t] = 1.0
    if bin_ and any(v < 1.0 for v in cov.values()):
        from PIL import Image
        views = g.get("bufferViews", [])
        for img in g.get("images", []):
            bv = img.get("bufferView")
            if bv is None:
                continue
            v = views[bv]
            data = bin_[v.get("byteOffset", 0): v.get("byteOffset", 0)
                        + v["byteLength"]]
            try:
                im = Image.open(io.BytesIO(data)).convert("RGBA")
            except Exception:
                continue
            px, (w, h) = im.load(), im.size
            step = max(1, min(w, h) // TEX_SAMPLE)
            tot = hit = 0
            for y in range(0, h, step):
                for x in range(0, w, step):
                    r, gg, b, a = px[x, y]
                    if a < 32:
                        continue
                    tot += 1
                    for t, rgb in targets.items():
                        if cov[t] < 1.0 and _match(r, gg, b, rgb):
                            hit += 1
            # a declared color counts present when it covers >= PALETTE_MIN
            # of sampled texture pixels
            if tot:
                frac = hit / tot
                for t in targets:
                    if cov[t] < 1.0:
                        cov[t] = max(cov[t], frac)
    meta = {"names": names, "joints": joints, "anims": anims,
            "n_images": len(g.get("images", []))}
    return (aspect, cov, meta), glbs[0]


def run(cid):
    d = os.path.join(ROOT, "pipeline", "components", cid)
    brief = json.load(open(os.path.join(d, "brief.json")))
    con = brief.get("contract", {})
    checks = []

    want_colors = con.get("palette_check", [])
    want_aspect = "aspect_min" in con or "aspect_max" in con
    gcon = con.get("glb", {})
    if want_colors or want_aspect or gcon:
        cols = _palette(brief, cid, want_colors)
        targets = {n: _hex_rgb(cols[n]) for n in want_colors if n in cols}
        is_glb = bool(glob.glob(os.path.join(d, "export", "*.glb")))
        if is_glb:
            res, glb_path = _glb_metrics(d, targets)
            if res is None:
                checks.append({"id": "glb_export", "pass": False,
                               "note": "no export/*.glb"})
                aspect, cov, meta = None, {}, {}
            else:
                aspect, cov, meta = res
        else:
            aspect, cov, meta = None, {}, None
            files = glob.glob(os.path.join(d, "processed", "**", "*.png"),
                              recursive=True)
            files = [f for f in files if not f.endswith("_n.png")]
            if not files:
                checks.append({"id": "processed", "pass": False,
                               "note": "no processed/*.png"})
            else:
                aspect, cov, files = _sprite_metrics(d, targets)
        for n in want_colors:
            c = cov.get(n, 0.0)
            checks.append({"id": f"palette:{n}", "pass": c >= PALETTE_MIN,
                           "value": round(c, 5), "target": PALETTE_MIN})
        if want_aspect and aspect is not None:
            lo, hi = con.get("aspect_min"), con.get("aspect_max")
            ok = (lo is None or aspect >= lo * (1 - ASPECT_PAD)) and \
                 (hi is None or aspect <= hi * (1 + ASPECT_PAD))
            checks.append({"id": "aspect", "pass": ok,
                           "value": round(aspect, 3), "target": [lo, hi]})
        if is_glb and res is not None:
            for b in gcon.get("bones", []):
                checks.append({"id": f"bone:{b}",
                               "pass": b in meta["joints"]})
            for a_ in gcon.get("anims", []):
                checks.append({"id": f"anim:{a_}", "pass": a_ in meta["anims"]})
            for nn in gcon.get("nodes", []):
                checks.append({"id": f"node:{nn}", "pass": nn in meta["names"]})
            tmin = gcon.get("textures_min")
            if tmin is not None:
                checks.append({"id": "textures", "pass": meta["n_images"] >= tmin,
                               "value": meta["n_images"], "target": tmin})

    if not checks:
        out = {"cid": cid, "pass": None,
               "note": "no contract declared — semantic review only"}
    else:
        out = {"cid": cid,
               "pass": all(c.get("pass") is not False for c in checks),
               "checks": checks}
    os.makedirs(os.path.join(d, "unit_render"), exist_ok=True)
    atomic_json(os.path.join(d, "unit_render", "contract.json"), out)
    print(json.dumps(out, indent=2))
    return 0 if out["pass"] is not False else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
