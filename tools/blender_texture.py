"""Texture + retopo post-step for provider-generated meshes.

Runs inside Blender:  blender --background --python tools/blender_texture.py -- \
    <in.glb> <out.glb> <ref_image.png> [--faces N] [--tex N] [--view front|turntable]

Pipeline: import -> optional Quadriflow retopo -> smart UV -> project the
reference image from a fitted camera -> bake to albedo texture -> export GLB.

This is mymeshy's degrade path: when the AI paint stage is unavailable, the
source concept art IS the albedo for the hemisphere it describes. Back faces
inherit baked-margin smear (honest limitation — single-view projection).
--view turntable samples 4 cardinal views into separate bake passes merged by
normal-weighted texel ownership, covering the full silhouette.
"""
import math
import os
import sys
import tempfile

import bpy
import mathutils
import numpy as np

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, DST, REF = ARGV[0], ARGV[1], ARGV[2]


def _opt(name, default=None):
    return ARGV[ARGV.index(name) + 1] if name in ARGV else default


FACES = int(_opt("--faces", "0"))
TEX = int(_opt("--tex", "1024"))
VIEWS = ["front"] if _opt("--view", "front") != "turntable" else \
    ["front", "back", "left", "right"]


def _bounds(objs):
    mn = mathutils.Vector((1e9,) * 3)
    mx = mathutils.Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(c)
            mn = mathutils.Vector(map(min, mn, w))
            mx = mathutils.Vector(map(max, mx, w))
    return (mn + mx) / 2, (mx - mn)


_VIEW_DIR = {"front": (0, -1, 0.05), "back": (0, 1, 0.05),
             "left": (-1, 0, 0.05), "right": (1, 0, 0.05)}


def _project_uv(obj, view, ctr, crop):
    """Manual ortho projection into UV layer 'proj_<view>' — the
    uv.project_from_view operator needs a UI region (fails headless), so
    transform verts into camera space and emit [0,1] coords directly.
    Scale fits the *projected* extents (not the bbox diagonal), and each
    axis is scaled independently so the image's figure bbox lands exactly
    on the mesh's silhouette bbox."""
    v = mathutils.Vector(_VIEW_DIR[view]).normalized()
    d = -v
    rot = d.to_track_quat("-Z", "Y").to_euler().to_matrix()
    mw = obj.matrix_world
    pts = [(rot @ (mw @ vert.co - ctr)) for vert in obj.data.vertices]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    sx = max(xs) - min(xs) or 1.0
    sy = max(ys) - min(ys) or 1.0
    cx = (max(xs) + min(xs)) / 2
    cy = (max(ys) + min(ys)) / 2
    uvl = obj.data.uv_layers.new(name="proj_" + view)
    data = uvl.data
    u0, v0, uw, vh = crop
    for poly in obj.data.polygons:
        for li in poly.loop_indices:
            p = pts[obj.data.loops[li].vertex_index]
            u = (p.x - cx) / sx + 0.5
            vv = (p.y - cy) / sy + 0.5
            data[li].uv = (u * uw + u0, vv * vh + v0)
    uvl.active_render = False


def _bake_normal(obj):
    """World-space normal map on the 'albedo' UV layer — one bake shared
    by the multi-view merge to pick each texel's best-facing view."""
    img = bpy.data.images.new("normals", width=TEX, height=TEX)
    mat = bpy.data.materials.new("nb")
    mat.use_nodes = True
    nt = mat.node_tree
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = img
    tn.select = True
    nt.nodes.active = tn
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    obj.data.uv_layers.active = obj.data.uv_layers["albedo"]
    bpy.context.view_layer.objects.active = obj
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 1
    bpy.ops.object.bake(type="NORMAL", normal_space="OBJECT", margin=0)
    return img


