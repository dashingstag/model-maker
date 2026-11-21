# MPFB probe: create human + game_engine rig, dump facts
import bpy, json, sys

try:
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService
except ImportError:
    from mpfb.services.humanservice import HumanService

basemesh = HumanService.create_human(
    mask_helpers=True, detailed_helpers=True,
    extra_vertex_groups=True, feet_on_ground=True, scale=0.1)
print("BASEMESH:", basemesh.name, "verts", len(basemesh.data.vertices),
      "faces", len(basemesh.data.polygons))
print("dims:", [round(d, 3) for d in basemesh.dimensions])
print("vgroups:", len(basemesh.vertex_groups))
print("vg names:", sorted(v.name for v in basemesh.vertex_groups))

rig = HumanService.add_builtin_rig(basemesh, "game_engine")
print("RIG:", rig.name if rig else None)
if rig:
    # world-space bone head positions
    arms = []
    for b in rig.data.bones:
        h = (rig.matrix_world @ b.head_local)
        t = (rig.matrix_world @ b.tail_local)
        arms.append((b.name, [round(v, 4) for v in h], [round(v, 4) for v in t],
                     b.parent.name if b.parent else None))
    print("BONES:", json.dumps(arms))
    wvg = [v.name for v in basemesh.vertex_groups]
    print("POST-RIG VGROUPS:", len(wvg))

# save for inspection
bpy.ops.wm.save_as_mainfile(filepath="C:/Workspace/Models/model-maker/experiment/scratch/mpfb_human.blend")
print("SAVED")
