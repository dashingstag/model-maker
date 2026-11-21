# inspect saved mpfb_human.blend: bones, joint cubes, render
import bpy, json
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath="C:/Workspace/Models/model-maker/experiment/scratch/mpfb_human.blend")

base = next(o for o in bpy.data.objects if o.type == 'MESH' and 'Human' in o.name and o.type=='MESH')
rig = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
print("MESHES:", [(o.name, len(o.data.vertices)) for o in bpy.data.objects if o.type == 'MESH'])

if rig:
    for b in rig.data.bones:
        h = rig.matrix_world @ b.head_local
        t = rig.matrix_world @ b.tail_local
        if b.name in ('Root','pelvis','spine_03','neck_01','head','thigh_l','calf_l','foot_l','ball_l','hand_l'):
            print("B", b.name, "H", [round(v,3) for v in h], "T", [round(v,3) for v in t],
                  "parent", b.parent.name if b.parent else None)

# joint-head cube verts
gidx = {g.index: g.name for g in base.vertex_groups}
for gi, name in gidx.items():
    if name == 'joint-head':
        vs = [v.co[:] for v in base.data.vertices if any(g.group == gi for g in v.groups)]
        print("joint-head verts:", len(vs), [tuple(round(c,3) for c in v) for v in vs[:8]])

# render
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'MATERIAL'
scene.render.resolution_x = 720; scene.render.resolution_y = 900
scene.render.filepath = "C:/Workspace/Models/model-maker/experiment/scratch/mpfb_probe.png"
cam_data = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam); scene.camera = cam
cam.location = (0, -3.5, 1.0)
cam.rotation_euler = (Vector((0,0.05,0.9)) - cam.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.render.render(write_still=True)
print("RENDERED")
