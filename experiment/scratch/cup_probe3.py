import bpy, sys
try:
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService
except ImportError:
    from mpfb.services.humanservice import HumanService
bpy.ops.wm.read_factory_settings(use_empty=True)
base = {"gender":0.0,"age":0.5,"muscle":0.5,"weight":0.5,"proportions":0.5,
        "height":0.5,"cupsize":0.0,"firmness":0.5,
        "race":{"asian":0.33,"caucasian":0.33,"african":0.33}}
def verts(**kw):
    m = dict(base); m.update(kw)
    h = HumanService.create_human(mask_helpers=True, detailed_helpers=False,
        extra_vertex_groups=False, feet_on_ground=True, scale=0.1,
        macro_detail_dict=m)
    vs = [(h.matrix_world @ v.co)[:] for v in h.data.vertices]
    bpy.data.objects.remove(h, do_unlink=True)
    return vs
a = verts(cupsize=0.0); b = verts(cupsize=1.0)
d = max(abs(a[i][k]-b[i][k]) for i in range(len(a)) for k in range(3))
print("max vert delta cup0 vs cup1:", round(d,5))
c = verts(gender=1.0)
d2 = max(abs(a[i][k]-c[i][k]) for i in range(len(a)) for k in range(3))
print("max vert delta cup0female vs male:", round(d2,5))
