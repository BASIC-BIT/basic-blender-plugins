"""Retained review integrity and supported body deformation, factory data only."""
from pathlib import Path
import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('review_fixture', ROOT / 'scripts/verify_clothing_session_regressions.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
session, preview = fixture.session, fixture.preview
PACKAGE = fixture.fixture.PACKAGE
identities = importlib.import_module(PACKAGE + '.operators.clothing_checks.identities')
assert bpy.app.background


def allocations():
    return tuple(len(getattr(bpy.data, name)) for name in
                 ('objects', 'meshes', 'armatures', 'shape_keys', 'scenes', 'actions'))


def body_deformation():
    for kind in ('missing', 'disabled', 'channels', 'no_weights', 'nondeforming', 'mask_zero', 'wrong_target'):
        body, rig, pairs, mapping, settings = fixture.setup('BodyBinding' + kind)
        mod = body.modifiers[0]
        if kind == 'missing':
            body.modifiers.remove(mod)
        elif kind == 'disabled':
            mod.show_viewport = False
        elif kind == 'channels':
            mod.use_vertex_groups = mod.use_bone_envelopes = False
        elif kind == 'no_weights':
            body.vertex_groups.clear()
        elif kind == 'nondeforming':
            rig.data.bones['hips'].use_deform = False
        elif kind == 'mask_zero':
            mod.vertex_group = body.vertex_groups.new(name='EmptyMask').name
        else:
            mod.object = fixture.fixture.ik_fixture.fixture('WrongBodyRig')
        sources = [body, rig, pairs[0]['reference'], pairs[0]['candidate']]
        before, counts = session.fingerprint_inputs(sources), allocations()
        token = 'body' if kind != 'wrong_target' else 'incompatible rig'
        fixture.fixture.reject(lambda: session.ValidationSession(bpy.context, body, rig, pairs, mapping, settings), token)
        assert session.fingerprint_inputs(sources) == before and allocations() == counts, kind
    for kind in ('weights', 'envelopes', 'render_disabled', 'inverted_mask', 'missing_mask'):
        body, rig, pairs, mapping, settings = fixture.setup('ValidBody' + kind, captured=True)
        if kind == 'envelopes':
            body.shape_key_clear()
            body.modifiers[0].use_vertex_groups = False
            body.modifiers[0].use_bone_envelopes = True
            # Capture after changing the supported evaluation configuration.
            record = fixture.baseline.capture_baseline(bpy.context, body, rig, [pairs[0]['candidate']])
            pairs[0]['reference'] = bpy.data.objects[record['pairs'][0]['reference']]
        elif kind == 'render_disabled':
            body.modifiers[0].show_render = False
            record = fixture.baseline.capture_baseline(bpy.context, body, rig, [pairs[0]['candidate']])
            pairs[0]['reference'] = bpy.data.objects[record['pairs'][0]['reference']]
        elif kind in {'inverted_mask', 'missing_mask'}:
            body.modifiers[0].vertex_group = 'EmptyMask'
            if kind == 'inverted_mask':
                body.vertex_groups.new(name='EmptyMask')
                body.modifiers[0].invert_vertex_group = True
            record = fixture.baseline.capture_baseline(bpy.context, body, rig, [pairs[0]['candidate']])
            pairs[0]['reference'] = bpy.data.objects[record['pairs'][0]['reference']]
        sources = [body, rig, pairs[0]['reference'], pairs[0]['candidate']]
        before = session.fingerprint_inputs(sources)
        worker = session.ValidationSession(bpy.context, body, rig, pairs, mapping, settings)
        def positions():
            worker.scene.view_layers[0].update()
            evaluated = worker.body.evaluated_get(worker.scene.view_layers[0].depsgraph)
            return [evaluated.matrix_world @ vertex.co for vertex in evaluated.data.vertices]
        rest = positions()
        worker.rig.pose.bones['hips'].location.x += .1
        assert any((a - b).length > .001 for a, b in zip(rest, positions())), (kind, 'supported body did not deform')
        worker.cancel()
        assert session.fingerprint_inputs(sources) == before, kind
    print('BODY_ENABLED_DEFORMATION_OK rejected=7 supported=5 native_deformation=1')


def make_report():
    body, rig, pairs, mapping, settings = fixture.setup('OwnedReview', captured=True)
    after = pairs[0]['candidate']
    identity = session.logical_id(after)
    base = settings['cases'][0]
    settings['cases'] = [base, fixture.fixture.ik_fixture.motion.interpolate_case(base, .25),
        fixture.fixture.ik_fixture.motion.interpolate_case(dict(base, shape_case='Fit',
            shape_values={identity: {'Fit': .8}}), .75)]
    settings['budget'] = 3
    settings['shape_cases'] = [{'id': 'current', 'values': {}}, {'id': 'Fit', 'values': {identity: {'Fit': .8}}}]
    sources = [body, rig, *[obj for pair in pairs for obj in (pair['reference'], pair['candidate'])]]
    before = session.fingerprint_inputs(sources)
    report = session.run_validation(bpy.context, body, rig, pairs, mapping, settings)
    assert report['status'] == 'COMPLETED', report['errors']
    return report, sources, before


def owned_review():
    report, sources, before = make_report()
    scene = bpy.data.scenes[report['review_scene']]
    candidate = next(o for o in scene.objects if o.get('_basic_clothing_role') == 'CANDIDATE')
    rig = next(o for o in scene.objects if o.get('_basic_clothing_role') == 'RIG')
    def show(index=0, side='CANDIDATE'):
        preview.preview_failure(bpy.context, report, index, side)
        preview.clear_preview(bpy.context)
    for index in range(len(report['results'])):
        show(index, 'REFERENCE' if index % 2 else 'CANDIDATE')
    candidate.show_wire = not candidate.show_wire
    candidate.data.polygons[0].select = not candidate.data.polygons[0].select
    candidate.active_shape_key_index = 1
    rig.data.display_type = 'STICK'
    rig.data.bones['hips'].show_wire = True
    rig.data.bones.active = rig.data.bones['head']
    show()
    def reject_edit(label, mutate, restore):
        mutate()
        altered = session.fingerprint_inputs(list(scene.objects))
        accepted = scene.get('_basic_clothing_review_state')
        fixture.fixture.reject(lambda: show(), 'modified retained review')
        assert session.fingerprint_inputs(list(scene.objects)) == altered, (label, 'preview overwrote manual edits')
        assert scene.get('_basic_clothing_review_state') == accepted, (label, 'rejection refreshed trusted state')
        restore()
        show()
    original = candidate.location.copy()
    reject_edit('transform', lambda: setattr(candidate, 'location', original + Vector((.1, 0, 0))),
                lambda: setattr(candidate, 'location', original))
    point = candidate.data.vertices[0].co.copy()
    reject_edit('mesh', lambda: setattr(candidate.data.vertices[0], 'co', point + Vector((.01, 0, 0))),
                lambda: setattr(candidate.data.vertices[0], 'co', point))
    key = candidate.data.shape_keys.key_blocks['Fit']
    point = key.data[0].co.copy()
    reject_edit('shape_geometry', lambda: setattr(key.data[0], 'co', point + Vector((0, 0, .01))),
                lambda: setattr(key.data[0], 'co', point))
    value = key.value
    reject_edit('shape_value', lambda: setattr(key, 'value', .6), lambda: setattr(key, 'value', value))
    group = candidate.vertex_groups['hips']
    weight = group.weight(0)
    reject_edit('weight', lambda: group.add([0], .5, 'REPLACE'), lambda: group.add([0], weight, 'REPLACE'))
    mod = candidate.modifiers[0]
    reject_edit('modifier', lambda: setattr(mod, 'show_viewport', False), lambda: setattr(mod, 'show_viewport', True))
    reject_edit('pin', lambda: setattr(candidate, 'show_only_shape_key', True),
                lambda: setattr(candidate, 'show_only_shape_key', False))
    bone = rig.data.bones['hips']
    reject_edit('rest_semantics', lambda: setattr(bone, 'inherit_scale', 'NONE'), lambda: setattr(bone, 'inherit_scale', 'FULL'))
    reject_edit('bbone', lambda: setattr(bone, 'bbone_curveinx', .125), lambda: setattr(bone, 'bbone_curveinx', 0.))
    basis = rig.pose.bones['hips'].matrix_basis.copy()
    reject_edit('manual_pose', lambda: setattr(rig.pose.bones['hips'], 'location', (.1, 0, 0)),
                lambda: setattr(rig.pose.bones['hips'], 'matrix_basis', basis))
    reject_edit('units', lambda: setattr(scene.unit_settings, 'scale_length', .5),
                lambda: setattr(scene.unit_settings, 'scale_length', 1.))
    frame = scene.frame_current
    reject_edit('frame', lambda: scene.frame_set(frame + 1), lambda: scene.frame_set(frame))
    extra = bpy.data.objects.new('UnexpectedReviewMember', bpy.data.meshes.new('UnexpectedReviewMesh'))
    reject_edit('membership', lambda: scene.collection.objects.link(extra), lambda: scene.collection.objects.unlink(extra))
    bpy.data.objects.remove(extra)
    reject_edit('missing_member', lambda: scene.collection.objects.unlink(candidate), lambda: scene.collection.objects.link(candidate))
    accepted = scene['_basic_clothing_review_state']
    del scene['_basic_clothing_review_state']
    fixture.fixture.reject(lambda: show(), 'rerun')
    scene['_basic_clothing_review_state'] = accepted
    show()
    assert session.fingerprint_inputs(sources) == before
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'review-state.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        command = [bpy.app.binary_path, '--background', '--factory-startup', str(path), '--python-exit-code', '9',
                   '--python', str(Path(__file__)), '--', '--reopen', report['text']]
        if '--installed-extension' in sys.argv:
            command.append('--installed-extension')
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0 and 'OWNED_REVIEW_FRESH_REOPEN_OK' in result.stdout, result.stdout + result.stderr
    accepted = scene['_basic_clothing_review_state']
    edited = json.loads(json.dumps(report))
    result = edited['results'][2]
    state = edited['poses'][result['pose_index']]['effective_shape_values']
    next(keys for keys in state.values() if 'Fit' in keys)['Fit'] = .123
    reporting = importlib.import_module(PACKAGE + '.operators.clothing_checks.reporting')
    edited['report_hash'] = reporting.report_digest(edited)
    fixture.fixture.reject(lambda: preview.preview_failure(bpy.context, edited, 2), 'effective shape')
    assert scene['_basic_clothing_review_state'] == accepted, 'failed controlled replay refreshed accepted state'
    assert session.fingerprint_inputs(sources) == before
    print('OWNED_REVIEW_STATE_OK tamper=14 controlled_replay=1 display_selection=1 source_preserved=1 failed_replay_preserved=1')


def reopen():
    reporting = importlib.import_module(PACKAGE + '.operators.clothing_checks.reporting')
    report = reporting.parse_report(bpy.data.texts[sys.argv[sys.argv.index('--reopen') + 1]].as_string())
    preview.preview_failure(bpy.context, report, 2)
    preview.clear_preview(bpy.context)
    scene = bpy.data.scenes[report['review_scene']]
    obj = next(o for o in scene.objects if o.get('_basic_clothing_role') == 'BODY')
    obj.data.shape_keys.key_blocks[0].data[0].co.x += .02
    before = session.fingerprint_inputs(list(scene.objects))
    fixture.fixture.reject(lambda: preview.preview_failure(bpy.context, report), 'modified retained review')
    assert session.fingerprint_inputs(list(scene.objects)) == before
    print('OWNED_REVIEW_FRESH_REOPEN_OK')


if __name__ == '__main__':
    if '--reopen' in sys.argv:
        reopen()
    else:
        cases = {'body': body_deformation, 'review': owned_review}
        selected = [sys.argv[sys.argv.index('--case') + 1]] if '--case' in sys.argv else list(cases)
        for name in selected:
            cases[name]()
        print('CLOTHING_REVIEW_STATE_OK')
