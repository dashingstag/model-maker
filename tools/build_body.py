# build_body.py — procedural bare-body (skin) parts on the shared
# humanoid skeleton.
#
#   python tools/build_body.py [part ...]     # default: all body parts
#
# The mannequin only models skin where its one outfit shows — upper
# arms, torso, pelvis, legs and feet are garments, not bodies. This
# tool builds the missing skin pieces as parametric lofts sized to the
# skeleton's model-space joint positions, then emits one part GLB per
# body slot (full skeleton + all anims + slot meshes) — same layout as
# std_parts output, so extract/contract/unit-render/assemble all work.
#
# Mesh nodes are bone-parented with local = inverse(bone rest world),
# verts authored in model space — the mannequin's own convention.
# Limb ends extend past joints so neighbours interpenetrate (research:
# modular kits hide seams inside joint overlap, not at coincident rings).

import json
import math
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from face_build import _read_glb, _write_glb, _acc  # noqa: E402
from pipelib import atomic_json  # noqa: E402
from std_parts import smooth_normals  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "shared", "mannequin", "humanoid_base.glb")
COMP = os.path.join(ROOT, "pipeline", "components")

NG = 12                      # verts per cross-section ring


# ---------- math helpers ----------

def _compose(n):
    """node local TRS -> 4x4."""
    T = np.eye(4)
    T[:3, 3] = n.get("translation", [0, 0, 0])
    q = n.get("rotation", [0, 0, 0, 1])
    x, y, z, w = q
    T[:3, :3] = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    s = n.get("scale", [1, 1, 1])
    T[:3, :3] = T[:3, :3] @ np.diag(s)
    return T


def _parent_map(g):
    par = {}
    for i, n in enumerate(g["nodes"]):
        for c in n.get("children", []):
            par[c] = i
    return par


def _world(g, par, i):
    M = _compose(g["nodes"][i])
    while i in par:
        i = par[i]
        M = _compose(g["nodes"][i]) @ M
    return M


