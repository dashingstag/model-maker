import bpy, sys
try:
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService
except ImportError:
    from mpfb.services.humanservice import HumanService
bpy.ops.wm.read_factory_settings(use_empty=True)
base = {"gender":0.0,"age":0.5,"muscle":0.5,"weight":0.5,"proportions":0.5,
        "height":0.5,"cupsize":0.0,"firmness":0.5,
        "race":{"asian":0.33,"caucasian":0.33,"african":0.33}}
for cup in (0.0, 1.0):
    m = dict(base); m["cupsize"] = cup
    h = HumanService.create_human(mask_helpers=True, detailed_helpers=False,
        extra_vertex_groups=False, feet_on_ground=True, scale=0.1,
        macro_detail_dict=m)
    # chest band z (blender) ~1.15-1.35 in 0.1-scale? measure max -y (front) at chest z
    vs = [h.matrix_world @ v.co for v in h.data.vertices]
    band = [v for v in vs if 0.11 < v.z < 0.13]
    front = min(v.y for v in band)
    print(f"cup={cup}: band={len(band)} front_y={front:.4f}")
    bpy.data.objects.remove(h, do_unlink=True)
