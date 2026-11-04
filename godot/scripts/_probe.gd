extends SceneTree
func _init():
	print("PROBE start")
	var t = load("res://assets/components/xx_azure_sage/sprite_idle.png")
	print("PROBE load ->", t)
	var img = Image.create(4,4,false,Image.FORMAT_RGBA8)
	img.fill(Color.RED)
	img.save_png("res://_probe_out.png")
	print("PROBE wrote png")
	quit()
