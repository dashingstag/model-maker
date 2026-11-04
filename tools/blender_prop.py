"""Headless Blender script: builds prop GLBs (staff, jian sword).

Origin at the grip point so BoneAttachment3D socketing puts the grip in
the hand. Both kinds ship a `blade_mid` empty — the contact-anchor marker
`shared/actions` measure specs reference.

Run:  blender.exe --background --python tools/blender_prop.py -- \
        --out <abs path>.glb --brief <abs brief.json> [--kind staff|jian]
"""
import bpy
import math
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "prop.glb"
KIND = argv[argv.index("--kind") + 1] if "--kind" in argv else "staff"

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

if KIND == "staff":
    GRIP_Z = 0.65   # origin at grip — shaft runs -0.45 .. +1.25

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
        bpy.context.object.name = f"twist_{i}"
        bpy.context.object.data.materials.append(metal)

    # claw prongs gripping the gem
    for i in range(4):
        a = math.radians(i * 90)
        x, y = math.cos(a) * 0.075, math.sin(a) * 0.075
        bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.018, radius2=0.006,
                                        depth=0.16, location=(x, y, GRIP_Z + 1.22))
        bpy.context.object.name = f"prong_{i}"
        bpy.context.object.data.materials.append(metal)

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

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, GRIP_Z + 1.05))
    bpy.context.object.name = "blade_mid"
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, GRIP_Z + 1.25))
    bpy.context.object.name = "blade_tip"
else:  # jian — straight double-edged sword, grip at guard base
    jian_steel = mat("jian_steel", (0.72, 0.75, 0.80), rough=0.25)
    bronze = mat("jian_guard", (0.45, 0.32, 0.15), rough=0.4)
    grip_m = mat("jian_grip", (0.15, 0.12, 0.10), rough=0.7)

    # blade: long thin box, tapered toward the tip (scale-z shear via cone)
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0.55))
    blade = bpy.context.object
    blade.name = "jian_blade"
    blade.scale = (0.016, 0.004, 0.55)
    bpy.ops.object.transform_apply(scale=True)
    blade.data.materials.append(jian_steel)
    # tip
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.016, radius2=0.0,
                                    depth=0.08, location=(0, 0, 1.14))
    tip = bpy.context.object
    tip.name = "jian_tip"
    tip.data.materials.append(jian_steel)
    # guard (flat disc perpendicular to blade)
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.07, depth=0.015,
                                        location=(0, 0, 0.0))
    guard = bpy.context.object
    guard.name = "jian_guard"
    guard.data.materials.append(bronze)
    # grip below guard
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.014, depth=0.13,
                                        location=(0, 0, -0.07))
    grip = bpy.context.object
    grip.name = "jian_grip"
    grip.data.materials.append(grip_m)
    # pommel + tassel
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=8, radius=0.025,
                                         location=(0, 0, -0.15))
    pom = bpy.context.object
    pom.name = "jian_pommel"
    pom.data.materials.append(bronze)
    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.018, radius2=0.006,
                                    depth=0.10, location=(0, 0, -0.22))
    tas = bpy.context.object
    tas.name = "jian_tassel"
    tas.data.materials.append(cord)

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0.55))
    bpy.context.object.name = "blade_mid"
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 1.15))
    bpy.context.object.name = "blade_tip"
bpy.ops.export_scene.gltf(filepath=OUT, export_yup=True,
                          export_apply=False, export_animations=False)
print("EXPORTED", OUT)
