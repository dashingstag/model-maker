import bpy, sys
try:
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService
    from bl_ext.blender_org.mpfb.services.targetservice import TargetService
except ImportError:
    from mpfb.services.humanservice import HumanService
    from mpfb.services.targetservice import TargetService
bpy.ops.wm.read_factory_settings(use_empty=True)
base = {"gender":0.0,"age":0.5,"muscle":0.5,"weight":0.5,"proportions":0.5,
        "height":0.5,"cupsize":1.0,"firmness":0.5,
        "race":{"asian":0.33,"caucasian":0.33,"african":0.33}}
h = HumanService.create_human(mask_helpers=True, detailed_helpers=False,
    extra_vertex_groups=False, feet_on_ground=True, scale=0.1,
    macro_detail_dict=base)
print("shape_keys:", h.data.shape_keys)
print("has sk:", bool(h.data.shape_keys))
if h.data.shape_keys:
    print("keys:", [k.name for k in h.data.shape_keys.key_blocks][:10])
# evaluated mesh (applies shape keys + modifiers)
dg = bpy.context.evaluated_depsgraph_get()
ev = h.evaluated_get(dg)
me = ev.to_mesh()
vs = [h.matrix_world @ v.co for v in me.vertices]
band = [v for v in vs if 0.11 < v.z < 0.13]
print("evaluated front_y:", round(min(v.y for v in band),4), "verts:", len(me.vertices))
# also check direct TargetService call
TargetService.reapply_macro_details(h)
dg = bpy.context.evaluated_depsgraph_get()
ev = h.evaluated_get(dg)
me2 = ev.to_mesh()
vs2 = [h.matrix_world @ v.co for v in me2.vertices]
band2 = [v for v in vs2 if 0.11 < v.z < 0.13]
print("post-reapply front_y:", round(min(v.y for v in band2),4))
