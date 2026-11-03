extends Node2D
## Pipeline harness: unit renders (C3) + composition run (A1/A2/A3).
## Usage: godot --path godot -- <abs job.json>
## job = {mode, out_dir, rig, unit_jobs:[], composition:{}}

var job: Dictionary
var report := {}
var cam: Camera2D
var mod: CanvasModulate
var rig: Dictionary
var out_dir: String

const SIM_DT := 1.0 / 60.0   # fixed sim step — never wall-clock delta

func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty() or not FileAccess.file_exists(args[0]):
		push_error("usage: godot --path godot -- <abs job.json>")
		get_tree().quit(2); return
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if typeof(parsed) != TYPE_DICTIONARY or not parsed.has("out_dir"):
		push_error("invalid job file: " + args[0])
		get_tree().quit(2); return
	job = parsed
	# never read assets mid-publish: wait for godot/.publish.lock to clear
	var lock := ProjectSettings.globalize_path("res://.publish.lock")
	var waited := 0
	while DirAccess.dir_exists_absolute(lock) and waited < 1200:
		await get_tree().create_timer(0.1).timeout
		waited += 1
	if DirAccess.dir_exists_absolute(lock):
		push_error("publish lock still held after 120s — aborting")
		get_tree().quit(3); return
	rig = job.get("rig", {})
	out_dir = job["out_dir"]
	DirAccess.make_dir_recursive_absolute(out_dir)
	cam = Camera2D.new()
	cam.position = Vector2(640, 360)
	add_child(cam)
	cam.make_current()
	mod = CanvasModulate.new()
	add_child(mod)
	await _frames(10)
	if job["mode"] in ["unit", "all"]:
		await _unit_mode()
	if job["mode"] in ["composition", "all"]:
		await _composition_mode()
	_write_report()
	get_tree().quit()

func _frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame

func _snap(path: String) -> Image:
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	img.save_png(path)
	return img

func _tex(path: String) -> Texture2D:
	var t: Texture2D = load(path)
	if t == null:
		push_error("MISSING ASSET: " + path)
		# 2x2 magenta stand-in so failures are loud, not invisible
		var im := Image.create(2, 2, false, Image.FORMAT_RGBA8)
		im.fill(Color.MAGENTA)
		t = ImageTexture.create_from_image(im)
	return t

func _mk_sprite(tex: Texture2D, feet_pos: Vector2, h_px: float, tint := Color.WHITE, normal: Texture2D = null) -> Sprite2D:
	var s := Sprite2D.new()
	if normal:
		var ct := CanvasTexture.new()
		ct.diffuse_texture = tex
		ct.normal_texture = normal
		s.texture = ct
	else:
		s.texture = tex
	var sc := h_px / tex.get_height()
	s.scale = Vector2(sc, sc)
	s.offset = Vector2(0, -tex.get_height() / 2.0)   # pivot = feet
	s.position = feet_pos
	s.modulate = tint
	return s

func _canvas_rect(s: Sprite2D) -> Rect2:
	var xf := s.get_global_transform_with_canvas()
	var sz := Vector2(s.texture.get_size()) * s.scale.abs()
	var origin := xf.origin + s.offset * s.scale
	if s.centered:
		origin -= sz / 2.0
	return Rect2(origin, sz)

func _bg_rect(color: Color) -> ColorRect:
	var r := ColorRect.new()
	r.color = color
	r.size = Vector2(1280, 720)
	add_child(r)
	return r

func _light() -> PointLight2D:
	var gtex := GradientTexture2D.new()
	gtex.width = 512; gtex.height = 512
	gtex.fill = GradientTexture2D.FILL_RADIAL
	gtex.fill_from = Vector2(0.5, 0.5); gtex.fill_to = Vector2(1.0, 0.5)
	var l := PointLight2D.new()
	l.texture = gtex
	l.texture_scale = rig.get("light_2d", {}).get("texture_scale", 3.0)
	l.energy = rig.get("light_2d", {}).get("energy", 1.4)
	l.color = Color(rig.get("light_2d", {}).get("color", "#ffbf73"))
	return l

func _mod_color() -> Color:
	return Color(rig.get("canvas_modulate", "#73738c"))

