extends Node2D
## Approach 3: painted 2.5D cutout. AI-painted layers on ParallaxLayers at
## different depths, normal-mapped pirate cutouts lit by a PointLight2D, and a
## dialogue UI with the captain's portrait.

var cam: Camera2D
var mod: CanvasModulate
var sky_spr: Sprite2D
var deck_spr: Sprite2D
var pirates: Array[Sprite2D] = []
var captain: Sprite2D
var dialogue: PanelContainer
var light2d: PointLight2D
var parallax_delta := Vector2.ZERO

func _ready() -> void:
	mod = CanvasModulate.new()
	mod.color = Color(0.45, 0.45, 0.55)   # dusk; lights do the heavy lifting
	add_child(mod)

	var bg := ParallaxBackground.new()
	add_child(bg)

	var sky_layer := ParallaxLayer.new()
	sky_layer.motion_scale = Vector2(0.2, 0.2)
	sky_spr = Sprite2D.new()
	sky_spr.texture = load("res://assets/bg_sky.png")
	sky_spr.centered = false
	sky_spr.scale = Vector2(3.0, 2.4)
	sky_spr.position = Vector2(-200, -120)
	sky_layer.add_child(sky_spr)
	bg.add_child(sky_layer)

	var deck_layer := ParallaxLayer.new()
	deck_layer.motion_scale = Vector2(0.6, 0.6)
	deck_spr = Sprite2D.new()
	deck_spr.texture = load("res://assets/bg_deck.png")
	deck_spr.centered = false
	deck_spr.scale = Vector2(3.0, 2.0)
	deck_spr.position = Vector2(-150, 180)
	deck_layer.add_child(deck_spr)
	bg.add_child(deck_layer)

	var diffuse: Texture2D = load("res://assets/cutout_pirate.png")
	var normal: Texture2D = load("res://assets/cutout_pirate_n.png")
	var ct := CanvasTexture.new()
	ct.diffuse_texture = diffuse
	ct.normal_texture = normal
	var crew_tints: Array[Color] = [
		Color(1, 1, 1), Color(0.75, 0.9, 0.75), Color(0.7, 0.8, 1.0),
		Color(1.0, 0.8, 0.6), Color(0.9, 0.7, 1.0), Color(0.7, 1.0, 0.9),
	]
	for i in 6:
		var s := Sprite2D.new()
		s.texture = ct
		s.position = Vector2(160 + i * 180, 560)
		s.scale = Vector2(0.55, 0.55)
		s.modulate = crew_tints[i]
		s.z_index = 5
		add_child(s)
		pirates.append(s)
	captain = pirates[0]

	var gtex := GradientTexture2D.new()
	gtex.width = 512
	gtex.height = 512
	gtex.fill = GradientTexture2D.FILL_RADIAL
	gtex.fill_from = Vector2(0.5, 0.5)
	gtex.fill_to = Vector2(1.0, 0.5)
	light2d = PointLight2D.new()
	light2d.texture = gtex
	light2d.texture_scale = 3.0
	light2d.energy = 1.4
	light2d.color = Color(1.0, 0.75, 0.45)
	light2d.position = Vector2(500, 300)
	add_child(light2d)

	var layer := CanvasLayer.new()
	layer.layer = 10
	add_child(layer)
	dialogue = PanelContainer.new()
	dialogue.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	dialogue.offset_top = -140
	dialogue.offset_left = 60
	dialogue.offset_right = -60
	var hbox := HBoxContainer.new()
	var portrait := TextureRect.new()
	portrait.texture = load("res://assets/portrait.png")
	portrait.custom_minimum_size = Vector2(96, 96)
	portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	hbox.add_child(portrait)
	var label := Label.new()
	label.text = "Arr! The sea be callin', mateys — raise the colours and set sail!"
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hbox.add_child(label)
	dialogue.add_child(hbox)
	layer.add_child(dialogue)
	dialogue.visible = false

	cam = Camera2D.new()
	cam.position = Vector2(640, 360)
	add_child(cam)
	cam.make_current()

func shots() -> Array:
	return ["wide_all", "captain_closeup", "crew_lineup", "ui_dialogue", "low_light"]

func setup_shot(n: String) -> void:
	dialogue.visible = false
	mod.color = Color(0.45, 0.45, 0.55)
	match n:
		"wide_all":
			cam.position = Vector2(640, 360); cam.zoom = Vector2.ONE
		"captain_closeup":
			cam.position = captain.position + Vector2(0, -80); cam.zoom = Vector2(2.0, 2.0)
		"crew_lineup":
			cam.position = Vector2(640, 500); cam.zoom = Vector2(1.5, 1.5)
		"ui_dialogue":
			cam.position = Vector2(640, 360); cam.zoom = Vector2.ONE
			dialogue.visible = true
		"low_light":
			cam.position = Vector2(640, 360); cam.zoom = Vector2.ONE
			mod.color = Color(0.08, 0.08, 0.14)

func record_parallax_before() -> Dictionary:
	return {
		"sky": sky_spr.get_global_transform_with_canvas().origin,
		"deck": deck_spr.get_global_transform_with_canvas().origin,
	}

func apply_pan(dx: float) -> void:
	cam.position.x += dx

func checks() -> Dictionary:
	# measure parallax: pan camera, wait a frame for canvas transform, compare drift
	var before := record_parallax_before()
	apply_pan(160)
	await get_tree().process_frame
	var sky_d: Vector2 = sky_spr.get_global_transform_with_canvas().origin - before["sky"]
	var deck_d: Vector2 = deck_spr.get_global_transform_with_canvas().origin - before["deck"]
	cam.position.x = 640
	await get_tree().process_frame
	parallax_delta = sky_d - deck_d
	return {
		"pirate_count": pirates.size(),
		"parallax_layers": 2,
		"sky_drift_x": snappedf(sky_d.x, 0.01),
		"deck_drift_x": snappedf(deck_d.x, 0.01),
		"parallax_differs": absf(sky_d.x - deck_d.x) > 1.0,
		"light2d_present": is_instance_valid(light2d),
		"dialogue_present": is_instance_valid(dialogue),
	}
