"""Procedural region/self-collision policy through real native session and replay."""
import importlib
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PACKAGE = ('bl_ext.user_default.basics_shape_key_manager' if '--installed-extension' in sys.argv
           else 'BASICs_shape_key_manager')
geometry = importlib.import_module(PACKAGE + '.operators.clothing_checks.geometry')
regions = importlib.import_module(PACKAGE + '.operators.clothing_checks.regions')
fingerprints = importlib.import_module(PACKAGE + '.operators.clothing_checks.fingerprints')
policy = importlib.import_module(PACKAGE + '.core.clothing_policy')
spec = importlib.util.spec_from_file_location('regressions', ROOT / 'scripts/verify_clothing_session_regressions.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
assert bpy.app.background, 'factory fixture only'


def make_mesh(name, points, faces):
    data = bpy.data.meshes.new(name)
    data.from_pydata(points, [], faces)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj['_basic_clothing_id'] = name
    return obj


def snap(obj, **options):
    bpy.context.view_layer.update()
    return geometry.snapshot_mesh(obj, bpy.context.evaluated_depsgraph_get(), **options)


def reject(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('malformed region accepted')


def nested_containment_ownership():
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    corners = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
               (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
    for garment_inside in (False, True):
        body_scale, shirt_scale = (1., .2) if garment_inside else (.2, 1.)
        body = make_mesh('nested_body_' + str(garment_inside),
                         [tuple(axis * body_scale for axis in point) for point in corners], faces)
        shirt = make_mesh('nested_shirt_' + str(garment_inside),
                          [tuple(axis * shirt_scale for axis in point) for point in corners], faces)
        raw = geometry.analyze_pair(snap(body), snap(shirt), primary_id=shirt['_basic_clothing_id'])
        result = policy.apply_policy(raw, {}, [])
        actionable = policy.actionable_analysis(result)
        assert actionable['contained_faces'] == raw['contained_faces'], (raw, actionable)
        expected = 'CLIPPING' if garment_inside else 'CLEAR'
        assert raw['absolute_fit'] == actionable['absolute_fit'] == expected
        source_id = shirt['_basic_clothing_id'] if garment_inside else body['_basic_clothing_id']
        assert raw['contained_polygon_pairs'] and all(
            row['source_id'] == source_id for row in raw['contained_polygon_pairs'])


def uncontrolled_neutral_baseline():
    session = fixture.session
    motion = fixture.fixture.ik_fixture.motion
    for authored_motion in ('reach_forward', 'neutral'):
        body, rig, pairs, mapping, settings = fixture.setup('Uncontrolled' + authored_motion)
        t = 1. if authored_motion == 'neutral' else 0.
        offset = [0, .03, .02] if authored_motion == 'neutral' else [0, .2, .1]
        case = motion.interpolate_case(dict(profile='HEAD_HANDS', motion=authored_motion,
            shape_case='current', shape_values={}, t=t, controls={'left_upper_arm': {'elevation': 70}},
            target_offsets_m={'left_hand': offset}), t)
        settings.update(cases=[case])
        calibration = session.ValidationSession(bpy.context, body, rig, pairs, mapping, settings)
        solved = calibration.motion.apply(case)
        hand = Matrix(solved['matrices']['left_hand'])
        hand_deform = hand @ rig.data.bones['left_hand'].matrix_local.inverted()
        hips_deform = Matrix(solved['matrices']['hips']) @ rig.data.bones['hips'].matrix_local.inverted()
        center = hand.translation
        crossed = [center + Vector(delta) for delta in
                   [(-.04, -.04, 0), (.04, -.04, 0), (0, .04, 0),
                    (0, -.04, -.04), (0, -.04, .04), (0, .04, 0)]]
        points = [tuple(hand_deform.inverted() @ point) for point in crossed[:3]]
        points += [tuple(hips_deform.inverted() @ point) for point in crossed[3:]]
        calibration.cancel()
        body.data = bpy.data.meshes.new('NeutralScreen' + authored_motion)
        body.data.from_pydata(points, [], [(0, 1, 2), (3, 4, 5)])
        body.vertex_groups.clear()
        body.vertex_groups.new(name='left_hand').add([0, 1, 2], 1., 'REPLACE')
        body.vertex_groups.new(name='hips').add([3, 4, 5], 1., 'REPLACE')
        sources = [body, rig, pairs[0]['reference'], pairs[0]['candidate']]
        original = session.fingerprint_inputs(sources)
        worker = session.ValidationSession(bpy.context, body, rig, pairs, mapping, settings)
        neutral = dict(profile=case['profile'], motion='neutral', t=0.,
                       shape_case=case['shape_case'], shape_values=case['shape_values'])
        worker.motion.apply(neutral)
        assert not geometry.body_self_crossings(worker._snapshots([worker.body])[worker.body])
        worker.motion.apply(case)
        assert geometry.body_self_crossings(worker._snapshots([worker.body])[worker.body]) == {(0, 1)}
        worker.cancel()
        worker = session.ValidationSession(bpy.context, body, rig, pairs, mapping, settings)
        applied, native_apply = [], worker.motion.apply
        def record_apply(pose_case):
            applied.append(json.loads(json.dumps(pose_case)))
            return native_apply(pose_case)
        worker.motion.apply = record_apply
        while not worker.step():
            pass
        report = worker.report
        worker.close()
        assert report['status'] == 'COMPLETED', report['errors']
        assert neutral in applied, (authored_motion, applied)
        pose = report['poses'][0]
        assert pose['body_self_crossings_baseline'] == [], (authored_motion, pose['body_self_crossings_baseline'])
        assert pose['body_self_crossings_new'] == [[0, 1]], (authored_motion, pose['body_self_crossings_new'])
        assert session.fingerprint_inputs(sources) == original


def bulk_equivalence():
    obj = make_mesh('transformed', [(0, 0, 0), (1, .3, .2), (1, 1, .7), (0, 1, 0)], [(0, 1, 2, 3)])
    for scale in (.01, .5, 1, 2):
        obj.matrix_world = Matrix.Translation((.37, -.42, 1.23)) @ Matrix.Diagonal((-2., .7, 1.3, 1.))
        fast, scalar = snap(obj, unit_scale=scale), snap(obj, unit_scale=scale, scalar=True)
        for key in ('topology', 'triangles', 'polygons'):
            assert fast[key] == scalar[key]
        assert max(abs(a[i] - b[i]) for a, b in zip(fast['points'], scalar['points']) for i in range(3)) < 1e-6
        obj.data.vertices[1].co.z += .02
        assert snap(obj, stable=fast)['triangles'] == fast['triangles']


def self_and_regions():
    obj = make_mesh('fold', [(-1, -1, 0), (1, -1, 0), (0, 1, 0),
                            (0, -1, -1), (0, -1, 1), (0, 1, 0), (0, 0, 1)],
                    [(0, 1, 2), (3, 4, 5), (0, 2, 6)])
    result = geometry.analyze_self(snap(obj))
    assert result['kind'] == 'SELF' and result['pair'] == ['fold', 'fold']
    assert [0, 1] in result['polygon_pairs'] and [0, 2] not in result['polygon_pairs']
    assert geometry.analyze_self(snap(obj), contact_m=2)['absolute_fit'] != 'CLIPPING'
    clean = geometry.analyze_self(snap(make_mesh('clean', [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])))
    assert clean['absolute_fit'] == 'CLEAR' and clean['scope'] == 'NONADJACENT_TRIANGLE_CROSSINGS'
    assert clean['containment'] == {'clean': 'NOT_APPLICABLE'}
    attribute = obj.data.attributes.new('fixed', 'INT', 'FACE')
    attribute.data[0].value = 4
    definition = {'fold': {'unchanged': {'attribute': 'fixed', 'value': 4}}}
    captured = regions.capture_regions([obj], definition)
    obj.data.vertices[6].co.z += 1
    assert regions.capture_regions([obj], definition) == captured
    assert captured['fold']['unchanged'] == [0]
    before = fingerprints.fingerprint(obj)
    attribute.data[1].value = 4
    assert fingerprints.fingerprint(obj) != before
    reject(lambda: regions.capture_regions([obj], {'fold': {'bad': {'attribute': 'absent'}}}))
    reject(lambda: regions.capture_regions([obj], {'fold': {'empty': {'attribute': 'fixed', 'value': 99}}}))
    obj.data.attributes.new('point', 'INT', 'POINT')
    reject(lambda: regions.capture_regions([obj], {'fold': {'bad': {'attribute': 'point'}}}))
    obj.data.attributes.new('float', 'FLOAT', 'FACE')
    reject(lambda: regions.capture_regions([obj], {'fold': {'bad': {'attribute': 'float'}}}))
    boolean = obj.data.attributes.new('boolean', 'BOOLEAN', 'FACE')
    boolean.data[2].value = True
    assert regions.capture_regions([obj], {'fold': {'boolean': {'attribute': 'boolean'}}})['fold']['boolean'] == [2]


def session_policy():
    body, rig, pairs, mapping, settings = fixture.setup('Policy')
    source = pairs[0]['candidate']
    body.data = bpy.data.meshes.new('RegionalBody')
    body.data.from_pydata([(10, -1, 0), (12, -1, 0), (11, 1, 0),
                          (11, -1, -1), (11, -1, 1), (11, 1, 0),
                          (-.1, -.1, 1), (.1, -.1, 1), (0, .1, 1)], [],
                         [(0, 1, 2), (3, 4, 5), (6, 7, 8)])
    region = body.data.attributes.new('anatomy', 'INT', 'FACE')
    region.data[0].value, region.data[1].value, region.data[2].value = 1, 1, 2
    for obj in (pairs[0]['reference'], source):
        obj.data = bpy.data.meshes.new(obj.name + 'Fold')
        obj.data.from_pydata([(-.1, -.1, 1), (.1, -.1, 1), (0, .1, 1),
                             (0, -.1, .9), (0, -.1, 1.1), (0, .1, 1)], [], [(0, 1, 2), (3, 4, 5)])
        attribute = obj.data.attributes.new('side', 'INT', 'FACE')
        attribute.data[0].value, attribute.data[1].value = 1, 2
    session = fixture.session
    identity = session.logical_id(source)
    settings.update(region_definitions={identity: {'front': {'attribute': 'side', 'value': 1},
                                                  'back': {'attribute': 'side', 'value': 2}}},
                    contact_allowances=[{'kind': 'CROSSING', 'a': {'object_id': identity, 'region': 'front'},
                                         'b': {'object_id': identity, 'region': 'back'}}])
    settings['region_definitions'][session.logical_id(body)] = {
        'shoulder': {'attribute': 'anatomy', 'value': 2}, 'thigh': {'attribute': 'anatomy', 'value': 1}}
    sources = [body, rig, pairs[0]['reference'], source]
    original = session.fingerprint_inputs(sources)
    worker = session.ValidationSession(bpy.context, body, rig, pairs, mapping, settings)
    worker.cancel()
    assert worker.report['status'] == 'CANCELLED' and session.fingerprint_inputs(sources) == original
    worker = session.ValidationSession(bpy.context, body, rig, pairs, mapping, settings)
    source.data.attributes['side'].data[0].value = 2
    assert worker.step() and worker.report['status'] == 'STALE'
    source.data.attributes['side'].data[0].value = 1
    report = session.run_validation(bpy.context, body, rig, pairs, mapping, settings)
    assert report['status'] == 'COMPLETED', report['errors']
    result = next(r for r in report['results'] if r['kind'] == 'SELF')
    assert result['candidate']['absolute_fit'] == 'CLIPPING'
    assert result['candidate']['policy']['allowed_count'] == 1
    assert result['candidate']['policy']['actionable_count'] == 0
    assert result['candidate']['crossing_faces'][identity] == [0, 1]
    local = report['poses'][result['pose_index']]['regional_body_plausibility']
    assert local['shoulder']['status'] == 'NO_LOCAL_CROSSINGS'
    assert local['shoulder']['global_crossing_count'] == 1
    assert local['thigh']['status'] == 'LOCAL_CROSSINGS'
    assert local['thigh']['baseline_crossing_pairs'] == [[0, 1]]
    assert not local['thigh']['new_crossing_pairs']
    assert result['candidate']['containment'][identity] == 'NOT_APPLICABLE'
    body_result = next(r for r in report['results'] if r['kind'] == 'BODY')
    assert body_result['candidate']['containment'][identity] == 'UNKNOWN'
    preview = importlib.import_module(PACKAGE + '.operators.clothing_checks.preview')
    preview.preview_failure(bpy.context, report, report['results'].index(result))
    assert any(p.select for obj in bpy.context.selected_objects for p in obj.data.polygons)
    preview.clear_preview(bpy.context)
    assert session.fingerprint_inputs(sources) == original
    saved = json.loads(bpy.data.texts[report['text']].as_string())
    assert saved == report and saved['report_hash'] and saved['settings_hash']
    replay = session.run_validation(bpy.context, body, rig, pairs, mapping, dict(settings, cases=report['cases']))
    assert replay['regions'] == report['regions'] and replay['settings_hash'] == report['settings_hash']
    addon = importlib.import_module(PACKAGE)
    if not hasattr(bpy.types.Scene, 'clothing_checks'):
        addon.register()
    options = bpy.context.scene.clothing_checks
    options.body, options.rig = body, rig
    row = options.pairs.add()
    row.reference, row.candidate, row.confirmed = pairs[0]['reference'], source, True
    for canonical, bone in mapping.items():
        row = options.mapping.add()
        row.canonical, row.bone = canonical, bone
    options.mapping_confirmed, options.replay, options.report_text = True, True, report['text']
    authoring = importlib.import_module(PACKAGE + '.operators.clothing_checks.authoring')
    replay_settings = authoring.inputs_from_ui(bpy.context)[-1]
    assert replay_settings['region_definitions'] == settings['region_definitions']
    assert replay_settings['contact_allowances'] == settings['contact_allowances']
    with tempfile.TemporaryDirectory() as temporary:
        path = str(Path(temporary) / 'policy.blend')
        bpy.ops.wm.save_as_mainfile(filepath=path)
        expression = f'''import bpy,json,sys,importlib
sys.path.insert(0,{str(ROOT)!r})
s=importlib.import_module({(PACKAGE + '.operators.clothing_checks.session')!r})
r=json.loads(bpy.data.texts[{report['text']!r}].as_string())
objects=list(r['objects'].values())
body=bpy.data.objects[next(o['source'] for o in objects if o['role']=='BODY')]
rig=bpy.data.objects[next(o['source'] for o in objects if o['role']=='RIG')]
refs={{o['id']:bpy.data.objects[o['source']] for o in objects if o['role']=='REFERENCE'}}
pairs=[dict(reference=refs[o['id']],candidate=bpy.data.objects[o['source']],confirmed=True) for o in objects if o['role']=='CANDIDATE']
again=s.run_validation(bpy.context,body,rig,pairs,r['mapping'],dict(r['settings'],cases=r['cases']))
assert again['status']=='COMPLETED',again['errors']
self_result=next(i for i in again['results'] if i['kind']=='SELF')
assert self_result['candidate']['policy']['allowed_count']==1
assert again['regions']==r['regions']
print('CLOTHING_POLICY_FRESH_REOPEN_OK')'''
        child = subprocess.run([bpy.app.binary_path, '--background', '--factory-startup', path,
                                '--python-exit-code', '1', '--python-expr', expression],
                               capture_output=True, text=True)
        assert child.returncode == 0 and 'CLOTHING_POLICY_FRESH_REOPEN_OK' in child.stdout, child.stdout + child.stderr
        print('CLOTHING_POLICY_FRESH_REOPEN_OK')
    print('CLOTHING_POLICY_SESSION_OK')


for test in (uncontrolled_neutral_baseline, nested_containment_ownership, bulk_equivalence, self_and_regions, session_policy):
    test()
    print('PASS', test.__name__)
print('CLOTHING_POLICY_OK')