func _lit_coverage(img: Image, rect: Rect2, floor := 0.18) -> float:
	var lit := 0
	var total := 0
	var x0 := clampi(int(rect.position.x), 0, img.get_width() - 1)
	var y0 := clampi(int(rect.position.y), 0, img.get_height() - 1)
	var x1 := clampi(int(rect.end.x), 0, img.get_width() - 1)
	var y1 := clampi(int(rect.end.y), 0, img.get_height() - 1)
	for y in range(y0, y1, 2):
		for x in range(x0, x1, 2):
			total += 1
			var c := img.get_pixel(x, y)
			if 0.299 * c.r + 0.587 * c.g + 0.114 * c.b > floor:
				lit += 1
	return float(lit) / maxf(1.0, total)

func _sprite_sat(tex: Texture2D) -> float:
	var img := tex.get_image()
	var sat := 0.0
	var n := 0
	for y in range(0, img.get_height(), 4):
		for x in range(0, img.get_width(), 4):
			var c := img.get_pixel(x, y)
			if c.a > 0.5:
				n += 1
				var mx := maxf(c.r, maxf(c.g, c.b))
				var mn := minf(c.r, minf(c.g, c.b))
				if mx > 0.01:
					sat += (mx - mn) / mx
	return sat / maxf(1.0, n)

# ---------------- unit render ----------------

func _unit_mode() -> void:
	var bg := _bg_rect(Color(rig.get("unit_render_bg", "#2e2e3a")))
	var comps := {}
	for uj in job["unit_jobs"]:
		var udir: String = uj["out"]
		DirAccess.make_dir_recursive_absolute(udir)
		var m := {"type": uj["type"]}
		match uj["type"]:
			"sprite":
				var tex := _tex(uj["assets"] + "/sprite_idle.png")
				var s := _mk_sprite(tex, Vector2(640, 620), uj.get("h_px", 384))
				add_child(s)
				mod.color = Color.WHITE
				await _frames(12)
				await _snap(udir + "/neutral.png")
				var l := _light()
				l.position = s.position + Vector2(0, -uj.get("h_px", 384) * 0.7)
				add_child(l)
				mod.color = _mod_color()
				await _frames(12)
				var img := await _snap(udir + "/lit.png")
				m["sat_mean"] = snappedf(_sprite_sat(tex), 0.001)
				m["lit_coverage"] = snappedf(_lit_coverage(img, _canvas_rect(s)), 0.001)
				s.queue_free(); l.queue_free()
			"parallax":
				var s := Sprite2D.new()
				s.texture = _tex(uj["assets"] + "/bg.png")
				s.centered = false
				s.scale = Vector2(1280.0 / s.texture.get_width(), 720.0 / s.texture.get_height())
				add_child(s)
				mod.color = Color.WHITE
				await _frames(10)
				await _snap(udir + "/neutral.png")
				mod.color = _mod_color()
				var l := _light()
				l.position = Vector2(640, 250)
				add_child(l)
				await _frames(10)
				var img := await _snap(udir + "/lit.png")
				m["lit_coverage"] = snappedf(_lit_coverage(img, Rect2(Vector2.ZERO, img.get_size())), 0.001)
				s.queue_free(); l.queue_free()
			"ui_image":
				var tr := TextureRect.new()
				tr.texture = _tex(uj["assets"] + "/portrait.png")
				tr.position = Vector2(512, 232)
				add_child(tr)
				mod.color = Color.WHITE
				await _frames(10)
				await _snap(udir + "/neutral.png")
				tr.queue_free()
			"glb":
				# canvas items draw over 3D — hide the 2D backdrop or the
				# capture is blank (captain_3d rev1 certified on empty frames)
				bg.visible = false
				mod.color = Color.WHITE
				var n3 := Node3D.new()
				add_child(n3)
				var ground := MeshInstance3D.new()
				var pm := PlaneMesh.new(); pm.size = Vector2(20, 20)
				ground.mesh = pm
				n3.add_child(ground)
				var sun := DirectionalLight3D.new()
				sun.rotation_degrees = Vector3(-50, -30, 0)
				sun.light_energy = 1.3
				n3.add_child(sun)
				var env := WorldEnvironment.new()
				var e := Environment.new()
				e.background_mode = Environment.BG_COLOR
				e.background_color = Color(0.18, 0.18, 0.23)
				e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
				e.ambient_light_color = Color(0.55, 0.58, 0.65)
				e.ambient_light_energy = 0.4
				env.environment = e
				n3.add_child(env)
				var c3 := Camera3D.new()
				c3.position = Vector3(0, 1.5, 4.5)
				c3.rotation_degrees = Vector3(-10, 0, 0)
				n3.add_child(c3)
				c3.make_current()
				var scn: PackedScene = load(uj["assets"] + "/" + uj.get("glb", "pirate.glb"))
				if scn == null:
					push_error("MISSING ASSET: glb for " + uj["id"])
					m["missing"] = true
					n3.queue_free()
					comps[uj["id"]] = m
					continue
				var inst: Node3D = scn.instantiate()
				n3.add_child(inst)
				await _frames(20)
				await _snap(udir + "/neutral.png")
				var ap: AnimationPlayer = inst.find_child("AnimationPlayer", true, false)
				if ap:
					m["animations"] = ap.get_animation_list()
					for anim in ap.get_animation_list():
						# deterministic: seek to fixed fractions, paused
						ap.play(anim); ap.pause()
						var length := ap.get_animation(anim).length
						for k in [0.25, 0.5]:
							ap.seek(length * k, true)
							await _frames(4)
							await _snap("%s/%s_%02d.png" % [udir, anim, int(k * 100)])
				else:
					m["animations"] = []
				n3.queue_free()
				bg.visible = true
		await _frames(8)
		comps[uj["id"]] = m
		bg.size = Vector2(1280, 720)
	report["unit"] = comps

