#!/usr/bin/env python3
"""MPFB-backed realistic body-part generator.

One Blender session:
  MPFB create_human + game_engine rig (authored weights)
  -> drop helper/genital/cube geometry, keep eyes/teeth/tongue
  -> merge MPFB weight groups onto humanoid_v2 bone names
  -> bone-space retarget: place each vert in our skeleton's rest pose
     (v' = sum_b w_b * F_ours[b'] * scale_b * F_mpfb[b]^-1 * v), mirrored on X
  -> slice into body_* slots by dominant bone (ring-consistent: boundary
     verts duplicated per part at identical positions/weights)
  -> export one skinned GLB per part (armature = our skeleton + clips)

Usage:
  blender -b --python tools/mpfb_body.py -- \\
      --skeleton-glb pipeline/components/body_torso/export/body_torso.glb \\
      --out-dir pipeline/components --scale 1.07 [--decimate 0.5] [--only body_torso]
"""
import bpy, sys, os, json, argparse
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService
except ImportError:
    from mpfb.services.humanservice import HumanService

# ---------------- config ----------------

# MPFB game_engine bone -> humanoid_v2 bone
BONE_MAP = {
    "Root": None,  # unused for weights; drop if any
    "pelvis": "root",
    "spine_01": "spine",
    "spine_02": "chest",
    "spine_03": "chest",
    "neck_01": "neck",
    "head": "head",
}
for side_m, side_o in (("l", "l"), ("r", "r")):
    BONE_MAP[f"clavicle_{side_m}"] = f"shoulder.{side_o}"
    BONE_MAP[f"upperarm_{side_m}"] = f"upper_arm.{side_o}"
    BONE_MAP[f"lowerarm_{side_m}"] = f"forearm.{side_o}"
    BONE_MAP[f"hand_{side_m}"] = f"hand.{side_o}"
    BONE_MAP[f"thigh_{side_m}"] = f"thigh.{side_o}"
    BONE_MAP[f"calf_{side_m}"] = f"shin.{side_o}"
    BONE_MAP[f"foot_{side_m}"] = f"foot.{side_o}"
    BONE_MAP[f"ball_{side_m}"] = f"foot.{side_o}"
    for finger in ("thumb", "index", "middle", "ring", "pinky"):
        for seg in (1, 2, 3):
            BONE_MAP[f"{finger}_{seg:02d}_{side_m}"] = f"hand.{side_o}.{finger}.{seg}"

# slot -> member bones (humanoid_v2 names)
SLOTS = {
    "body_head":  {"head", "jaw", "eye.l", "eye.r"},
    "body_neck":  {"neck"},
    "body_torso": {"root", "spine", "chest", "shoulder.l", "shoulder.r"},
    "body_arm_l": {"upper_arm.l", "forearm.l"},
    "body_arm_r": {"upper_arm.r", "forearm.r"},
    "body_hand_l": {"hand.l"} | {f"hand.l.{f}.{n}" for f in ("thumb", "index", "middle", "ring", "pinky") for n in (1, 2, 3)},
    "body_hand_r": {"hand.r"} | {f"hand.r.{f}.{n}" for f in ("thumb", "index", "middle", "ring", "pinky") for n in (1, 2, 3)},
    "body_leg_l": {"thigh.l", "shin.l"},
    "body_leg_r": {"thigh.r", "shin.r"},
    "body_foot_l": {"foot.l"},
    "body_foot_r": {"foot.r"},
}

# helper vertex groups -> what to do with those verts:
#  ("keep", forced_bone) | "drop" | (None -> inherit weights if present)
HELPER_REGIONS = {
    "helper-hair": "drop",
    "helper-skirt": "drop",
    "helper-tights": "drop",
    "helper-genital": "drop",
    "genitals": "drop",
    "JointCubes": "drop",
    "helper-l-eyelashes-1": "drop",
    "helper-l-eyelashes-2": "drop",
    "helper-r-eyelashes-1": "drop",
    "helper-r-eyelashes-2": "drop",
    "helper-l-eye": ("keep", "eye.l"),
    "helper-r-eye": ("keep", "eye.r"),
    "helper-lower-teeth": ("keep", "jaw"),
    "helper-upper-teeth": ("keep", "head"),
    "helper-tongue": ("keep", "jaw"),
}

LATERAL_SCALE = 1.07  # girth scale relative to MPFB (tunable via --scale)

def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--skeleton-glb", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--scale", type=float, default=LATERAL_SCALE)
    p.add_argument("--decimate", type=float, default=0.0, help="collapse ratio (0=off)")
    p.add_argument("--only", default="")
    p.add_argument("--preview", default="", help="write merged preview GLB here")
    return p.parse_args(argv)

# ---------------- helpers ----------------

