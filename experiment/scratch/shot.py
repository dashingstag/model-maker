import bpy, sys, math
import mathutils
argv = sys.argv[sys.argv.index("--") + 1:]
src, out, az = argv[0], argv[1], float(argv[2])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
scene = bpy.context.scene

# combined world bbox of all mesh objects
lo = mathutils.Vector((1e9, 1e9, 1e9))
hi = mathutils.Vector((-1e9, -1e9, -1e9))
for ob in scene.objects:
    if ob.type != 'MESH':
        continue
    for c in ob.bound_box:
        w = ob.matrix_world @ mathutils.Vector(c)
        lo = mathutils.Vector(map(min, lo, w))
        hi = mathutils.Vector(map(max, hi, w))
ctr = (lo + hi) / 2
dim = max((hi - lo).length, 0.01)
print("BBOX", tuple(round(v, 2) for v in lo), tuple(round(v, 2) for v in hi))

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 4.0
sun.rotation_euler = (math.radians(50), 0, math.radians(25))
scene.collection.objects.link(sun)
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[1].default_value = 0.5
scene.world = w

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("c"))
scene.collection.objects.link(cam)
scene.camera = cam
azr = math.radians(az)
d = dim * 1.1
cam.location = ctr + mathutils.Vector(
    (d * math.sin(azr), -d * math.cos(azr), dim * 0.15))
dv = ctr - cam.location
cam.rotation_euler = dv.to_track_quat('-Z', 'Y').to_euler()
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.resolution_x = 640
scene.render.resolution_y = 720
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
