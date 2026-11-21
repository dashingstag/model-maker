# face_build.py <in.glb> <out.glb> [spec.json]
# Surgical face stage — replaces the 'face' card-stack + 'faceplate' patch.
#
# What revs 13-17 proved: the hy3d shell-cloud has NO face topology (4/82
# forward tris in the recess), so additive fixes could never converge —
# paint lands on hair, a glued-on plate reads as a billboard, and floating
# feature cards always shadow or z-fight. The fix is subtraction + a real
# face:
#
#   1. DELETE the card meshes + old faceplate (frees the tris).
#   2. CUT the hood shell inside the face box — a real opening, not a
#      sticker on a solid wall. The recess side walls stay (they read as
#      hood depth/shadow).
#   3. INSTALL a canonical low-poly face — an ellipsoid head with
#      gaussian relief (brow ridge, sockets, nose, cheek, lip, chin),
#      wider than the opening so its rim tucks behind the shell edge.
#   4. PAINT features into the face's OWN texture (planar-mapped UVs) —
#      eyes/brows/lips are albedo, not shadow-casting quads.
#
# The face box is declared in the brief's "face" spec as fractions of the
# head bbox (verts weighted to the head joint) — spec position, not
# shell-derived guesses. contract_check's face:* gate verifies the result.
#
# Pure-GLB edit: buffers are only appended (old index data goes dead),
# joints/animations/atlas survive byte-for-byte.

import io
import json
import math
import os
import struct
import sys

import numpy as np

# ---------- defaults (sage) — spec.json overrides ----------

DEF_SPEC = {
    # face box in MODEL coords — authored from the concept (face is
    # narrow, low-center in the hood opening). Fractional "box" of the
    # head band (verts in the top 0.45m) is the portable fallback.
    "box_model": {"x": [-0.055, 0.055], "y": [2.295, 2.415]},
    "recess": 0.010,          # face front sits this far behind the hood wall
    "colors": {
        "skin": "#e9c3a6", "skin_shade": "#c9997f",
        "socket": "#c08f7e", "sclera": "#f4efe8",
        "iris": "#7cc4d4", "pupil": "#22303a", "hi": "#ffffff",
        "brow": "#c9cdd6", "lip": "#a86970",
        "lining": "#2b3044",   # hidden/back-of-head + edge bleed
    },
}
CARD_MESHES = {
    "brow.l", "brow.r", "eye_hi.l", "eye_hi.r",
    "eye_iris.l", "eye_iris.r", "eye_pupil.l", "eye_pupil.r",
    "eye_sclera.l", "eye_sclera.r", "lips", "faceplate", "face_mesh",
}


# ---------- tiny GLB io (same convention as face_plate.py) ----------

def _read_glb(path):
    d = open(path, "rb").read()
    assert d[:4] == b"glTF"
    jl = struct.unpack("<I", d[12:16])[0]
    g = json.loads(d[20:20 + jl])
    bo = 20 + jl + 8
    bl = struct.unpack("<I", d[20 + jl:24 + jl])[0]
    return g, bytearray(d[bo:bo + bl])


