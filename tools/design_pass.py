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

# palette — keyed to the accepted concept art (idle.png): open pale
# face, silver-white hair, dark jeweled crown, moonlit blue-white cape
CAPE_TOP = np.array([0.62, 0.70, 0.85])   # shoulder — misty moon-blue
CAPE_BOT = np.array([0.30, 0.38, 0.60])   # hem — pale indigo
CAPE_TRIM = np.array([0.14, 0.18, 0.38])  # trim band — navy accent
HAIR = np.array([0.82, 0.85, 0.92])       # silver-white hair
SKIN = np.array([0.83, 0.68, 0.60])       # pale face/neck skin
CROWN = np.array([0.10, 0.16, 0.30])      # dark jeweled crown
HOOD_INNER = np.array([0.34, 0.40, 0.55]) # unused legacy (mask pass)


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


def rebuild(d, g, bo, repl):
    """rebuild the BIN chunk; repl = {bufferView_idx: new_bytes}"""
    payload = d[bo:]
    out = bytearray()
    for i, b in enumerate(g["bufferViews"]):
        out += b"\x00" * ((4 - len(out) % 4) % 4)
        off, ln = b.get("byteOffset", 0), b["byteLength"]
        r = repl.get(i, payload[off:off + ln])
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

    # === head, matched to the concept art ===
    # Concept: open pale face framed by silver-white hair, dark
    # jeweled crown on top — NOT a hooded mask. Order: crown tip,
    # then face+neck skin core, then hair everywhere else on the head.
    crown_mask = (y > 2.50) & (np.abs(pos[:, 0]) < 0.20)
    n0 = paint(crown_mask, lambda p: CROWN, votes=2)
    print("design_pass: crown tris repainted:", n0)

    # face: the feature cards (eyes/brows/lips) sit ON the front
    # protrusion at y~2.42-2.51, z~0.58 — that surface IS the face.
    # Paint it skin around the cards; the mass hanging below the
    # chin stays hair-white and reads as a veil
    face_mask = (y > 2.30) & (y < 2.56) & (pos[:, 2] > 0.46) \
        & (np.abs(pos[:, 0]) < 0.24)
    neck_mask = (y > 1.88) & (y < 2.10) & (pos[:, 2] > 0.32) \
        & (np.abs(pos[:, 0]) < 0.18)
    n2 = paint(face_mask | neck_mask, lambda p: SKIN, votes=2)
    print("design_pass: face/neck tris repainted:", n2)

    # the recessed inner cavity (z~0.17-0.29) goes HAIR, not skin:
    # it's occluded from the front by the protrusion, but its
    # backfaces show through the opening from behind (#84) — a
    # white patch in white hair is invisible; a skin one is a bald
    # spot
    cavity_mask = (y > 2.02) & (y < 2.44) & (pos[:, 2] > 0.08) \
        & (pos[:, 2] < 0.46) & (np.abs(pos[:, 0]) < 0.24) \
        & ~face_mask
    n2b = paint(cavity_mask, lambda p: HAIR, votes=2)
    print("design_pass: cavity tris repainted:", n2b)

    # hair: the rest of the upper head — white-silver, absorbing the
    # spiky noise; gold circlet at |x|>0.35 stays outside the bound
    hair_mask = (y > 2.0) & (pos[:, 2] > 0.05) \
        & (np.abs(pos[:, 0]) < 0.38) \
        & ~(face_mask | neck_mask) & ~crown_mask
    n3 = paint(hair_mask, lambda p: HAIR, votes=2)
    print("design_pass: hair tris repainted:", n3)

    # strays: face-texture islands scattered outside the face volume
    # (hood-top dot, side-edge smear). Inside the head region only,
    # repaint tris whose CURRENT texel reads skin-pink — leaves the
    # hood's white/blue shells and the hands (below y=2.0) untouched
    # strays repaint skin-texel tris to HAIR — must not repaint the
    # just-painted face itself (SKIN reads as warm-pale)
    head_mask = (y > 1.8) & (np.abs(pos[:, 0]) < 0.62) \
        & (pos[:, 2] > -0.10) & (pos[:, 2] < 0.75) \
        & ~(face_mask | neck_mask)
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
            dr.polygon(pts, fill=tuple(int(x * 255) for x in HAIR))
            stray.append(t)
    print("design_pass: stray face-texel tris repainted:", len(stray))

    # seat the eyes mid-face: the cards ride high at the hairline
    # (placed for the hood look); shift eye/brow card bind verts
    # down so they sit on the face oval. Lips stays put — it's
    # correctly hidden behind the veil (beard read)
    repl = {img_ref["bufferView"]: None}  # placeholder, set below
    for m in g["meshes"]:
        nm = m.get("name", "")
        if not nm.startswith(("eye", "brow")):
            continue
        pa = g["accessors"][m["primitives"][0]["attributes"]["POSITION"]]
        bvi = pa["bufferView"]
        bv = g["bufferViews"][bvi]
        off = bo + bv.get("byteOffset", 0) + pa.get("byteOffset", 0)
        verts = np.frombuffer(d, np.float32, pa["count"] * 3, off) \
            .reshape(-1, 3).copy()
        verts[:, 1] -= 0.03
        raw_v = np.frombuffer(
            d, np.uint8, bv["byteLength"], bo + bv.get("byteOffset", 0)) \
            .copy()
        ao = pa.get("byteOffset", 0)
        raw_v[ao:ao + verts.nbytes] = np.frombuffer(
            verts.tobytes(), np.uint8)
        repl[bvi] = bytes(raw_v)
        print("design_pass: shifted", nm, "down 0.03")

    buf = io.BytesIO()
    fmt = "JPEG" if img_ref.get("mimeType") == "image/jpeg" else "PNG"
    im.save(buf, fmt, quality=95) if fmt == "JPEG" else im.save(buf, fmt)
    repl[img_ref["bufferView"]] = buf.getvalue()
    rebuild(d, g, bo, repl)
    print("design_pass ->", OUT)


main()
