# face_plate.py <in.glb> <out.glb>
# Adds a sculpted low-poly face plate as a bone-parented child of the `head`
# joint, seated on the hood's front shell — the model has no real face surface
# (the recessed region is inner-shell backfaces), so texture alone can only
# paint skin onto hair. The plate is real geometry: shrink-wrapped to the
# shell, with gaussian relief for brow ridge / nose / sockets / chin, and the
# feature cards re-seated on top of it.
#
# Pure-GLB edit: appends accessors/bufferViews/mesh/material/node in place so
# joints, animations and the existing atlas survive byte-for-byte.

import json
import struct
import sys

import numpy as np

# Face oval in model coords (same field as design_pass face_fill)
CX, CY = 0.0, 2.430
AX, AY = 0.095, 0.105
CLEAR = 0.004          # plate floats this far off the shell
CARD_CLEAR = 0.004     # cards re-seat this far above the plate
SHELL_R = 0.028        # radius for shell-front depth sampling

# relief gaussians: (cx, cy, sx, sy, amplitude)  +z forward
RELIEF = [
    (0.0,    2.478, 0.075, 0.013, +0.016),   # brow ridge
    (0.0,    2.447, 0.013, 0.030, +0.022),   # nose bridge
    (0.0,    2.406, 0.018, 0.015, +0.036),   # nose tip
    (-0.037, 2.450, 0.023, 0.016, -0.015),   # eye socket l
    (+0.037, 2.450, 0.023, 0.016, -0.015),   # eye socket r
    (-0.050, 2.395, 0.028, 0.026, +0.007),   # cheek l
    (+0.050, 2.395, 0.028, 0.026, +0.007),   # cheek r
    (0.0,    2.378, 0.022, 0.009, +0.008),   # upper lip
    (0.0,    2.350, 0.030, 0.013, +0.013),   # chin
]


def _wfac(v):
    """Horizontal scale vs height v in [-1,1]: faces taper at chin, narrower
    at crown — widest at the cheekbone line."""
    chin = _smoothstep(min(max((-v - 0.15) / 0.85, 0.0), 1.0))
    brow = _smoothstep(min(max((v - 0.55) / 0.45, 0.0), 1.0))
    return 1.0 - 0.38 * chin - 0.18 * brow
SKIN = [0.87, 0.74, 0.66, 1.0]

CARD_MESH_NAMES = {
    "brow.l", "brow.r", "eye_hi.l", "eye_hi.r",
    "eye_iris.l", "eye_iris.r", "eye_pupil.l", "eye_pupil.r",
    "eye_sclera.l", "eye_sclera.r", "lips",
}


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


