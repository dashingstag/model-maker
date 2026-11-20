"""Head close-up turntable — diagnostic renders of the face/hair zone.

  blender.exe --background --python tools/head_shots.py -- \
      <model.glb> <out_dir> [z_frac] [radius]

Emits a000..a315 (8 angles around the head region).
"""
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = argv[0], argv[1]
ZFRAC = float(argv[2]) if len(argv) > 2 else 0.12
RAD = float(argv[3]) if len(argv) > 3 else 1.2
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

import numpy as np
verts = []
for o in bpy.data.objects:
    if o.type != 'MESH':
        continue
    mw = o.matrix_world
    verts += [mw @ v.co for v in o.data.vertices]
V = np.array([(v.x, v.y, v.z) for v in verts])
lo, hi = V.min(axis=0), V.max(axis=0)
ztop = hi[2] - ZFRAC * (hi[2] - lo[2])
head = V[V[:, 2] > ztop - 0.35]
target = Vector((head[:, 0].mean(), head[:, 1].mean(), ztop))

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 0.6
cam.data.clip_start = 0.01
cam.data.clip_end = 50
bpy.context.collection.objects.link(cam)
bpy.context.scene.camera = cam

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN'))
sun.data.energy = 2.5
sun.rotation_euler = (math.radians(55), 0, math.radians(-25))
bpy.context.collection.objects.link(sun)

sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x = sc.render.resolution_y = 512
sc.render.film_transparent = False
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
bg = sc.world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (0.06, 0.08, 0.12, 1)
bg.inputs[1].default_value = 0.7

for deg in range(0, 360, 45):
    a = math.radians(deg)
    cam.location = target + Vector((RAD * math.sin(a),
                                    -RAD * math.cos(a), 0.15 * RAD))
    look = target - cam.location
    cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, f"a{deg:03d}.png")
    bpy.ops.render.render(write_still=True)

# tight close-up of the feature zone (model coords ~(0,2.45,0.58))
face = Vector((0.0, -0.575, 2.447))
cam.data.ortho_scale = 0.30
for deg, tag in ((0, "f000"), (35, "f035"), (-35, "f315")):
    a = math.radians(deg)
    cam.location = face + Vector((0.8 * math.sin(a), -0.8 * math.cos(a), 0.05))
    look = face - cam.location
    cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, f"{tag}.png")
    bpy.ops.render.render(write_still=True)
