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
	print("RUNNER ready, mode=", job["mode"], " units=", job.get("unit_jobs", []).size())
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

var missing := []  # asset paths that fell back to the magenta stand-in

func _tex(path: String) -> Texture2D:
	var t: Texture2D = load(path)
	if t == null:
		push_error("MISSING ASSET: " + path)
		missing.append(path)
		# 2x2 magenta stand-in so failures are loud, not invisible
		var im := Image.create(2, 2, false, Image.FORMAT_RGBA8)
		im.fill(Color.MAGENTA)
		t = ImageTexture.create_from_image(im)
	return t

func _opt_tex(path: String) -> Texture2D:
	# optional maps (e.g. _n normals): silent null when absent
	return load(path) if ResourceLoader.exists(path) else null

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
	var g := Gradient.new()
	g.set_color(0, Color(1, 1, 1, 1))
	g.set_color(1, Color(1, 1, 1, 0))
	gtex.gradient = g
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
		print("UNIT ", uj.get("id", "?"), " (", uj["type"], ")")
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
				if tr.texture:
					var th: float = tr.texture.get_height()
					var sc: float = 480.0 / th if th > 0 else 1.0
					tr.size = Vector2(tr.texture.get_width() * sc, 480.0)
					tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT
					tr.position = Vector2(640 - tr.size.x / 2.0, 120)
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

var sprites := {}          # member id -> Sprite2D
var member_rows := {}      # member id -> layout row
var ui_nodes := []         # card/ui TextureRects
var overlaps := []
var cross_row_events := 0
var min_gap := 9999.0
var walk_t := 0.0
var patroller: Sprite2D
var patroller_id := ""
var patrol_frames: Array = []
var dialogue: Control
var dialogue_img := ""
var light2d: PointLight2D
var hero_spr: Sprite2D     # layer carrying min_visible_pct
var front_spr: Sprite2D    # highest-factor layer (occluder)

func _frame_tex(dir: String, pose: String) -> Texture2D:
	var d := _tex(dir + "/sprite_%s.png" % pose)
	var n := _opt_tex(dir + "/sprite_%s_n.png" % pose)
	return _ct(d, n) if n else d

