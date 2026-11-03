extends Node2D
## Approach 1: 2D sprites. One generated pirate texture reused for all 6 pirates;
## crew are palette recolors via modulate (zero extra texture/draw cost).

var pirates: Array[Sprite2D] = []
var crew_tints: Array[Color] = [
	Color(1, 1, 1),        # captain, untinted
	Color(0.55, 0.9, 0.55),
	Color(0.55, 0.7, 1.0),
	Color(1.0, 0.75, 0.5),
	Color(0.85, 0.6, 1.0),
	Color(0.6, 1.0, 0.9),
]
var cam: Camera2D
var mod: CanvasModulate
var captain: Sprite2D
var walk_t := 0.0

func _ready() -> void:
	var tex: Texture2D = load("res://assets/sprite_pirate.png")
	for i in 6:
		var s := Sprite2D.new()
		s.texture = tex
		s.position = Vector2(170 + i * 190, 430)
		s.modulate = crew_tints[i]
		add_child(s)
		pirates.append(s)
	captain = pirates[0]
	cam = Camera2D.new()
	cam.position = Vector2(640, 360)
	add_child(cam)
	cam.make_current()
	mod = CanvasModulate.new()
	add_child(mod)

func _process(d: float) -> void:
	walk_t += d
	captain.position.x = 170.0 + sin(walk_t * 0.8) * 120.0
	captain.position.y = 430.0 + abs(sin(walk_t * 6.0)) * 8.0

func shots() -> Array:
	return ["wide_all", "crew_lineup", "captain_closeup", "walk_t1", "low_light"]

func setup_shot(n: String) -> void:
	mod.color = Color.WHITE
	match n:
		"wide_all":
			cam.position = Vector2(640, 360); cam.zoom = Vector2.ONE
		"crew_lineup":
			cam.position = Vector2(640, 400); cam.zoom = Vector2(1.7, 1.7)
		"captain_closeup":
			cam.position = captain.position; cam.zoom = Vector2(2.2, 2.2)
		"walk_t1":
			cam.position = Vector2(640, 380); cam.zoom = Vector2(1.4, 1.4)
		"low_light":
			cam.position = Vector2(640, 360); cam.zoom = Vector2.ONE
			mod.color = Color(0.25, 0.25, 0.35)

func checks() -> Dictionary:
	var distinct := {}
	for p in pirates:
		distinct[p.modulate] = true
	return {
		"pirate_count": pirates.size(),
		"distinct_tints": distinct.size(),
		"single_texture_reuse": true,
	}
