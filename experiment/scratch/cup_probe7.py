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
    zs = [v.z for v in vs]
    # front protrusion per 1cm-z slice (torso only: z 0.10-0.15)
    prof = []
    for i in range(10, 16):
        band = [v for v in vs if i/100 <= v.z < (i+1)/100]
        if band:
            prof.append((i, len(band), round(min(v.y for v in band),4)))
    return round(min(zs),3), round(max(zs),3), prof
for label, kw in (("cup0",dict(cupsize=0.0)), ("cup1",dict(cupsize=1.0)),
                  ("male",dict(gender=1.0, cupsize=0.0))):
    print("EVAL", label, eval_front(**kw))