def bone_world_map(arm_obj):
    """bone name -> (head_v, tail_v, matrix_local orthonormal frame)"""
    out = {}
    for b in arm_obj.data.bones:
        out[b.name] = (
            arm_obj.matrix_world @ b.head_local,
            arm_obj.matrix_world @ b.tail_local,
            arm_obj.matrix_world @ b.matrix_local,
        )
    return out

def vert_groups_dict(obj):
    """vert index -> {group_index: weight}"""
    return {v.index: {g.group: g.weight for g in v.groups} for v in obj.data.vertices}

def vert_weight_map(obj):
    """vert index -> {group_name: weight} read from mesh groups."""
    gnames = {g.index: g.name for g in obj.vertex_groups}
    return {v.index: {gnames[g.group]: g.weight for g in v.groups}
            for v in obj.data.vertices}

def cap_influences(w, k=4):
    """keep top-k weights, renormalize."""
    if len(w) <= k:
        return w
    top = sorted(w.items(), key=lambda kv: -kv[1])[:k]
    tot = sum(v for _, v in top) or 1.0
    return {b: v / tot for b, v in top}

def mirror_mesh_x(obj):
    me = obj.data
    me.transform(Matrix.Scale(-1, 4, (1, 0, 0)))
    me.flip_normals()

def mirror_frame_x(m):
    mx = Matrix.Diagonal((-1, 1, 1, 1))
    return mx @ m @ mx

# ---------------- main ----------------

