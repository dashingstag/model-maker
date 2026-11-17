"""Painted-mesh reskin — bind a generated (textured, non-manifold) mesh
to the rigged template's skeleton by transferring vertex-group weights
from the *conformed* template parts, which already sit on the target's
silhouette carrying semantically correct rigid bone assignments
(sleeve part -> forearm, skirt panel -> thigh, hair -> head).

    blender --background --python tools/blender_reskin.py -- \
        <weight_src.glb> <target.glb> <out.glb>

weight_src = a rigged GLB whose meshes are conformed to the target
(certified export/ GLB works — armature + skin + per-part weights).
Steps:
  1. import source, keep armature + its meshes (joined for lookup)
  2. import target, normalize to source frame (height fit, feet z=0)
  3. drop loose floating islands (provider artifacts like detached rods)
  4. DATA_TRANSFER vertex groups source->target, nearest-face interp
  5. target takes the armature modifier; source meshes are removed
  6. export GLB — same skeleton/clips/sockets, painted mesh skinned

Honest limits: a single generated blob still deforms like a blob —
fused hands keep mitten geometry, skirt verts near legs inherit leg
weights (acceptable on robed figures), and texture follows whatever
the transfer assigns at seams. Retopo for cleaner deformation is a
separate question — QuadriFlow no-ops on non-manifold input (#75+).
"""
import math
import os
import sys

import bpy
import mathutils
from mathutils.bvhtree import BVHTree

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, TARGET, OUT = ARGV[0], ARGV[1], ARGV[2]


def _bounds(objs):
    mn = mathutils.Vector((1e9,) * 3)
    mx = mathutils.Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            mn = mathutils.Vector(map(min, mn, w))
            mx = mathutils.Vector(map(max, mx, w))
    return (mn + mx) / 2, (mx - mn)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=SRC)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    src_meshes = [o for o in bpy.data.objects if o.type == "MESH"]

    pre = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=TARGET)
    tgen = [o for o in bpy.data.objects
            if o not in pre and o.type == "MESH"]
    for o in [x for x in bpy.data.objects
              if x not in pre and x.type != "MESH"]:
        bpy.data.objects.remove(o)
    for o in tgen[1:]:
        o.select_set(True)
    tgen[0].select_set(True)
    bpy.context.view_layer.objects.active = tgen[0]
    if len(tgen) > 1:
        bpy.ops.object.join()
    tgt = tgen[0]

    # normalize target to source frame (same as blender_conform)
    _sc, sdim = _bounds([arm] + src_meshes)
    gc, gdim = _bounds([tgt])
    s = sdim.z / gdim.z if gdim.z else 1.0
    tgt.scale = (s,) * 3
    tgt.location -= mathutils.Vector(
        (gc.x, gc.y, gc.z - gdim.z / 2)) * s
    bpy.context.view_layer.update()

    # drop loose floating islands — provider artifacts (detached rods,
    # shards) sit as separate loose components; keep the main body.
    bpy.context.view_layer.objects.active = tgt
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")
    parts = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    parts.sort(key=lambda o: len(o.data.vertices), reverse=True)
    # generated meshes arrive as hundreds of detached shells — the body
    # is the *cluster* of bbox-touching islands, not a main island.
    # Flood-fill from the largest; floaters (detached rods, shards) sit
    # in their own cluster and get dropped.
    def _bb(o):
        return _bounds([o])
    cluster = {0}
    bbs = [_bb(o) for o in parts]
    changed = True
    while changed:
        changed = False
        for i in range(len(parts)):
            if i in cluster:
                continue
            ic, idd = bbs[i]
            for j in cluster:
                jc, jd = bbs[j]
                if (abs(ic.x - jc.x) <= (idd.x + jd.x) / 2
                        and abs(ic.y - jc.y) <= (idd.y + jd.y) / 2
                        and abs(ic.z - jc.z) <= (idd.z + jd.z) / 2):
                    cluster.add(i)
                    changed = True
                    break
    kept, dropped = [], []
    for i, o in enumerate(parts):
        if i in cluster:
            kept.append(o)
        else:
            dropped.append((o.name, len(o.data.vertices)))
            bpy.data.objects.remove(o)
    main = parts[0]
    if kept:
        # re-join kept islands back into the main mesh
        bpy.ops.object.select_all(action="DESELECT")
        for o in [x for x in bpy.data.objects if x.type == "MESH"
                  and x is not main and x in parts]:
            o.select_set(True)
        main.select_set(True)
        bpy.context.view_layer.objects.active = main
        bpy.ops.object.join()
    tgt = main
    if dropped:
        print("dropped floaters:", dropped)

    # weight transfer — the template parts are *bone-parented* (no
    # vertex groups): each vert samples its two nearest source parts
    # via BVH and inherits their parent_bone, inverse-distance-squared
    # blended so joints deform smoothly instead of tearing
    parts_bvh = []
    dg = bpy.context.evaluated_depsgraph_get()
    for m in src_meshes:
        if m.parent_type != "BONE" or not m.parent_bone:
            continue
        ev = m.evaluated_get(dg)
        bvh = mathutils.bvhtree.BVHTree.FromObject(ev, dg)
        # detail bones (finger phalanges, jaw, eyes) drive tiny stub
        # parts — cap their grab radius or distant cloth verts bind to
        # them and stretch into spikes when the hand/jaw moves
        detail = (m.parent_bone.count(".") >= 3
                  or m.parent_bone in ("jaw", "eye.l", "eye.r"))
        parts_bvh.append((bvh, m.parent_bone, 0.06 if detail else None))
    bones = sorted({b for _, b, _ in parts_bvh})
    vgs = {b: tgt.vertex_groups.new(name=b) for b in bones}
    mw = tgt.matrix_world
    for v in tgt.data.vertices:
        co = mw @ v.co
        near = []  # (dist_sq, bone) top-2
        for bvh, bname, cap in parts_bvh:
            hit = bvh.find_nearest(co)
            if hit[0] is None:
                continue
            d2 = (hit[0] - co).length_squared
            if cap and d2 > cap * cap:
                continue
            near.append((d2, bname))
        near.sort(key=lambda t: t[0])
        if len(near) >= 2 and near[1][0] < near[0][0] * 1.5 + 1e-8:
            w1 = 1.0 / (near[0][0] + 1e-8)
            w2 = 1.0 / (near[1][0] + 1e-8)
            vgs[near[0][1]].add([v.index], w1 / (w1 + w2), "REPLACE")
            vgs[near[1][1]].add([v.index], w2 / (w1 + w2), "REPLACE")
        elif near:
            vgs[near[0][1]].add([v.index], 1.0, "REPLACE")

    # report transfer coverage — verts with no weight would freeze
    # in rest pose while everything else moves (loud, not silent)
    weighted = 0
    for v in tgt.data.vertices:
        if any(g.weight > 0.01 for g in v.groups):
            weighted += 1
    print("weighted verts: %d/%d" % (weighted, len(tgt.data.vertices)))

    # armature binding — the transferred groups already carry the skin
    arm_mod = tgt.modifiers.new("armature", "ARMATURE")
    arm_mod.object = arm
    tgt.parent = arm

    for m in src_meshes:
        bpy.data.objects.remove(m)
    bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB",
                              export_yup=True)
    print("reskinned ->", OUT)


main()
