extends SceneTree
## Loads a .tscn by absolute path, reports the instantiated tree, and
## optionally saves a frame: -s scripts/scene_probe.gd -- <scene.tscn> [out.png]
var _inst: Node
var _snap := ""
var _f := 0

func _init() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty():
		print("PROBE_FAIL no path")
		quit(2)
		return
	var scn: PackedScene = load(args[0])
	if scn == null:
		print("PROBE_FAIL load returned null: ", args[0])
		quit(3)
		return
	_inst = scn.instantiate()
	root.add_child(_inst)
	_snap = args[1] if args.size() > 1 else ""

func _process(_dt: float) -> bool:
	_f += 1
	if _f < 30:
		return false
	var counts := {}
	for c in _inst.find_children("*", "", true, false):
		var t := c.get_class()
		counts[t] = counts.get(t, 0) + 1
	print("PROBE_OK nodes=", _inst.get_child_count(), " tree=", counts)
	if _snap:
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(_snap)
		print("PROBE_SNAP ", _snap)
	return true
