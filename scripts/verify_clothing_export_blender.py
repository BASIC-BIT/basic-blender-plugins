"""Native export invariants. Run with Blender --background --factory-startup."""
from pathlib import Path
from copy import deepcopy
import hashlib
import importlib
import json
import sys

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
assert (HERE / 'clothing_export_fixture.py').exists(), 'procedural export fixture missing'
from clothing_export_fixture import (POSES, SHAPES, SCENE, apply_case, assert_analytic_skin,
                                     build_fixture, points, source_record)

ROOT = HERE.parent
if '--installed-extension' not in sys.argv:
    sys.path.insert(0, str(ROOT))
PACKAGE = ('bl_ext.user_default.basics_shape_key_manager' if '--installed-extension' in sys.argv
           else 'BASICs_shape_key_manager')
geometry = importlib.import_module(PACKAGE + '.operators.clothing_checks.geometry')
print('CLOTHING_EXPORT_PACKAGE', geometry.__file__)


def close_points(expected, actual, tolerance=1e-5):
    assert len(expected) == len(actual), (len(expected), len(actual))
    error = max((Vector(a) - Vector(b)).length for a, b in zip(expected, actual))
    assert error < tolerance, ('world point error', error, tolerance)
    return error


def assert_roundtrip(scene, rig, meshes, before, samples):
    """Compare imported rest/bind, topology, loop data, keys and actual skinning."""
    after = source_record(rig, meshes)
    for name, bone in before['bones'].items():
        assert after['bones'][name]['parent'] == bone['parent']
        close_points(bone['rest_matrix'], after['bones'][name]['rest_matrix'])
    errors = []
    for name, expected in before['meshes'].items():
        actual = after['meshes'][name]
        close_points(expected['vertices'], actual['vertices'])
        assert actual['triangles'] == expected['triangles'], name
        assert actual['material_indices'] == expected['material_indices'], name
        assert len(actual['materials']) == len(expected['materials']) == 2
        assert all(a.split('.')[0] == e for a, e in zip(actual['materials'], expected['materials']))
        assert len(actual['uv']) == len(expected['uv'])
        assert max(abs(a - e) for uv_a, uv_e in zip(actual['uv'], expected['uv'])
                   for a, e in zip(uv_a, uv_e)) < 1e-6
        for a, e in zip(actual['weights'], expected['weights']):
            assert set(a) == set(e) and len(a) <= 4
            assert abs(sum(a.values()) - 1) < 1e-6
            assert all(abs(a[key] - e[key]) < 1e-6 for key in e)
            assert abs(a['ProtectedRibbon'] - .1) < 1e-6
        assert set(actual['shapes']) == set(expected['shapes'])
        for key, value in expected['shapes'].items():
            close_points(value['vertices'], actual['shapes'][key]['vertices'])
            assert abs(value['value'] - actual['shapes'][key]['value']) < 1e-6, (name, key, 'key value')
        for bone, value in expected['bind_poses'].items():
            close_points(value, actual['bind_poses'][bone])
    for sample in samples:
        apply_case(scene, rig, meshes, sample['pose'], sample['shape'])
        for obj in meshes:
            assert_analytic_skin(scene, rig, obj)
            errors.append(close_points(sample['world_points'][obj.name], points(scene, obj)))
    return max(errors)


def assert_corruption_rejected(scene, rig, meshes, before, samples):
    mutations = {
        'weights': lambda record: record['meshes']['Body']['weights'][0].update(Chest=.5),
        'protected_weight': lambda record: record['meshes']['Garment']['weights'][0].update(ProtectedRibbon=.2),
        'bind_pose': lambda record: record['meshes']['Body']['bind_poses']['Chest'][0].__setitem__(3, .5),
        'shape_value': lambda record: record['meshes']['Body']['shapes']['Heels'].update(value=.2),
        'topology': lambda record: record['meshes']['Body']['triangles'][0].reverse(),
    }
    for name, mutate in mutations.items():
        damaged = deepcopy(before)
        mutate(damaged)
        try:
            assert_roundtrip(scene, rig, meshes, damaged, samples)
        except AssertionError:
            print('PASS rejected_corrupt_' + name)
        else:
            raise AssertionError('accepted corrupt ' + name)
    damaged_samples = deepcopy(samples)
    damaged_samples[0]['world_points']['Body'][0][0] += .01
    try:
        assert_roundtrip(scene, rig, meshes, before, damaged_samples)
    except AssertionError:
        print('PASS rejected_corrupt_posed_point')
    else:
        raise AssertionError('accepted corrupt posed point')
    apply_case(scene, rig, meshes, 'Rest', 'LinkedHeels')


