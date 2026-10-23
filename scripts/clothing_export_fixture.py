"""Small vendor-free, editable skinning fixture shared by native export checks."""
from math import radians

import bpy
from mathutils import Matrix, Vector

SCENE = 'BASIC_ClothingExportFixture'
WEIGHTS = {'Chest': .4, 'UpperArm': .3, 'Forearm': .2, 'ProtectedRibbon': .1}
SHAPES = {'Neutral': {'Body': {}, 'Garment': {}},
          'LinkedHeels': {'Body': {'Heels': .65}, 'Garment': {'HeelsFollow': .65}},
          'LinkedWidth': {'Body': {'Width': .35}, 'Garment': {'WidthFollow': .35}}}
POSES = {'Rest': {}, 'ArmRaised': {'UpperArm': (0, 0, 55), 'Forearm': (20, 0, 0)},
         'Twist': {'Chest': (5, 0, 12), 'UpperArm': (0, 30, -25),
                   'Forearm': (0, -15, 35), 'ProtectedRibbon': (10, 0, 0)}}


def matrix(value):
    return [list(row) for row in value]


def build_fixture():
    """Create only a named owned scene; never delete a caller's objects."""
    assert bpy.data.scenes.get(SCENE) is None, 'fixture scene already exists'
    scene = bpy.data.scenes.new(SCENE)
    bpy.context.window.scene = scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    data = bpy.data.armatures.new('FixtureSkeleton')
    rig = bpy.data.objects.new('FixtureRig', data)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for name, head, tail, parent in [
            ('Chest', (0, 0, 1), (0, 0, 1.4), None),
            ('UpperArm', (.15, 0, 1.4), (.5, 0, 1.4), 'Chest'),
            ('Forearm', (.5, 0, 1.4), (.8, 0, 1.4), 'UpperArm'),
            ('ProtectedRibbon', (.2, .04, 1.3), (.2, .04, 1.5), 'Chest')]:
        bone = data.edit_bones.new(name)
        bone.head, bone.tail = head, tail
        if parent:
            bone.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.location = (.15, -.07, .1)
    rig.rotation_euler = (.05, .09, .02)
    rig.select_set(False)
    meshes = []
    for name, center, extent in [('Body', (.2, 0, 1.35), (.16, .12, .15)),
                                 ('Garment', (.31, .03, 1.42), (.15, .14, .13))]:
        points = [(center[0] + x * extent[0], center[1] + y * extent[1],
                   center[2] + z * extent[2])
                  for x, y, z in [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                                  (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]]
        quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                 (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        triangles = [tri for a, b, c, d in quads for tri in [(a, b, c), (a, c, d)]]
        mesh = bpy.data.meshes.new(name + 'Source')
        mesh.from_pydata(points, [], triangles)
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        obj.parent = rig
        obj['_basic_clothing_id'] = name
        obj.modifiers.new('FixtureSkin', 'ARMATURE').object = rig
        for group, weight in WEIGHTS.items():
            target = obj.vertex_groups.new(name=group)
            target.add(list(range(len(points))), weight, 'REPLACE')
            target.lock_weight = group == 'ProtectedRibbon'
        for suffix, color in [('Cloth', (.15, .35, .8, 1)), ('Trim', (.8, .25, .12, 1))]:
            material = bpy.data.materials.new(name + suffix)
            material.diffuse_color = color
            mesh.materials.append(material)
        uv = mesh.uv_layers.new(name='FixtureUV')
        for face in mesh.polygons:
            face.material_index = face.index % 2
            for index in face.loop_indices:
                vertex = mesh.vertices[mesh.loops[index].vertex_index].co
                uv.data[index].uv = (vertex.x, vertex.z)
        region = mesh.attributes.new('Armpit', 'BOOLEAN', 'FACE')
        for entry in region.data:
            entry.value = True
        obj.shape_key_add(name='Basis')
        for key_name in (('Heels', 'Width') if name == 'Body' else ('HeelsFollow', 'WidthFollow')):
            key = obj.shape_key_add(name=key_name)
            for index, point in enumerate(key.data):
                if key_name.startswith('Heels') and index < 4:
                    point.co.z += .025
                if key_name.startswith('Width'):
                    point.co.x += .03 * (-1 if index in (0, 3, 4, 7) else 1)
        meshes.append(obj)
    scene['linked_shape_cases'] = __import__('json').dumps(SHAPES)
    scene.view_layers[0].update()
    return scene, rig, meshes


def apply_case(scene, rig, meshes, pose_name, shape_name):
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)
        bone.rotation_mode = 'XYZ'
        bone.rotation_euler = tuple(radians(v) for v in POSES[pose_name].get(bone.name, (0, 0, 0)))
    for obj in meshes:
        for key in obj.data.shape_keys.key_blocks[1:]:
            key.value = SHAPES[shape_name][obj.name].get(key.name, 0)
    scene.view_layers[0].update()


def points(scene, obj):
    evaluated = obj.evaluated_get(scene.view_layers[0].depsgraph)
    return [list(evaluated.matrix_world @ v.co) for v in evaluated.data.vertices]


def assert_analytic_skin(scene, rig, obj):
    actual = points(scene, obj)
    for vertex in obj.data.vertices:
        coordinate = vertex.co.copy()
        for key in obj.data.shape_keys.key_blocks[1:]:
            coordinate += (key.data[vertex.index].co - vertex.co) * key.value
        expected = Vector((0, 0, 0))
        for assignment in vertex.groups:
            name = obj.vertex_groups[assignment.group].name
            bind = rig.data.bones[name].matrix_local
            expected += (rig.matrix_world @ rig.pose.bones[name].matrix @ bind.inverted()
                         @ coordinate) * assignment.weight
        assert (Vector(actual[vertex.index]) - expected).length < 2e-6, obj.name


def source_record(rig, meshes):
    return {'rig_matrix': matrix(rig.matrix_world),
            'bones': {b.name: {'parent': b.parent.name if b.parent else None,
                               'rest_matrix': matrix(b.matrix_local)} for b in rig.data.bones},
            'meshes': {obj.name: {
                'vertices': [list(v.co) for v in obj.data.vertices],
                'triangles': [list(p.vertices) for p in obj.data.polygons],
                'materials': [m.name for m in obj.data.materials],
                'material_indices': [p.material_index for p in obj.data.polygons],
                'uv': [list(v.uv) for v in obj.data.uv_layers.active.data],
                'weights': [{obj.vertex_groups[g.group].name: g.weight for g in v.groups}
                            for v in obj.data.vertices],
                'protected': [g.name for g in obj.vertex_groups if g.lock_weight],
                'shapes': {k.name: {'value': k.value, 'vertices': [list(v.co) for v in k.data]}
                           for k in obj.data.shape_keys.key_blocks},
                'bind_poses': {b.name: matrix((rig.matrix_world @ b.matrix_local).inverted()
                                             @ obj.matrix_world) for b in rig.data.bones}}
                       for obj in meshes}}
