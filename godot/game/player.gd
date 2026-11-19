extends CharacterBody3D
## Genshin-style third-person controller for pipeline glb assets.
## WASD camera-relative move, mouse orbit, LMB attack combo, RMB parry,
## E cast, Shift sprint, R emote. Animation switching via the GLB's own
## AnimationPlayer — no AnimationTree needed at this scale.
##
## Staff rides the skeleton's `hand.r` socket via BoneAttachment3D —
## same mechanism the composition harness uses (rot from the brief's
## layout.attach3d entry).

const WALK_SPEED := 3.2
const RUN_SPEED := 6.0
const TURN_SPEED := 12.0
const GRAVITY := 20.0
const STAFF_ROT := Vector3(-80, 0, 0)  # layout.attach3d socket rot
const STAFF_GLB := "res://assets/components/xx_sage_staff_3d/xx_sage_staff_3d.glb"

var yaw := 0.0
var pitch := -0.28
var busy := false
var combo_queued := false
var force_move := Vector2.ZERO      # autotest injection
var _outline_shader: Shader = null

@onready var model: Node3D = $Model
@onready var anim: AnimationPlayer = _find_anim(model)
@onready var pivot: Node3D = $CamPivot


func _find_anim(root: Node) -> AnimationPlayer:
	for c in root.find_children("", "AnimationPlayer", true, false):
		return c
	return null


func _toonify(inst: Node3D) -> void:
	# same override the harness runner applies for material:"toon"
	if _outline_shader == null:
		_outline_shader = Shader.new()
		_outline_shader.code = """shader_type spatial;
render_mode unshaded, cull_front;
uniform vec4 edge_color : source_color = vec4(0.05, 0.05, 0.09, 1.0);
uniform float grow = 0.015;
void vertex() { VERTEX += NORMAL * grow; }
void fragment() { ALBEDO = edge_color.rgb; }"""
	for mi in inst.find_children("", "MeshInstance3D", true, false):
		for surf in mi.mesh.get_surface_count():
			var src: Material = mi.get_active_material(surf)
			var toon := StandardMaterial3D.new()
			toon.diffuse_mode = BaseMaterial3D.DIFFUSE_TOON
			toon.specular_mode = BaseMaterial3D.SPECULAR_TOON
			toon.metallic = 0.0
			toon.roughness = 1.0
			if src is BaseMaterial3D:
				toon.albedo_color = src.albedo_color
				toon.albedo_texture = src.albedo_texture
			var edge := ShaderMaterial.new()
			edge.shader = _outline_shader
			toon.next_pass = edge
			mi.set_surface_override_material(surf, toon)


func _ready() -> void:
	_toonify(model)
	# socket the staff — prop glb parented to the hand.r bone
	var skel: Skeleton3D = null
	for c in model.find_children("", "Skeleton3D", true, false):
		skel = c
		break
	if skel != null and ResourceLoader.exists(STAFF_GLB):
		var ba := BoneAttachment3D.new()
		ba.bone_name = "hand.r"
		skel.add_child(ba)
		var staff: Node3D = load(STAFF_GLB).instantiate()
		staff.rotation_degrees = STAFF_ROT
		_toonify(staff)
		ba.add_child(staff)
	if anim:
		anim.play("idle")
		anim.animation_finished.connect(_on_anim_finished)


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw -= e.relative.x * 0.0032
		pitch = clampf(pitch - e.relative.y * 0.0032, -1.0, 0.4)
	elif e.is_action_pressed("attack") and not busy:
		_start_action("sword_swing")
	elif e.is_action_pressed("cast") and not busy:
		_start_action("talisman_cast")
	elif e.is_action_pressed("parry") and not busy:
		_start_action("parry")
	elif e.is_action_pressed("emote") and not busy:
		_start_action("staff_salute")


func _start_action(clip: String) -> void:
	if anim == null or not anim.has_animation(clip):
		return
	busy = true
	anim.play(clip, 0.08)


func _on_anim_finished(name: StringName) -> void:
	# a queued click during the tail of the swing chains the flourish
	if name == "sword_swing" and Input.is_action_pressed("attack") \
			and anim.has_animation("spinning_parry"):
		anim.play("spinning_parry", 0.08)
		return
	busy = false
	if anim:
		anim.play("idle", 0.15)


func _physics_process(dt: float) -> void:
	pivot.rotation.y = yaw
	pivot.rotation.x = pitch

	var iv := force_move if force_move != Vector2.ZERO else Input.get_vector(
		"move_left", "move_right", "move_forward", "move_back")
	# camera-relative ground direction (pivot -Z is camera forward)
	var dir := (pivot.basis * Vector3(iv.x, 0, iv.y))
	dir.y = 0
	dir = dir.normalized()

	var speed := RUN_SPEED if Input.is_action_pressed("sprint") else WALK_SPEED
	if busy or dir.length() < 0.05:
		velocity.x = move_toward(velocity.x, 0, speed * 6 * dt)
		velocity.z = move_toward(velocity.z, 0, speed * 6 * dt)
	else:
		velocity.x = dir.x * speed
		velocity.z = dir.z * speed
		# model +Z is its forward (glTF) — yaw where +Z aligns to dir
		model.rotation.y = lerp_angle(model.rotation.y,
				atan2(dir.x, dir.z), TURN_SPEED * dt)
		if anim and not busy:
			if anim.current_animation != "walk":
				anim.play("walk", 0.15)
			anim.speed_scale = speed / WALK_SPEED
	if not busy and dir.length() < 0.05 and anim:
		anim.speed_scale = 1.0
		if anim.current_animation != "idle":
			anim.play("idle", 0.2)

	velocity.y -= GRAVITY * dt
	move_and_slide()
