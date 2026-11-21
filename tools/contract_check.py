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


_FACE_DROP = {"brow.l", "brow.r", "eye_hi.l", "eye_hi.r",
              "eye_iris.l", "eye_iris.r", "eye_pupil.l", "eye_pupil.r",
              "eye_sclera.l", "eye_sclera.r", "lips", "faceplate"}


def _acc(g, bin_, ai):
    import numpy as np
    a = g["accessors"][ai]
    bv = g["bufferViews"][a["bufferView"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    nc = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    dt = {5126: np.float32, 5123: np.uint16, 5125: np.uint32,
          5121: np.uint8}[a["componentType"]]
    return np.frombuffer(bin_, dt, a["count"] * nc, off).reshape(-1, nc)


def _world_pos(g, bin_, node_i):
    """POSITION accessor of node's mesh, pushed through the parent chain
    (TRS compose — enough for rigid bone-parented attachments)."""
    import numpy as np

    def trs(n):
        t = np.array(n.get("translation", [0, 0, 0]), dtype=np.float64)
        r = np.array(n.get("rotation", [0, 0, 0, 1]), dtype=np.float64)
        s = np.array(n.get("scale", [1, 1, 1]), dtype=np.float64)
        x, y, z, w = r
        R = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        return R, t, s

    parent = {}
    for i, n in enumerate(g["nodes"]):
        for c in n.get("children", []):
            parent[c] = i
    chain = [node_i]
    while chain[-1] in parent:
        chain.append(parent[chain[-1]])
    Rs, ts, ss = [], [], []
    for i in reversed(chain):
        R, t, s = trs(g["nodes"][i])
        Rs.append(R)
        ts.append(t)
        ss.append(s)

    def xform(v):
        p = np.asarray(v, dtype=np.float64)
        for R, t, s in zip(Rs, ts, ss):
            p = R @ (p * s) + t
        return p
    prims = g["meshes"][g["nodes"][node_i]["mesh"]]["primitives"]
    outs = []
    for p in prims:
        pos = _acc(g, bin_, p["attributes"]["POSITION"]).astype(np.float64)
        outs.append(np.apply_along_axis(xform, 1, pos))
    return np.vstack(outs)


def _face_box(g, bin_, fcon):
    """Resolve the face spec to a model-coord box (x0,x1,y0,y1)."""
    if "box_model" in fcon:
        bm = fcon["box_model"]
        return (bm["x"][0], bm["x"][1], bm["y"][0], bm["y"][1])
    # normalized fractions of the head band (verts in top 0.45m)
    import numpy as np
    allp = []
    for m in g["meshes"]:
        for p in m.get("primitives", []):
            if "POSITION" in p["attributes"]:
                allp.append(_acc(g, bin_, p["attributes"]["POSITION"]))
    P = np.vstack(allp)
    H = P[P[:, 1] > P[:, 1].max() - 0.45]
    bx, by = fcon["box"]["x"], fcon["box"]["y"]
    return (H[:, 0].min() + bx[0] * (H[:, 0].max() - H[:, 0].min()),
            H[:, 0].min() + bx[1] * (H[:, 0].max() - H[:, 0].min()),
            H[:, 1].min() + by[0] * (H[:, 1].max() - H[:, 1].min()),
            H[:, 1].min() + by[1] * (H[:, 1].max() - H[:, 1].min()))


def _face_checks(g, bin_, fcon):
    """Product-truth gate: a face EXISTS at the spec'd position, forward,
    unobstructed, right-sized, with painted features — the thing revs
    13-17 got past every technical check without having."""
    import numpy as np
    checks = []
    box = _face_box(g, bin_, fcon)
    x0, x1, y0, y1 = box
    face_i = next((i for i, n in enumerate(g["nodes"])
                   if n.get("name") == "face_mesh" and "mesh" in n), None)
    checks.append({"id": "face:node", "pass": face_i is not None,
                   "note": "canonical face mesh child of head"})
    if face_i is None:
        return checks
    parent = {}
    for i, n in enumerate(g["nodes"]):
        for c in n.get("children", []):
            parent[c] = i
    a = face_i
    under_head = False
    while a in parent:
        a = parent[a]
        if g["nodes"][a].get("name") == "head":
            under_head = True
            break
    checks.append({"id": "face:parent_head", "pass": under_head})
    mesh_names = {m.get("name", "") for m in g["meshes"]}
    checks.append({"id": "face:cards_gone",
                   "pass": bool(not (mesh_names & _FACE_DROP)),
                   "note": "card/plate meshes deleted"})
    fv = _world_pos(g, bin_, face_i)
    fmesh = g["meshes"][g["nodes"][face_i]["mesh"]]
    tris = []
    for p in fmesh["primitives"]:
        idx = _acc(g, bin_, p["indices"]).reshape(-1, 3)
        tris.append(fv[idx].mean(axis=1))
    fc = np.vstack(tris)
    pad = 0.10 * (x1 - x0)
    inb = (fc[:, 0] > x0 - pad) & (fc[:, 0] < x1 + pad) \
        & (fc[:, 1] > y0 - pad) & (fc[:, 1] < y1 + pad)
    frac = inb.mean()
    checks.append({"id": "face:tris_in_box", "pass": bool(frac >= 0.6),
                   "value": round(float(frac), 3), "target": 0.6})
    # occluders: shell tris in front of the face inside the opening
    ffront = fc[:, 2].max()
    occ = 0
    fi_mesh = g["nodes"][face_i]["mesh"]
    for mi, m in enumerate(g["meshes"]):
        if mi == fi_mesh:
            continue
        for p in m.get("primitives", []):
            if "indices" not in p:
                continue
            pos = _acc(g, bin_, p["attributes"]["POSITION"])
            idx = _acc(g, bin_, p["indices"]).reshape(-1, 3)
            c = pos[idx].mean(axis=1)
            eu = (c[:, 0] - (x0 + x1) / 2) / ((x1 - x0) / 2)
            ev = (c[:, 1] - (y0 + y1) / 2) / ((y1 - y0) / 2)
            occ += int(((eu * eu + ev * ev < 1.0)
                        & (c[:, 2] > ffront + 0.004)).sum())
    checks.append({"id": "face:occluders", "pass": bool(occ == 0),
                   "value": int(occ), "target": 0})
    # size: face width vs head-band width
    allp = []
    for m in g["meshes"]:
        for p in m.get("primitives", []):
            if "POSITION" in p["attributes"]:
                allp.append(_acc(g, bin_, p["attributes"]["POSITION"]))
    P = np.vstack(allp)
    hb = P[P[:, 1] > P[:, 1].max() - 0.45]
    ratio = (x1 - x0) / max(1e-6, hb[:, 0].max() - hb[:, 0].min())
    checks.append({"id": "face:width", "pass": bool(0.15 <= ratio <= 0.55),
                   "value": round(float(ratio), 3),
                   "target": [0.15, 0.55]})
    # features live in the face texture: iris-colored pixels exist
    feat_ok = False
    want = (fcon.get("colors") or {}).get("iris")
    if want:
        rgb = _hex_rgb(want)
        for img in g.get("images", []):
            if img.get("name") != "face_tex":
                continue
            bv = g["bufferViews"][img["bufferView"]]
            data = bin_[bv.get("byteOffset", 0):
                        bv.get("byteOffset", 0) + bv["byteLength"]]
            try:
                from PIL import Image
                im = Image.open(io.BytesIO(data)).convert("RGB")
                px = im.load()
                n = 0
                for yy in range(0, im.size[1], 4):
                    for xx in range(0, im.size[0], 4):
                        n += _match(*px[xx, yy], rgb)
                feat_ok = n >= 4
            except Exception:
                pass
    checks.append({"id": "face:texture_features", "pass": feat_ok,
                   "note": "iris-colored texels in face_tex"})
    return checks


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

    if brief.get("face"):
        glbs = glob.glob(os.path.join(d, "export", "*.glb"))
        if glbs:
            g2, bin2 = _glb(glbs[0])
            checks += _face_checks(g2, bin2, brief["face"])
        else:
            checks.append({"id": "face:glb", "pass": False,
                           "note": "no export/*.glb"})

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