# ---------------- composition ----------------

var captain: Sprite2D
var crew: Array = []
var sky_rect := Rect2()
var deck_rect := Rect2()
var overlaps := []
var cross_row_events := 0
var min_gap := 9999.0
var walk_t := 0.0
var sky_spr: Sprite2D
var deck_spr: Sprite2D
var dialogue: Control
var light2d: PointLight2D

func _composition_mode() -> void:
	var comp: Dictionary = job["composition"]
	var comp_dir: String = comp["components_dir"]

	# parallax layers
	var pbg := ParallaxBackground.new()
	add_child(pbg)
	for L in comp["layers"]:
		var pl := ParallaxLayer.new()
		pl.motion_scale = Vector2(L["factor"], L["factor"])
		var s := Sprite2D.new()
		s.texture = _tex(comp_dir + "/" + L["id"] + "/bg.png")
		s.centered = false
		var sc := Vector2(2560.0 / s.texture.get_width(), 1440.0 / s.texture.get_height())
		s.scale = sc
		s.position = Vector2(-300.0 * L["factor"], L.get("y_off", 0))
		pl.add_child(s)
		pbg.add_child(pl)
		if L["id"] == "bg_sky": sky_spr = s
		if L["id"] == "bg_deck": deck_spr = s

	# characters + layout from the brief (no free-floating constants)
	var layout: Dictionary = comp.get("layout", {})
	var rows := {}
	for r in layout.get("rows", [{"id": "front", "y": 648}, {"id": "back", "y": 560}]):
		rows[r["id"]] = r["y"]
	var cap_y: float = rows.get(layout.get("captain_row", "front"), 648)
	var crew_y: float = rows.get(layout.get("crew_row", "back"), 560)
	var spacing: float = layout.get("spacing_px", 170)
	var patrol: Dictionary = layout.get("patrol", {"speed_px": 110, "from_x": -120, "to_x": 1200})
	patrol_speed_px = patrol.get("speed_px", 110)
	var anchor: Array = layout.get("light_anchor", {}).get("offset", [40, -290])
	light_offset = Vector2(anchor[0], anchor[1])

	mod.color = _mod_color()
	captain = _mk_sprite(
		_tex(comp_dir + "/captain/sprite_idle.png"), Vector2(140, cap_y), 384,
		Color.WHITE, _tex(comp_dir + "/captain/sprite_idle_n.png"))
	add_child(captain)
	var frame_tex := [
		_ct(_tex(comp_dir + "/captain/sprite_walk_a.png"),
		    _tex(comp_dir + "/captain/sprite_walk_a_n.png")),
		_ct(_tex(comp_dir + "/captain/sprite_walk_b.png"),
		    _tex(comp_dir + "/captain/sprite_walk_b_n.png"))]
	walk_frames = frame_tex
	var frame_i := 0
	var crew_paths: Array = []
	var variants: Dictionary = comp.get("variants", {})
	for vc in variants:
		for vid in variants[vc]:
			crew_paths.append("%s/%s/%s" % [comp_dir, vc, vid])
	for i in crew_paths.size():
		var cr := _mk_sprite(
			_tex(crew_paths[i] + "/sprite_idle.png"),
			Vector2(140 + (i + 1) * spacing, crew_y), 360, Color.WHITE,
			_tex(crew_paths[i] + "/sprite_idle_n.png"))
		add_child(cr)
		crew.append(cr)

	light2d = _light()
	add_child(light2d)

	# patrol + checks: 240 fixed sim steps (deterministic, frame-rate free)
	var start_x := 140.0
	for f in 240:
		await get_tree().process_frame
		walk_t += SIM_DT
		captain.position.x = start_x + walk_t * patrol_speed_px
		# walk frame swap at 6fps
		frame_i = int(walk_t * 6.0) % 2
		captain.texture = frame_tex[frame_i]
		light2d.position = captain.position + light_offset
		var cr := _canvas_rect(captain)
		for c2 in crew:
			var r2 := _canvas_rect(c2)
			var inter := cr.intersection(r2)
			var pen := minf(inter.size.x, inter.size.y)
			# same-row violation = deep penetration; front-row pass = expected occlusion
			if pen > 40 and absf(c2.position.y - captain.position.y) < 1.0:
				overlaps.append({"t": snappedf(walk_t, 0.01), "pair": "same-row"})
			elif pen > 40:
				cross_row_events += 1
			var gap := maxf(r2.position.x - cr.end.x, cr.position.x - r2.end.x)
			if gap < min_gap:
				min_gap = gap
		if captain.position.x > patrol.get("to_x", 1200):
			walk_t = 0.0; start_x = patrol.get("from_x", -120)

	# layer visibility: fraction of sky not occluded by deck on screen
	sky_rect = _canvas_rect(sky_spr).intersection(Rect2(Vector2.ZERO, Vector2(1280, 720)))
	deck_rect = _canvas_rect(deck_spr).intersection(Rect2(Vector2.ZERO, Vector2(1280, 720)))
	var sky_vis := 1.0 - sky_rect.intersection(deck_rect).get_area() / maxf(1.0, sky_rect.get_area())

	# lit coverage on captain
	await _frames(6)
	var frame_img := get_viewport().get_texture().get_image()
	var lit_cov := _lit_coverage(frame_img, _canvas_rect(captain))

	# shots — walk_tN seek to t = N * spacing / speed (deterministic)
	walk_step_s = spacing / maxf(1.0, patrol_speed_px)
	var shots_dir := out_dir + "/shots"
	DirAccess.make_dir_recursive_absolute(shots_dir)
	var shot_lit := {}
	for shot in comp["shots"]:
		_setup_shot(shot)
		await _frames(8)
		var img := await _snap("%s/%s.png" % [shots_dir, shot])
		shot_lit[shot] = {
			"lit": _lit_coverage(img, _canvas_rect(captain)
				.intersection(Rect2(Vector2.ZERO, Vector2(img.get_size())))),
			"portrait": dialogue != null and dialogue.visible}

	var metrics := {
		"draw_calls": int(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)),
		"same_row_overlap_events": overlaps.size(),
		"cross_row_occlusions": cross_row_events,
		"min_crew_gap_px": snappedf(min_gap, 0.1),
		"sky_visible_pct": snappedf(sky_vis * 100.0, 0.1),
		"captain_lit_coverage": snappedf(lit_cov, 0.001),
		"crew_count": crew.size(),
		"shots": comp["shots"],
	}
	report["composition"] = metrics
	report["shot_expect"] = _eval_expect(comp.get("shot_expect", {}), metrics, shot_lit)
	if not comp.get("action_shots", []).is_empty():
		report["action_shots"] = {"status": "not_implemented",
			"note": "rigged-glb action clock is backlog; declared shots skipped"}

