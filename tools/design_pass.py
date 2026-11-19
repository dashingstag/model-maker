"""Design pass — texture-space repaint for regions whose generated
design reads as empty or wrong. Works per-triangle in UV space,
keyed on model-space position (the shell-cloud's islands scatter
across the whole atlas, so UV-region bboxes are meaningless).

    python tools/design_pass.py <in.glb> <out.glb>

Passes:
  * cape — the back shell is a featureless blue balloon. Rasterize
    each cape tri, color by model height: light shoulder -> deep
    indigo hem, plus a darker trim band at the hem edge. Real
    gradient fabric, not a flat fill.
  * face — the painted face is a smear buried inside the hood, and
    it bleeds onto the head's BACKFACES through the hood opening
    (#84). Geometric cards carry the face now, so the face tris get
    repainted to hood-lining blue: smear gone, backface blob gone.
"""
import io
import json
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

ARGV = sys.argv[1:]
SRC, OUT = ARGV[0], ARGV[1]

# palette (xianxia indigo family)
CAPE_TOP = np.array([0.42, 0.52, 0.72])   # shoulder — cool steel blue
CAPE_BOT = np.array([0.16, 0.20, 0.38])   # hem — deep indigo
CAPE_TRIM = np.array([0.10, 0.12, 0.28])  # trim band
HOOD_INNER = np.array([0.34, 0.40, 0.55]) # face repaint — hood lining


def load_glb(path):
    d = open(path, "rb").read()
    jl = struct.unpack("<I", d[12:16])[0]
    return d, json.loads(d[20:20 + jl]), 20 + jl + 8


def acc(gltf, d, bo, ai):
    a = gltf["accessors"][ai]
    bv = gltf["bufferViews"][a["bufferView"]]
    off = bo + bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    dt = {5126: np.float32, 5123: np.uint16, 5125: np.uint32,
          5121: np.uint8}[a["componentType"]]
    nc = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    return np.frombuffer(d, dt, a["count"] * nc, off).reshape(a["count"], nc)


