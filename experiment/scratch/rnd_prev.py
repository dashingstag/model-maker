import bpy, sys, math
argv = sys.argv[sys.argv.index("--")+1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=argv[0])
for o in bpy.data.objects:
    if o.type=='ARMATURE':
        o.data.pose_position='REST'
        for pb in o.pose.bones: pb.matrix_basis.identity()
sc=bpy.context.scene
mn=[1e9]*3; mx=[-1e9]*3
for o in bpy.data.objects:
    if o.type=='MESH':
        for v in o.bound_box:
            w=o.matrix_world@__import__('mathutils').Vector(v)
            for i in range(3): mn[i]=min(mn[i],w[i]); mx[i]=max(mx[i],w[i])
ctr=[(a+b)/2 for a,b in zip(mn,mx)]
h=max(mx[2]-mn[2],0.1)
cam=bpy.data.objects.new('c',bpy.data.cameras.new('c'))
sc.collection.objects.link(cam); sc.camera=cam
cam.location=(ctr[0]+h*1.7, ctr[1]-h*1.7, ctr[2]+h*0.35)
import mathutils
cam.rotation_euler=(mathutils.Vector(ctr)-cam.location).to_track_quat('Z','Y').to_euler()
cam.data.lens=55
sun=bpy.data.objects.new('s',bpy.data.lights.new('s','SUN'))
sc.collection.objects.link(sun); sun.rotation_euler=(0.6,0.3,0.9)
sun.data.energy=3
w=bpy.data.worlds.new('w'); sc.world=w; w.use_nodes=True
w.node_tree.nodes['Background'].inputs[0].default_value=(0.05,0.05,0.08,1)
sc.render.engine='BLENDER_WORKBENCH' 
sc.render.resolution_x=720; sc.render.resolution_y=720
sc.render.filepath=argv[1]
bpy.ops.render.render(write_still=True)
