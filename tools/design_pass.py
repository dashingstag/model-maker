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
SKIN = np.array([0.86, 0.73, 0.65])       # pale face/neck skin
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
            col = tuple(int(c * 255) for c in color_of(pos[t].mean(axis=0)))
            if max(us) - min(us) < 1 and max(vs) - min(vs) < 1:
                # zero-area UV island (all verts share one texel):
                # a polygon fill draws nothing, so stamp a small disc
                cx_, cy_ = sum(us) / 3, sum(vs) / 3
                dr.ellipse([cx_ - 2, cy_ - 2, cx_ + 2, cy_ + 2], fill=col)
            else:
                dr.polygon(pts, fill=col)
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
    # jeweled crown on top — NOT a hooded mask.
    # Selection hulls for the soft passes — generous boxes around the
    # feature-card zone (cards span |x|<0.075, y 2.41-2.49 on the
    # front protrusion z~0.58)
    ax = np.abs(pos[:, 0])
    face_zone = (y > 2.24) & (y < 2.56) & (pos[:, 2] > 0.40) & (ax < 0.22)
    neck_zone = (y > 1.86) & (y < 2.14) & (pos[:, 2] > 0.28) & (ax < 0.16)

    # the recessed inner cavity (z~0.17-0.29) goes HAIR, not skin:
    # it's occluded from the front by the protrusion, but its
    # backfaces show through the opening from behind (#84) — a
    # white patch in white hair is invisible; a skin one is a bald
    # spot
    cavity_mask = (y > 2.02) & (y < 2.44) & (pos[:, 2] > 0.08) \
        & (pos[:, 2] < 0.42) & (ax < 0.24)
    n2b = paint(cavity_mask, lambda p: HAIR, votes=2)
    print("design_pass: cavity tris repainted:", n2b)

    # strays: face-texture islands scattered outside the head volume
    # (hood-top dot, side-edge smear). Inside the head region only,
    # repaint tris whose CURRENT texel reads skin-pink — leaves the
    # hood's white/blue shells and the hands (below y=2.0) untouched
    head_mask = (y > 1.8) & (np.abs(pos[:, 0]) < 0.62) \
        & (pos[:, 2] > -0.10) & (pos[:, 2] < 0.75) \
        & ~(face_zone | neck_zone)
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

    # ---- soft per-texel passes ----
    # Barycentric rasterizer with nearest-r texel ownership: several
    # surface tris can share the same atlas island, so each texel is
    # claimed by the covering tri whose interpolated position is
    # closest to the feature centre; its colour ramps hair->skin by
    # that closeness. The whole head region is repainted as ONE field
    # — inside the face oval it becomes shaded skin, outside it
    # silver hair — so no seams or stray islands can survive.
    px = np.asarray(im, dtype=np.float32) / 255.0
    bestr = np.full((H, W), 1e9, np.float32)
    # covmin_y[px] = lowest interpolated y among ALL tris covering the
    # texel — crown navy is only safe where every covering surface
    # lives in the crown zone (shared islands can't bleed to the face)
    covmin_y = np.full((H, W), 1e9, np.float32)
    # covcount[px] = how many tris cover the texel. Zero-coverage
    # texels are atlas GUTTERS: they keep whatever the generator
    # painted (the old face smear lives there) and mip/bilinear
    # filtering bleeds it onto the surface as blurry marks — the
    # persistent "painted brows" no tri-level fix could remove.
    covcount = np.zeros((H, W), np.int32)

    def covered(t):
        """yield (gy,gx,P) texels covered by tri t (disc for slivers)"""
        puv = uv[t] * np.array([W, H])
        us, vs = puv[:, 0], puv[:, 1]
        if us.max() - us.min() > W * 0.5 or vs.max() - vs.min() > H * 0.5:
            return
        a_, b_, c_ = puv
        den = ((b_[1] - c_[1]) * (a_[0] - c_[0])
               + (c_[0] - b_[0]) * (a_[1] - c_[1]))
        x0 = max(0, int(us.min()) - 1)
        x1 = min(W, int(us.max()) + 2)
        y0 = max(0, int(vs.min()) - 1)
        y1 = min(H, int(vs.max()) + 2)
        if x1 <= x0 or y1 <= y0 or abs(den) < 1e-8:
            cx_ = int(np.clip(us.mean(), 0, W - 1))
            cy_ = int(np.clip(vs.mean(), 0, H - 1))
            for yy in range(max(0, cy_ - 2), min(H, cy_ + 3)):
                for xx in range(max(0, cx_ - 2), min(W, cx_ + 3)):
                    yield yy, xx, pos[t].mean(axis=0)[None, :]
            return
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5,
                             np.arange(y0, y1) + 0.5)
        l0 = ((b_[1] - c_[1]) * (gx - c_[0])
              + (c_[0] - b_[0]) * (gy - c_[1])) / den
        l1 = ((c_[1] - a_[1]) * (gx - c_[0])
              + (a_[0] - c_[0]) * (gy - a_[1])) / den
        l2 = 1.0 - l0 - l1
        inside = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        if not inside.any():
            cx_ = int(np.clip(us.mean(), 0, W - 1))
            cy_ = int(np.clip(vs.mean(), 0, H - 1))
            for yy in range(max(0, cy_ - 2), min(H, cy_ + 3)):
                for xx in range(max(0, cx_ - 2), min(W, cx_ + 3)):
                    yield yy, xx, pos[t].mean(axis=0)[None, :]
            return
        pp = pos[t]
        P = (l0[..., None] * pp[0] + l1[..., None] * pp[1]
             + l2[..., None] * pp[2])
        yy, xx = np.nonzero(inside)
        yield y0 + yy, x0 + xx, P[inside]

    for t in idx.reshape(-1, 3):
        for yy, xx, P in covered(t):
            yy, xx = np.atleast_1d(yy), np.atleast_1d(xx)
            covmin_y[yy, xx] = np.minimum(covmin_y[yy, xx], P[:, 1])
            covcount[yy, xx] += 1

    def paint_soft(sel_mask, fill, votes=1):
        """fill(P)->(col,score); texel repainted when score < bestr."""
        sel = sel_mask[idx].reshape(-1, 3).sum(axis=1) >= votes
        done = 0
        for t in idx.reshape(-1, 3)[sel]:
            puv = uv[t] * np.array([W, H])
            us, vs = puv[:, 0], puv[:, 1]
            if us.max() - us.min() > W * 0.5 or vs.max() - vs.min() > H * 0.5:
                continue
            x0 = max(0, int(us.min()) - 1)
            x1 = min(W, int(us.max()) + 2)
            y0 = max(0, int(vs.min()) - 1)
            y1 = min(H, int(vs.max()) + 2)
            if x1 <= x0 or y1 <= y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5,
                                 np.arange(y0, y1) + 0.5)
            a_, b_, c_ = puv
            den = ((b_[1] - c_[1]) * (a_[0] - c_[0])
                   + (c_[0] - b_[0]) * (a_[1] - c_[1]))
            def stamp_point():
                # zero-area / sliver UV island (no pixel centres fall
                # inside the poly): stamp a small disc at the shared
                # texel, still gated by nearest-score ownership
                cx_ = int(np.clip(us.mean(), 0, W - 1))
                cy_ = int(np.clip(vs.mean(), 0, H - 1))
                col, score = fill(pos[t].mean(axis=0)[None, :],
                                  px[cy_, cx_][None, :])
                for yy in range(max(0, cy_ - 2), min(H, cy_ + 3)):
                    for xx in range(max(0, cx_ - 2), min(W, cx_ + 3)):
                        if score[0] < bestr[yy, xx]:
                            px[yy, xx] = col[0]
                            bestr[yy, xx] = score[0]

            if abs(den) < 1e-8:
                stamp_point()
                done += 1
                continue
            l0 = ((b_[1] - c_[1]) * (gx - c_[0])
                  + (c_[0] - b_[0]) * (gy - c_[1])) / den
            l1 = ((c_[1] - a_[1]) * (gx - c_[0])
                  + (a_[0] - c_[0]) * (gy - a_[1])) / den
            l2 = 1.0 - l0 - l1
            inside = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
            if not inside.any():
                stamp_point()
                done += 1
                continue
            pp = pos[t]
            P = (l0[..., None] * pp[0] + l1[..., None] * pp[1]
                 + l2[..., None] * pp[2])
            yy, xx = np.nonzero(inside)
            col, score = fill(P[inside], px[y0:y1, x0:x1][inside])
            gy_, gx_ = y0 + yy, x0 + xx
            better = score < bestr[gy_, gx_]
            px[gy_[better], gx_[better]] = col[better]
            bestr[gy_[better], gx_[better]] = score[better]
            done += 1
        return done

    def face_fill(P, base):
        """Skin oval centred on the card features with painterly
        shading; score = oval radius so the most face-like surface
        owns each texel."""
        x, yv, z = P[:, 0], P[:, 1], P[:, 2]
        # face sits in the hood opening, low-center of the head mass —
        # matches face_plate CX/CY/AX/AY (the plate covers the shell;
        # this oval is the skin surround at its edges)
        r = np.sqrt((x / 0.095) ** 2 + ((yv - 2.360) / 0.088) ** 2)
        w = np.clip((1.15 - r) / 0.38, 0.0, 1.0)
        w = w * w * (3.0 - 2.0 * w)          # smoothstep edge
        # z-gate: skin lives on the protrusion front (z>0.5); the
        # recessed cavity (z<0.36) is hair — its backfaces show
        # through the hood opening from behind and skin reads as a
        # brown blob (#84). Smooth ramp, not a hard gate: the bumpy
        # front surface dips to z~0.4 and hard cutoffs speckle.
        w *= np.clip((z - 0.34) / 0.14, 0.0, 1.0)
        sh = np.ones(len(P))
        sh -= 0.07 * np.exp(-((yv - 2.376) / 0.011) ** 2)          # under-brow
        sh -= 0.05 * np.exp(-((yv - 2.346) / 0.013) ** 2)          # under-eye
        sh += 0.05 * np.exp(-((x / 0.055) ** 2
                              + ((yv - 2.413) / 0.030) ** 2))      # forehead
        sh -= 0.10 * np.clip((np.abs(x) - 0.038) / 0.05, 0, 1) \
            * np.clip((2.368 - yv) / 0.05, 0, 1)                   # cheek sides
        sh += 0.05 * np.exp(-(x / 0.017) ** 2) \
            * np.exp(-((yv - 2.353) / 0.016) ** 2)                 # nose bridge
        sh -= 0.05 * np.exp(-(x / 0.013) ** 2) \
            * np.exp(-((yv - 2.327) / 0.006) ** 2)                 # nose base
        sh -= 0.10 * np.clip((2.311 - yv) / 0.025, 0, 1)           # chin fade
        col = SKIN[None, :] * np.clip(sh, 0.5, 1.2)[:, None]
        col = HAIR[None, :] * (1 - w[:, None]) + col * w[:, None]
        return np.clip(col, 0, 1), r

    head_soft = (y > 2.0) & (pos[:, 2] > -0.60) & (ax < 0.38)
    nh = paint_soft(head_soft, face_fill, votes=1)
    print("design_pass: head-field tris repainted:", nh)

    def neck_fill(P, base):
        x, yv = P[:, 0], P[:, 1]
        r = np.sqrt((x / 0.085) ** 2 + ((yv - 2.00) / 0.105) ** 2)
        w = np.clip((1.0 - r) / 0.35, 0.0, 1.0)
        w = w * w * (3.0 - 2.0 * w)
        col = SKIN[None, :] * 0.96
        out = base * (1 - w[:, None]) + col * w[:, None]
        return np.clip(out, 0, 1), r

    nn = paint_soft(neck_zone, neck_fill, votes=2)
    print("design_pass: neck tris repainted:", nn)

    # crown tip — painted dark navy, but ONLY onto texels exclusively
    # covered by crown-zone tris (covmin_y > 2.54 means every surface
    # mapping to this texel lives in the crown zone). Crown tris share
    # atlas islands with face and back-of-head tris; an unguarded
    # stamp bleeds navy strokes onto the face (the "painted brows"
    # artifact). Shared texels stay hair/skin — the crown gets a pale
    # patch there, an acceptable trade for a clean face.
    crown_mask = (y > 2.56) & (np.abs(pos[:, 0]) < 0.17)
    csel = crown_mask[idx].reshape(-1, 3).sum(axis=1) >= 2
    n0 = 0
    for t in idx.reshape(-1, 3)[csel]:
        hits = 0
        for yy, xx, P in covered(t):
            yy, xx = np.atleast_1d(yy), np.atleast_1d(xx)
            sel = covmin_y[yy, xx] > 2.54
            if np.any(sel):
                px[yy[sel], xx[sel]] = CROWN
                hits += int(sel.sum())
        n0 += hits > 0
    print("design_pass: crown tris repainted:", n0)

    # gutter dilation — standard bake padding. Texels no tri covers
    # still feed mipmaps/bilinear at island borders; fill them by
    # iteratively averaging covered neighbours so island colours
    # bleed OUTWARD instead of old paint bleeding INWARD.
    cov = covcount > 0
    uncovered = int((~cov).sum())
    for _ in range(12):
        un = ~cov
        if not un.any():
            break
        nsum = np.zeros((H, W, 3), np.float32)
        ncnt = np.zeros((H, W), np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            npx = np.roll(np.roll(px, dy, 0), dx, 1)
            ncv = np.roll(np.roll(cov, dy, 0), dx, 1)
            nsum += npx * ncv[..., None]
            ncnt += ncv
        fill = un & (ncnt > 0)
        px[fill] = nsum[fill] / ncnt[fill][:, None]
        cov |= fill
    print("design_pass: gutter texels dilated:",
          uncovered - int((~cov).sum()), "of", uncovered)

    im = Image.fromarray((np.clip(px, 0, 1) * 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)

    # lips card: baseColorFactor is a dark red that reads as a smudge
    # under the nose — soften toward a muted rose closer to the
    # concept's elder-sage palette
    for m in g["materials"]:
        if m.get("name") == "lips":
            m["pbrMetallicRoughness"]["baseColorFactor"] = \
                [0.58, 0.34, 0.33, 1.0]

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
