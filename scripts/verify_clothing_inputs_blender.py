"""Native UI input, adaptive-budget and persistent rename regressions."""
from pathlib import Path
import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import bpy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('inputs_fixture', ROOT / 'scripts/verify_clothing_checks_blender.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
PACKAGE = fixture.PACKAGE
authoring = importlib.import_module(PACKAGE + '.operators.clothing_checks.authoring')
reporting = importlib.import_module(PACKAGE + '.operators.clothing_checks.reporting')
preview = importlib.import_module(PACKAGE + '.operators.clothing_checks.preview')
identities = importlib.import_module(PACKAGE + '.operators.clothing_checks.identities')
assert bpy.app.background


def ui_fixture(name):
    rig = fixture.ik_fixture.fixture(name + 'Rig', roll=23, short_tails=True)
    body, before, after = [fixture.mesh(name + suffix, rig) for suffix in ('Body', 'Before', 'After')]
    options = bpy.context.scene.clothing_checks
    options.body, options.rig = body, rig
    options.pairs.clear()
    row = options.pairs.add()
    row.reference, row.candidate, row.confirmed = before, after, True
    options.mapping.clear()
    for canonical, bone in fixture.ik_fixture.confirmed(rig).items():
        mapping = options.mapping.add()
        mapping.canonical, mapping.bone = canonical, bone
    options.mapping_confirmed = True
    return options, rig, body, row


def pair_confirmation():
    options, rig, _, row = ui_fixture('PairConfirm')
    other = fixture.mesh('UnrelatedSameTopology', rig)
    row.candidate = other
    assert not row.confirmed, 'changing After retained confirmation for unrelated same-topology mesh'
    row.confirmed = True
    row.reference = other
    assert not row.confirmed, 'changing Before retained old pair confirmation'
    row.confirmed = True
    authoring.inputs_from_ui(bpy.context)
    print('PAIR_CONFIRMATION_RNA_OK')


def mapping_confirmation():
    options, rig, _, _ = ui_fixture('MappingConfirm')
    left = next(row for row in options.mapping if row.canonical == 'left_hand')
    left.bone = 'right_hand'
    assert not options.mapping_confirmed, 'bone search field retained old mapping confirmation'
    left.bone = 'left_hand'
    options.mapping_confirmed = True
    options.rig = fixture.ik_fixture.fixture('DifferentSelectedRig')
    assert not options.mapping_confirmed, 'selected rig retained old mapping confirmation'
    options.rig = rig
    options.mapping_confirmed = True
    index = next(i for i, row in enumerate(options.mapping) if row.canonical == 'left_hand')
    options.mapping.remove(index)
    fixture.reject(lambda: authoring.inputs_from_ui(bpy.context), 'confirm')
    print('MAPPING_CONFIRMATION_RNA_OK')


def replay_ignored_live_json():
    options, _, _, _ = ui_fixture('ReplayJSON')
    sampling = importlib.import_module(PACKAGE + '.operators.clothing_checks.sampling')
    settings, _, _ = sampling.prepare({})
    case = fixture.ik_fixture.motion.seed_cases(['HEAD_HANDS'], budget=1)[0]
    previous = dict(settings=settings, cases=[case], coverage={'status': 'INCOMPLETE'})
    previous['report_hash'] = reporting.report_digest(previous)
    text = bpy.data.texts.new('RetainedReplaySettings')
    text.write(json.dumps(previous))
    options.report_text, options.replay = text.name, True
    for name in ('bend_directions', 'accessory_bones', 'region_definitions', 'contact_allowances', 'utility_groups'):
        setattr(options, name, '{ invalid unused JSON')
    options.shapes.clear()
    try:
        actual = authoring.inputs_from_ui(bpy.context)[-1]
        assert all(actual[key] == value for key, value in settings.items())
        assert actual['cases'] == previous['cases'] and actual['replay_coverage'] == previous['coverage']
        options.shapes.add()
        assert authoring.inputs_from_ui(bpy.context)[-1] == actual
        print('REPLAY_IGNORED_LIVE_JSON_OK')
    finally:
        options.replay = False
        options.shapes.clear()
        for name in ('bend_directions', 'region_definitions', 'utility_groups'):
            setattr(options, name, '{}')
        for name in ('accessory_bones', 'contact_allowances'):
            setattr(options, name, '[]')


def default_adaptive_budget():
    options, rig, body, row = ui_fixture('DefaultAdaptive')
    row.candidate.location.z = .0005
    inputs = authoring.inputs_from_ui(bpy.context)
    settings = inputs[-1]
    assert settings['budget'] == 512 and settings['refinement_depth'] == 3
    assert set(settings['profiles']) == {'HEAD_HANDS', 'FULL_BODY'}
    before = fixture.session.fingerprint_inputs([body, rig, row.reference, row.candidate])
    worker = fixture.session.ValidationSession(bpy.context, *inputs)
    seed_ids = {case['id'] for case in worker.expected}
    try:
        while worker.report['status'] == 'RUNNING':
            worker.step()
        assert worker.report['status'] == 'COMPLETED', worker.report['errors']
        assert any(m.get('clearance_m', 1.) < settings['clearance_m'] for m in worker.measurements)
        refined = [case for case in worker.report['cases'] if case['id'] not in seed_ids]
        assert refined, 'default budget exhausted by seeds: adaptive midpoint count is zero'
        coverage = worker.report['coverage']
        assert coverage['evaluated_cases'] <= 512 and coverage['expected_seed_cases'] == len(worker.expected)
        assert coverage['uncovered_cases'] and coverage['status'] == 'INCOMPLETE'
        assert coverage['uncovered_strata'] == [], coverage['uncovered_strata']
        assert not coverage['continuous_coverage']
        assert fixture.session.fingerprint_inputs([body, rig, row.reference, row.candidate]) == before
        print('DEFAULT_ADAPTIVE_BUDGET_OK', 'expected=' + str(len(worker.expected)),
              'evaluated=' + str(len(worker.report['cases'])), 'refinements=' + str(len(refined)))
    finally:
        worker.cancel()


def rig_labels():
    _, rig, body, row = ui_fixture('RenameRig')
    after = row.candidate
    body.parent = rig
    rig['rename_driver_value'] = .2
    for obj in (body, after):
        curve = obj.data.shape_keys.driver_add('key_blocks["Fit"].value')
        curve.driver.type = 'AVERAGE'
        variable = curve.driver.variables.new()
        variable.type = 'SINGLE_PROP'
        variable.targets[0].id = rig
        variable.targets[0].data_path = '["rename_driver_value"]'
    captured = fixture.baseline.capture_baseline(bpy.context, body, rig, [after])
    reference = bpy.data.objects[captured['pairs'][0]['reference']]
    pairs = [dict(reference=reference, candidate=after, confirmed=True)]
    sources = list(dict.fromkeys([body, rig, after, *bpy.data.scenes[captured['scene']].objects]))
    property_keys = {obj: (set(obj.keys()), set(obj.data.keys())) for obj in sources}
    source_ids = identities.capture_source_ids(sources)
    before = fixture.session.fingerprint_inputs(sources, source_ids)
    case = fixture.ik_fixture.motion.seed_cases(['HEAD_HANDS'], budget=1)
    settings = dict(cases=case, budget=1, refinement_depth=0,
                    motion_library_version=fixture.ik_fixture.motion.LIBRARY_VERSION)
    rig.name, rig.data.name = 'Creator renamed working rig', 'Creator renamed armature data'
    report = fixture.session.run_validation(bpy.context, body, rig, pairs, fixture.ik_fixture.confirmed(rig), settings)
    assert report['status'] == 'COMPLETED', report['errors']
    legacy = dict(report, fingerprint_format='BASIC-CLOTHING-BINARY-1')
    legacy['report_hash'] = reporting.report_digest(legacy)
    fixture.reject(lambda: preview.preview_failure(bpy.context, legacy), 'legacy report')
    rig.name, rig.data.name = 'Creator renamed rig after report', 'Creator renamed data after report'
    assert fixture.session.fingerprint_inputs(sources, source_ids) == before, 'rig labels changed canonical fingerprints'
    for side in ('REFERENCE', 'CANDIDATE'):
        preview.preview_failure(bpy.context, report, 0, side)
        preview.clear_preview(bpy.context)
    assert all((set(obj.keys()), set(obj.data.keys())) == keys for obj, keys in property_keys.items())
    scene = bpy.data.scenes[report['review_scene']]
    scene['rename_fixture_sources'] = {'body': body, 'rig': rig, 'reference': reference, 'candidate': after}
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'renamed-rig-review.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        command = [bpy.app.binary_path, '--background', '--factory-startup', str(path), '--python-exit-code', '9',
                   '--python', str(Path(__file__)), '--', '--reopen', report['text']]
        if '--installed-extension' in sys.argv:
            command.append('--installed-extension')
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0 and 'RENAMED_RIG_FRESH_REOPEN_OK' in result.stdout, result.stdout + result.stderr
    print('RIG_LABELS_CAPTURE_PREVIEW_REOPEN_OK')


