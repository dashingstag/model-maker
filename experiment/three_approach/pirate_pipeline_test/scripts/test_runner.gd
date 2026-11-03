extends Node
## Pipeline test harness: runs each approach scene, samples perf metrics,
## captures the standard screenshot set, writes reports/report.json, quits.

const TESTS := [
	["sprites", "res://scripts/sprites_test.gd"],
	["realtime_3d", "res://scripts/realtime_3d_test.gd"],
	["cutout", "res://scripts/cutout_test.gd"],
]
const BASE := "res://reports"

func _ready() -> void:
	DirAccess.make_dir_recursive_absolute(BASE)
	var report := {}
	for t in TESTS:
		var approach: String = t[0]
		var inst: Node = load(t[1]).new()
		add_child(inst)
		await _frames(45)

		var res: Dictionary = await inst.checks()
		await _frames(10)
		res["draw_calls"] = int(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
		res["primitives"] = int(Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME))

		var times: Array = []
		var last := Time.get_ticks_usec()
		for i in 120:
			await RenderingServer.frame_post_draw
			var now := Time.get_ticks_usec()
			times.append((now - last) / 1000.0)
			last = now
		times.sort()
		res["frame_ms_p50"] = snappedf(times[times.size() / 2], 0.01)
		res["frame_ms_p95"] = snappedf(times[int(times.size() * 0.95)], 0.01)

		DirAccess.make_dir_recursive_absolute(BASE + "/" + approach)
		for shot in inst.shots():
			inst.setup_shot(shot)
			await _frames(8)
			await RenderingServer.frame_post_draw
			var img := get_viewport().get_texture().get_image()
			img.save_png("%s/%s/%s.png" % [BASE, approach, shot])
		report[approach] = res

		inst.queue_free()
		await _frames(10)

	var f := FileAccess.open(BASE + "/report.json", FileAccess.WRITE)
	f.store_string(JSON.stringify(report, "  "))
	f.close()
	print("REPORT_JSON_BEGIN")
	print(JSON.stringify(report, "  "))
	print("REPORT_JSON_END")
	get_tree().quit()

func _frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame
