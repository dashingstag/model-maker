import bpy, sys
from mathutils import Vector, Matrix

sys.path.insert(0, "C:/Workspace/Models/model-maker/tools")
from mpfb_body import BONE_MAP  # noqa

bpy.ops.wm.open_mainfile(filepath="C:/Workspace/Models/model-maker/experiment/scratch/mpfb_human.blend")
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
hum = next(o for o in bpy.data.objects if o.name == "Human")

bpy.ops.import_scene.gltf(filepath="C:/Workspace/Models/model-maker/pipeline/components/body_torso/export/body_torso.glb")
our_arm = [o for o in bpy.data.objects if o.type == "ARMATURE" and o is not rig][0]

def frames(arm):
    return {b.name: (arm.matrix_world @ b.head_local,
                     arm.matrix_world @ b.tail_local,
                     arm.matrix_world @ b.matrix_local) for b in arm.data.bones}

Fm, Fo = frames(rig), frames(our_arm)
MX = Matrix.Diagonal((-1, 1, 1, 1))
S_scale = 1.07
for mn, on in BONE_MAP.items():
    if on is None or mn == "Root":
        continue
    if mn not in Fm:
        print("MISSING-MPFB", mn); continue
    if on not in Fo:
        print("MISSING-OURS", on); continue
    mh, mt, mm = Fm[mn]
    oh, ot, om = Fo[on]
    mh2, mt2, mm2 = Vector((-mh.x, mh.y, mh.z)), Vector((-mt.x, mt.y, mt.z)), MX @ mm @ MX
    mlen = max((mt2 - mh2).length, 1e-6); olen = max((ot - oh).length, 1e-6)
    S = Matrix.Diagonal((S_scale, olen / mlen, S_scale, 1))
    T = om @ S @ mm2.inverted()
    p_head = T @ mh2
    p_tail = T @ mt2
    det = T.to_3x3().determinant()
    print(f"{mn:>14}->{on:<22} axial={olen/mlen:6.2f} det={det:7.3f} "
          f"H-> {[round(v,2) for v in p_head]} (want {[round(v,2) for v in oh]}) "
          f"T-> {[round(v,2) for v in p_tail]} (want {[round(v,2) for v in ot]})")
