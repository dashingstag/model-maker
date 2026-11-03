"""Hybrid pipeline stage 1: multipass renders of the rigged pirate glTF.
For each pose in the character spec, emits:
  <pose>_beauty.png  - flat-shaded reference (transparent bg)
  <pose>_depth.png   - normalized depth (near=white) for ControlNet-depth
  <pose>_normal.png  - view-space normal map (usable as Light2D normal map)

Run from experiment/hybrid/:
  blender.exe --background --python tools/blender_render.py -- \
        --spec specs/pirate_captain.json --out renders/
"""
import bpy, json, math, os, sys

argv = sys.argv[sys.argv.index("--") + 1:]
SPEC = json.load(open(argv[argv.index("--spec") + 1]))
OUT = argv[argv.index("--out") + 1]
os.makedirs(OUT, exist_ok=True)
GLB = argv[argv.index("--glb") + 1] if "--glb" in argv else SPEC["glb"]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
for o in bpy.data.objects:          # -colonly means collision-only in Godot,
    if "-colonly" in o.name:        # not a renderable mesh
        o.hide_render = True
        o.hide_set(True)

# ---------- camera ----------
cam_data = bpy.data.cameras.new("cam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = SPEC["camera"]["ortho_scale"]
cam_data.clip_start = 0.1
cam_data.clip_end = 50
cam = bpy.data.objects.new("cam", cam_data)
cam.location = SPEC["camera"]["location"]
cam.rotation_euler = (math.radians(90), 0, 0)   # -Y -> +Y, up = +Z
bpy.context.collection.objects.link(cam)
bpy.context.scene.camera = cam

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN'))
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
bpy.context.collection.objects.link(sun)

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.film_transparent = True
scene.render.resolution_x, scene.render.resolution_y = SPEC["camera"]["size"]

# ---------- override materials ----------
def make_depth_mat():
    m = bpy.data.materials.new("_depth")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -5.2
    mr.inputs["From Max"].default_value = -3.2
    mr.clamp = True
    nt.links.new(tc.outputs["Camera"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m

def make_normal_mat():
    """World-space shading normal -> view-space RGB (R=+X right, G=+Z up,
    B=-Y toward camera). Camera looks +Y so view mapping is fixed."""
    m = bpy.data.materials.new("_normal")
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    neg = nt.nodes.new("ShaderNodeMath"); neg.operation = 'MULTIPLY'
    neg.inputs[1].default_value = -1.0
    scale = nt.nodes.new("ShaderNodeVectorMath"); scale.operation = 'SCALE'
    scale.inputs[3].default_value = 0.5
    add = nt.nodes.new("ShaderNodeVectorMath"); add.operation = 'ADD'
    add.inputs[1].default_value = (0.5, 0.5, 0.5)
    nt.links.new(geo.outputs["Normal"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["X"], comb.inputs["X"])
    nt.links.new(sep.outputs["Z"], comb.inputs["Y"])
    nt.links.new(sep.outputs["Y"], neg.inputs[0])
    nt.links.new(neg.outputs[0], comb.inputs["Z"])
    nt.links.new(comb.outputs["Vector"], scale.inputs[0])
    nt.links.new(scale.outputs["Vector"], add.inputs[0])
    nt.links.new(add.outputs["Vector"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m

DEPTH_MAT = make_depth_mat()
NORMAL_MAT = make_normal_mat()

# Eevee has no material_override; swap mesh materials per pass instead
meshes = [o for o in bpy.data.objects if o.type == 'MESH' and not o.hide_render]
orig_mats = {o.name: list(o.data.materials) for o in meshes}

def set_pass(mat):
    for o in meshes:
        o.data.materials.clear()
        mats = orig_mats[o.name]
        o.data.materials.append(mat if mat else (mats[0] if mats else DEPTH_MAT))

# ---------- render loop ----------
for pose, cfg in SPEC["poses"].items():
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = cfg["bones"].get(pb.name, (0, 0, 0))
    bpy.context.view_layer.update()
    for suffix, mat in [("beauty", None), ("depth", DEPTH_MAT), ("normal", NORMAL_MAT)]:
        set_pass(mat)
        scene.render.filepath = os.path.join(OUT, f"{pose}_{suffix}.png")
        bpy.ops.render.render(write_still=True)
        print("RENDERED", scene.render.filepath)

print("DONE ->", OUT)
