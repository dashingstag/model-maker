extends Node3D
## Approach 2: real-time 3D. Six instances of the Blender-built rigged pirate
## (separate meshes per part -> high draw calls). Captain walks a patrol path
## that passes crew member #1 -> measures min separation (walk-through
## regression check) while the glTF 'walk' clip plays.

const PirateScene := preload("res://assets/models/pirate.glb")

var pirates: Array[Node3D] = []
var cam: Camera3D
var sun: DirectionalLight3D
var env_node: WorldEnvironment
var captain: Node3D
var walk_t := 0.0
var min_sep := 999.0
var walk_anim_found := false

func _ready() -> void:
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(40, 40)
	ground.mesh = pm
	var gmat := StandardMaterial3D.new()
	gmat.albedo_color = Color(0.35, 0.26, 0.16)
	ground.material_override = gmat
	add_child(ground)

	sun = DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, -30, 0)
	sun.light_energy = 1.6
	add_child(sun)

	env_node = WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.5, 0.65, 0.8)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.7, 0.75, 0.8)
	e.ambient_light_energy = 0.6
	env_node.environment = e
	add_child(env_node)

	cam = Camera3D.new()
	add_child(cam)
	cam.position = Vector3(0, 2.2, 7)
	cam.rotation_degrees = Vector3(-12, 0, 0)
	cam.make_current()

	for i in 6:
		var p := PirateScene.instantiate()
		p.position = Vector3(-3.0 + i * 1.2, 0, 0.8)
		p.name = "pirate_%d" % i
		add_child(p)
		pirates.append(p)
		var ap := p.find_child("AnimationPlayer", true, false) as AnimationPlayer
		if ap and ap.has_animation("walk"):
			walk_anim_found = true
			if i == 0:
				ap.play("walk")
	captain = pirates[0]

func _process(d: float) -> void:
	walk_t += d
	captain.position.x = -3.0 + walk_t * 0.6   # patrols left->right past crew
	if walk_t * 0.6 > 7.0:
		walk_t = 0.0
	for p in pirates:
		if p == captain:
			continue
		var dist := Vector2(captain.position.x, captain.position.z).distance_to(
			Vector2(p.position.x, p.position.z))
		min_sep = minf(min_sep, dist)

func shots() -> Array:
	return ["wide_all", "captain_closeup", "crew_lineup", "walk_t1", "walk_t2", "low_light"]

func setup_shot(n: String) -> void:
	sun.light_energy = 1.6
	match n:
		"wide_all":
			cam.position = Vector3(0.3, 2.2, 7); cam.rotation_degrees = Vector3(-12, 0, 0)
		"captain_closeup":
			cam.position = captain.position + Vector3(0.8, 1.6, 2.2)
			cam.look_at(captain.position + Vector3(0, 1.0, 0))
		"crew_lineup":
			cam.position = Vector3(0.3, 1.6, 5.5); cam.rotation_degrees = Vector3(-8, 0, 0)
		"walk_t1", "walk_t2":
			cam.position = captain.position + Vector3(0, 1.5, 3.2)
			cam.look_at(captain.position + Vector3(0, 0.9, 0))
		"low_light":
			cam.position = Vector3(0.3, 2.2, 7); cam.rotation_degrees = Vector3(-12, 0, 0)
			sun.light_energy = 0.15

func checks() -> Dictionary:
	var inst := pirates[1]
	var meshes := 0
	var colliders := 0
	var bodies := 0
	for c in inst.find_children("*", "", true, false):
		if c is MeshInstance3D:
			meshes += 1
		if c is CollisionShape3D:
			colliders += 1
		if c is StaticBody3D or c is AnimatableBody3D or c is RigidBody3D:
			bodies += 1
	return {
		"pirate_count": pirates.size(),
		"meshes_per_pirate": meshes,
		"collision_shapes": colliders,
		"physics_bodies": bodies,
		"walk_animation_present": walk_anim_found,
		"min_captain_separation": snappedf(min_sep, 0.001),
	}