def main():
    ARGS = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # 1) our skeleton + clips: import from an existing part GLB
    bpy.ops.import_scene.gltf(filepath=ARGS.skeleton_glb)
    our_arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    for o in list(bpy.data.objects):
        if o.type == "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    F_ours = {n: (h, t, m) for n, (h, t, m) in bone_world_map(our_arm).items()}
    print("our bones:", len(F_ours))

    # 2) MPFB human + game_engine rig
    human = HumanService.create_human(
        mask_helpers=True, detailed_helpers=True,
        extra_vertex_groups=True, feet_on_ground=True, scale=0.1)
    rig = HumanService.add_builtin_rig(human, "game_engine")
    F_mpfb = bone_world_map(rig)
    print("mpfb bones:", len(F_mpfb))

    # drop stray objects (marker cubes etc.)
    for o in list(bpy.data.objects):
        if o.type == "MESH" and o is not human:
            bpy.data.objects.remove(o, do_unlink=True)

    me = human.data
    gnames = {g.index: g.name for g in human.vertex_groups}
    name2idx = {v: k for k, v in gnames.items()}

    # 3) classify verts: drop-helpers / forced-bone helpers / body
    vgroups = vert_groups_dict(human)
    drop_v = set()
    forced = {}  # vert -> our bone name
    for vi, gs in vgroups.items():
        forced_hit = None
        dropped = False
        for gi, w in gs.items():
            n = gnames.get(gi, "")
            if n in HELPER_REGIONS:
                rule = HELPER_REGIONS[n]
                if rule == "drop":
                    dropped = True
                elif isinstance(rule, tuple):
                    forced_hit = rule[1]
        if dropped:
            drop_v.add(vi)
        elif forced_hit:
            forced[vi] = forced_hit

    # weight groups: rig bone names only (45)
    rig_bone_names = set(BONE_MAP) | {"Root"}
    wgroup_idx = {gi: n for gi, n in gnames.items() if n in rig_bone_names}

    print("drop verts:", len(drop_v), "forced:", len(forced))

    # keep faces that have no dropped verts; mark helper faces (verts with
    # forced bone) separately is unnecessary — they stay as mesh verts
    keep_faces = [p for p in me.polygons if not any(v in drop_v for v in p.vertices)]
    keep_verts = sorted({v for p in keep_faces for v in p.vertices})
    remap = {old: new for new, old in enumerate(keep_verts)}

    # build a clean mesh with kept geometry only
    new_me = bpy.data.meshes.new("body")
    verts_new = [human.matrix_world @ me.vertices[i].co for i in keep_verts]
    faces_new = [[remap[v] for v in p.vertices] for p in keep_faces]
    new_me.from_pydata(verts_new, [], faces_new)
    new_me.update()
    body = bpy.data.objects.new("body", new_me)
    bpy.context.collection.objects.link(body)

    # named materials (contract convention): skin for body, dedicated extras
    mat_skin = bpy.data.materials.new("skin")
    mat_skin.diffuse_color = (0.85, 0.66, 0.55, 1.0)
    mat_skin.use_nodes = True
    bsdf = mat_skin.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.85, 0.66, 0.55, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.7
    mat_eye = bpy.data.materials.new("eye_white")
    mat_eye.diffuse_color = (0.9, 0.9, 0.88, 1.0)
    mat_eye.use_nodes = True
    mat_eye.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.9, 0.9, 0.88, 1.0)
    new_me.materials.append(mat_skin)
    new_me.materials.append(mat_eye)
    # eye helper faces -> eye material (verts forced to eye.l/r)
    eye_orig = {oi for oi, b in forced.items() if b.startswith("eye.")}
    for p in new_me.polygons:
        orig = {keep_verts[v] for v in p.vertices}
        if orig and orig.issubset(eye_orig):
            p.material_index = 1

    # per-vert weights in MPFB bone names (for the deform modifier) —
    # forced helper verts ride 'head' (mpfb rig has no jaw/eye bones)
    FORCED_MPFB = {"eye.l": "head", "eye.r": "head", "jaw": "head", "head": "head"}
    mpfb_weights = {}
    for new_i, old_i in enumerate(keep_verts):
        w = {}
        if old_i in forced:
            w[FORCED_MPFB[forced[old_i]]] = 1.0
        else:
            for gi, wt in vgroups.get(old_i, {}).items():
                n = wgroup_idx.get(gi)
                if n and n != "Root":
                    w[n] = w.get(n, 0.0) + wt
            if not w:
                w["__unweighted__"] = 1.0
        total = sum(w.values())
        mpfb_weights[new_i] = {k: v / total for k, v in w.items()}

    # resolve unweighted verts to nearest mpfb bone head
    for new_i, w in mpfb_weights.items():
        if "__unweighted__" in w:
            p = body.data.vertices[new_i].co
            best, bestd = None, 1e9
            for m_name in BONE_MAP:
                if m_name == "Root" or m_name not in F_mpfb:
                    continue
                d = (p - F_mpfb[m_name][0]).length
                if d < bestd:
                    bestd, best = d, m_name
            mpfb_weights[new_i] = {best: 1.0}

    m_vgs = {}
    for new_i, w in mpfb_weights.items():
        for mn, wt in w.items():
            vg = m_vgs.get(mn) or m_vgs.setdefault(mn, body.vertex_groups.new(name=mn))
            vg.add([new_i], wt, "REPLACE")

    # 4) proportion-fit via pose+apply: pose each mpfb bone so its head lands
    # on our (un-mirrored) joint position and its Y aims at our tail, then
    # apply the armature modifier — mesh gets our proportions through ordinary
    # coherent skinning (no scale terms => no blend discontinuities).
    mw_inv = rig.matrix_world.inverted()
    topo = []
    def _walk(b):
        topo.append(b.name)
        for c in b.children:
            _walk(c)
    for b in rig.data.bones:
        if b.parent is None:
            _walk(b)
    for bn in topo:
        m_name = bn
        our_name = BONE_MAP.get(m_name)
        if our_name is None or m_name == "Root":
            continue
        if our_name not in F_ours:
            continue
        pb = rig.pose.bones.get(m_name)
        if pb is None:
            continue
        oh, ot, _om = F_ours[our_name]
        # our targets in mpfb space: un-mirror x
        th = Vector((-oh.x, oh.y, oh.z))
        tt = Vector((-ot.x, ot.y, ot.z))
        cur = rig.matrix_world @ pb.matrix
        cur_dir = (cur.to_3x3() @ Vector((0, 1, 0)))
        tgt_dir = tt - th
        if tgt_dir.length < 1e-6:
            continue
        rot = cur_dir.rotation_difference(tgt_dir.normalized()).to_matrix().to_4x4()
        new_w = rot @ cur
        new_w.translation = th
        pb.matrix = mw_inv @ new_w
        bpy.context.view_layer.update()
        got = rig.matrix_world @ pb.head
        err = (got - th).length
        if err > 0.005:
            print(f"  posefit MISS {m_name}: got {[round(v,3) for v in got]} want {[round(v,3) for v in th]} err={err:.3f}")

    # bake the pose into the mesh
    bpy.context.view_layer.objects.active = body
    mod = body.modifiers.new("fit", "ARMATURE")
    mod.object = rig
    bpy.ops.object.modifier_apply(modifier=mod.name)
    print("bbox post-fit:", [[round(min(v.co[i] for v in body.data.vertices), 2),
                              round(max(v.co[i] for v in body.data.vertices), 2)]
                             for i in range(3)])
    # diagnose outlier verts
    gnames2 = {g.index: g.name for g in body.vertex_groups}
    hi = sorted(body.data.vertices, key=lambda v: -v.co.z)[:12]
    for v in hi:
        ws = {gnames2[g.group]: round(g.weight, 2) for g in v.groups}
        print(f"  outlier z={v.co.z:.2f} pos=({v.co.x:.2f},{v.co.y:.2f}) w={ws}")

    # 4b) mirror into our space: mpfb _l (+x) -> our .l (-x)
    mirror_mesh_x(body)

    # merge mpfb-name groups -> our names (sum merges: spine_02+03 -> chest)
    for g in list(body.vertex_groups):
        body.vertex_groups.remove(g)
    our_vgs = {}
    for our_name in set(BONE_MAP.values()) | set(forced.values()):
        if our_name:
            our_vgs[our_name] = body.vertex_groups.new(name=our_name)
    vweights = {}
    for new_i, w in mpfb_weights.items():
        merged = {}
        for mn, wt in w.items():
            on = BONE_MAP.get(mn)
            if on:
                merged[on] = merged.get(on, 0.0) + wt
        total = sum(merged.values()) or 1.0
        vweights[new_i] = cap_influences({k: v / total for k, v in merged.items()})
    # forced helpers keep their dedicated bones (eyes -> eye.l/r, jaw extras)
    for new_i, old_i in enumerate(keep_verts):
        if old_i in forced:
            vweights[new_i] = {forced[old_i]: 1.0}
    for new_i, w in vweights.items():
        for our_b, wt in w.items():
            our_vgs[our_b].add([new_i], wt, "REPLACE")

    # 5) optional decimate (mesh groups carry the weights through)
    if ARGS.decimate > 0:
        mod = body.modifiers.new("dec", "DECIMATE")
        mod.ratio = ARGS.decimate
        mod.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = body
        bpy.ops.object.modifier_apply(modifier=mod.name)

    # 6) dominant bone per vert -> slot (weights re-read post-decimate)
    body.data.update()
    wmap = vert_weight_map(body)
    vert_slot = {}
    for vi, gs in wmap.items():
        b = max(gs.items(), key=lambda kv: kv[1])[0] if gs else "root"
        for slot, bones in SLOTS.items():
            if b in bones:
                vert_slot[vi] = slot
                break
        else:
            vert_slot[vi] = "body_torso"  # fallback

    # face -> slot by plurality (ties -> smaller slot id)
    def face_slot(p):
        cnt = {}
        for vi in p.vertices:
            s = vert_slot[vi]
            cnt[s] = cnt.get(s, 0) + 1
        return sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    slot_faces = {s: [] for s in SLOTS}
    for p in body.data.polygons:
        slot_faces[face_slot(p)].append(p)

    # 7) emit per-part GLBs
    only = set(ARGS.only.split(",")) if ARGS.only else set(SLOTS)
    emitted = {}
    for slot, faces in slot_faces.items():
        if slot not in only or not faces:
            continue
        vset = sorted({vi for p in faces for vi in p.vertices})
        vremap = {o: n for n, o in enumerate(vset)}
        part_me = bpy.data.meshes.new(slot)
        part_me.from_pydata(
            [body.data.vertices[i].co.copy() for i in vset], [],
            [[vremap[v] for v in p.vertices] for p in faces])
        part_me.update()
        for m in new_me.materials:
            part_me.materials.append(m)
        for n_i, p in enumerate(part_me.polygons):
            p.material_index = faces[n_i].material_index
        part = bpy.data.objects.new(slot, part_me)
        bpy.context.collection.objects.link(part)
        # vertex groups: only bones actually used by this part
        used = set()
        for o_i in vset:
            used.update(b for b, w in wmap.get(o_i, {}).items() if w > 0)
        for b in used:
            vg = part.vertex_groups.new(name=b)
            for n_i, o_i in enumerate(vset):
                wt = wmap.get(o_i, {}).get(b, 0.0)
                if wt > 0:
                    vg.add([n_i], wt, "REPLACE")
        part.parent = our_arm
        mod = part.modifiers.new("arm", "ARMATURE")
        mod.object = our_arm
        emitted[slot] = len(faces)
        print(f"PART {slot}: {len(vset)} verts {len(faces)} faces bones={len(used)}")

    # 8) export: hide kept-body object; export parts + armature
    body.hide_set(True)
    body.hide_render = True
    out_dir = os.path.abspath(ARGS.out_dir)
    for slot in emitted:
        part = bpy.data.objects[slot]
        for o in bpy.data.objects:
            o.select_set(False)
        our_arm.select_set(True)
        part.select_set(True)
        part_dir = os.path.join(out_dir, slot, "export")
        os.makedirs(part_dir, exist_ok=True)
        bpy.ops.export_scene.gltf(
            filepath=os.path.join(part_dir, f"{slot}.glb"),
            use_selection=True, export_animations=True,
            export_skins=True, export_yup=True)
        print("WROTE", slot)
    if ARGS.preview:
        for o in bpy.data.objects:
            o.select_set(False)
        our_arm.select_set(True)
        for s in emitted:
            bpy.data.objects[s].select_set(True)
        bpy.ops.export_scene.gltf(filepath=ARGS.preview, use_selection=True,
                                  export_animations=True, export_skins=True)
    print("DONE", json.dumps(emitted))

if __name__ == "__main__":
    main()