## shot_expect: {shot: {metric: target}} -> per-check {value, target, pass}
func _eval_expect(expect: Dictionary, metrics: Dictionary, shot_lit: Dictionary) -> Dictionary:
	var out := {}
	for shot in expect:
		var res := {}
		for key in expect[shot]:
			var target = expect[shot][key]
			var value = null
			var ok := false
			match key:
				"lit_coverage_min":
					value = snappedf(shot_lit.get(shot, {}).get("lit", 0.0), 0.001)
					ok = value >= target
				"same_row_overlap_events":
					value = metrics["same_row_overlap_events"]
					ok = value <= target
				"portrait_visible":
					value = shot_lit.get(shot, {}).get("portrait", false)
					ok = value == target
				_:
					value = "unknown_check"
			res[key] = {"value": value, "target": target, "pass": ok}
		out[shot] = res
	return out

var patrol_speed_px := 110.0
var light_offset := Vector2(40, -290)
var walk_step_s := 1.5
var walk_frames: Array = []

func _ct(d: Texture2D, n: Texture2D) -> CanvasTexture:
	var ct := CanvasTexture.new()
	ct.diffuse_texture = d
	ct.normal_texture = n
	return ct

func _setup_shot(n: String) -> void:
	if dialogue: dialogue.visible = false
	mod.color = _mod_color()
	cam.zoom = Vector2.ONE
	match n:
		"wide_all":
			cam.position = Vector2(640, 360)
		"captain_closeup":
			cam.position = captain.position + Vector2(0, -200); cam.zoom = Vector2(2.0, 2.0)
		"crew_lineup":
			cam.position = Vector2(640, 500); cam.zoom = Vector2(1.5, 1.5)
		"walk_t0", "walk_t1", "walk_t2":
			var k := int(n.substr(6))
			var t := k * walk_step_s
			captain.position.x = 140.0 + t * patrol_speed_px
			if not walk_frames.is_empty():
				captain.texture = walk_frames[int(t * 6.0) % 2]
			light2d.position = captain.position + light_offset
			cam.position = captain.position + Vector2(60, -120); cam.zoom = Vector2(1.4, 1.4)
		"low_light":
			cam.position = Vector2(640, 360); mod.color = Color("#141424")
		"ui_dialogue":
			cam.position = Vector2(640, 360)
			_show_dialogue()