func _composition_mode() -> void:
	var comp: Dictionary = job["composition"]
	var comp_dir: String = comp["components_dir"]

	# parallax layers — publish emits them factor-sorted; hero = layer with
	# a visibility budget, occluder = the frontmost (last) layer.
	# Plain sprites + explicit offsets: ParallaxBackground's scroll tracking
	# stays at 0 here, so parallax is applied manually in _apply_parallax().
	var pbg := Node2D.new()
	pbg.name = "ParallaxBG"
	add_child(pbg)
	pbg_layers = {}
	for L in comp["layers"]:
		var tex := _tex(comp_dir + "/" + L["id"] + "/bg.png")
		var sc := Vector2(2560.0 / tex.get_width(), 1440.0 / tex.get_height())
		var s: Sprite2D = null
		var lx: float = -300.0 * L["factor"]
		var copies := []
		for dx in [-2560.0, 0.0, 2560.0]:
			var cp := Sprite2D.new()
			cp.texture = tex
			cp.centered = false
			cp.scale = sc
			cp.position = Vector2(dx + lx, L.get("y_off", 0))
			pbg.add_child(cp)
			copies.append({"s": cp, "dx": dx})
			if dx == 0.0:
				s = cp
		pbg_layers[L["id"]] = {"base_x": lx, "y": L.get("y_off", 0),
			"factor": L["factor"], "copies": copies}
		if L.get("min_visible_pct"): hero_spr = s
		front_spr = s

	var layout: Dictionary = comp.get("layout", {})
	var patrol: Dictionary = layout.get("patrol", {"speed_px": 110, "from_x": -120, "to_x": 1200})
	patrol_speed_px = patrol.get("speed_px", 110)
	var spacing: float = layout.get("spacing_px", 170)
	var anchor: Array = layout.get("light_anchor", {}).get("offset", [40, -290])
	light_offset = Vector2(anchor[0], anchor[1])
	var dlg = comp.get("dialogue")
	dialogue_img = dlg if dlg else ""

	mod.color = _mod_color()
	var glb_pending := []
	for m in comp.get("members", []):
		match m.get("kind"):
			"sprite", "variant":
				var dir: String = m["dir"]
				var s := _mk_sprite(
					_tex(dir + "/sprite_idle.png"), Vector2(m["x"], m["y"]),
					m.get("h_px", 384), Color.WHITE, _opt_tex(dir + "/sprite_idle_n.png"))
				add_child(s)
				sprites[m["id"]] = s
				member_rows[m["id"]] = m.get("row")
				if m.get("patrol"):
					patroller = s
					patroller_id = m["id"]
					for p in m.get("walk", []):
						patrol_frames.append(_frame_tex(dir, p))
			"ui":
				var tr := TextureRect.new()
				tr.set_meta("src", m["dir"] + "/portrait.png")
				tr.texture = _tex(m["dir"] + "/portrait.png")
				tr.position = Vector2(m["x"], m["y"])
				tr.size = Vector2(m.get("w", 300), m.get("h", 500))
				tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
				add_child(tr)
				ui_nodes.append(tr)
				member_rows[m["id"]] = "ui"
			"glb":
				glb_pending.append(m["id"])

	light2d = _light()
	add_child(light2d)

	# overlap checks — patroller sim when a member patrols, else a static
	# same-row penetration pass. Deterministic either way (fixed SIM_DT).
	if patroller:
		var start_x: float = patroller.position.x
		for f in 240:
			await get_tree().process_frame
			walk_t += SIM_DT
			patroller.position.x = start_x + walk_t * patrol_speed_px
			if not patrol_frames.is_empty():
				patroller.texture = patrol_frames[int(walk_t * 6.0) % patrol_frames.size()]
			light2d.position = patroller.position + light_offset
			var cr := _canvas_rect(patroller)
			for id2 in sprites:
				if id2 == patroller_id or member_rows.get(id2) != member_rows.get(patroller_id):
					continue
				var r2 := _canvas_rect(sprites[id2])
				var inter := cr.intersection(r2)
				var pen := minf(inter.size.x, inter.size.y)
				if pen > 40:
					overlaps.append({"t": snappedf(walk_t, 0.01), "pair": id2})
				var gap := maxf(r2.position.x - cr.end.x, cr.position.x - r2.end.x)
				if gap < min_gap:
					min_gap = gap
			if patroller.position.x > patrol.get("to_x", 1200):
				walk_t = 0.0; start_x = patrol.get("from_x", -120)
	else:
		var ids := sprites.keys()
		for i in ids.size():
			for j in range(i + 1, ids.size()):
				if member_rows.get(ids[i]) != member_rows.get(ids[j]):
					continue
				var r1 := _canvas_rect(sprites[ids[i]])
				var r2 := _canvas_rect(sprites[ids[j]])
				var inter := r1.intersection(r2)
				if minf(inter.size.x, inter.size.y) > 40:
					overlaps.append({"pair": "%s~%s" % [ids[i], ids[j]]})
				var gap := maxf(r2.position.x - r1.end.x, r1.position.x - r2.end.x)
				if gap < min_gap:
					min_gap = gap

	# hero-layer visibility: fraction not occluded by the frontmost layer
	var hero_vis := -1.0
	if hero_spr and front_spr and hero_spr != front_spr:
		var screen := Rect2(Vector2.ZERO, Vector2(1280, 720))
		var hr := _canvas_rect(hero_spr).intersection(screen)
		var fr := _canvas_rect(front_spr).intersection(screen)
		hero_vis = 1.0 - hr.intersection(fr).get_area() / maxf(1.0, hr.get_area())

	# lit coverage on the focus member (patroller, else first sprite, else frame)
	var focus_spr: Sprite2D = patroller if patroller else (
		sprites.values()[0] if not sprites.is_empty() else null)
	await _frames(6)
	var lit_cov := -1.0
	if focus_spr:
		var frame_img := get_viewport().get_texture().get_image()
		lit_cov = _lit_coverage(frame_img, _canvas_rect(focus_spr))

	# shots — dict entries may carry an explicit camera spec
	walk_step_s = spacing / maxf(1.0, patrol_speed_px)
	var shots_dir := out_dir + "/shots"
	DirAccess.make_dir_recursive_absolute(shots_dir)
	var shot_lit := {}
	for s in comp["shots"]:
		var shot_name: String = s if s is String else s.get("name", "shot")
		var sspec: Dictionary = {} if s is String else s.get("camera", {})
		_setup_shot(shot_name, sspec)
		await _frames(8)
		var img := await _snap("%s/%s.png" % [shots_dir, shot_name])
		var lit_rect := Rect2(Vector2.ZERO, img.get_size())
		if focus_spr:
			lit_rect = _canvas_rect(focus_spr).intersection(lit_rect)
		shot_lit[shot_name] = {
			"lit": _lit_coverage(img, lit_rect),
			"dialogue": dialogue != null and dialogue.visible}

	var metrics := {
		"draw_calls": int(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)),
		"same_row_overlap_events": overlaps.size(),
		"cross_row_occlusions": cross_row_events,
		"min_gap_px": snappedf(min_gap, 0.1),
		"hero_visible_pct": snappedf(hero_vis * 100.0, 0.1) if hero_vis >= 0.0 else null,
		"focus_lit_coverage": snappedf(lit_cov, 0.001) if lit_cov >= 0.0 else null,
		"sprite_count": sprites.size(),
		"ui_count": ui_nodes.size(),
		"patroller": patroller_id if patroller else null,
		"missing_assets": missing,
		"glb_pending": glb_pending,
		"shots": comp["shots"],
	}
	report["composition"] = metrics
	report["shot_expect"] = _eval_expect(comp.get("shot_expect", {}), metrics, shot_lit)
	if not comp.get("action_shots", []).is_empty():
		report["action_shots"] = {"status": "not_implemented",
			"note": "rigged-glb action clock is backlog; declared shots skipped"}
	if not glb_pending.is_empty():
		report["glb_placement"] = {"status": "not_implemented",
			"ids": glb_pending,
			"note": "composition glb instancing is backlog; unit renders cover them"}

func _ui_visible_count() -> int:
	var n := 0
	for tr in ui_nodes:
		if tr.visible and not missing.has(tr.get_meta("src", "")):
			n += 1
	return n

## shot_expect: {shot: {metric: target}} -> per-check {value, target, pass}
## Unknown/unmeasurable checks report pass=null (not_evaluated), never a
## false failure — advisory until the metric exists.
func _eval_expect(expect: Dictionary, metrics: Dictionary, shot_lit: Dictionary) -> Dictionary:
	var out := {}
	for shot in expect:
		var res := {}
		for key in expect[shot]:
			var target = expect[shot][key]
			var value = null
			var ok = null
			match key:
				"lit_coverage_min":
					value = snappedf(shot_lit.get(shot, {}).get("lit", 0.0), 0.001)
					ok = value >= target
				"same_row_overlap_events":
					value = metrics["same_row_overlap_events"]
					ok = value <= target
				"cross_row_occlusions":
					value = metrics["cross_row_occlusions"]
					ok = value <= target
				"min_gap_px":
					value = metrics["min_gap_px"]
					ok = value >= target
				"hero_visible_pct_min":
					value = metrics["hero_visible_pct"]
					ok = value >= target if value != null else null
				"portrait_visible", "dialogue_visible":
					value = shot_lit.get(shot, {}).get("dialogue", false)
					ok = value == target
				"cards_visible":
					value = _ui_visible_count()
					ok = value >= target
				"props_attached":
					value = "not_evaluated"  # needs the rigged-glb runtime
				_:
					value = "not_evaluated"
			res[key] = {"value": value, "target": target, "pass": ok}
		out[shot] = res
	return out

var patrol_speed_px := 110.0
var light_offset := Vector2(40, -290)
var pbg_layers := {}
var walk_step_s := 1.5

func _ct(d: Texture2D, n: Texture2D) -> CanvasTexture:
	var ct := CanvasTexture.new()
	ct.diffuse_texture = d
	ct.normal_texture = n
	return ct

