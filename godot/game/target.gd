extends Node3D
## Floating jian sparring dummy — bobs in place, flashes on hit,
## tilts away from the blow, breaks and respawns at HP 0.
## The certified prop glb doubles as the target body.

const GLB := "res://assets/components/xx_jian_3d/xx_jian_3d.glb"
const HP_MAX := 3
const RESPAWN := 2.0

var hp := HP_MAX
var _bob := 0.0
var _hit_t := 0.0
var _knock := Vector3.ZERO
var _respawn := 0.0
var _mats: Array = []

@onready var body: Node3D = $Body


func _ready() -> void:
	var inst: Node3D = load(GLB).instantiate()
	inst.rotation_degrees = Vector3(0, 0, -90)  # blade horizontal display
	body.add_child(inst)
	for mi in inst.find_children("", "MeshInstance3D", true, false):
		var m: Material = mi.get_active_material(0)
		if m is BaseMaterial3D:
			var dm: StandardMaterial3D = m.duplicate()
			dm.emission_enabled = true
			dm.emission = Color(0, 0, 0)
			mi.set_surface_override_material(0, dm)
			_mats.append(dm)


func hit(from: Vector3) -> void:
	if hp <= 0:
		return
	hp -= 1
	print("target: hit -> hp=%d" % hp)
	_hit_t = 0.25
	_knock = (global_position - from)
	_knock.y = 0
	_knock = _knock.normalized()
	for m in _mats:
		m.emission = Color(1.0, 0.25, 0.2) if hp <= 0 \
				else Color(1.0, 0.6, 0.2)
	if hp <= 0:
		_respawn = RESPAWN


func _process(dt: float) -> void:
	_bob += dt
	if hp <= 0:
		body.scale = body.scale.lerp(Vector3.ZERO, dt * 8)
		_respawn -= dt
		if _respawn <= 0:
			hp = HP_MAX
			body.rotation_degrees = Vector3.ZERO
			body.scale = Vector3.ONE
			for m in _mats:
				m.emission = Color(0, 0, 0)
	else:
		body.position.y = 1.1 + sin(_bob * 2.2) * 0.12
		_hit_t = maxf(_hit_t - dt, 0.0)
		var k := _hit_t / 0.25
		if k > 0:
			body.rotation_degrees = Vector3(_knock.z, 0, -_knock.x) * 18 * k
			for m in _mats:
				m.emission_energy = k * 3.0
		else:
			body.rotation_degrees = body.rotation_degrees.lerp(
					Vector3.ZERO, dt * 6)
			for m in _mats:
				m.emission = Color(0, 0, 0)
