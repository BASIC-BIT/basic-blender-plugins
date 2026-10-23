"""Owned-session fixtures. Run with --background --factory-startup only."""
from pathlib import Path
import importlib
import importlib.util
import json
import sys
import tempfile
import subprocess
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PACKAGE = ('bl_ext.user_default.basics_shape_key_manager' if '--installed-extension' in sys.argv
           else 'BASICs_shape_key_manager')
assert bpy.app.background, 'never run fixtures in the user scene'
spec = importlib.util.spec_from_file_location('ik_fixture', ROOT / 'scripts/verify_clothing_ik_blender.py')
ik_fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ik_fixture)
session = importlib.import_module(PACKAGE + '.operators.clothing_checks.session')
baseline = importlib.import_module(PACKAGE + '.operators.clothing_checks.baseline')
ik_fixture.motion = importlib.import_module(PACKAGE + '.core.clothing_motion')
ik_fixture.native = importlib.import_module(PACKAGE + '.operators.clothing_checks.rig')


def mesh(name, rig, offset=0):
    data = bpy.data.meshes.new(name)
    data.from_pydata([(offset, 0, 1), (offset + .2, 0, 1), (offset, .2, 1)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    mod = obj.modifiers.new('Armature', 'ARMATURE')
    mod.object = rig
    obj.vertex_groups.new(name='hips').add([0, 1, 2], 1, 'REPLACE')
    obj.shape_key_add(name='Basis')
    obj.shape_key_add(name='Fit').value = .2
    return obj


def reject(call, token):
    try:
        call()
    except (ValueError, RuntimeError) as exc:
        assert token.lower() in str(exc).lower(), str(exc)
    else:
        raise AssertionError('expected rejection: ' + token)


def run():
    addon = importlib.import_module(PACKAGE)
    if not hasattr(bpy.types.Scene, 'clothing_checks'):
        addon.register()
    assert hasattr(bpy.types, 'BASIC_PT_clothing_pose_checks')
    for name in ('capture_clothing_baseline', 'run_clothing_checks', 'cancel_clothing_checks',
                 'preview_clothing_failure', 'clear_clothing_preview', 'export_clothing_report'):
        assert getattr(bpy.ops.basic, name).get_rna_type()
    assert bpy.types.Scene.bl_rna.properties['clothing_checks'].fixed_type.identifier == 'BASIC_ClothingSettings'
    assert bpy.types.BASIC_PT_clothing_pose_checks.bl_parent_id == 'BASIC_PT_developer'
    rig = ik_fixture.fixture('SessionRig', roll=37, short_tails=True)
    body, a, b = [mesh(name, rig, offset) for name, offset in [('Body', 0), ('A', .02), ('B', .03)]]
    mapping = ik_fixture.confirmed(rig)
    before = session.fingerprint_inputs([body, rig, a, b])
    captured = baseline.capture_baseline(bpy.context, body, rig, [a, b])
    assert session.fingerprint_inputs([body, rig, a, b]) == before
    assert bpy.data.scenes[captured['scene']].use_fake_user
    refs = [bpy.data.objects[row['reference']] for row in captured['pairs']]
    assert refs[0].data != a.data and refs[0].data.shape_keys != a.data.shape_keys
    pairs = [dict(reference=ref, candidate=obj, confirmed=True) for ref, obj in zip(refs, [a, b])]
    neutral = ik_fixture.motion.seed_cases(['HEAD_HANDS', 'FULL_BODY'])[:2]
    settings = dict(cases=neutral, budget=2, refinement_depth=0, sample_limit=16,
                    motion_library_version=ik_fixture.motion.LIBRARY_VERSION)
    run_once = lambda: session.ValidationSession(bpy.context, body, rig, pairs, mapping, settings)
    reject(lambda: session.ValidationSession(bpy.context, body, rig, pairs, {}, settings), 'confirm')
    external = bpy.data.objects.new('External', None)
    bpy.context.scene.collection.objects.link(external)
    a.parent = external
    reject(run_once, 'parent')
    a.parent = None
    mod = a.modifiers.new('Unsupported', 'SOLIDIFY')
    reject(run_once, 'modifier')
    a.modifiers.remove(mod)
    constraint = rig.pose.bones[0].constraints.new('COPY_ROTATION')
    reject(run_once, 'constraint')
    rig.pose.bones[0].constraints.remove(constraint)
    driver = a.data.shape_keys.key_blocks['Fit'].driver_add('value').driver
    driver.type = 'SCRIPTED'
    reject(run_once, 'driver')
    a.data.shape_keys.key_blocks['Fit'].driver_remove('value')
    # Known simple internal drivers are copied and retargeted, never disabled.
    driver = a.data.shape_keys.key_blocks['Fit'].driver_add('value').driver
    driver.type = 'AVERAGE'
    variable = driver.variables.new()
    variable.type = 'SINGLE_PROP'
    variable.targets[0].id_type = 'KEY'
    variable.targets[0].id = body.data.shape_keys
    variable.targets[0].data_path = 'key_blocks["Fit"].value'
    worker = run_once()
    copied_driver = worker.copies[a].data.shape_keys.animation_data.drivers[0].driver
    assert copied_driver.variables[0].targets[0].id == worker.body.data.shape_keys
    worker.cancel()
    variable.targets[0].id_type = 'OBJECT'
    variable.targets[0].id = external
    variable.targets[0].data_path = 'location.x'
    reject(run_once, 'driver target')
    a.data.shape_keys.key_blocks['Fit'].driver_remove('value')
    original_data = b.data
    b.data = bpy.data.meshes.new('ChangedTopology')
    b.data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(2, 1, 0)])
    reject(run_once, 'topology')
    changed = b.data
    b.data = original_data
    bpy.data.meshes.remove(changed)
    # Native actions and keyframe data remain independent and source-owned.
    rig.pose.bones['hips'].keyframe_insert('location', frame=1)
    original_action = rig.animation_data.action
    worker = run_once()
    assert worker.rig.animation_data.action is None
    assert worker.rig['basic_clothing_action'] != original_action
    worker.cancel()
    for key in a.data.shape_keys.key_blocks:
        for vertex, z in zip(key.data, (.9, 1.1, 1.1)):
            vertex.co.z = z
    before = session.fingerprint_inputs([body, rig, a, b])
    start_scenes = set(bpy.data.scenes)
    worker = run_once()
    assert all(o not in [body, rig, a, b, *refs] for o in worker.scene.objects)
    assert all(m.object == worker.rig for o in worker.scene.objects if o.type == 'MESH'
               for m in o.modifiers if m.type == 'ARMATURE')
    worker.cancel()
    worker.close()
    assert worker.report['status'] == 'CANCELLED'
    assert set(bpy.data.scenes) == start_scenes
    assert session.fingerprint_inputs([body, rig, a, b]) == before
    worker = run_once()
    a.data.vertices[0].co.x += .01
    assert worker.step()
    assert worker.report['status'] == 'STALE'
    worker.close()
    a.data.vertices[0].co.x -= .01
    worker = run_once()
    while len(worker.report['cases']) < 1:
        assert not worker.step()
    worker.motion.apply = lambda case: (_ for _ in ()).throw(RuntimeError('injected'))
    assert worker.step() and worker.report['status'] == 'ERROR'
    worker.close()
    assert len(worker.report['cases']) == 1
    assert set(bpy.data.scenes) == start_scenes
    worker = run_once()
    while len(worker.report['cases']) < 1:
        assert not worker.step()
    worker.cancel()
    assert worker.report['status'] == 'CANCELLED' and len(worker.report['cases']) == 1
    assert set(bpy.data.scenes) == start_scenes
    source_view = (bpy.context.scene, bpy.context.view_layer.objects.active,
                   tuple(bpy.context.selected_objects), bpy.context.scene.frame_current, bpy.context.mode)
    report = session.run_validation(bpy.context, body, rig, pairs, mapping, settings)
    assert report['status'] == 'COMPLETED', report
    assert len(report['cases']) == 2 and len(report['results']) == 10
    assert len(report['poses']) == 2
    assert report['summary']['new_faces'] > 0, report['summary']
    assert report['summary']['absolute_fit'] == 'CLIPPING'
    assert report['summary']['unknown'] > 0
    assert report['summary']['absolute_unique_faces'] > 0
    assert report['summary']['absolute_crossing_faces'] > 0
    assert report['coverage']['continuous_coverage'] is False
    assert report['review_scene'] in bpy.data.scenes
    assert json.loads(json.dumps(report)) == report
    assert session.fingerprint_inputs([body, rig, a, b]) == before
    assert source_view == (bpy.context.scene, bpy.context.view_layer.objects.active,
        tuple(bpy.context.selected_objects), bpy.context.scene.frame_current, bpy.context.mode)
    preview = importlib.import_module(PACKAGE + '.operators.clothing_checks.preview')
    preview_failure, clear_preview = preview.preview_failure, preview.clear_preview
    origin = bpy.context.window.scene
    # Existing clipping remains selectable even with an identical baseline.
    checks = importlib.import_module(PACKAGE + '.core.clothing_checks')
    result = report['results'][0]
    existing = checks.classify_pair(result['candidate'], result['candidate'])
    existing.update({key: result[key] for key in ('case_id', 'pose_index', 'kind')})
    assert not existing['new'] and existing['existing']
    assert existing['absolute_fit'] == 'CLIPPING'
    preview_report = dict(report, results=[existing])
    preview_failure(bpy.context, preview_report, 0, 'CANDIDATE')
    assert bpy.context.window.scene.name == report['review_scene']
    assert any(p.select for o in bpy.context.selected_objects for p in o.data.polygons)
    clear_preview(bpy.context)
    assert bpy.context.window.scene == origin
    a.data.vertices[0].co.x += .01
    reject(lambda: preview_failure(bpy.context, report, 0, 'CANDIDATE'), 'stale')
    a.data.vertices[0].co.x -= .01
    replayed = session.run_validation(bpy.context, body, rig, pairs, mapping,
        dict(settings, cases=report['cases'], replay_coverage=report['coverage'],
             motion_library_version=report['settings']['motion_library_version']))
    assert replayed['cases'] == report['cases']
    assert replayed['coverage']['status'] == report['coverage']['status']
    assert replayed['coverage']['uncovered_cases'] == report['coverage']['uncovered_cases']
    # Different objects may share a shape-key name without sharing its value namespace.
    body_id = session.logical_id(body)
    a_id = session.logical_id(a)
    shaped_case = dict(neutral[0], shape_values={body_id: {'Fit': .8}, a_id: {'Fit': .3}})
    shaped = session.ValidationSession(bpy.context, body, rig, pairs, mapping,
        dict(settings, budget=1, cases=[shaped_case]))
    assert not shaped.step()
    assert abs(shaped.body.data.shape_keys.key_blocks['Fit'].value - .8) < 1e-6
    assert abs(shaped.copies[a].data.shape_keys.key_blocks['Fit'].value - .3) < 1e-6
    shaped.cancel()
    options = bpy.context.scene.clothing_checks
    options.body, options.rig = body, rig
    for pair in pairs:
        row = options.pairs.add()
        row.reference, row.candidate, row.confirmed = pair['reference'], pair['candidate'], True
    for canonical, bone in mapping.items():
        row = options.mapping.add()
        row.canonical, row.bone = canonical, bone
    options.mapping_confirmed = True
    options.budget = 2
    options.refinement_depth = 0
    assert bpy.ops.basic.run_clothing_checks('EXEC_DEFAULT') == {'FINISHED'}
    assert bpy.data.texts.get(options.report_text)
    # The fake-user native scene and Text report must survive an actual reopen.
    with tempfile.TemporaryDirectory() as temporary:
        path = str(Path(temporary) / 'review.blend')
        scene_name, text_name = report['review_scene'], report['text']
        bpy.ops.wm.save_as_mainfile(filepath=path)
        expression = (
            'import bpy,json,sys,importlib; '
            f'assert bpy.data.scenes[{scene_name!r}].use_fake_user; '
            f'r=json.loads(bpy.data.texts[{text_name!r}].as_string()); '
            'assert r["poses"] and r["inputs"]; '
            f'sys.path.insert(0,{str(ROOT)!r}); '
            f's=importlib.import_module({(PACKAGE + ".operators.clothing_checks.session")!r}); '
            'objects=list(r["objects"].values()); '
            'body=bpy.data.objects[next(o["source"] for o in objects if o["role"]=="BODY")]; '
            'rig=bpy.data.objects[next(o["source"] for o in objects if o["role"]=="RIG")]; '
            'before={o["id"]:bpy.data.objects[o["source"]] for o in objects if o["role"]=="REFERENCE"}; '
            'pairs=[dict(reference=before[o["id"]],candidate=bpy.data.objects[o["source"]],confirmed=True) '
            'for o in objects if o["role"]=="CANDIDATE"]; '
            'case=dict(r["cases"][0]); '
            'bodyid=next(o["id"] for o in objects if o["role"]=="BODY"); '
            'garmentid=next(o["id"] for o in objects if o["role"]=="CANDIDATE"); '
            'case["shape_values"]={bodyid:{"Fit":.8},garmentid:{"Fit":.3}}; '
            'settings=dict(r["settings"],budget=1,cases=[case]); '
            'again=s.run_validation(bpy.context,body,rig,pairs,r["mapping"],settings); '
            'assert again["status"]=="COMPLETED",again["errors"]; '
            'assert again["cases"][0]["shape_values"]==case["shape_values"]; '
            'print("CLOTHING_FRESH_REOPEN_OK")')
        fresh = subprocess.run([bpy.app.binary_path, '--background', '--factory-startup', path,
            '--python-exit-code', '1', '--python-expr', expression], capture_output=True, text=True)
        assert fresh.returncode == 0 and 'CLOTHING_FRESH_REOPEN_OK' in fresh.stdout, fresh.stdout + fresh.stderr
        print('CLOTHING_FRESH_REOPEN_OK')
        bpy.ops.wm.open_mainfile(filepath=path)
        assert bpy.data.scenes[scene_name].use_fake_user
        restored = json.loads(bpy.data.texts[text_name].as_string())
        assert restored['poses'] and restored['inputs']
    print('CLOTHING_SESSION_OK')


if __name__ == '__main__':
    run()