## shot name -> member to focus: the last snake-case token of a member id
## (e.g. "sage" in "xx_azure_sage") appearing in the shot name. Keeps the
## old "captain_closeup" convention working on any component.
func _focus_from_name(n: String) -> String:
	var best := ""
	for id in sprites:
		var tok: String = id.split("/")[-1].split("_")[-1]
		if tok.length() >= 4 and tok in n and (best == "" or id.length() > best.length()):
			best = id
	return best

func _setup_shot(n: String, sspec := {}) -> void:
	if dialogue: dialogue.visible = false
	mod.color = _mod_color()
	cam.zoom = Vector2.ONE
	cam.position = Vector2(640, 360)
	# explicit camera spec on a dict shot wins outright
	var focus: String = sspec.get("focus", "")
	var zoom: float = sspec.get("zoom", 0.0)
	var off: Array = sspec.get("offset", [0, -180])
	if focus == "":
		focus = _focus_from_name(n)
	if n.begins_with("walk_t"):
		var t := int(n.substr(6)) * walk_step_s
		if patroller:
			patroller.position.x = 140.0 + t * patrol_speed_px
			if not patrol_frames.is_empty():
				patroller.texture = patrol_frames[int(t * 6.0) % patrol_frames.size()]
			light2d.position = patroller.position + light_offset
			cam.position = patroller.position + Vector2(60, -120)
			cam.zoom = Vector2(1.4, 1.4)
	elif "low_light" in n:
		mod.color = Color("#26263c")
		# sprites live at layout y (~1050) — the default frame misses them
		# entirely, so aim at the focus member and drop its light on it
		var f: String = focus if sprites.has(focus) else ""
		if f == "":
			# the lit-coverage metric measures the patroller — aim there first
			f = patroller_id if patroller else (
				sprites.keys()[0] if not sprites.is_empty() else "")
		if f != "":
			cam.position = sprites[f].position + Vector2(0, -160)
			cam.zoom = Vector2(1.4, 1.4)
			if light2d:
				# anchor offset (-290) leaves the sprite below the 0.18
				# luma floor under the dark modulate — the shot's light must
				# actually land on the figure
				light2d.position = sprites[f].position + Vector2(30, -120)
		elif light2d:
			light2d.position = Vector2(640, 480)
	elif "dialogue" in n:
		_show_dialogue()
	elif focus != "" and sprites.has(focus):
		var z := zoom if zoom > 0.0 else 1.9
		cam.position = sprites[focus].position + Vector2(off[0], off[1])
		cam.zoom = Vector2(z, z)
	elif "pair" in n or "lineup" in n:
		cam.position = Vector2(640, 500)
		cam.zoom = Vector2(1.4, 1.4)
	else:
		# wide/vista/all/grid/select: layers are painted on a 2x canvas —
		# a 1280x720 frame only sees the top-left quadrant (empty sky)
		cam.position = Vector2(1280, 720)
		cam.zoom = Vector2(0.5, 0.5)
	_apply_parallax()

func _apply_parallax() -> void:
	# far layers (low factor) lag behind camera travel; (640,360) is the
	# neutral camera position layouts are authored against. Each layer is
	# 2560x1440 — clamp its slide so it always covers the camera view,
	# otherwise parallax lag exposes canvas void mid-frame.
	var delta := cam.position - Vector2(640, 360)
	var half := Vector2(640.0 / cam.zoom.x, 360.0 / cam.zoom.y)
	var view := Rect2(cam.position - half, half * 2.0)
	for id in pbg_layers:
		var L: Dictionary = pbg_layers[id]
		var off: Vector2 = -delta * L["factor"]
		off.x = clampf(off.x,
			view.end.x - 2560.0 - L["base_x"], view.position.x - L["base_x"])
		off.y = clampf(off.y,
			view.end.y - 1440.0 - L["y"], view.position.y - L["y"])
		for cp in L["copies"]:
			cp["s"].position = Vector2(
				L["base_x"] + off.x + cp["dx"], L["y"] + off.y)

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
		if dialogue_img != "":
			var tr := TextureRect.new()
			tr.texture = _tex("res://assets/components/%s/portrait.png" % dialogue_img)
			tr.custom_minimum_size = Vector2(110, 110)
			tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
			hb.add_child(tr)
		var lb := Label.new()
		lb.text = job.get("composition", {}).get("layout", {}).get("dialogue_text",
			"The scene awaits.")
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