def rebuild(d, g, bo, bvi, raw):
    payload = d[bo:]
    out = bytearray()
    for i, b in enumerate(g["bufferViews"]):
        out += b"\x00" * ((4 - len(out) % 4) % 4)
        off, ln = b.get("byteOffset", 0), b["byteLength"]
        r = raw if i == bvi else payload[off:off + ln]
        b["byteOffset"] = len(out)
        b["byteLength"] = len(r)
        out += r
    out += b"\x00" * ((4 - len(out) % 4) % 4)
    g["buffers"][0]["byteLength"] = len(out)
    bch = struct.pack("<II", len(out), 0x004E4942) + bytes(out)
    js = json.dumps(g, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    jch = struct.pack("<II", len(js), 0x4E4F534A) + js
    open(OUT, "wb").write(
        b"glTF" + struct.pack("<II", 2, 12 + len(jch) + len(bch))
        + jch + bch)


def main():
    d, g, bo = load_glb(SRC)
    mi = max(range(len(g["meshes"])), key=lambda i: sum(
        g["accessors"][p["indices"]]["count"]
        for p in g["meshes"][i]["primitives"]))
    pr = g["meshes"][mi]["primitives"][0]
    pos = acc(g, d, bo, pr["attributes"]["POSITION"])
    nrm = acc(g, d, bo, pr["attributes"]["NORMAL"])
    uv = acc(g, d, bo, pr["attributes"]["TEXCOORD_0"])
    idx = acc(g, d, bo, pr["indices"]).reshape(-1)

    img_ref = g["images"][g["textures"][g["materials"][0][
        "pbrMetallicRoughness"]["baseColorTexture"]["index"]]["source"]]
    bv = g["bufferViews"][img_ref["bufferView"]]
    raw = d[bo + bv.get("byteOffset", 0):
            bo + bv.get("byteOffset", 0) + bv["byteLength"]]
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    W, H = im.size
    dr = ImageDraw.Draw(im)

    y = pos[:, 1]

    def paint(mask, color_of, votes=3):
        """mask: per-vert bool. color_of(tri_mean_pos)->rgb tuple.
        Rasterizes tris with >=votes masked verts into the atlas."""
        tv = mask[idx].reshape(-1, 3).sum(axis=1) >= votes
        tris = idx.reshape(-1, 3)[tv]
        done = 0
        for t in tris:
            pts = [(float(uv[i, 0] * W), float(uv[i, 1] * H)) for i in t]
            # skip degenerate/wrap-around islands (uv jumps > 0.5)
            us = [p[0] for p in pts]; vs = [p[1] for p in pts]
            if max(us) - min(us) > W * 0.5 or max(vs) - min(vs) > H * 0.5:
                continue
            col = color_of(pos[t].mean(axis=0))
            dr.polygon(pts, fill=tuple(int(c * 255) for c in col))
            done += 1
        return done

    # cape: strong back-facing normals, mid-upper body
    cape_mask = (nrm[:, 2] < -0.5) & (y > 0.9) & (y < 2.25)
    ylo, yhi = y[cape_mask].min(), y[cape_mask].max()

    # cape width vs height — edge trim must be relative to the local
    # silhouette, not a global x threshold (the cape flares downward)
    cy = y[cape_mask]
    cx = np.abs(pos[:, 0])[cape_mask]
    bins = np.linspace(ylo, yhi, 25)
    edge_x = np.zeros(24)
    for b in range(24):
        sel = (cy >= bins[b]) & (cy < bins[b + 1])
        edge_x[b] = cx[sel].max() if sel.any() else 0.0
    for b in range(24):  # fill empty buckets from neighbors
        if edge_x[b] == 0:
            edge_x[b] = edge_x[max(0, b - 1)]

    def cape_col(p):
        t = np.clip((p[1] - ylo) / max(yhi - ylo, 1e-3), 0, 1)
        b = min(23, int(t * 24))
        if edge_x[b] > 0 and abs(p[0]) > edge_x[b] * 0.80:
            return CAPE_TRIM          # silhouette border trim
        if t < 0.16 or t > 0.94:
            return CAPE_TRIM          # hem + shoulder trim
        col = CAPE_BOT + (CAPE_TOP - CAPE_BOT) * ((t - 0.16) / 0.84)
        for lo, hi in ((0.40, 0.46), (0.70, 0.76)):
            if lo < t < hi:           # seam bands — layered mantle
                col = col * 0.82
        return col

    n1 = paint(cape_mask, cape_col)
    print("design_pass: cape tris repainted:", n1)

    # upper head: unify to hood blue — the white spiky crown reads as
    # noise from behind and its stray face-texel islands keep leaking.
    # Gold circlet sits at |x|>0.35, outside the repaint bound
    hood_mask = (y > 2.28) & (pos[:, 2] > 0.05) \
        & (np.abs(pos[:, 0]) < 0.38)
    n0 = paint(hood_mask, lambda p: HOOD_INNER, votes=2)
    print("design_pass: hood tris repainted:", n0)

    # face mask: position, not normals — recessed mouth shells tilt
    # below the normal threshold and leak through. Everything in the
    # face volume goes hood-blue: the painted face AND the hood-front
    # shells (uniform mask) AND their backfaces through the opening
    # chin/mouth smear sits lower than the eyes (~2.1-2.25); the
    # x-bound keeps the chest embroidery out of the repaint
    face_mask = (y > 1.95) & (pos[:, 2] > 0.28) \
        & (np.abs(pos[:, 0]) < 0.26)
    n2 = paint(face_mask, lambda p: HOOD_INNER, votes=2)
    print("design_pass: face tris repainted:", n2)

    # strays: face-texture islands scattered outside the face volume
    # (hood-top dot, side-edge smear). Inside the head region only,
    # repaint tris whose CURRENT texel reads skin-pink — leaves the
    # hood's white/blue shells and the hands (below y=2.0) untouched
    head_mask = (y > 1.8) & (np.abs(pos[:, 0]) < 0.62) \
        & (pos[:, 2] > -0.10) & (pos[:, 2] < 0.75)
    tv = head_mask[idx].reshape(-1, 3).sum(axis=1) >= 1
    px = np.asarray(im, dtype=np.float32) / 255.0

    def warm(c):
        return (c[0] - c[2] > 0.08) and (c[0] - c[1] > 0.02)

    def skin_or_red(c):
        # pink/tan skin AND saturated red share G~B; vivid gold has
        # G>>B so it fails — but no gold exists at |x|<0.35 anyway
        return warm(c) and (c[1] - c[2] < 0.20)

    stray = []
    for t in idx.reshape(-1, 3)[tv]:
        pts = [(float(uv[i, 0] * W), float(uv[i, 1] * H)) for i in t]
        us = [p[0] for p in pts]; vs = [p[1] for p in pts]
        if max(us) - min(us) > W * 0.5 or max(vs) - min(vs) > H * 0.5:
            continue
        samps = [(np.mean(us), np.mean(vs))] + list(zip(us, vs))
        cols = [px[min(H - 1, int(sv)), min(W - 1, int(su))]
                for su, sv in samps]
        mx = abs(pos[t][:, 0]).max()
        if mx < 0.35:
            go = any(skin_or_red(c) for c in cols)
        else:
            # side band: skin and pauldron tris interleave. Pale
            # skin separates from muted dark-gold on brightness —
            # need >=2 pale-warm samples (a gold-straddling tri
            # gets outvoted instead of vetoed)
            go = sum(1 for c in cols if warm(c)
                     and c.max() - c.min() < 0.40
                     and c[0] > 0.45) >= 2
        if go:
            dr.polygon(pts, fill=tuple(int(x * 255) for x in HOOD_INNER))
            stray.append(t)
    print("design_pass: stray face-texel tris repainted:", len(stray))

    buf = io.BytesIO()
    fmt = "JPEG" if img_ref.get("mimeType") == "image/jpeg" else "PNG"
    im.save(buf, fmt, quality=95) if fmt == "JPEG" else im.save(buf, fmt)
    rebuild(d, g, bo, img_ref["bufferView"], buf.getvalue())
    print("design_pass ->", OUT)


main()