def _frame(axis):
    a = np.asarray(axis, float)
    a /= np.linalg.norm(a)
    ref = np.array([0, 0, 1.0]) if abs(a[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(a, ref)
    u /= np.linalg.norm(u)
    v = np.cross(a, u)
    return u, v


def loft(rings, cap=True):
    """rings: [(center, rx, rz, axis)] -> verts, faces (smooth body)."""
    verts, faces = [], []
    for c, rx, rz, ax in rings:
        u, v = _frame(ax)
        for k in range(NG):
            t = 2 * math.pi * k / NG
            p = np.asarray(c) + u * (rx * math.cos(t)) + v * (rz * math.sin(t))
            verts.append(p)
    for j in range(len(rings) - 1):
        for k in range(NG):
            a = j * NG + k
            b = j * NG + (k + 1) % NG
            c2 = (j + 1) * NG + (k + 1) % NG
            d = (j + 1) * NG + k
            faces += [[a, b, c2], [a, c2, d]]
    if cap:
        for end, flip in ((0, True), (len(rings) - 1, False)):
            c = np.asarray(rings[end][0])
            ci = len(verts)
            verts.append(c)
            for k in range(NG):
                a = end * NG + k
                b = end * NG + (k + 1) % NG
                faces.append([ci, b, a] if flip else [ci, a, b])
    return np.array(verts), faces


def _normals(verts, faces):
    n = np.zeros_like(verts)
    for f in faces:
        a, b, c = verts[f[0]], verts[f[1]], verts[f[2]]
        fn = np.cross(b - a, c - a)
        for i in f:
            n[i] += fn
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    return n / ln


# ---------- GLB emit ----------

def _push_data(g, blob, arr, target=None):
    data = np.ascontiguousarray(arr)
    bv = {"buffer": 0, "byteOffset": len(blob),
          "byteLength": data.nbytes}
    blob += data.tobytes()
    blob += b"\0" * ((4 - data.nbytes % 4) % 4)
    if target:
        bv["target"] = target
    g["bufferViews"].append(bv)
    return len(g["bufferViews"]) - 1


def add_mesh(g, blob, name, verts, faces, mat_i, bone_name, par):
    """Append a mesh + a bone-parented node carrying it. Returns node idx."""
    nv = _push_data(g, blob, verts.astype("<f4"), 34962)
    g["accessors"].append({
        "bufferView": nv, "componentType": 5126, "count": len(verts),
        "type": "VEC3",
        "min": [float(x) for x in verts.min(0)],
        "max": [float(x) for x in verts.max(0)]})
    pa = len(g["accessors"]) - 1
    nn = _push_data(g, blob, _normals(verts, faces).astype("<f4"), 34962)
    g["accessors"].append({"bufferView": nn, "componentType": 5126,
                           "count": len(verts), "type": "VEC3"})
    na = len(g["accessors"]) - 1
    idx = np.array([i for f in faces for i in f], dtype="<u2")
    ni = _push_data(g, blob, idx, 34963)
    g["accessors"].append({"bufferView": ni, "componentType": 5123,
                           "count": len(idx), "type": "SCALAR",
                           "min": [0], "max": [len(verts) - 1]})
    g["meshes"].append({"name": name, "primitives": [{
        "attributes": {"POSITION": pa, "NORMAL": na},
        "indices": len(g["accessors"]) - 1, "material": mat_i,
        "mode": 4}]})

    # node: local = inverse(bone rest world) -> model-space verts
    bi = next(i for i, n in enumerate(g["nodes"])
              if n.get("name") == bone_name)
    Minv = np.linalg.inv(_world(g, par, bi))
    t = Minv[:3, 3]
    R = Minv[:3, :3]
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1) * 2
        q = [(R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s,
             (R[1, 0] - R[0, 1]) / s, s / 4]
    else:                                   # handle ~180° rotations
        m = np.argmax(np.diag(R))
        i2, j2 = (m + 1) % 3, (m + 2) % 3
        s = math.sqrt(max(1e-12, 1 + R[m, m] - R[i2, i2] - R[j2, j2])) * 2
        q = [0, 0, 0, 0]
        q[m] = s / 4
        q[i2] = (R[m, i2] + R[i2, m]) / s
        q[j2] = (R[m, j2] + R[j2, m]) / s
        q[3] = (R[j2, i2] - R[i2, j2]) / s
    nn2 = {"name": name, "mesh": len(g["meshes"]) - 1,
           "translation": [float(x) for x in t],
           "rotation": [float(x) for x in q]}
    g["nodes"].append(nn2)
    g["nodes"][bi].setdefault("children", []).append(len(g["nodes"]) - 1)


def _mirror_x(verts):
    v = verts.copy()
    v[:, 0] = -v[:, 0]
    return v


def _flip_faces(faces):
    return [[f[0], f[2], f[1]] for f in faces]


# ---------- body piece geometry (model-space, meters) ----------

def piece_torso_pelvis():
    """Hips: widest at the trochanter line, tapering up into the waist
    and down to a hidden crotch cap."""
    rings = [
        ((0, 0.835, 0), 0.096, 0.080, (0, 1, 0)),
        ((0, 0.885, 0), 0.118, 0.094, (0, 1, 0)),
        ((0, 0.935, 0), 0.128, 0.100, (0, 1, 0)),
        ((0, 0.985, 0), 0.126, 0.099, (0, 1, 0)),
        ((0, 1.030, 0), 0.118, 0.094, (0, 1, 0)),
        ((0, 1.062, 0), 0.112, 0.090, (0, 1, 0)),
    ]
    return loft(rings)


def piece_torso_waist():
    """Abdomen: narrowest at the navel, flares into the ribcage."""
    rings = [
        ((0, 1.050, 0), 0.112, 0.090, (0, 1, 0)),
        ((0, 1.100, 0), 0.104, 0.083, (0, 1, 0)),
        ((0, 1.150, 0), 0.100, 0.080, (0, 1, 0)),
        ((0, 1.190, 0), 0.118, 0.088, (0, 1, 0)),
    ]
    return loft(rings)


def piece_torso_chest():
    """Ribcage: belly->chest->shoulder slope; top ring hidden in neck."""
    rings = [
        ((0, 1.175, 0), 0.118, 0.088, (0, 1, 0)),
        ((0, 1.235, 0), 0.136, 0.098, (0, 1, 0)),
        ((0, 1.300, 0), 0.148, 0.104, (0, 1, 0)),
        ((0, 1.365, 0), 0.154, 0.106, (0, 1, 0)),
        ((0, 1.425, 0), 0.146, 0.100, (0, 1, 0)),
        ((0, 1.470, 0), 0.118, 0.086, (0, 1, 0)),
        ((0, 1.505, 0), 0.075, 0.065, (0, 1, 0)),
    ]
    return loft(rings)


def _tube(p0, p1, radii, n_rings=None, bulb=0.0):
    """Tube p0->p1 through a per-t radius profile (shape, not taper)."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    n_rings = n_rings or len(radii)
    rings = []
    for i in range(n_rings):
        t = i / (n_rings - 1)
        r = np.interp(t, np.linspace(0, 1, len(radii)), radii)
        c = p0 + (p1 - p0) * t
        if bulb and i == 0:
            r *= 1 + bulb
        rings.append((c, r, r, p1 - p0))
    return loft(rings)


def piece_up_arm(side):
    """Deltoid cap -> bicep -> elbow. Radius profile is the anatomy:
    shoulder bulb, mid-bicep bulk, elbow pinch."""
    s = -1 if side == "l" else 1
    p0 = (s * 0.145, 1.435, 0)
    p1 = (s * 0.400, 1.265, 0)
    radii = [0.055, 0.050, 0.043, 0.037, 0.033, 0.030]
    v, f = _tube(p0, p1, radii)
    return v, f


def piece_thigh(side):
    """Hip -> quad mass -> knee. Thigh is thickest just below the hip."""
    s = -1 if side == "l" else 1
    p0 = (s * 0.110, 0.965, 0)
    p1 = (s * 0.110, 0.490, 0)
    radii = [0.062, 0.075, 0.073, 0.066, 0.058, 0.050, 0.046]
    v, f = _tube(p0, p1, radii)
    return v, f


def piece_shin(side):
    """Knee -> calf bulge (upper third) -> slim ankle."""
    s = -1 if side == "l" else 1
    p0 = (s * 0.110, 0.545, 0)
    p1 = (s * 0.110, 0.110, 0)
    radii = [0.048, 0.052, 0.055, 0.050, 0.042, 0.035, 0.031]
    v, f = _tube(p0, p1, radii)
    return v, f


def piece_foot(side):
    """Heel -> arch -> ball -> toe; ankle collar hidden in the shin.
    For a z-axis loft, rx is the vertical radius and rz the width."""
    s = -1 if side == "l" else 1
    x = s * 0.110
    rings = [
        ((x, 0.095, -0.070), 0.042, 0.036, (0, 0, 1)),   # ankle collar
        ((x, 0.062, -0.055), 0.050, 0.040, (0, 0, 1)),   # heel
        ((x, 0.050, 0.005), 0.044, 0.044, (0, 0, 1)),    # heel-mid
        ((x, 0.040, 0.075), 0.038, 0.047, (0, 0, 1)),    # arch
        ((x, 0.036, 0.150), 0.036, 0.052, (0, 0, 1)),    # ball
        ((x, 0.026, 0.200), 0.026, 0.048, (0, 0, 1)),    # toe-mid
        ((x, 0.018, 0.235), 0.018, 0.034, (0, 0, 1)),    # toe tip
    ]
    return loft(rings)


def piece_forearm_stub(side):
    """Forearm already exists as skin — nothing to build."""
    return None


# slot -> [(node_name, builder_fn, bone)]
BUILT = {
    "body_torso": [
        ("btorso_pelvis", piece_torso_pelvis, "root"),
        ("btorso_waist", piece_torso_waist, "spine"),
        ("btorso_chest", piece_torso_chest, "chest"),
    ],
    "body_arm_l": [("barm_up_l", lambda: piece_up_arm("l"), "upper_arm.l")],
    "body_arm_r": [("barm_up_r", lambda: piece_up_arm("r"), "upper_arm.r")],
    "body_leg_l": [
        ("bthigh_l", lambda: piece_thigh("l"), "thigh.l"),
        ("bshin_l", lambda: piece_shin("l"), "shin.l"),
    ],
    "body_leg_r": [
        ("bthigh_r", lambda: piece_thigh("r"), "thigh.r"),
        ("bshin_r", lambda: piece_shin("r"), "shin.r"),
    ],
    "body_foot_l": [("bfoot_l", lambda: piece_foot("l"), "foot.l")],
    "body_foot_r": [("bfoot_r", lambda: piece_foot("r"), "foot.r")],
}

# existing mannequin skin meshes kept per slot (name -> bone node name)
KEEP = {
    "body_head": ["head_m", "jaw_m"],
    "body_neck": ["neck_m"],
    "body_arm_l": ["forearm_l"],
    "body_arm_r": ["forearm_r"],
    "body_hand_l": ["hand_l", "finger_l_thumb", "finger_l_index",
                    "finger_l_middle", "finger_l_ring", "finger_l_pinky"],
    "body_hand_r": ["hand_r", "finger_r_thumb", "finger_r_index",
                    "finger_r_middle", "finger_r_ring", "finger_r_pinky"],
    "body_torso": [], "body_leg_l": [], "body_leg_r": [],
    "body_foot_l": [], "body_foot_r": [],
}

SLOT_BONES = {
    "body_head": ["head", "jaw", "neck"],
    "body_neck": ["neck"],
    "body_torso": ["root", "spine", "chest"],
    "body_arm_l": ["upper_arm.l", "forearm.l", "hand.l"],
    "body_arm_r": ["upper_arm.r", "forearm.r", "hand.r"],
    "body_hand_l": ["hand.l", "hand.l.index.2", "hand.l.thumb.2"],
    "body_hand_r": ["hand.r", "hand.r.index.2", "hand.r.thumb.2"],
    "body_leg_l": ["thigh.l", "shin.l", "foot.l"],
    "body_leg_r": ["thigh.r", "shin.r", "foot.r"],
    "body_foot_l": ["foot.l"],
    "body_foot_r": ["foot.r"],
}


def main():
    parts = sys.argv[1:] or sorted(set(BUILT) | set(KEEP))
    for slot in parts:
        cid = slot
        cdir = os.path.join(COMP, cid)
        os.makedirs(os.path.join(cdir, "export"), exist_ok=True)
        g, blob = _read_glb(BASE)
        blob = bytearray(blob)
        par = _parent_map(g)
        skin_i = next(i for i, m in enumerate(g["materials"])
                      if m.get("name") == "skin")

        # strip every mesh node; re-add kept skins + built pieces
        keep = set(KEEP.get(slot, []))
        for n in g["nodes"]:
            if "mesh" in n and n.get("name") not in keep:
                del n["mesh"]
        used = {n["mesh"] for n in g["nodes"] if "mesh" in n}
        mmap, nm = {}, []
        for i, m in enumerate(g["meshes"]):
            if i in used:
                mmap[i] = len(nm)
                nm.append(m)
        g["meshes"] = nm
        for n in g["nodes"]:
            if "mesh" in n:
                n["mesh"] = mmap[n["mesh"]]
        for i in range(len(g["meshes"])):   # kept skins are flat-shaded
            smooth_normals(g, blob, i)

        for name, fn, bone in BUILT.get(slot, []):
            verts, faces = fn()
            add_mesh(g, blob, name, verts, faces, skin_i, bone, par)

        out = os.path.join(cdir, "export", cid + ".glb")
        g["buffers"][0]["byteLength"] = len(blob)
        _write_glb(g, bytes(blob), out)
        tris = sum(g["accessors"][p["indices"]]["count"] // 3
                   for m in g["meshes"] for p in m["primitives"]
                   if "indices" in p)
        meshes = [n["name"] for n in g["nodes"] if "mesh" in n]
        brief = {
            "id": cid, "type": "glb",
            "part": {"slot": slot, "layer": "body", "meshes": meshes,
                     "source": "build_body"},
            "skeleton": "@skeletons/humanoid_v2",
            "tri_budget": 1500,
            "contract": {"glb": {
                "bones": SLOT_BONES.get(slot, []),
                "anims": ["idle", "walk"],
                "nodes": meshes,
            }},
        }
        atomic_json(os.path.join(cdir, "brief.json"), brief)
        print(f"{cid}: {len(meshes)} meshes, {tris} tris -> {out}")


if __name__ == "__main__":
    main()
