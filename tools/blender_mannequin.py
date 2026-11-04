"""Headless Blender script: builds a neutral rigged humanoid mannequin GLB
conforming to shared/skeletons/humanoid_v1.json bone names, for use as a
`guide_from` pose/depth guide (and a starting point for hero-track meshes).

Primitives are rigidly bone-parented (same scheme as blender_pirate.py) so
any pose spec of {bone: euler-xyz radians} deforms the whole silhouette.
Hakama cones + wide sleeve cones keep a xianxia-ish outline. Canonical
props `prop_sword` / `prop_staff` are bone-parented to hand.r and toggled
per pose via blender_render.py's `props` key (hidden by default).

Run:  blender.exe --background --python tools/blender_mannequin.py -- \
        --out <abs path>/guide_humanoid.glb
"""
import bpy
import math
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "guide_humanoid.glb"

bpy.ops.wm.read_factory_settings(use_empty=True)

def mat(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.8
    return m

MATS = {
    "cloth":  mat("cloth",  (0.55, 0.55, 0.60)),   # neutral robe
    "sleeve": mat("sleeve", (0.45, 0.45, 0.52)),
    "skin":   mat("skin",   (0.80, 0.70, 0.62)),
    "hair":   mat("hair",   (0.20, 0.20, 0.24)),
    "steel":  mat("steel",  (0.65, 0.68, 0.72)),
    "wood":   mat("wood",   (0.42, 0.32, 0.22)),
}

parts = []

def sphere(name, loc, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=14, ring_count=10, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    if material: o.data.materials.append(material)
    parts.append(o)
    return o

def cyl(name, loc, radius, depth, material, rot=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=radius, depth=depth,
                                        location=loc, rotation=rot or (0, 0, 0))
    o = bpy.context.object
    o.name = name
    if material: o.data.materials.append(material)
    parts.append(o)
    return o

def cone(name, loc, r1, r2, depth, material, rot=None):
    bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=r1, radius2=r2,
                                  depth=depth, location=loc, rotation=rot or (0, 0, 0))
    o = bpy.context.object
    o.name = name
    if material: o.data.materials.append(material)
    parts.append(o)
    return o

def cube(name, loc, scale, material, rot=None):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot or (0, 0, 0))
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    if material: o.data.materials.append(material)
    parts.append(o)
    return o

# ---------------- body (~1.75m, origin at feet, faces -Y) ----------------
# torso / head
sphere("pelvis", (0, 0, 0.98), (0.15, 0.11, 0.12), MATS["cloth"])
sphere("chest_m", (0, 0, 1.33), (0.17, 0.12, 0.16), MATS["cloth"])
sphere("head_m", (0, 0, 1.64), (0.12, 0.11, 0.13), MATS["skin"])
sphere("topknot", (0, 0.01, 1.78), (0.035, 0.035, 0.05), MATS["hair"])
cyl("neck_m", (0, 0, 1.48), 0.05, 0.10, MATS["skin"])
# wide sleeves (upper arm -> elbow, elbow -> wrist flare)
cone("sleeve_up_l", (-0.26, 0, 1.36), 0.075, 0.10, 0.28, MATS["sleeve"], rot=(0, 0.5, 0))
cone("sleeve_lo_l", (-0.50, 0, 1.18), 0.16, 0.07, 0.30, MATS["sleeve"], rot=(0, 0.6, 0))
cone("sleeve_up_r", ( 0.26, 0, 1.36), 0.075, 0.10, 0.28, MATS["sleeve"], rot=(0, -0.5, 0))
cone("sleeve_lo_r", ( 0.50, 0, 1.18), 0.16, 0.07, 0.30, MATS["sleeve"], rot=(0, -0.6, 0))
sphere("hand_l", (-0.60, 0, 1.06), (0.05, 0.045, 0.05), MATS["skin"])
sphere("hand_r", ( 0.60, 0, 1.06), (0.05, 0.045, 0.05), MATS["skin"])
# hakama legs (wide cones) + feet
cone("hakama_l", (-0.11, 0, 0.55), 0.17, 0.13, 0.85, MATS["cloth"])
cone("hakama_r", ( 0.11, 0, 0.55), 0.17, 0.13, 0.85, MATS["cloth"])
cube("foot_l", (-0.11, -0.05, 0.04), (0.06, 0.12, 0.04), MATS["cloth"])
cube("foot_r", ( 0.11, -0.05, 0.04), (0.06, 0.12, 0.04), MATS["cloth"])
# props (bone-parented to hand.r below; hidden per-pose by blender_render)
cube("prop_sword", (0.62, -0.02, 1.32), (0.035, 0.025, 0.45), MATS["steel"])
cyl("prop_staff", (0.62, -0.02, 1.05), 0.028, 1.7, MATS["wood"])

