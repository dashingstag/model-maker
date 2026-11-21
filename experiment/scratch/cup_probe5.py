import bpy
try:
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService
except ImportError:
    from mpfb.services.humanservice import HumanService
bpy.ops.wm.read_factory_settings(use_empty=True)
base = {"gender":0.0,"age":0.5,"muscle":0.45,"weight":0.5,"proportions":0.65,
        "height":0.5,"cupsize":0.0,"firmness":0.6,
        "race":{"asian":0.33,"caucasian":0.33,"african":0.33}}
def eval_band_front(**kw):
    m = dict(base); m.update(kw)
    h = HumanService.create_human(mask_helpers=True, detailed_helpers=False,
        extra_vertex_groups=False, feet_on_ground=True, scale=0.1,
        macro_detail_dict=m)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = h.evaluated_get(dg)
    me = ev.to_mesh()
    n = len(me.vertices)
    vs = [h.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    bpy.data.objects.remove(h, do_unlink=True)
    band = [v for v in vs if 0.11 < v.z < 0.13]
    return min(v.y for v in band), n
f0, n = eval_band_front(cupsize=0.0)
f1, _ = eval_band_front(cupsize=1.0)
gm, _ = eval_band_front(gender=1.0, cupsize=0.0)
print(f"EVAL front_y: cup0={f0:.4f} cup1={f1:.4f} male={gm:.4f} verts={n}")
