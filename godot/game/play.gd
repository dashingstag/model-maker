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
	if "--autotest" not in OS.get_cmdline_user_args():
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _snap(name: String) -> void:
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(
		OUT.path_join(name + ".png"))
	print("playtest:", name)


func _autotest() -> void:
	await _snap("t0_idle")
	player.force_move = Vector2(0, -1)
	await get_tree().create_timer(1.2).timeout
	await _snap("t1_walk")
	await get_tree().create_timer(0.8).timeout
	player.force_move = Vector2.ZERO
	player._start_action("sword_swing")
	await get_tree().create_timer(0.7).timeout
	await _snap("t2_swing")
	await get_tree().create_timer(1.2).timeout
	player._start_action("talisman_cast")
	await get_tree().create_timer(0.6).timeout
	await _snap("t3_cast")
	await get_tree().create_timer(1.4).timeout
	# orbit view of the arena
	player.yaw = 0.9
	await _snap("t4_orbit")
	print("playtest: done")
	get_tree().quit()


func _physics_process(dt: float) -> void:
	if "--autotest" in OS.get_cmdline_user_args():
		if _step == 0:
			_step = 1
			_autotest()