# ---------------- armature (humanoid_v1 names) ----------------
bpy.ops.object.armature_add(location=(0, 0, 0))
arm = bpy.context.object
arm.name = "humanoid_armature"

bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones
root_b = arm.data.edit_bones['Bone']
root_b.name = "root"
root_b.head, root_b.tail = (0, 0, 0.95), (0, 0, 1.05)

def bone(name, head, tail, parent):
    b = eb.new(name)
    b.head, b.tail, b.parent = head, tail, parent
    return b

spine   = bone("spine", (0, 0, 1.05), (0, 0, 1.25), root_b)
chest   = bone("chest", (0, 0, 1.25), (0, 0, 1.44), spine)
neck    = bone("neck",  (0, 0, 1.44), (0, 0, 1.53), chest)
head_b  = bone("head",  (0, 0, 1.53), (0, 0, 1.76), neck)
sh_l    = bone("shoulder.l", (-0.07, 0, 1.42), (-0.16, 0, 1.42), chest)
ua_l    = bone("upper_arm.l", (-0.16, 0, 1.42), (-0.38, 0, 1.28), sh_l)
fa_l    = bone("forearm.l", (-0.38, 0, 1.28), (-0.57, 0, 1.10), ua_l)
hand_l  = bone("hand.l", (-0.57, 0, 1.10), (-0.65, 0, 1.04), fa_l)
sh_r    = bone("shoulder.r", (0.07, 0, 1.42), (0.16, 0, 1.42), chest)
ua_r    = bone("upper_arm.r", (0.16, 0, 1.42), (0.38, 0, 1.28), sh_r)
fa_r    = bone("forearm.r", (0.38, 0, 1.28), (0.57, 0, 1.10), ua_r)
hand_r  = bone("hand.r", (0.57, 0, 1.10), (0.65, 0, 1.04), fa_r)
th_l    = bone("thigh.l", (-0.11, 0, 0.95), (-0.11, 0, 0.52), root_b)
sn_l    = bone("shin.l", (-0.11, 0, 0.52), (-0.11, 0, 0.10), th_l)
ft_l    = bone("foot.l", (-0.11, 0, 0.10), (-0.11, -0.16, 0.04), sn_l)
th_r    = bone("thigh.r", (0.11, 0, 0.95), (0.11, 0, 0.52), root_b)
sn_r    = bone("shin.r", (0.11, 0, 0.52), (0.11, 0, 0.10), th_r)
ft_r    = bone("foot.r", (0.11, 0, 0.10), (0.11, -0.16, 0.04), sn_r)

bpy.ops.object.mode_set(mode='OBJECT')

# ---------------- rigid bone-parenting ----------------
BONE_OF = {
    "pelvis": "root", "chest_m": "chest", "head_m": "head",
    "topknot": "head", "neck_m": "neck",
    "sleeve_up_l": "upper_arm.l", "sleeve_lo_l": "forearm.l", "hand_l": "hand.l",
    "sleeve_up_r": "upper_arm.r", "sleeve_lo_r": "forearm.r", "hand_r": "hand.r",
    "hakama_l": "thigh.l", "hakama_r": "thigh.r",
    "foot_l": "foot.l", "foot_r": "foot.r",
    "prop_sword": "hand.r", "prop_staff": "hand.r",
}
for o in parts:
    bname = BONE_OF[o.name]
    mw = o.matrix_world.copy()
    o.parent = arm
    o.parent_type = 'BONE'
    o.parent_bone = bname
    o.matrix_world = mw   # bone parenting snaps to tail; restore world pos

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=OUT, export_yup=True,
                        export_apply=False, export_animations=False)
print("EXPORTED", OUT)
