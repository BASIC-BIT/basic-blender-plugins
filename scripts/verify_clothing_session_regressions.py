"""Review regressions on generated factory objects, never a live creator scene."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import tempfile
import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('session_fixture', ROOT / 'scripts/verify_clothing_checks_blender.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
session, baseline = fixture.session, fixture.baseline
preview = __import__(fixture.PACKAGE + '.operators.clothing_checks.preview', fromlist=['preview_failure'])


def setup(name, captured=False):
    rig = fixture.ik_fixture.fixture(name, roll=37, short_tails=True)
    body = fixture.mesh(name + 'Body', rig)
    candidate = fixture.mesh(name + 'After', rig, .03)
    if captured:
        record = baseline.capture_baseline(bpy.context, body, rig, [candidate])
        reference = bpy.data.objects[record['pairs'][0]['reference']]
    else:
        reference = fixture.mesh(name + 'Before', rig, .03)
    pair = dict(reference=reference, candidate=candidate, confirmed=True)
    case = next(c for c in fixture.ik_fixture.motion.seed_cases(['HEAD_HANDS'])
                if c['motion'] == 'reach_forward' and c['t'] == 1)
    settings = dict(cases=[case], budget=1, refinement_depth=0, sample_limit=16,
                    motion_library_version=fixture.ik_fixture.motion.LIBRARY_VERSION)
    return body, rig, [pair], fixture.ik_fixture.confirmed(rig), settings


def triangulation():
    body, rig, pairs, mapping, settings = setup('Quad')
    ref, candidate = pairs[0]['reference'], pairs[0]['candidate']
    for obj, points in [(ref, [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]),
                        (candidate, [(0, 0, 0), (.2, .8, 0), (1, 1, 0), (0, 1, 0)])]:
        obj.data = bpy.data.meshes.new(obj.name + 'Quad')
        obj.data.from_pydata(points, [], [(0, 1, 2, 3)])
        obj.data.calc_loop_triangles()
    assert [tuple(t.vertices) for t in ref.data.loop_triangles] != [tuple(t.vertices) for t in candidate.data.loop_triangles]
    worker = session.ValidationSession(bpy.context, body, rig, pairs, mapping, settings)
    try:
        a, b = worker.copies[ref], worker.copies[candidate]
        assert worker.stable[a]['triangles'] == worker.stable[b]['triangles'], 'shared pre-pose template absent'
        expected = worker.stable[a]['triangles']
        assert not worker.step(), worker.report['errors']
        assert worker.current['snapshots'][a]['triangles'] == expected
        assert worker.current['snapshots'][b]['triangles'] == expected
    finally:
        worker.cancel()


def driven_shapes():
    for driven_side in ('reference', 'candidate'):
        body, rig, pairs, mapping, settings = setup('Driver' + driven_side)
        driven = pairs[0][driven_side]
        driver = driven.data.shape_keys.key_blocks['Fit'].driver_add('value').driver
        driver.type = 'AVERAGE'
        variable = driver.variables.new()
        variable.type = 'SINGLE_PROP'
        variable.targets[0].id_type = 'KEY'
        variable.targets[0].id = body.data.shape_keys
        variable.targets[0].data_path = 'key_blocks["Fit"].value'
        identity = session.logical_id(pairs[0]['candidate'])
        conflicting = dict(settings['cases'][0], shape_values={identity: {'Fit': .8}})
        report = session.run_validation(bpy.context, body, rig, pairs, mapping, dict(settings, cases=[conflicting]))
        assert report['status'] == 'ERROR' and not report['cases'], 'unrealized endpoint was counted'
        mismatch = report['unsupported_shape_values'][0]
        assert mismatch['object_id'] == identity and mismatch['key'] == 'Fit'
        assert abs(mismatch['requested'] - .8) < 1e-6 and abs(mismatch['effective'] - .2) < 1e-6
        current = session.run_validation(bpy.context, body, rig, pairs, mapping, settings)
        assert current['status'] == 'COMPLETED', current['errors']
        effective = current['poses'][0]['effective_shape_values']
        copied = next(name for name, info in current['objects'].items() if info['source'] == driven.name)
        assert abs(effective[copied]['Fit'] - .2) < 1e-6
    body, rig, pairs, mapping, settings = setup('Clamp')
    identity = session.logical_id(pairs[0]['candidate'])
    case = dict(settings['cases'][0], shape_values={identity: {'Fit': 100}})
    report = session.run_validation(bpy.context, body, rig, pairs, mapping, dict(settings, cases=[case]))
    assert report['status'] == 'ERROR' and report['unsupported_shape_values'], 'clamped endpoint was counted'


def _geometry(context, scene, obj):
    with context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        scene.view_layers[0].update()
        graph = context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(graph)
        data = evaluated.to_mesh()
        try:
            return [list(evaluated.matrix_world @ v.co) for v in data.vertices]
        finally:
            evaluated.to_mesh_clear()


def full_fingerprint_staleness():
    body, rig, pairs, mapping, settings = setup('Fingerprint')
    candidate = pairs[0]['candidate']
    rig.pose.bones['hips'].keyframe_insert('location', frame=1)
    action = rig.animation_data.action
    curve = action.layers[0].strips[0].channelbag(action.slots[0]).fcurves[0]
    body['Drive'], body['Drive2'] = .2, .2
    driver = candidate.data.shape_keys.key_blocks['Fit'].driver_add('value').driver
    driver.type = 'AVERAGE'
    variable = driver.variables.new()
    variable.type = 'SINGLE_PROP'
    target = variable.targets[0]
    target.id_type, target.id, target.data_path = 'OBJECT', body, '["Drive"]'
    driver_curve = candidate.data.shape_keys.animation_data.drivers[0]
    driver_modifier = driver_curve.modifiers.new('GENERATOR')
    driver_modifier.coefficients = (0., 1.)
    action_modifier = curve.modifiers.new('GENERATOR')
    action_modifier.coefficients = (0., 1.)
    mutations = [
        (lambda: setattr(body.data.vertices[0].co, 'x', .01), lambda: setattr(body.data.vertices[0].co, 'x', 0.)),
        (lambda: setattr(body.data.shape_keys.key_blocks['Fit'].data[0].co, 'z', 1.01),
         lambda: setattr(body.data.shape_keys.key_blocks['Fit'].data[0].co, 'z', 1.)),
        (lambda: candidate.vertex_groups['hips'].add([0], .5, 'REPLACE'),
         lambda: candidate.vertex_groups['hips'].add([0], 1., 'REPLACE')),
        (lambda: setattr(candidate.vertex_groups['hips'], 'lock_weight', True),
         lambda: setattr(candidate.vertex_groups['hips'], 'lock_weight', False)),
        (lambda: setattr(candidate.modifiers[0], 'use_deform_preserve_volume', True),
         lambda: setattr(candidate.modifiers[0], 'use_deform_preserve_volume', False)),
        (lambda: setattr(curve.keyframe_points[0].co, 'y', .01),
         lambda: setattr(curve.keyframe_points[0].co, 'y', 0.)),
        (lambda: setattr(target, 'data_path', '["Drive2"]'), lambda: setattr(target, 'data_path', '["Drive"]')),
        (lambda: body.__setitem__('Drive', .3), lambda: body.__setitem__('Drive', .2)),
        (lambda: setattr(driver_curve, 'mute', True), lambda: setattr(driver_curve, 'mute', False)),
        (lambda: setattr(driver_modifier, 'coefficients', (.1, 1.)),
         lambda: setattr(driver_modifier, 'coefficients', (0., 1.))),
        (lambda: setattr(curve, 'mute', True), lambda: setattr(curve, 'mute', False)),
        (lambda: setattr(action_modifier, 'coefficients', (.1, 1.)),
         lambda: setattr(action_modifier, 'coefficients', (0., 1.))),
    ]
    for change, restore in mutations:
        worker = session.ValidationSession(bpy.context, body, rig, pairs, mapping, settings)
        try:
            change()
            assert worker.step() and worker.report['status'] == 'STALE', 'full source edit was not detected'
        finally:
            worker.cancel()
            restore()


def reference_shape_authoring():
    addon = __import__(fixture.PACKAGE, fromlist=['register'])
    if not hasattr(bpy.types.Scene, 'clothing_checks'):
        addon.register()
    body, rig, pairs, mapping, _ = setup('AuthoringReference')
    options = bpy.context.scene.clothing_checks
    options.pairs.clear()
    options.mapping.clear()
    options.shapes.clear()
    options.body, options.rig = body, rig
    row = options.pairs.add()
    row.reference, row.candidate, row.confirmed = pairs[0]['reference'], pairs[0]['candidate'], True
    for canonical, bone in mapping.items():
        item = options.mapping.add()
        item.canonical, item.bone = canonical, bone
    options.mapping_confirmed = True
    endpoint = options.shapes.add()
    endpoint.object, endpoint.key, endpoint.value, endpoint.case = row.reference, 'Fit', .6, 'Reference endpoint'
    authoring = __import__(fixture.PACKAGE + '.operators.clothing_checks.authoring', fromlist=['inputs_from_ui'])
    _, _, _, _, settings = authoring.inputs_from_ui(bpy.context)
    values = next(shape['values'] for shape in settings['shape_cases'] if shape['id'] == endpoint.case)
    assert set(values) == {session.logical_id(row.candidate)}, values
    assert abs(values[session.logical_id(row.candidate)]['Fit'] - .6) < 1e-6


def pose_dependent_current():
    body, rig, pairs, mapping, settings = setup('CurrentDriver')
    candidate = pairs[0]['candidate']
    driver = candidate.data.shape_keys.key_blocks['Fit'].driver_add('value').driver
    driver.type = 'AVERAGE'
    variable = driver.variables.new()
    variable.type = 'TRANSFORMS'
    variable.targets[0].id = rig
    variable.targets[0].bone_target = 'left_hand'
    variable.targets[0].transform_type = 'LOC_X'
    variable.targets[0].transform_space = 'WORLD_SPACE'
    neutral = fixture.ik_fixture.motion.seed_cases(['HEAD_HANDS'], budget=1)[0]
    report = session.run_validation(bpy.context, body, rig, pairs, mapping,
        dict(settings, budget=2, cases=[neutral, settings['cases'][0]]))
    assert report['status'] == 'COMPLETED', report['errors']
    copied = next(name for name, info in report['objects'].items() if info['source'] == candidate.name)
    first, second = [pose['effective_shape_values'][copied]['Fit'] for pose in report['poses']]
    assert abs(first - second) > .01, 'pose-dependent CURRENT values were not recorded'
    result_index = next(i for i, result in enumerate(report['results'])
                        if result['pose_index'] == 1 and result['kind'] == 'BODY')
    for side in ('REFERENCE', 'CANDIDATE'):
        scene = preview.preview_failure(bpy.context, report, result_index, side)
        actual = session.effective_shapes(bpy.context, scene, scene.objects)
        assert abs(actual[copied]['Fit'] - second) < 1e-6
        preview.clear_preview(bpy.context)


def nonneutral_preview():
    body, rig, pairs, mapping, settings = setup('Preview', captured=True)
    # Make actual skinning depend on several moving ancestors, not only hips.
    for obj in [pairs[0]['reference'], pairs[0]['candidate']]:
        obj.vertex_groups.clear()
        obj.vertex_groups.new(name='left_forearm').add([0, 1, 2], 1, 'REPLACE')
    worker = session.ValidationSession(bpy.context, body, rig, pairs, mapping, settings)
    assert not worker.step(), worker.report['errors']
    expected = {role: _geometry(bpy.context, worker.scene, obj) for obj in worker.scene.objects
                if (role := obj.get('_basic_clothing_role')) in {'REFERENCE', 'CANDIDATE'}}
    matrices = worker.report['poses'][0]['matrices']
    # Compare independent expected skinning from the saved evaluated bone frame.
    for obj in worker.scene.objects:
        if obj.get('_basic_clothing_role') in expected:
            deform = Matrix(matrices['left_forearm']) @ worker.rig.data.bones['left_forearm'].matrix_local.inverted()
            predicted = [list(obj.matrix_world @ deform @ key.co) for key in obj.data.shape_keys.key_blocks['Basis'].data]
            assert max(abs(a[i] - b[i]) for a, b in zip(predicted, expected[obj['_basic_clothing_role']])
                       for i in range(3)) < 1e-4
    while not worker.step():
        pass
    report = worker.report
    assert report['status'] == 'COMPLETED', report['errors']
    for side in ('REFERENCE', 'CANDIDATE'):
        scene = preview.preview_failure(bpy.context, report, 0, side)
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            graph = bpy.context.evaluated_depsgraph_get()
            eval_rig = worker.rig.evaluated_get(graph)
            error = max(abs(eval_rig.pose.bones[name].matrix[i][j] - value[i][j])
                        for name, value in matrices.items() for i in range(4) for j in range(4))
            assert error < 1e-4, ('preview pose changed', error)
        for obj in scene.objects:
            role = obj.get('_basic_clothing_role')
            if role == 'DEPENDENCY':
                assert obj.hide_get(view_layer=scene.view_layers[0]), 'preview exposed dependency'
            elif role in expected:
                assert obj.hide_get(view_layer=scene.view_layers[0]) == (role != side)
                if role == side:
                    got = _geometry(bpy.context, scene, obj)
                    assert max(abs(a[i] - b[i]) for a, b in zip(got, expected[side]) for i in range(3)) < 1e-4
        preview.clear_preview(bpy.context)
    return {'text': report['text'], 'expected': expected}


def external_reopen(non_neutral):
    body, rig, pairs, mapping, settings = setup('External')
    source_objects = [body, rig, pairs[0]['reference'], pairs[0]['candidate']]
    for obj in [body, pairs[0]['reference'], pairs[0]['candidate']]:
        for point in obj.data.shape_keys.key_blocks['Fit'].data:
            point.co.y += .2
    original = session.fingerprint_inputs(source_objects)
    case = dict(settings['cases'][0], shape_values={session.logical_id(body): {'Fit': .8},
                session.logical_id(pairs[0]['candidate']): {'Fit': .3}})
    worker = session.ValidationSession(bpy.context, body, rig, pairs, mapping, dict(settings, cases=[case]))
    assert not worker.step(), worker.report['errors']
    expected = {role: _geometry(bpy.context, worker.scene, obj) for obj in worker.scene.objects
                if (role := obj.get('_basic_clothing_role')) in {'REFERENCE', 'CANDIDATE'}}
    while not worker.step():
        pass
    assert worker.report['status'] == 'COMPLETED', worker.report['errors']
    assert session.fingerprint_inputs(source_objects) == original
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        evidence = folder / 'evidence.json'
        evidence.write_text(json.dumps([non_neutral, {'text': worker.report['text'], 'expected': expected}]))
        path = folder / 'external-review.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        command = [bpy.app.binary_path, '--background', '--factory-startup', str(path), '--python-exit-code', '1',
                   '--python', str(ROOT / 'scripts/clothing_session_reopen.py'), '--', '--evidence', str(evidence)]
        if '--installed-extension' in sys.argv:
            command.append('--installed-extension')
        child = subprocess.run(command, capture_output=True, text=True)
        assert child.returncode == 0 and 'CLOTHING_EXTERNAL_AND_NONNEUTRAL_REOPEN_OK' in child.stdout, child.stdout + child.stderr
        print('CLOTHING_EXTERNAL_AND_NONNEUTRAL_REOPEN_OK')


def main():
    failed = []
    non_neutral = None
    for test in (triangulation, driven_shapes, full_fingerprint_staleness, reference_shape_authoring,
                 pose_dependent_current, nonneutral_preview):
        try:
            result = test()
            if test == nonneutral_preview:
                non_neutral = result
            print('PASS', test.__name__)
        except Exception as exc:
            failed.append(test.__name__ + ': ' + repr(exc))
            print('FAIL', failed[-1])
    assert not failed, failed
    external_reopen(non_neutral)
    print('CLOTHING_SESSION_REVIEW_OK')


if __name__ == '__main__':
    main()
