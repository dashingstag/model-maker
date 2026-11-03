"""Headless Blender script: builds a rigged pirate from separate primitive parts
and exports pirate.glb. Each part stays its own mesh (mirrors the multi-mesh /
high-draw-call characteristic of the original 3D approach).

Run:  blender.exe --background --python tools/blender_pirate.py -- --out <abs path>/pirate.glb
"""
import bpy
import math
import sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "pirate.glb"

bpy.ops.wm.read_factory_settings(use_empty=True)

# ---------------- materials ----------------
def mat(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.8
    return m

MATS = {
    "coat":   mat("coat",   (0.45, 0.08, 0.08)),   # captain red
    "shirt":  mat("shirt",  (0.85, 0.80, 0.70)),
    "pants":  mat("pants",  (0.16, 0.16, 0.22)),
    "boots":  mat("boots",  (0.10, 0.07, 0.05)),
    "skin":   mat("skin",   (0.85, 0.62, 0.45)),
    "hat":    mat("hat",    (0.12, 0.10, 0.10)),
    "belt":   mat("belt",   (0.20, 0.12, 0.06)),
    "gold":   mat("gold",   (0.90, 0.70, 0.20)),
    "steel":  mat("steel",  (0.60, 0.65, 0.70)),
    "beard":  mat("beard",  (0.15, 0.10, 0.06)),
    "eye":    mat("eye",    (0.02, 0.02, 0.02)),
}

# ---------------- part builders ----------------
parts = []

def cube(name, loc, scale, material):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    if material: o.data.materials.append(material)
    parts.append(o)
    return o

def uv_sphere(name, loc, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=12, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    if material: o.data.materials.append(material)
    parts.append(o)
    return o

def cyl(name, loc, radius, depth, material, rot=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=radius, depth=depth, location=loc,
                                        rotation=rot or (0, 0, 0))
    o = bpy.context.object
    o.name = name
    if material: o.data.materials.append(material)
    parts.append(o)
    return o

def cone(name, loc, r1, r2, depth, material):
    bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=r1, radius2=r2, depth=depth, location=loc)
    o = bpy.context.object
    o.name = name
    if material: o.data.materials.append(material)
    parts.append(o)
    return o

# body (~1.8m tall, origin at feet)
torso   = cube("torso",   (0, 0, 1.15), (0.28, 0.16, 0.32), MATS["coat"])
shirt   = cube("shirt",   (0, -0.02, 1.20), (0.20, 0.14, 0.22), MATS["shirt"])
head    = uv_sphere("head", (0, 0, 1.62), (0.13, 0.12, 0.14), MATS["skin"])
beard   = cube("beard",   (0, -0.09, 1.55), (0.09, 0.04, 0.06), MATS["beard"])
eyepatch= cube("eyepatch",(0.05, -0.115, 1.66), (0.04, 0.01, 0.03), MATS["eye"])
hatbrim = cyl("hat_brim", (0, 0, 1.74), 0.20, 0.03, MATS["hat"])
hattop  = cone("hat_top", (0, 0, 1.80), 0.14, 0.05, 0.12, MATS["hat"])
belt    = cube("belt",    (0, 0, 0.92), (0.29, 0.17, 0.05), MATS["belt"])
buckle  = cube("buckle",  (0, -0.16, 0.92), (0.06, 0.02, 0.04), MATS["gold"])

arm_L   = cyl("arm_L",  (-0.36, 0, 1.15), 0.06, 0.55, MATS["coat"])
arm_R   = cyl("arm_R",  ( 0.36, 0, 1.15), 0.06, 0.55, MATS["coat"])
hand_L  = uv_sphere("hand_L", (-0.36, 0, 0.86), (0.055, 0.05, 0.05), MATS["skin"])
hand_R  = uv_sphere("hand_R", ( 0.36, 0, 0.86), (0.055, 0.05, 0.05), MATS["skin"])

leg_L   = cyl("leg_L",  (-0.12, 0, 0.55), 0.075, 0.62, MATS["pants"])
leg_R   = cyl("leg_R",  ( 0.12, 0, 0.55), 0.075, 0.62, MATS["pants"])
boot_L  = cube("boot_L", (-0.12, -0.03, 0.18), (0.09, 0.14, 0.08), MATS["boots"])
boot_R  = cube("boot_R", ( 0.12, -0.03, 0.18), (0.09, 0.14, 0.08), MATS["boots"])

sword   = cube("sword",   (0.30, 0.02, 0.80), (0.02, 0.03, 0.30), MATS["steel"])
guard   = cube("guard",   (0.30, 0.02, 1.05), (0.08, 0.05, 0.02), MATS["gold"])

# collision-only node (Godot glTF import convention: -colonly suffix)
coll = cube("pirate_collision-colonly", (0, 0, 0.95), (0.35, 0.25, 0.95), None)

# ---------------- armature ----------------
bpy.ops.object.armature_add(location=(0, 0, 0.9))
arm = bpy.context.object
arm.name = "pirate_armature"
eb = arm.data.edit_bones
bpy.ops.object.mode_set(mode='EDIT')
root = arm.data.edit_bones['Bone']
root.name = "hips"
root.head = (0, 0, 0.0); root.tail = (0, 0, 0.25)

def bone(name, head, tail, parent):
    b = arm.data.edit_bones.new(name)
    b.head, b.tail = head, tail
    b.parent = parent
    return b

spine = bone("spine", (0,0,0.2), (0,0,0.5), root)
neck  = bone("neck",  (0,0,0.5), (0,0,0.62), spine)
aL = bone("arm_L", (-0.25,0,0.5), (-0.36,0,0.25), spine)
aR = bone("arm_R", ( 0.25,0,0.5), ( 0.36,0,0.25), spine)
tL = bone("leg_L", (-0.12,0,0.0), (-0.12,0,-0.5), root)
tR = bone("leg_R", ( 0.12,0,0.0), ( 0.12,0,-0.5), root)
bpy.ops.object.mode_set(mode='OBJECT')

# rigid bone-parenting (whole part follows one bone)
BONEMAP = {
    "hips":   [torso, shirt, belt, buckle, sword, guard],
    "neck":   [head, beard, eyepatch, hatbrim, hattop],
    "arm_L":  [arm_L, hand_L],
    "arm_R":  [arm_R, hand_R],
    "leg_L":  [leg_L, boot_L],
    "leg_R":  [leg_R, boot_R],
}
for bname, objs in BONEMAP.items():
    for o in objs:
        mw = o.matrix_world.copy()
        o.parent = arm
        o.parent_type = 'BONE'
        o.parent_bone = bname
        o.matrix_world = mw

# ---------------- walk animation (24 fps, 24f loop) ----------------
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 24
scene.render.fps = 24
act = bpy.data.actions.new("walk")
arm.animation_data_create()
arm.animation_data.action = act

swing = math.radians(28)
for f, s in [(1, 1.0), (7, 0.0), (13, -1.0), (19, 0.0), (25, 1.0)]:
    arm.pose.bones["leg_L"].rotation_euler = (swing * s, 0, 0)
    arm.pose.bones["leg_R"].rotation_euler = (-swing * s, 0, 0)
    arm.pose.bones["arm_L"].rotation_euler = (-swing * 0.7 * s, 0, 0)
    arm.pose.bones["arm_R"].rotation_euler = (swing * 0.7 * s, 0, 0)
    for bn in ("leg_L", "leg_R", "arm_L", "arm_R"):
        arm.pose.bones[bn].keyframe_insert("rotation_euler", frame=f)
for fc in act.fcurves:
    for kp in fc.keyframe_points:
        kp.interpolation = 'BEZIER'
scene.frame_end = 25

# ---------------- export ----------------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(
    filepath=OUT,
    export_format='GLB',
    export_animations=True,
    export_animation_mode='ACTIONS',
    export_apply=True,
    export_yup=True,
)
print("EXPORTED", OUT)