def _write_glb(g, bin_blob, path):
    js = json.dumps(g, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    bin_blob = bytes(bin_blob) + b"\0" * (-len(bin_blob) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_blob)
    with open(path, "wb") as f:
        f.write(b"glTF" + struct.pack("<II", 2, total))
        f.write(struct.pack("<I", len(js)) + b"JSON" + js)
        f.write(struct.pack("<I", len(bin_blob)) + b"BIN\x00" + bin_blob)


def _acc(g, blob, ai):
    a = g["accessors"][ai]
    bv = g["bufferViews"][a["bufferView"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    nc = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[a["type"]]
    dt = {5126: np.float32, 5123: np.uint16, 5125: np.uint32,
          5121: np.uint8}[a["componentType"]]
    return np.frombuffer(bytes(blob), dt, a["count"] * nc, off).reshape(-1, nc)


def _push(g, blob, arr, target, ctype, a_type):
    data = np.ascontiguousarray(arr).tobytes()
    pad = -len(blob) % 4
    if pad:
        blob += b"\0" * pad
    g["bufferViews"].append({"buffer": 0, "byteOffset": len(blob),
                             "byteLength": len(data), "target": target})
    blob += data
    flat = np.asarray(arr).reshape(-1, {"SCALAR": 1, "VEC2": 2, "VEC3": 3,
                                        "VEC4": 4}[a_type])
    acc = {"bufferView": len(g["bufferViews"]) - 1, "componentType": ctype,
           "count": flat.shape[0], "type": a_type}
    if ctype == 5126:
        acc["min"] = flat.min(axis=0).tolist()
        acc["max"] = flat.max(axis=0).tolist()
    g["accessors"].append(acc)
    return len(g["accessors"]) - 1


def _smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


# ---------- stage ----------

def _head_bbox(g, blob):
    """Bbox of verts weighted to the head joint (reskin assigns head
    influence); falls back to the top 18% of the model if no skin."""
    # mesh index -> skin index (via the node that instances it); JOINTS_0
    # values index into THAT mesh's skin joint list
    skin_of_mesh = {}
    for n in g.get("nodes", []):
        if "mesh" in n and "skin" in n:
            skin_of_mesh[n["mesh"]] = n["skin"]
    joints_of_mesh = {}
    for mi, si in skin_of_mesh.items():
        for ji, ni in enumerate(g["skins"][si].get("joints", [])):
            if g["nodes"][ni].get("name") == "head":
                joints_of_mesh[mi] = ji
    pts = []
    for mi, m in enumerate(g.get("meshes", [])):
        if mi not in joints_of_mesh:
            continue
        ji = joints_of_mesh[mi]
        for p in m.get("primitives", []):
            a = p["attributes"]
            if "JOINTS_0" not in a or "WEIGHTS_0" not in a:
                continue
            pos = _acc(g, blob, a["POSITION"]).astype(np.float64)
            jo = _acc(g, blob, a["JOINTS_0"]).astype(int)
            wt = _acc(g, blob, a["WEIGHTS_0"]).astype(np.float64)
            mask = ((wt * (jo == ji)).max(axis=1) > 0.4)
            pts.append(pos[mask])
    if pts:
        P = np.vstack(pts)
        P = P[(P[:, 1] > np.percentile(P[:, 1], 5))]
        if (P[:, 0].max() - P[:, 0].min()) < 0.6:
            return P.min(axis=0), P.max(axis=0)
    # skin weights are unreliable on hy3d reskins (half the body binds to
    # 'head') — head band = verts in the top 0.45m of the model
    allp = []
    for m in g.get("meshes", []):
        for p in m.get("primitives", []):
            allp.append(_acc(g, blob, p["attributes"]["POSITION"]))
    P = np.vstack(allp)
    y0 = P[:, 1].max() - 0.45
    H = P[P[:, 1] > y0]
    return H.min(axis=0), H.max(axis=0)


def _drop_meshes(g, names):
    """Remove named meshes; remap node.mesh refs; strip mesh off card nodes
    and remove the card/plate nodes themselves (reindexing node refs)."""
    drop_mesh = {i for i, m in enumerate(g["meshes"])
                 if m.get("name") in names}
    mesh_map = {}
    nm = []
    for i, m in enumerate(g["meshes"]):
        if i in drop_mesh:
            continue
        mesh_map[i] = len(nm)
        nm.append(m)
    g["meshes"] = nm
    drop_node = set()
    for i, n in enumerate(g["nodes"]):
        if n.get("mesh") in drop_mesh or n.get("name") in names:
            drop_node.add(i)
        elif "mesh" in n:
            n["mesh"] = mesh_map[n["mesh"]]
    node_map = {}
    nn = []
    for i, n in enumerate(g["nodes"]):
        if i in drop_node:
            continue
        node_map[i] = len(nn)
        nn.append(n)
    g["nodes"] = nn
    for n in g["nodes"]:
        n["children"] = [node_map[c] for c in n.get("children", [])
                         if c in node_map]
        if not n["children"]:
            n.pop("children")
    for sc in g.get("scenes", []):
        sc["nodes"] = [node_map[i] for i in sc.get("nodes", [])
                       if i in node_map]
    for sk in g.get("skins", []):
        sk["joints"] = [node_map[j] for j in sk["joints"]]
        if sk.get("skeleton") is not None:
            sk["skeleton"] = node_map.get(sk["skeleton"])
    for an in g.get("animations", []):
        keep_ch = []
        for ch in an.get("channels", []):
            t = ch.get("target", {})
            if t.get("node") in drop_node:
                continue
            if t.get("node") in node_map:
                t["node"] = node_map[t["node"]]
            keep_ch.append(ch)
        an["channels"] = keep_ch
    return len(drop_mesh)


def _cut_opening(g, blob, box, cut_z_min):
    """Delete shell tris whose centroid lands inside the (shrunk) face box
    above cut_z_min — the front wall goes; the recess walls below stay as
    hood depth. Returns (removed tris, wall-front z samples)."""
    x0, x1, y0, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ax, ay = (x1 - x0) / 2 * 0.92, (y1 - y0) / 2 * 0.96   # cut < face: tuck
    removed = 0
    wall_z = []
    for m in g["meshes"]:
        for p in m.get("primitives", []):
            if "indices" not in p:
                continue
            pos = _acc(g, blob, p["attributes"]["POSITION"]).astype(np.float64)
            idx = _acc(g, blob, p["indices"]).reshape(-1).astype(np.int64)
            tris = idx.reshape(-1, 3)
            cent = pos[tris].mean(axis=1)
            # open cleanly: centroid inside the ellipse, OR >=2 verts
            # inside (edge straddlers would leave a jagged mouth rim)
            vu = (pos[tris][:, :, 0] - cx) / ax
            vv = (pos[tris][:, :, 1] - cy) / ay
            inside = (vu * vu + vv * vv < 1.0)
            u = (cent[:, 0] - cx) / ax
            v = (cent[:, 1] - cy) / ay
            dead = (((u * u + v * v < 1.0) | (inside.sum(axis=1) >= 2))
                    & (cent[:, 2] > cut_z_min))
            if dead.any():
                wall_z += cent[dead][:, 2].tolist()
            keep = tris[~dead].reshape(-1)
            if dead.any():
                p["indices"] = _push(
                    g, blob, keep.astype(np.uint32), 34963, 5125, "SCALAR")
                removed += int(dead.sum())
    return removed, wall_z


# Feature positions + face relief, all in FACE-BOX normalized coords
# (u,v in [-1,1] over the opening, +v up). One source feeds geometry and
# texture so painted features land exactly on their sculpted shapes.
FEAT = {
    "eye": (0.46, 0.20),      # ±x
    "brow": (0.46, 0.55),
    "lip": (0.0, -0.50),
    "nose_tip": (0.0, -0.22),
    "chin": (0.0, -0.86),
}
RELIEF = [                       # (u, v, su, sv, amplitude m)  +z forward
    (0.00,  +0.55, 0.80, 0.14, +0.016),   # brow ridge
    (0.00,  +0.10, 0.16, 0.34, +0.024),   # nose bridge
    (0.00,  -0.22, 0.20, 0.16, +0.040),   # nose tip
    (-0.46, +0.20, 0.26, 0.18, -0.015),   # eye socket l
    (+0.46, +0.20, 0.26, 0.18, -0.015),   # eye socket r
    (-0.55, -0.28, 0.30, 0.28, +0.008),   # cheek l
    (+0.55, -0.28, 0.30, 0.28, +0.008),   # cheek r
    (0.00,  -0.50, 0.24, 0.10, +0.009),   # upper lip
    (0.00,  -0.86, 0.34, 0.14, +0.014),   # chin
]
# mesh is wider than the opening so the rim tucks behind the shell edge
TUCK_X, TUCK_Y = 1.28, 1.22


def _build_face(box, front_z):
    """Canonical face: flattened ellipsoid front + gaussian relief (real
    form, not a billboard), rim receding so the hood edge overlaps it, and
    a coarse back-of-head hemi so any view through the opening edge still
    finds head, not void. UVs: front -> planar face texture; back -> dark
    corner."""
    x0, x1, y0, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rxf, ryf = (x1 - x0) / 2, (y1 - y0) / 2
    rx, ry = rxf * TUCK_X, ryf * TUCK_Y
    rz = max(0.085, rxf * 1.1)
    cz = front_z - rz
    SECT, LAT = 16, 5           # ~290 tris — must stay under the 15k budget

    def _vert(u, v):            # u,v in [-1,1] on the mesh disc
        # taper toward the chin — faces are not ellipses
        w = 1.0 - 0.35 * _smoothstep(-v) if v < 0 else 1.0
        x = cx + u * rx * w
        y = cy + v * ry
        e = math.sqrt(max(0.0, 1.0 - u * u - v * v))
        uf, vf = u * TUCK_X, v * TUCK_Y       # face-box coords for relief
        rim = _smoothstep((1.0 - u * u - v * v) / 0.35)
        rel = 0.0
        for gu, gv, su, sv, a in RELIEF:
            rel += a * math.exp(-(((uf - gu) / su) ** 2
                                  + ((vf - gv) / sv) ** 2))
        z = cz + rz * e * 0.72 + rel * rim
        return x, y, min(z, front_z + 0.004)

    # front disc: center + rings
    RINGS = [0.30, 0.58, 0.82, 1.0]
    verts = [_vert(0.0, 0.0)]
    for r in RINGS:
        for s in range(SECT):
            t = 2 * math.pi * s / SECT
            verts.append(_vert(math.cos(t) * r, math.sin(t) * r))
    n_front = len(verts)
    faces = [(0, 1 + s, 1 + (s + 1) % SECT) for s in range(SECT)]
    for ri in range(len(RINGS) - 1):
        a0, b0 = 1 + ri * SECT, 1 + (ri + 1) * SECT
        for s in range(SECT):
            s1 = (s + 1) % SECT
            faces += [(a0 + s, b0 + s, b0 + s1),
                      (a0 + s, b0 + s1, a0 + s1)]
    # back of head: hemi-ellipsoid starting AT the rim (rr ~1 -> 0)
    b0 = len(verts)
    for la in range(LAT):
        a = (math.pi / 2) * (la + 1) / (LAT + 1)
        rr, dz = math.cos(a), math.sin(a)
        for s in range(SECT):
            t = 2 * math.pi * s / SECT
            verts.append((cx + math.cos(t) * rr * rx,
                          cy + math.sin(t) * rr * ry,
                          cz - rz * dz))
    pl = len(verts)
    verts.append((cx, cy, cz - rz))
    rim0 = n_front - SECT
    for s in range(SECT):
        s1 = (s + 1) % SECT
        faces += [(rim0 + s, b0 + s, b0 + s1),
                  (rim0 + s, b0 + s1, rim0 + s1)]
    for la in range(LAT - 1):
        a0, b1 = b0 + la * SECT, b0 + (la + 1) * SECT
        for s in range(SECT):
            s1 = (s + 1) % SECT
            faces += [(a0 + s, b1 + s, b1 + s1),
                      (a0 + s, b1 + s1, a0 + s1)]
    l0 = b0 + (LAT - 1) * SECT
    for s in range(SECT):
        faces.append((l0 + s, pl, l0 + (s + 1) % SECT))

    pv = np.array(verts, dtype=np.float32)
    fi = np.array(faces, dtype=np.uint32)
    nrm = np.zeros_like(pv)
    for a, b, c in fi:
        n = np.cross(pv[b].astype(np.float64) - pv[a],
                     pv[c].astype(np.float64) - pv[a])
        nrm[a] += n
        nrm[b] += n
        nrm[c] += n
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
    # UVs: front disc -> planar face rect [0.06,0.94]; back -> dark corner
    uv = np.zeros((len(pv), 2), dtype=np.float32)
    for i in range(n_front):
        u = (pv[i, 0] - (cx - rx)) / (2 * rx)
        v = 1.0 - (pv[i, 1] - (cy - ry)) / (2 * ry)
        uv[i] = (0.06 + 0.88 * u, 0.06 + 0.88 * v)
    uv[n_front:] = (0.02, 0.02)
    return pv, nrm.astype(np.float32), uv, fi, (cx, cy, rxf, ryf)


# ---------- face texture ----------

def _face_texture(spec, geom):
    """Paint features into the face's own texture — what the card quads
    faked. Planar layout matches the front-disc UV map exactly."""
    from PIL import Image, ImageDraw, ImageFilter
    cx, cy, rxf, ryf = geom
    rx, ry = rxf * 1.28, ryf * 1.22
    C = {k: tuple(int(v.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
         for k, v in spec["colors"].items()}
    W = 256
    im = Image.new("RGB", (W, W), C["lining"])
    dr = ImageDraw.Draw(im)

    def P(fx, fy):
        """face-normalized (u,v in mesh ellipse) -> texel"""
        u = (cx + fx * rxf - (cx - rx)) / (2 * rx)
        v = 1.0 - (cy + fy * ryf - (cy - ry)) / (2 * ry)
        return ((0.06 + 0.88 * u) * W, (0.06 + 0.88 * v) * W)

    def E(fx, fy, hw, hh, col, blur=0, layer=None):
        x, y = P(fx, fy)
        sx, sy = P(fx + hw, fy + hh)
        hw_px, hh_px = abs(sx - x), abs(y - sy)
        t = layer if layer is not None else dr
        t.ellipse([x - hw_px, y - hh_px, x + hw_px, y + hh_px], fill=col)

    # skin field — soft ellipse + edge shading (fake hood AO at the rim)
    skin = Image.new("RGB", (W, W), C["lining"])
    sd = ImageDraw.Draw(skin)
    sd.ellipse([W * 0.10, W * 0.10, W * 0.90, W * 0.90], fill=C["skin"])
    edge = Image.new("L", (W, W), 0)
    ed = ImageDraw.Draw(edge)
    ed.ellipse([W * 0.10, W * 0.10, W * 0.90, W * 0.90], fill=255)
    edge = edge.filter(ImageFilter.GaussianBlur(W * 0.05))
    im.paste(skin, (0, 0), edge)
    ex, ey = FEAT["eye"]
    bx, by = FEAT["brow"]
    lx, ly = FEAT["lip"]
    # sockets + nose side shade + under-lip shade on a blur layer
    shade = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    shd = ImageDraw.Draw(shade)
    for sgn in (-1, 1):
        E(ex * sgn, ey, 0.24, 0.15, C["socket"] + (110,), layer=shd)
        E(0.14 * sgn, -0.06, 0.06, 0.28, C["socket"] + (70,), layer=shd)
    E(lx, ly - 0.12, 0.16, 0.05, C["socket"] + (90,), layer=shd)
    E(0.0, -0.30, 0.05, 0.05, C["socket"] + (45,), layer=shd)  # under nose
    shade = shade.filter(ImageFilter.GaussianBlur(3))
    im.paste(Image.alpha_composite(im.convert("RGBA"), shade)
             .convert("RGB"), (0, 0))
    dr = ImageDraw.Draw(im)
    # eyes: sclera / iris / pupil / highlight
    for sgn in (-1, 1):
        E(ex * sgn, ey, 0.17, 0.075, C["sclera"])
        E(ex * sgn, ey - 0.01, 0.075, 0.075, C["iris"])
        E(ex * sgn, ey - 0.01, 0.034, 0.034, C["pupil"])
        E(ex * sgn + 0.025, ey + 0.03, 0.016, 0.016, C["hi"])
        # brow — silver arc stroke
        x0, y0 = P(bx * sgn - 0.16, by)
        x1, y1 = P(bx * sgn + 0.16, by)
        dr.line([x0, y0 + 2, (x0 + x1) / 2, y1 - 4, x1, y1],
                fill=C["brow"], width=4, joint="curve")
    # nose: bridge highlight + nostril shade
    E(0.0, -0.05, 0.045, 0.16, C["skin"])
    E(0.0, FEAT["nose_tip"][1] - 0.01, 0.075, 0.028, C["socket"])
    # lips
    E(lx, ly, 0.20, 0.055, C["lip"])
    E(lx, ly + 0.02, 0.10, 0.020, C["socket"])
    return im


# ---------- main ----------

def main():
    src, dst = sys.argv[1], sys.argv[2]
    spec = dict(DEF_SPEC)
    if len(sys.argv) > 3:
        us = json.load(open(sys.argv[3]))
        us = us.get("face", us)          # accept a component brief.json
        spec.update(us)
        spec["colors"] = {**DEF_SPEC["colors"], **us.get("colors", {})}
    g, blob = _read_glb(src)

    if "box_model" in spec:
        bm = spec["box_model"]
        box = (bm["x"][0], bm["x"][1], bm["y"][0], bm["y"][1])
        print(f"face box (model spec) x {box[0]:.3f}..{box[1]:.3f} "
              f"y {box[2]:.3f}..{box[3]:.3f}")
    else:
        hmn, hmx = _head_bbox(g, blob)
        bx, by = spec["box"]["x"], spec["box"]["y"]
        box = (hmn[0] + bx[0] * (hmx[0] - hmn[0]),
               hmn[0] + bx[1] * (hmx[0] - hmn[0]),
               hmn[1] + by[0] * (hmx[1] - hmn[1]),
               hmn[1] + by[1] * (hmx[1] - hmn[1]))
        print(f"head band y {hmn[1]:.3f}..{hmx[1]:.3f} "
              f"x {hmn[0]:.3f}..{hmx[0]:.3f} -> face box "
              f"x {box[0]:.3f}..{box[1]:.3f} y {box[2]:.3f}..{box[3]:.3f}")

    card_tris = 0
    for m in g["meshes"]:
        if m.get("name") in CARD_MESHES:
            for p in m["primitives"]:
                if "indices" in p:
                    card_tris += g["accessors"][p["indices"]]["count"] // 3
    ndrop = _drop_meshes(g, CARD_MESHES)

    # wall front = high-percentile z of the tris about to be cut
    cut_z_min = 0.40
    removed, wall_z = _cut_opening(g, blob, box, cut_z_min)
    front_z = (float(np.percentile(wall_z, 80)) - spec["recess"]
               if wall_z else 0.60)

    pv, nrm, uv, fi, geom = _build_face(box, front_z)
    tex = _face_texture(spec, geom)
    png = io.BytesIO()
    tex.save(png, "PNG")
    png_b = png.getvalue()

    ai_pos = _push(g, blob, pv, 34962, 5126, "VEC3")
    ai_nrm = _push(g, blob, nrm, 34962, 5126, "VEC3")
    ai_uv = _push(g, blob, uv, 34962, 5126, "VEC2")
    ai_idx = _push(g, blob, fi, 34963, 5125, "SCALAR")
    pad = -len(blob) % 4
    if pad:
        blob += b"\0" * pad
    g["bufferViews"].append({"buffer": 0, "byteOffset": len(blob),
                             "byteLength": len(png_b)})
    blob += png_b
    g.setdefault("images", []).append(
        {"name": "face_tex", "mimeType": "image/png",
         "bufferView": len(g["bufferViews"]) - 1})
    g.setdefault("textures", []).append(
        {"source": len(g["images"]) - 1})
    g.setdefault("samplers", [{}])
    tex_i = len(g["textures"]) - 1
    g["materials"].append({
        "name": "face_skin",
        "pbrMetallicRoughness": {
            "baseColorTexture": {"index": tex_i},
            "metallicFactor": 0.0, "roughnessFactor": 0.9},
    })
    g["meshes"].append({
        "name": "face_mesh",
        "primitives": [{"attributes": {"POSITION": ai_pos,
                                       "NORMAL": ai_nrm,
                                       "TEXCOORD_0": ai_uv},
                        "indices": ai_idx,
                        "material": len(g["materials"]) - 1}]})
    # parent to head like the cards were — same node translation so accessor
    # verts are authored in model coords
    head_i = next(i for i, n in enumerate(g["nodes"])
                  if n.get("name") == "head")
    g["nodes"].append({
        "name": "face_mesh", "mesh": len(g["meshes"]) - 1,
        "translation": [0.0, -1.529754638671875, 0.02450842596590519]})
    g["nodes"][head_i].setdefault("children", []).append(
        len(g["nodes"]) - 1)

    total = sum(g["accessors"][p["indices"]]["count"] // 3
                for m in g["meshes"] for p in m["primitives"]
                if "indices" in p)
    _write_glb(g, blob, dst)
    print(f"face_build: dropped {ndrop} card/plate meshes ({card_tris} tris)"
          f" | cut {removed} shell tris (wall z p80 {front_z:.3f})"
          f" | face {len(pv)}v/{len(fi)}t | total {total} tris")


if __name__ == "__main__":
    main()