def _bake_view(obj, view, img):
    """Bake ref image sampled through proj_<view> into per-view texture."""
    proj = obj.data.uv_layers["proj_" + view]
    final = obj.data.uv_layers["albedo"]
    # shader: image at projected-UV -> emission -> bake to `albedo` UV layer
    mat = bpy.data.materials.new("bake_" + view)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    tex = nt.nodes.new("ShaderNodeTexImage")
    uvm = nt.nodes.new("ShaderNodeUVMap")
    uvm.uv_map = proj.name
    tex.image = img
    nt.links.new(uvm.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    # bake target image on the final UV layer
    baked = bpy.data.images.new("bake_" + view, width=TEX, height=TEX)
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = baked
    obj.data.uv_layers.active = final
    tn.select = True
    nt.nodes.active = tn
    bpy.context.view_layer.objects.active = obj
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.samples = 1
    bpy.ops.object.bake(type="EMIT", margin=8)
    return baked


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=SRC)
    objs = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in objs[1:]:
        bpy.data.objects.remove(o)
    obj = objs[0]
    if FACES:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.quadriflow_remesh(target_faces=FACES)
        print("quadriflow ->", len(obj.data.polygons), "faces")
        # QuadriFlow overshoots its target on dense organic inputs (it
        # keeps a topology-dependent minimum) — collapse to the budget
        # when the remesh leaves us over it
        if len(obj.data.polygons) > FACES:
            mod = obj.modifiers.new("decimate", "DECIMATE")
            mod.ratio = FACES / len(obj.data.polygons)
            mod.use_collapse_triangulate = True
            bpy.ops.object.modifier_apply(modifier=mod.name)
            print("decimate ->", len(obj.data.polygons), "faces")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj.data.uv_layers.active.name = "albedo"
    ctr, dim = _bounds([obj])
    img = bpy.data.images.load(REF)
    # sprite art has margins — find the drawn figure's alpha bbox so
    # projections land it exactly on the mesh silhouette (uv remap below)
    px = np.array(img.pixels[:]).reshape(img.size[1], img.size[0], 4)
    ys, xs = np.where(px[:, :, 3] > 0.05)
    if len(ys):
        w, h = img.size
        x0, x1 = xs.min() / w, (xs.max() + 1) / w
        y0, y1 = ys.min() / h, (ys.max() + 1) / h
        crop = (x0, y0, x1 - x0, y1 - y0)
    else:
        crop = (0.0, 0.0, 1.0, 1.0)
    del px
    bakes = []
    for v in VIEWS:
        _project_uv(obj, v, ctr, crop)
        bakes.append(_bake_view(obj, v, img))
    # merge views by normal alignment — each texel takes the view whose
    # direction best matches its surface normal (baked once to a world
    # normal map); coverage alone would let front win everywhere since
    # projected UVs cover the whole island
    merged = bakes[0] if len(bakes) == 1 else bakes[0].copy()
    merged.name = "albedo"
    if len(bakes) > 1:
        normals = _bake_normal(obj)
        n = np.array(normals.pixels[:]).reshape(-1, 4)[:, :3] * 2 - 1
        n /= (np.linalg.norm(n, axis=1, keepdims=True) + 1e-9)
        cov = np.array(bakes[0].pixels[:]).reshape(-1, 4)[:, 3] > 0.01
        views = np.stack([np.array(b.pixels[:]).reshape(-1, 4)
                          for b in bakes])
        # view dirs live in world space — the baked normal map is OBJECT
        # space, so rotate dirs into the object's own frame
        inv_rot = np.array(obj.matrix_world.inverted().to_3x3())
        dirs = np.stack([inv_rot @ np.array(_VIEW_DIR[v])
                         for v in VIEWS])
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
        score = n @ dirs.T
        best = score.argmax(axis=1)
        base = views[0].copy()
        for vi in range(1, len(bakes)):
            sel = (best == vi)
            base[sel] = views[vi][sel]
        base[~cov, 3] = 0.0
        merged.pixels[:] = base.ravel()
        merged.update()
    merged.filepath_raw = os.path.join(
        tempfile.gettempdir(), "mm_albedo_%d.png" % os.getpid())
    merged.file_format = "PNG"
    merged.save()
    merged.pack()
    os.remove(merged.filepath_raw)
    # final material: baked albedo -> principled -> export with textures
    mat = bpy.data.materials.new("albedo")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bs.inputs["Roughness"].default_value = 0.7
    bs.inputs["Metallic"].default_value = 0.0
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = merged
    nt.links.new(tex.outputs["Color"], bs.inputs["Base Color"])
    nt.links.new(bs.outputs["BSDF"], out.inputs["Surface"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    obj.data.uv_layers.active = obj.data.uv_layers["albedo"]
    bpy.ops.export_scene.gltf(
        filepath=DST, export_format="GLB",
        export_image_format="AUTO", export_yup=True)
    print("textured ->", DST)


main()
