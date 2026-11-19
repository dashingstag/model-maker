extends Node3D
## Playable sandbox — third-person sage on a small arena.
## `--autotest` runs a scripted input sequence and saves screenshots
## to res://reports/playtest/ so the gameplay loop is verifiable
## headlessly: idle -> walk -> sprint -> attack -> cast -> orbit shot.

const OUT := "res://reports/playtest"

var _t := 0.0
var _step := 0
@onready var player: CharacterBody3D = $Player


func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUT))
	player.target = $Target
	if "--autotest" not in OS.get_cmdline_user_args():
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _snap(name: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(
		OUT.path_join(name + ".png"))
	print("playtest:", name)


func _autotest() -> void:
	await _snap("t0_idle")
	player.force_move = Vector2(-0.35, -0.94)   # toward the floating jian
	await get_tree().create_timer(1.2).timeout
	await _snap("t1_walk")
	await get_tree().create_timer(0.3).timeout
	player.force_move = Vector2.ZERO
	player._start_action("sword_swing")   # in range — should hit
	await get_tree().create_timer(0.7).timeout
	await _snap("t2_hit")
	await get_tree().create_timer(1.0).timeout
	player._start_action("sword_swing")   # second hit
	await get_tree().create_timer(0.9).timeout
	player._start_action("spinning_parry")# third — target breaks
	await get_tree().create_timer(0.5).timeout
	await _snap("t3_break")
	await get_tree().create_timer(1.2).timeout
	player.velocity.y = 7.5
	player.airborne = true
	if player.anim and player.anim.has_animation("aerial_flourish"):
		player.anim.play("aerial_flourish", 0.08)
	await get_tree().create_timer(0.35).timeout
	await _snap("t4_jump")
	await get_tree().create_timer(1.0).timeout
	player.dash_dir = Vector3(0, 0, -1)
	player.dash_t = 0.24
	player._start_action("lunge_strike")
	await get_tree().create_timer(0.3).timeout
	await _snap("t5_dash")
	await get_tree().create_timer(1.0).timeout
	player._start_action("talisman_cast")
	if player.vfx:
		player.vfx.restart()
	await get_tree().create_timer(0.55).timeout
	await _snap("t6_cast")
	await get_tree().create_timer(1.2).timeout
	player.yaw = 0.9
	await _snap("t7_orbit")
	print("playtest: done")
	get_tree().quit()


func _physics_process(dt: float) -> void:
	if "--autotest" in OS.get_cmdline_user_args():
		if _step == 0:
			_step = 1
			_autotest()