func _show_dialogue() -> void:
	if dialogue == null:
		var layer := CanvasLayer.new()
		layer.layer = 10
		add_child(layer)
		var panel := PanelContainer.new()
		panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
		panel.offset_top = -150
		panel.offset_left = 60
		panel.offset_right = -60
		var hb := HBoxContainer.new()
		var tr := TextureRect.new()
		tr.texture = _tex("res://assets/components/portrait/portrait.png")
		tr.custom_minimum_size = Vector2(110, 110)
		tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
		hb.add_child(tr)
		var lb := Label.new()
		lb.text = "Arr! The sea be callin', mateys — raise the colours and set sail!"
		lb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		lb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		hb.add_child(lb)
		panel.add_child(hb)
		layer.add_child(panel)
		dialogue = panel
	dialogue.visible = true

func _write_report() -> void:
	report["provenance"] = {
		"godot_version": Engine.get_version_info().get("string", "?"),
		"job_file": FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]).sha256_text().substr(0, 12),
		"timestamp": Time.get_datetime_string_from_system(),
		"mode": job.get("mode"),
		"inputs": job.get("provenance", {}),
	}
	# atomic: write tmp, then rename over report.json
	var tmp := out_dir + "/report.json.tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	f.store_string(JSON.stringify(report, "  "))
	f.close()
	DirAccess.remove_absolute(out_dir + "/report.json")
	DirAccess.rename_absolute(tmp, out_dir + "/report.json")
	print("REPORT_JSON_BEGIN")
	print(JSON.stringify(report, "  "))
	print("REPORT_JSON_END")
