import bpy, sys
try:
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService
except ImportError:
    from mpfb.services.humanservice import HumanService
bpy.ops.wm.read_factory_settings(use_empty=True)
base = {"gender":0.0,"age":0.5,"muscle":0.5,"weight":0.5,"proportions":0.5,
        "height":0.5,"cupsize":0.0,"firmness":0.5,
        "race":{"asian":0.33,"caucasian":0.33,"african":0.33}}
def probe(**kw):
    m = dict(base); m.update(kw)
    h = HumanService.create_human(mask_helpers=True, detailed_helpers=False,
        extra_vertex_groups=False, feet_on_ground=True, scale=0.1,
        macro_detail_dict=m)
    vs = [h.matrix_world @ v.co for v in h.data.vertices]
    band = [v for v in vs if 0.11 < v.z < 0.13]
    ys = [v.y for v in band]
    print(f"{kw}: band={len(band)} ymin={min(ys):.4f} ymax={max(ys):.4f}")
    bpy.data.objects.remove(h, do_unlink=True)
probe(cupsize=0.0); probe(cupsize=1.0)
probe(gender=0.0, cupsize=1.0); probe(gender=1.0)
