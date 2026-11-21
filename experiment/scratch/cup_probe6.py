import bpy
try:
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService
except ImportError:
    from mpfb.services.humanservice import HumanService
bpy.ops.wm.read_factory_settings(use_empty=True)
base = {"gender":0.0,"age":0.5,"muscle":0.45,"weight":0.5,"proportions":0.65,
        "height":0.5,"cupsize":0.0,"firmness":0.6,
        "race":{"asian":0.33,"caucasian":0.33,"african":0.33}}
def eval_front(**kw):
    m = dict(base); m.update(kw)
    h = HumanService.create_human(mask_helpers=True, detailed_helpers=False,
        extra_vertex_groups=False, feet_on_ground=True, scale=0.1,
        macro_detail_dict=m)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = h.evaluated_get(dg)
    me = ev.to_mesh()
    vs = [h.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    bpy.data.objects.remove(h, do_unlink=True)
    out = {}
    for lo, hi, nm in ((0.12,0.135,"chest-lo"),(0.135,0.148,"chest-hi")):
        band = [v for v in vs if lo < v.z < hi]
        out[nm] = (round(min(v.y for v in band),4), len(band))
    return out
for label, kw in (("cup0",dict(cupsize=0.0)), ("cup1",dict(cupsize=1.0)),
                  ("male",dict(gender=1.0, cupsize=0.0))):
    print("EVAL", label, eval_front(**kw))