def reopen():
    report = reporting.parse_report(bpy.data.texts[sys.argv[sys.argv.index('--reopen') + 1]].as_string())
    scene = bpy.data.scenes[report['review_scene']]
    sources = scene['rename_fixture_sources']
    rig = sources['rig']
    rig.name, rig.data.name = 'Fresh process rig rename', 'Fresh process armature rename'
    preview.preview_failure(bpy.context, report)
    preview.clear_preview(bpy.context)
    # A semantic change must still invalidate the retained report.
    rig.data.bones['hips'].envelope_weight += .25
    fixture.reject(lambda: preview.preview_failure(bpy.context, report), 'stale')
    print('RENAMED_RIG_FRESH_REOPEN_OK')


def incremental_baselines():
    _, rig, body, row = ui_fixture('Incremental')
    a, b = row.candidate, fixture.mesh('SecondIncrementalGarment', rig, .03)
    first = fixture.baseline.capture_baseline(bpy.context, body, rig, [a, b])
    second = fixture.baseline.capture_baseline(bpy.context, body, rig, [b, a])
    pairs = [dict(reference=bpy.data.objects[first['pairs'][0]['reference']], candidate=a, confirmed=True),
             dict(reference=bpy.data.objects[second['pairs'][0]['reference']], candidate=b, confirmed=True)]
    before = fixture.session.fingerprint_inputs([body, rig, a, b])
    worker = fixture.session.ValidationSession(bpy.context, body, rig, pairs, fixture.ik_fixture.confirmed(rig), {})
    worker.cancel()
    assert fixture.session.fingerprint_inputs([body, rig, a, b]) == before
    reference = pairs[0]['reference']
    reference['_basic_clothing_fingerprint_format'] = 'BASIC-CLOTHING-BINARY-1'
    fixture.reject(lambda: fixture.session.ValidationSession(bpy.context, body, rig, pairs,
        fixture.ik_fixture.confirmed(rig), {}), 'recapture')
    old_scene = bpy.data.scenes[first['scene']]
    frozen_body = next(o for o in old_scene.objects if o.get('_basic_clothing_role') == 'BODY')
    frozen_rig = next(o for o in old_scene.objects if o.get('_basic_clothing_role') == 'RIG')
    preserved = fixture.session.fingerprint_inputs(list(old_scene.objects))
    recovered = fixture.baseline.capture_baseline(bpy.context, frozen_body, frozen_rig, [reference])
    assert fixture.session.fingerprint_inputs(list(old_scene.objects)) == preserved
    new_reference = bpy.data.objects[recovered['pairs'][0]['reference']]
    assert new_reference != reference and new_reference.data != reference.data
    worker = fixture.session.ValidationSession(bpy.context, frozen_body, frozen_rig,
        [dict(reference=new_reference, candidate=reference, confirmed=True)], fixture.ik_fixture.confirmed(frozen_rig), {})
    worker.cancel()
    print('FROZEN_LEGACY_RECAPTURE_OK old_evidence_preserved=1')
    working = fixture.baseline.capture_baseline(bpy.context, body, rig, [reference])
    worker = fixture.session.ValidationSession(bpy.context, body, rig,
        [dict(reference=bpy.data.objects[working['pairs'][0]['reference']], candidate=a, confirmed=True)],
        fixture.ik_fixture.confirmed(rig), {})
    worker.cancel()
    assert fixture.session.fingerprint_inputs(list(old_scene.objects)) == preserved
    other_body = fixture.mesh('DistinctCapturedBody', rig)
    other = fixture.baseline.capture_baseline(bpy.context, other_body, rig, [b])
    mixed = [pairs[0], dict(reference=bpy.data.objects[other['pairs'][0]['reference']], candidate=b, confirmed=True)]
    fixture.reject(lambda: fixture.session.ValidationSession(bpy.context, body, rig, mixed,
        fixture.ik_fixture.confirmed(rig), {}), 'different captured bodies')
    print('INCREMENTAL_CAPTURE_CONTEXTS_OK')


def main():
    if '--reopen' in sys.argv:
        reopen()
        return
    importlib.import_module(PACKAGE).register()
    cases = {f.__name__: f for f in (pair_confirmation, mapping_confirmation, replay_ignored_live_json,
                                    default_adaptive_budget, rig_labels, incremental_baselines)}
    selected = [sys.argv[sys.argv.index('--case') + 1]] if '--case' in sys.argv else list(cases)
    for name in selected:
        cases[name]()
    print('CLOTHING_INPUTS_FOLLOWUP_OK')


if __name__ == '__main__':
    main()
