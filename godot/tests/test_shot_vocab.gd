extends GdUnitTestSuite
## Shot/camera vocabulary contract — the bugs fixed in ledger #50.

const RUNNER := "res://scripts/runner.gd"


func test_cap_cams_vocabulary() -> void:
	var cam_names: Array = load(RUNNER).CAP_CAMS.keys()
	for n in ["mid", "front_close", "attach_close", "wide", "side"]:
		assert_array(cam_names).contains(n)


func test_focus_matches_inner_id_token() -> void:
	var r: Node2D = load(RUNNER).new()
	r.sprites = {"xx_azure_sage_3d": null, "crew_05": null}
	assert_str(r._focus_from_name("sage_attach_close")) \
		.is_equal("xx_azure_sage_3d")
	r.free()


func test_focus_ignores_short_tokens() -> void:
	var r: Node2D = load(RUNNER).new()
	r.sprites = {"xx_azure_sage_3d": null}
	# "3d" is under the 4-char minimum — must never focus
	assert_str(r._focus_from_name("3d_shot")).is_equal("")
	r.free()
