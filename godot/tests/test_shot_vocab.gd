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


func test_cast_on_row_pass_and_miss() -> void:
	var r: Node2D = load(RUNNER).new()
	r.member_rows = {"xx_immortal_m": "terrace", "xx_immortal_f": "terrace",
		"xx_azure_sage_3d": "vista"}
	assert_bool(r._cast_on_row(["xx_immortal_m", "xx_immortal_f"],
		"terrace")).is_true()
	assert_bool(r._cast_on_row(["xx_immortal_m", "xx_azure_sage_3d"],
		"terrace")).is_false()
	r.free()


func test_cast_on_row_empty_cast_is_null() -> void:
	# honesty contract: unmeasurable expectations report null, never pass
	var r: Node2D = load(RUNNER).new()
	assert_that(r._cast_on_row([], "terrace")).is_null()
	r.free()


func test_min_gap_px_measures_leftmost_pair() -> void:
	var r: Node2D = load(RUNNER).new()
	# rects sorted internally — a=[100,200), b=[280,380) -> gap 80
	var gap: float = r._min_gap_px([
		Rect2(280, 0, 100, 50), Rect2(100, 0, 100, 50)])
	assert_float(gap).is_equal_approx(80.0, 0.001)
	r.free()


func test_min_gap_px_unmeasurable_is_negative() -> void:
	var r: Node2D = load(RUNNER).new()
	# fewer than two rects cannot produce a gap — -1 -> pass:null upstream
	assert_float(r._min_gap_px([])).is_equal(-1.0)
	assert_float(r._min_gap_px([Rect2(0, 0, 10, 10)])).is_equal(-1.0)
	r.free()