def export_and_verify(output):
    output.mkdir(parents=True, exist_ok=True)
    native = output / 'clothing-export-fixture.blend'
    fbx = output / 'clothing-export-fixture.fbx'
    manifest = output / 'clothing-export-fixture.json'
    original_scene = bpy.context.scene
    original_objects = set(original_scene.objects)
    scene, rig, meshes = build_fixture()
    samples = []
    for pose in POSES:
        for shape in SHAPES:
            apply_case(scene, rig, meshes, pose, shape)
            for obj in meshes:
                assert_analytic_skin(scene, rig, obj)
            samples.append({'pose': pose, 'shape': shape,
                            'world_points': {obj.name: points(scene, obj) for obj in meshes}})
    apply_case(scene, rig, meshes, 'Rest', 'LinkedHeels')
    before = source_record(rig, meshes)
    assert_corruption_rejected(scene, rig, meshes, before, samples)
    assert set(original_scene.objects) == original_objects, 'source objects changed'
    assert all(value['protected'] == ['ProtectedRibbon'] for value in before['meshes'].values())
    graph = scene.view_layers[0].depsgraph
    body, garment = [geometry.snapshot_mesh(obj, graph) for obj in meshes]
    crossing = geometry.analyze_pair(body, garment)
    assert crossing['absolute_fit'] == 'CLIPPING', crossing
    assert all(crossing['crossing_faces'].values()), crossing
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    bpy.ops.wm.open_mainfile(filepath=str(native))
    scene = bpy.data.scenes[SCENE]
    bpy.context.window.scene = scene
    rig = scene.objects['FixtureRig']
    meshes = [scene.objects[name] for name in ('Body', 'Garment')]
    assert source_record(rig, meshes) == before, 'native reopen changed source'
    for obj in scene.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'ARMATURE', 'MESH'},
                             use_mesh_modifiers=False, add_leaf_bones=False, bake_anim=False,
                             use_armature_deform_only=True, axis_forward='-Z', axis_up='Y')
    assert source_record(rig, meshes) == before, 'export mutated source data'
    imported_scene = bpy.data.scenes.new(SCENE + '_Reimport')
    bpy.context.window.scene = imported_scene
    bpy.ops.import_scene.fbx(filepath=str(fbx), use_anim=False)
    imported_rig = next(obj for obj in imported_scene.objects if obj.type == 'ARMATURE')
    imported_meshes = sorted((obj for obj in imported_scene.objects if obj.type == 'MESH'),
                             key=lambda obj: obj.name)
    assert len(imported_meshes) == 2
    # Blender adds suffixes because native sources remain loaded during import.
    for obj in imported_meshes:
        obj.name = obj.name.split('.')[0] + '_Imported'
    source_names = {obj.name: obj.name.removesuffix('_Imported') for obj in imported_meshes}
    # Comparisons use stable source identities without renaming source objects.
    for obj in meshes:
        obj.name += '_Source'
    for obj in imported_meshes:
        obj.name = source_names[obj.name]
    maximum_error = assert_roundtrip(imported_scene, imported_rig, imported_meshes, before, samples)
    for obj in imported_meshes:
        obj.name += '_Imported'
    for obj in meshes:
        obj.name = obj.name.removesuffix('_Source')
    assert source_record(rig, meshes) == before, 'roundtrip evaluation mutated native sources'
    payload = {'schema_version': 1, 'fixture': 'vendor-free-clothing-export',
               'native_file': str(native.resolve()), 'fbx_file': str(fbx.resolve()),
               'source_sha256': hashlib.sha256(fbx.read_bytes()).hexdigest(),
               'native_sha256': hashlib.sha256(native.read_bytes()).hexdigest(),
               'blender_version': bpy.app.version_string,
               'coordinate_system': 'Blender right-handed Z-up world meters',
               'export_axes': {'forward': '-Z', 'up': 'Y'},
               'rig': 'FixtureRig', 'source': before, 'shape_cases': SHAPES,
               'pose_controls_degrees_xyz': POSES, 'samples': samples,
               'deliberate_intersection': {'region': 'Armpit', 'finding': 'CLIPPING',
                                            'crossing_faces': crossing['crossing_faces']},
               'verification': {'native_reopened': True, 'fbx_reimported': True,
                                'posed_cases': len(samples), 'maximum_world_point_error_m': maximum_error,
                                'source_preserved': True, 'four_influences': True,
                                'protected_weights_preserved': True},
               'limitations': ['FACE attributes and weight locks are native authoring metadata, not FBX data.',
                              'Unity coordinate mapping, SDK dynamics and VRChat behavior require separate checks.']}
    encoded = json.dumps(payload, indent=2, allow_nan=False)
    manifest.write_text(encoded, encoding='utf-8')
    assert json.loads(manifest.read_text(encoding='utf-8')) == json.loads(encoded)
    bpy.context.window.scene = scene
    for obj in list(imported_scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.scenes.remove(imported_scene)
    print('CLOTHING_EXPORT_MANIFEST', manifest)

assert bpy.app.background, 'fixture must never run in an interactive user scene'
output = (Path(sys.argv[sys.argv.index('--output-dir') + 1])
          if '--output-dir' in sys.argv else HERE.parents[1] / 'clothing-validator-fixtures')
export_and_verify(output)
print('CLOTHING_EXPORT_OK')
