"""Face geometry pass — crisp eye/brow cards bone-parented to `head`
on generated painted meshes whose face texture is too coarse to carry
features (the whole face lands on ~50x80 atlas texels — drawn detail
smears back into noise; geometry is the only honest route).

    blender --background --python tools/blender_face.py -- \
        <in.glb> <out.glb>

What it adds:
  * two eye groups — white sclera ellipse + iris disc + catchlight,
    placed on the detected face surface (front-most skin-band verts),
    bone-parented to `head` so they ride head anims
  * two brow bars angled off the eye tops
Honest limits: flat cards on a blob — no lids, no SDF shadowing;
reads at gameplay distance, not closeups. Positions derive from the
mesh's own eye-band verts (front z at x ~ +-0.065), not the template
frame — the painted head sits ~1m above the template's head pivot.

Cards are built with from_pydata in world space — no bpy.ops, no
object scale — because parented-ops ordering loses transforms.
Also strips stray unskinned provider artifacts (e.g. the Icosphere
the generator hides inside the shell cloud).
"""
import math
import os
import sys

import bpy
import mathutils

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = ARGV[0], ARGV[1]


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=SRC)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    body = max(meshes, key=lambda o: len(o.data.vertices))

    # strip unskinned strays the generator leaves inside the shell
    # (e.g. its hidden Icosphere — a 2m ball at the origin that only
    # stays invisible while buried inside the body shells)
    for o in [m for m in meshes if m is not body]:
        if not o.vertex_groups:
            bpy.data.objects.remove(o, do_unlink=True)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]

    # face surface: head cluster = verts near the top; face plane =
    # most-forward y at eye height (glTF->Blender: forward is -y)
    mw = body.matrix_world
    verts = [mw @ v.co for v in body.data.vertices]
    zs = [v.z for v in verts]
    ztop = max(zs)
    head_v = [v for v in verts if v.z > ztop - 0.35]
    eye_y = ztop - 0.20

    def surface_at(xc, zc=None):
        # hood rim juts past the recessed face at eye height — the
        # face is the DENSEST depth cluster, not the front-most vert
        zc = eye_y if zc is None else zc
        cand = [v.y for v in head_v
                if abs(v.x - xc) < 0.02 and abs(v.z - zc) < 0.04]
        if len(cand) < 3:
            return None
        bins = {}
        for y in cand:
            bins[round(y / 0.01)] = bins.get(round(y / 0.01), 0) + 1
        best = max(bins, key=bins.get)
        ys = [y for y in cand if abs(y - best * 0.01) < 0.008]
        return sum(ys) / len(ys)

    def mat(name, rgb, rough=0.5):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*rgb, 1.0)
        b.inputs["Roughness"].default_value = rough
        m.use_backface_culling = False
        return m

    sclera_m = mat("sclera", (0.92, 0.90, 0.86))
    iris_m = mat("iris", (0.10, 0.22, 0.26), rough=0.25)
    pupil_m = mat("pupil", (0.02, 0.02, 0.03), rough=0.3)
    brow_m = mat("brow", (0.28, 0.30, 0.34), rough=0.7)
    lip_m = mat("lips", (0.45, 0.22, 0.24), rough=0.55)

    def card(name, center, rx, ry, m, depth=0.004, roll=0.0):
        """Flat ellipse card built directly in world space — single
        n-gon keeps tri cost tiny (tri_budget is a hard gate).
        Face plane is XZ (normal = -y). roll slants it in-plane.
        depth is accepted for call compatibility and ignored."""
        cx, cy, cz = center
        seg = 14
        cr, sr = math.cos(roll), math.sin(roll)
        vs = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            u, v = rx * math.cos(a), ry * math.sin(a)
            vs.append((cx + u * cr - v * sr,
                       cy,
                       cz + u * sr + v * cr))
        me = bpy.data.meshes.new(name)
        # reversed winding: ccw seen from -y (the viewer side)
        me.from_pydata(vs, [], [tuple(reversed(range(seg)))])
        me.update()
        o = bpy.data.objects.new(name, me)
        bpy.context.collection.objects.link(o)
        me.materials.append(m)
        return o

    made = []
    for side, sx in (("l", -1.0), ("r", 1.0)):
        y_face = surface_at(sx * 0.040)
        if y_face is None:
            print("face: no %s eye surface" % side)
            continue
        ex, ey, ez = sx * 0.040, y_face - 0.006, eye_y
        made.append(card("eye_sclera." + side, (ex, ey, ez),
                         0.034, 0.019, sclera_m))
        made.append(card("eye_iris." + side, (ex, ey - 0.005, ez + 0.002),
                         0.014, 0.014, iris_m))
        made.append(card("eye_pupil." + side, (ex, ey - 0.008, ez + 0.002),
                         0.006, 0.006, pupil_m))
        made.append(card("eye_hi." + side, (ex - 0.005, ey - 0.011,
                                            ez + 0.006), 0.003, 0.003,
                         sclera_m, depth=0.003))
        made.append(card("brow." + side, (ex, ey - 0.004, ez + 0.036),
                         0.032, 0.006, brow_m, depth=0.005,
                         roll=sx * -0.18))

    # lip line — a thin muted card that covers the painted mouth smear
    y_mouth = surface_at(0.0, zc=eye_y - 0.055)
    if y_mouth is not None:
        made.append(card("lips", (0.0, y_mouth - 0.006, eye_y - 0.055),
                         0.022, 0.007, lip_m, depth=0.004))

    for o in made:
        o.parent = arm
        o.parent_type = 'BONE'
        o.parent_bone = "head"
        # verts are world-space; writing matrix_world makes Blender
        # solve matrix_basis for whatever bone frame it uses
        o.matrix_world = mathutils.Matrix.Identity(4)

    bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB",
                              export_yup=True)
    print("face ->", OUT, "| parts:", len(made))


main()
