"""Ambient-occlusion bake for generated shell-cloud meshes — writes
an AO map in the existing UV atlas layout, for pbr_fix.py --ao to
embed as occlusionTexture (R channel).

    blender --background --python tools/blender_ao.py -- \
        <in.glb> <out.png> [size]

Cycles raycast AO tolerates non-manifold island geometry — bake
doesn't need manifoldness, only UVs. Low sample count is fine: AO
is a soft multiplier, not a detail map.
"""
import sys

import bpy

ARGV = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = ARGV[0], ARGV[1]
SIZE = int(ARGV[2]) if len(ARGV) > 2 else 1024


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=SRC)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 48
    sc.cycles.bake_type = "AO"
    sc.cycles.use_denoising = False
    try:
        sc.cycles.device = "GPU"
    except Exception:
        pass

    body = max((o for o in bpy.data.objects if o.type == "MESH"),
               key=lambda o: len(o.data.vertices))
    img = bpy.data.images.new("ao_bake", width=SIZE, height=SIZE)
    img.colorspace_settings.name = "Non-Color"
    for m in body.data.materials:
        if not m or not m.use_nodes:
            continue
        node = m.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = img
        m.node_tree.nodes.active = node
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.bake(type="AO", margin=16)
    img.filepath_raw = OUT
    img.file_format = "PNG"
    img.save()
    print("ao ->", OUT)


main()
