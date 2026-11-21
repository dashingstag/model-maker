import bpy
try:
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService
except ImportError:
    from mpfb.services.humanservice import HumanService
bpy.ops.wm.read_factory_settings(use_empty=True)
base = {"gender":0.0,"age":0.5,"muscle":0.45,"weight":0.5,"proportions":0.65,
        "height":0.5,"cupsize":0.0,"firmness":0.6,
        "race":{"asian":0.33,"caucasian":0.33,"african":0.33}}
for label, kw in (("cup0",dict(cupsize=0.0)), ("cup1",dict(cupsize=1.0))):
    m = dict(base); m.update(kw)
    h = HumanService.create_human(mask_helpers=True, detailed_helpers=False,
        extra_vertex_groups=False, feet_on_ground=True, scale=0.1,
        macro_detail_dict=m)
    print("KEYS", label)
    for k in h.data.shape_keys.key_blocks:
        if k.name != "Basis" and abs(k.value) > 0.0001:
            print("  ", k.name, round(k.value,3))
    bpy.data.objects.remove(h, do_unlink=True)
