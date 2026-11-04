"""Headless Blender script: builds the sage staff prop GLB.

Twisted dark-metal shaft, claw-set glowing blue gem head, tassel cord.
Origin at the grip point (~40% up the shaft) so BoneAttachment3D socketing
puts the grip in the hand. Length ~1.7m to match the hero rig.

Run:  blender.exe --background --python tools/blender_prop.py -- \
        --out <abs path>.glb --brief <abs brief.json>
"""
import bpy
import math
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "prop.glb"

bpy.ops.wm.read_factory_settings(use_empty=True)

def mat(name, rgb, rough=0.8, emit=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 2.0
    return m

metal = mat("staff_metal", (0.16, 0.15, 0.20), rough=0.35)
gem   = mat("staff_gem",   (0.15, 0.55, 0.70), rough=0.15, emit=(0.10, 0.45, 0.60))
cord  = mat("tassel",      (0.20, 0.55, 0.50))

GRIP_Z = 0.65   # origin at grip — shaft runs -0.45 .. +1.25

# shaft
bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.025, depth=1.7,
                                    location=(0, 0, GRIP_Z - 0.45 + 0.85))
shaft = bpy.context.object
shaft.name = "staff_shaft"
shaft.data.materials.append(metal)

# twist rings along the shaft for the twisted-metal read
for i in range(6):
    z = -0.30 + i * 0.22
    bpy.ops.mesh.primitive_torus_add(major_radius=0.030, minor_radius=0.008,
                                     major_segments=10, minor_segments=6,
                                     location=(0, 0, GRIP_Z + z))
    r = bpy.context.object
    r.name = f"twist_{i}"
    r.data.materials.append(metal)

# claw prongs gripping the gem
for i in range(4):
    a = math.radians(i * 90)
    x, y = math.cos(a) * 0.075, math.sin(a) * 0.075
    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.018, radius2=0.006,
                                    depth=0.16, location=(x, y, GRIP_Z + 1.22))
    p = bpy.context.object
    p.name = f"prong_{i}"
    p.data.materials.append(metal)

# glowing blue gem in claw setting
bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=12, radius=0.075,
                                     location=(0, 0, GRIP_Z + 1.22))
g = bpy.context.object
g.name = "staff_gem"
g.scale = (1.0, 1.0, 1.25)
bpy.ops.object.transform_apply(scale=True)
g.data.materials.append(gem)

# tassel cord below the head
bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.02, radius2=0.008,
                                depth=0.14, location=(0.03, 0, GRIP_Z + 1.02),
                                rotation=(0, 0.15, 0))
t = bpy.context.object
t.name = "tassel"
t.data.materials.append(cord)

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=OUT, export_yup=True,
                          export_apply=False, export_animations=False)
print("EXPORTED", OUT)
