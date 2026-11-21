# std_parts.py — slice shared/mannequin/humanoid_base into standard
# part components (pipeline/components/std_<slot>/).
#
# Each part GLB = the FULL skeleton node tree + all 22 anim clips +
# only that slot's mesh nodes. Carrying the skeleton/anims means a part
# animates standalone in unit renders — evidence it rides its bone —
# and assemble.py can re-graft parts by matching bone names.
#
#   python tools/std_parts.py [slot ...]     # default: all slots

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from face_build import _read_glb, _write_glb, _acc  # noqa: E402
from pipelib import atomic_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_SPEC = os.path.join(ROOT, "shared", "mannequin", "humanoid_base.json")

# contract per slot — bones/nodes/anims that must exist in the part GLB
SLOT_BONES = {
    "cloth_torso": ["chest", "spine"],
    "cloth_sleeve_l": ["upper_arm.l", "forearm.l"],
    "cloth_sleeve_r": ["upper_arm.r", "forearm.r"],
    "cloth_waist": ["root"],
    "cloth_skirt": ["skirt.l", "skirt.r", "skirt.front"],
    "cloth_legs": ["thigh.l", "thigh.r"],
    "cloth_feet": ["foot.l", "foot.r"],
    "std_hair": ["head", "hair.1", "hair.4"],
    "std_ornament": ["head"],
}


def smooth_normals(g, blob, mesh_i):
    """Weld-split verts (the mannequin stores per-face verts = flat
    shading) and write smooth vertex normals. Positions/indices are
    untouched — a per-position normal is shared by every dup vert."""
    for p in g["meshes"][mesh_i]["primitives"]:
        if "NORMAL" not in p["attributes"] or "indices" not in p:
            continue
        pos = _acc(g, blob, p["attributes"]["POSITION"])
        idx = _acc(g, blob, p["indices"]).ravel()
        groups = {}
        for i, k in enumerate(map(tuple, np.round(pos.astype(float), 5))):
            groups.setdefault(k, []).append(i)
        n = np.zeros_like(pos)
        for f in idx.reshape(-1, 3):
            fn = np.cross(pos[f[1]] - pos[f[0]], pos[f[2]] - pos[f[0]])
            for vi in f:
                n[vi] += fn
        gn = np.zeros_like(pos)
        for ids in groups.values():
            s = n[ids].sum(0)
            for i in ids:
                gn[i] = s
        ln = np.linalg.norm(gn, axis=1, keepdims=True)
        ln[ln == 0] = 1
        data = (gn / ln).astype("<f4")
        off = (len(blob) + 3) & ~3
        blob += b"\0" * (off - len(blob))
        blob += data.tobytes()
        g["bufferViews"].append({"buffer": 0, "byteOffset": off,
                                 "byteLength": data.nbytes,
                                 "target": 34962})
        a = dict(g["accessors"][p["attributes"]["NORMAL"]])
        a["bufferView"] = len(g["bufferViews"]) - 1
        a.pop("byteOffset", None)
        g["accessors"].append(a)
        p["attributes"]["NORMAL"] = len(g["accessors"]) - 1


def slice_part(g, blob, meshes, out_path, smooth=True):
    """Emit a GLB with the full node tree but only nodes named in
    `meshes` keeping their mesh references; other meshes are dropped
    (reindexed). Slot names are NODE names — glTF mesh objects carry
    Blender defaults (Cone.001), not slot ids."""
    keep_nodes = {n.get("name") for n in g["nodes"]}
    missing = [m for m in meshes if m not in keep_nodes]
    if missing:
        raise SystemExit(f"slot meshes not in base tree: {missing}")
    keep = {n["mesh"] for n in g["nodes"]
            if "mesh" in n and n.get("name") in meshes}
    mmap, nm = {}, []
    for i, m in enumerate(g["meshes"]):
        if i in keep:
            mmap[i] = len(nm)
            nm.append(m)
    g["meshes"] = nm
    for n in g["nodes"]:
        if "mesh" in n:
            if n["mesh"] in mmap:
                n["mesh"] = mmap[n["mesh"]]
            else:
                del n["mesh"]       # empty transform — skeleton intact
    if smooth:
        for i in range(len(g["meshes"])):
            smooth_normals(g, blob, i)
        g["buffers"][0]["byteLength"] = len(blob)
    _write_glb(g, blob, out_path)


def main():
    spec = json.load(open(BASE_SPEC))
    base = os.path.join(ROOT, spec["glb"])
    slots = sys.argv[1:] or list(spec["slots"].keys())
    made = []
    for slot in slots:
        sm = spec["slots"][slot]
        if sm.get("layer") == "body":
            continue            # body parts come from build_body.py
        cid = slot if "_" in slot else "std_" + slot
        cdir = os.path.join(ROOT, "pipeline", "components", cid)
        os.makedirs(os.path.join(cdir, "export"), exist_ok=True)
        g, blob = _read_glb(base)
        out = os.path.join(cdir, "export", cid + ".glb")
        slice_part(g, bytearray(blob), sm["meshes"], out)
        tris = sum(g["accessors"][p["indices"]]["count"] // 3
                   for m in g["meshes"] for p in m["primitives"]
                   if "indices" in p)
        brief = {
            "id": cid, "type": "glb",
            "part": {"slot": slot, "layer": sm.get("layer"),
                     "covers": sm.get("covers", []),
                     "meshes": sm["meshes"],
                     "source": "@mannequin/humanoid_base"},
            "skeleton": "@skeletons/humanoid_v2",
            "tri_budget": 1500,
            "contract": {"glb": {
                "bones": SLOT_BONES.get(slot, []),
                "anims": ["idle", "walk"],
                "nodes": sm["meshes"],
            }},
        }
        atomic_json(os.path.join(cdir, "brief.json"), brief)
        made.append((cid, len(sm["meshes"]), tris))
        print(f"{cid}: {len(sm['meshes'])} meshes, {tris} tris -> {out}")
    print(f"{len(made)} standard parts emitted")


if __name__ == "__main__":
    main()