def _acc(g, blob, ai, nc):
    a = g["accessors"][ai]
    bv = g["bufferViews"][a["bufferView"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    dt = {5126: np.float32, 5123: np.uint16, 5125: np.uint32,
          5121: np.uint8}[a["componentType"]]
    return np.frombuffer(bytes(blob), dt, a["count"] * nc, off).reshape(-1, nc)


def _push(bv_list, acc_list, blob, arr, target, ctype, n_comp, a_type):
    data = np.ascontiguousarray(arr).tobytes()
    pad = -len(blob) % 4
    if pad:
        blob += b"\0" * pad
    bv_list.append({"buffer": 0, "byteOffset": len(blob),
                    "byteLength": len(data), "target": target})
    blob += data
    flat = np.asarray(arr).reshape(-1, n_comp)
    acc = {"bufferView": len(bv_list) - 1, "componentType": ctype,
           "count": flat.shape[0], "type": a_type}
    if ctype == 5126:
        acc["min"] = flat.min(axis=0).tolist()
        acc["max"] = flat.max(axis=0).tolist()
    acc_list.append(acc)
    return len(acc_list) - 1


def _smoothstep(t):
    return t * t * (3.0 - 2.0 * t)


Z0 = 0.605     # face plane depth at eye line (shell recedes above this)
TILT = 0.12    # slight backward tilt with height — natural, not shell slope
WRAP = 0.030   # cylindrical wrap: edges recede into the hair frame


def plate_z_fn(shell_cents):
    """Return f(x, y) -> plate surface z.

    The face is a vertical surface of its own — the hood shell recedes with
    height (front z ~0.62 at the jaw, ~0.45 at the crown), so shrink-wrapping
    made the face lie on top of the head. Base is a near-vertical plane with
    a slight back-tilt and x-wrap; the shell-follow survives only as a floor
    so shell bumps can never poke through the face.
    """
    def f(x, y):
        u, v = (x - CX) / AX, (y - CY) / AY
        r2 = u * u + v * v
        fall = _smoothstep(min(max((1.0 - r2) / 0.3, 0.0), 1.0))
        rel = 0.0
        for cx, cy, sx, sy, a in RELIEF:
            rel += a * np.exp(-(((x - cx) / sx) ** 2
                                + ((y - cy) / sy) ** 2))
        plane = Z0 - TILT * (y - CY) - WRAP * u * u + rel * fall
        floor = 0.0
        m = ((np.abs(shell_cents[:, 0] - x) < SHELL_R)
             & (np.abs(shell_cents[:, 1] - y) < SHELL_R))
        if m.any():
            floor = float(shell_cents[m][:, 2].max()) + CLEAR
        return max(plane, floor)
    return f


def main():
    src, dst = sys.argv[1], sys.argv[2]
    g, blob = _read_glb(src)

    pr = g["meshes"][0]["primitives"][0]
    pos = _acc(g, blob, pr["attributes"]["POSITION"], 3).astype(np.float64)
    idx = _acc(g, blob, pr["indices"], 1).reshape(-1).astype(np.int64)
    tris = idx.reshape(-1, 3)
    cents = pos[tris].mean(axis=1)
    band = ((np.abs(cents[:, 0]) < 0.16) & (cents[:, 1] > 2.30)
            & (cents[:, 1] < 2.60) & (cents[:, 2] > 0.40))
    shell_cents = cents[band]

    pz = plate_z_fn(shell_cents)

    # concentric-ring topology — smooth elliptical rim, no sawtooth boundary
    RINGS = [0.22, 0.45, 0.68, 0.87, 1.0]
    SECT = 18
    vl = [(CX, CY, pz(CX, CY))]               # center vert
    for r in RINGS:
        for s in range(SECT):
            t = 2 * np.pi * s / SECT
            u, v = np.cos(t) * r, np.sin(t) * r
            x = CX + u * AX * _wfac(v)
            y = CY + v * AY
            vl.append((x, y, pz(x, y)))
    pv = np.array(vl, dtype=np.float32)

    faces = []
    for s in range(SECT):                     # center fan
        faces.append((0, 1 + s, 1 + (s + 1) % SECT))
    for ri in range(len(RINGS) - 1):          # ring quads
        a0, b0 = 1 + ri * SECT, 1 + (ri + 1) * SECT
        for s in range(SECT):
            s1 = (s + 1) % SECT
            faces += [(a0 + s, b0 + s, b0 + s1),
                      (a0 + s, b0 + s1, a0 + s1)]
    fi = np.array(faces, dtype=np.uint16)

    # smooth vertex normals (glTF +z forward: face winding CCW seen from +z)
    nrm = np.zeros_like(pv)
    for a, b, c in fi:
        n = np.cross(pv[b] - pv[a], pv[c] - pv[a])
        nrm[a] += n
        nrm[b] += n
        nrm[c] += n
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
    if nrm[:, 2].mean() < 0:
        nrm = -nrm

    uvs = np.tile(np.array([[0.98, 0.02]], dtype=np.float32), (len(pv), 1))

    # re-seat cards above the plate — each eye is a z-layered stack
    # (sclera/iris/pupil/hi), so shift the whole stack by one shared delta to
    # preserve the layering instead of flattening it to a single plane
    ptri = fi.reshape(-1, 3)
    pcent = pv[ptri].mean(axis=1)
    CLUSTERS = [
        ("eye.l", {"eye_sclera.l", "eye_iris.l", "eye_pupil.l", "eye_hi.l"}),
        ("eye.r", {"eye_sclera.r", "eye_iris.r", "eye_pupil.r", "eye_hi.r"}),
        ("brow.l", {"brow.l"}), ("brow.r", {"brow.r"}), ("lips", {"lips"}),
    ]
    card_data = {}
    for node in g["nodes"]:
        if node.get("name") not in CARD_MESH_NAMES or "mesh" not in node:
            continue
        cp = g["meshes"][node["mesh"]]["primitives"][0]
        a = g["accessors"][cp["attributes"]["POSITION"]]
        bv = g["bufferViews"][a["bufferView"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        cv = np.frombuffer(bytes(blob), np.float32,
                           a["count"] * 3, off).reshape(-1, 3).copy()
        card_data[node["name"]] = (off, cv)
    moved = []
    for cname, members in CLUSTERS:
        cards = [(n, card_data[n]) for n in members if n in card_data]
        if not cards:
            continue
        lo = min(float(cv[:, 2].min()) for _, (_, cv) in cards)
        x0 = np.mean([cv[:, 0].mean() for _, (_, cv) in cards])
        y0 = np.mean([cv[:, 1].mean() for _, (_, cv) in cards])
        m = ((np.abs(pcent[:, 0] - x0) < 0.045)
             & (np.abs(pcent[:, 1] - y0) < 0.045))
        if not m.any():
            continue
        delta = float(pcent[m][:, 2].max()) + CARD_CLEAR - lo
        if delta <= 0.001:
            continue
        for n, (off, cv) in cards:
            cv[:, 2] += np.float32(delta)
            blob[off:off + cv.nbytes] = cv.tobytes()
        moved.append((cname, round(delta, 4)))

    # append plate resources
    ai_pos = _push(g["bufferViews"], g["accessors"], blob, pv, 34962,
                   5126, 3, "VEC3")
    ai_nrm = _push(g["bufferViews"], g["accessors"], blob,
                   nrm.astype(np.float32), 34962, 5126, 3, "VEC3")
    ai_uv = _push(g["bufferViews"], g["accessors"], blob, uvs, 34962,
                  5126, 2, "VEC2")
    ai_idx = _push(g["bufferViews"], g["accessors"], blob, fi, 34963,
                   5123, 1, "SCALAR")

    g["materials"].append({
        "name": "faceplate",
        "pbrMetallicRoughness": {
            "baseColorFactor": SKIN,
            "metallicFactor": 0.0,
            "roughnessFactor": 0.85,
        },
    })
    g["meshes"].append({
        "name": "faceplate",
        "primitives": [{
            "attributes": {"POSITION": ai_pos, "NORMAL": ai_nrm,
                           "TEXCOORD_0": ai_uv},
            "indices": ai_idx,
            "material": len(g["materials"]) - 1,
        }],
    })
    card_t = None
    head_i = None
    for i, n in enumerate(g["nodes"]):
        if n.get("name") == "head":
            head_i = i
        if n.get("name") in CARD_MESH_NAMES and card_t is None:
            card_t = n.get("translation")
    if head_i is None:
        raise RuntimeError("faceplate needs a 'head' bone in the rig")
    if card_t is None:
        raise RuntimeError("faceplate needs face cards (run 'face' first)")
    g["nodes"].append({
        "name": "faceplate",
        "mesh": len(g["meshes"]) - 1,
        "translation": card_t or [0.0, -1.529754638671875, 0.02450842596590519],
    })
    g["nodes"][head_i]["children"].append(len(g["nodes"]) - 1)

    _write_glb(g, blob, dst)
    print(f"faceplate: {len(pv)} verts {len(fi)} tris | "
          f"cards re-seated: {moved}")
    print(f"tris total now {idx.shape[0] // 3 + len(fi)} (budget 15000)")


if __name__ == "__main__":
    main()
