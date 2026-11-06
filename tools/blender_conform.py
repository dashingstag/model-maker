"""Template conform — deform a rigged humanoid_v1 template onto a
generated silhouette so the result keeps the template's skeleton,
vertex groups, and UVs.

    blender --background --python tools/blender_conform.py -- \
        <template.glb> <target.glb> <out.glb>

The template is any rigged mannequin GLB (armature + skinned meshes —
its bind-pose should roughly match the target's stance; Hunyuan3D emits
neutral-ish figures). The target is a generated (optionally textured)
mesh. Steps:

  1. import template, keep armature + its meshes
  2. import target, normalize it to the template's frame (height fit,
     feet at z=0)
  3. shrinkwrap every template mesh to the target surface
  4. bake the target's albedo onto the template UVs (selected→active
     EMIT bake — texture follows the conform, UVs stay template's)
  5. export GLB — armature, skinned meshes, baked albedo

Honest limits: silhouette mismatches (open robe vs bare armature pose)
stretch faces toward the nearest surface — reads as a fitted costume,
not topology-aware cloth. Pose offset between template bind pose and
the generated stance is the main artifact source.
"""
import math
import os
import sys
import tempfile

import bpy
import mathutils

ARGV = sys.argv[sys.argv.index("--") + 1:]
TEMPLATE, TARGET, OUT = ARGV[0], ARGV[1], ARGV[2]
TEX = 1024


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
    bpy.ops.import_scene.gltf(filepath=TEMPLATE)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    tmesh = [o for o in bpy.data.objects if o.type == "MESH"]

    pre = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=TARGET)
    tgen = [o for o in bpy.data.objects if o not in pre and o.type == "MESH"]
    for o in list(bpy.data.objects):
        if o not in pre and o.type != "MESH":
            bpy.data.objects.remove(o)
    tgt = tgen[0]
    if len(tgen) > 1:
        for o in tgen[1:]:
            o.select_set(True)
        tgt.select_set(True)
        bpy.context.view_layer.objects.active = tgt
        bpy.ops.object.join()
    # join() may leave extra target objects unselected — drop non-tgt
    for o in [x for x in bpy.data.objects if x not in pre and x is not tgt]:
        bpy.data.objects.remove(o)

    # fit target to template frame: same height, feet to z=0, centered
    _tc, tdim = _bounds([arm] + tmesh)
    gc, gdim = _bounds([tgt])
    s = tdim.z / gdim.z if gdim.z else 1.0
    tgt.scale = (s,) * 3
    tgt.location -= mathutils.Vector(
        (gc.x, gc.y, gc.z - gdim.z / 2)) * s
    bpy.context.view_layer.update()

    # conform: shrinkwrap each template mesh onto the target surface
    for m in tmesh:
        bpy.context.view_layer.objects.active = m
        mod = m.modifiers.new("conform", "SHRINKWRAP")
        mod.target = tgt
        mod.wrap_method = "NEAREST_SURFACEPOINT"
        mod.offset = 0.004
        bpy.ops.object.modifier_apply(modifier=mod.name)

    # texture transfer: target emits its albedo, template bakes to own UV
    tmp_pngs = []
    src_img = None
    for slot in tgt.data.materials:
        if not slot or not slot.use_nodes:
            continue
        for n in slot.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                src_img = n.image
                break
    if src_img is not None:
        mat = bpy.data.materials.new("emit_src")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out_n = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = src_img
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out_n.inputs["Surface"])
        tgt.data.materials.clear()
        tgt.data.materials.append(mat)

        bpy.context.scene.render.engine = "CYCLES"
        bpy.context.scene.cycles.samples = 1
        for m in tmesh:
            # primitive-template meshes may carry no UV layer — the bake
            # needs one; smart-project gives a deterministic default
            if not m.data.uv_layers:
                bpy.context.view_layer.objects.active = m
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                bpy.ops.uv.smart_project(
                    angle_limit=math.radians(66), island_margin=0.02)
                bpy.ops.object.mode_set(mode="OBJECT")
            img = bpy.data.images.new(
                "albedo_" + m.name, width=TEX, height=TEX)
            mm = bpy.data.materials.new("bake_" + m.name)
            mm.use_nodes = True
            tn = mm.node_tree.nodes.new("ShaderNodeTexImage")
            tn.image = img
            tn.select = True
            mm.node_tree.nodes.active = tn
            m.data.materials.clear()
            m.data.materials.append(mm)
            m.hide_set(False)
        # bake checks effective visibility incl. parents — armature-parented
        # parts inherit OB_HIDE_RENDER, so clear it scene-wide
        for o in bpy.data.objects:
            o.hide_render = False
            o.hide_viewport = False
        # selected_to_active writes only to the active object — bake each
        # template mesh in turn or every other part exports black
        missed = []
        for m in tmesh:
            bpy.ops.object.select_all(action="DESELECT")
            m.select_set(True)
            tgt.select_set(True)
            bpy.context.view_layer.objects.active = m
            try:
                bpy.ops.object.bake(
                    type="EMIT", use_selected_to_active=True, margin=8,
                    cage_extrusion=0.5)
            except RuntimeError as e:
                missed.append(m.name)
                print("bake skipped:", m.name, "-", e)
        if missed:
            print("bake missed parts:", ", ".join(missed))
        tmp_pngs = []
        for m in tmesh:
            m.select_set(False)
            img = bpy.data.images["albedo_" + m.name]
            p = os.path.join(
                tempfile.gettempdir(),
                "mm_conf_%s_%d.png" % (m.name, os.getpid()))
            img.filepath_raw = p
            img.file_format = "PNG"
            img.save()
            img.pack()
            tmp_pngs.append(p)
            mat = bpy.data.materials["bake_" + m.name]
            mat.name = "albedo"
            nt = mat.node_tree
            nt.nodes.clear()
            out_n = nt.nodes.new("ShaderNodeOutputMaterial")
            bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
            bs.inputs["Roughness"].default_value = 0.75
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = img
            nt.links.new(tex.outputs["Color"], bs.inputs["Base Color"])
            nt.links.new(bs.outputs["BSDF"], out_n.inputs["Surface"])

    bpy.data.objects.remove(tgt)
    bpy.ops.export_scene.gltf(
        filepath=OUT, export_format="GLB", export_yup=True)
    for p in tmp_pngs:
        try:
            os.remove(p)
        except OSError:
            pass
    print("conformed ->", OUT)


main()
