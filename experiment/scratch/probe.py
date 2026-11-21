import bpy, sys
argv = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=argv[0])
for ob in bpy.context.scene.objects:
    if ob.type == 'MESH':
        print("MESH", ob.name, "hide_r=", ob.hide_render,
              "dim=", tuple(round(v, 3) for v in ob.dimensions),
              "loc=", tuple(round(v, 2) for v in ob.matrix_world.translation),
              "parent=", ob.parent.name if ob.parent else None,
              "ptype=", ob.parent_type,
              "pbone=", ob.parent_bone if ob.parent_type == 'BONE' else "")
    else:
        print(ob.type, ob.name)
