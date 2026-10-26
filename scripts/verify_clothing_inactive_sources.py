"""Fresh inactive-scene source evaluation regression on generated native data."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import tempfile
import bpy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('session_fixture', ROOT / 'scripts/verify_clothing_checks_blender.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def authored(objects):
    return {obj.name: {'location': list(obj.location), 'rotation': list(obj.rotation_euler),
                      'scale': list(obj.scale), 'parent': obj.parent.name if obj.parent else None,
                      'modifiers': [(m.type, m.object.name) for m in obj.modifiers],
                      'keys': [[k.name, k.value, [list(p.co) for p in k.data]]
                               for k in obj.data.shape_keys.key_blocks] if obj.type == 'MESH' else [],
                      'pose': {p.name: [list(r) for r in p.matrix_basis] for p in obj.pose.bones}
                              if obj.type == 'ARMATURE' else {}}
            for obj in objects}


def child():
    body, rig, reference, candidate, inactive_rig = [bpy.data.objects[name] for name in
        ('InactiveBody', 'ActiveRig', 'InactiveBefore', 'InactiveAfter', 'InactiveRig')]
    assert [list(r) for r in rig.matrix_world] != [list(r) for r in inactive_rig.matrix_world], 'fixture was already evaluated'
    objects = [body, rig, reference, candidate, inactive_rig]
    before = authored(objects)
    window = bpy.context.window
    view = (window.scene, window.view_layer, bpy.context.view_layer.objects.active,
            tuple(bpy.context.selected_objects), bpy.context.mode)
    frames = {s.name: (s.frame_current, s.frame_subframe) for s in bpy.data.scenes}
    pairs = [dict(reference=reference, candidate=candidate, confirmed=True)]
    motion = fixture.ik_fixture.motion.seed_cases(['HEAD_HANDS'], budget=1)
    worker = fixture.session.ValidationSession(bpy.context, body, rig, pairs,
        fixture.ik_fixture.confirmed(rig), dict(cases=motion, budget=1, sample_limit=16, refinement_depth=0,
            motion_library_version=fixture.ik_fixture.motion.LIBRARY_VERSION))
    try:
        assert [list(r) for r in rig.matrix_world] == [list(r) for r in inactive_rig.matrix_world]
        assert [list(r) for r in worker.copies[inactive_rig].matrix_world] == [list(r) for r in inactive_rig.matrix_world]
        assert not worker.step(), worker.report['errors']
    finally:
        worker.cancel()
    assert authored(objects) == before
    assert frames == {s.name: (s.frame_current, s.frame_subframe) for s in bpy.data.scenes}
    assert view == (window.scene, window.view_layer, bpy.context.view_layer.objects.active,
                    tuple(bpy.context.selected_objects), bpy.context.mode)
    report = fixture.session.run_validation(bpy.context, body, rig, pairs, fixture.ik_fixture.confirmed(rig),
        dict(cases=motion, budget=1, sample_limit=16, refinement_depth=0,
            motion_library_version=fixture.ik_fixture.motion.LIBRARY_VERSION))
    assert report['status'] == 'COMPLETED', report['errors']
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'retained-inactive-review.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        command = [bpy.app.binary_path, '--background', '--factory-startup', str(path), '--python-exit-code', '1',
                   '--python', str(Path(__file__)), '--', '--preview-child', '--report', report['text']]
        if '--installed-extension' in sys.argv:
            command.append('--installed-extension')
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0 and 'CLOTHING_INACTIVE_PREVIEW_REOPEN_OK' in result.stdout, result.stdout + result.stderr
        print('CLOTHING_INACTIVE_PREVIEW_REOPEN_OK')
    print('CLOTHING_INACTIVE_SOURCE_REOPEN_OK')


def preview_child():
    report = json.loads(bpy.data.texts[sys.argv[sys.argv.index('--report') + 1]].as_string())
    rig, inactive_rig = bpy.data.objects['ActiveRig'], bpy.data.objects['InactiveRig']
    assert [list(r) for r in rig.matrix_world] != [list(r) for r in inactive_rig.matrix_world]
    preview = __import__(fixture.PACKAGE + '.operators.clothing_checks.preview', fromlist=['preview_failure'])
    window = bpy.context.window
    before = (window.scene, window.view_layer, bpy.context.view_layer.objects.active,
              tuple(bpy.context.selected_objects), bpy.context.mode)
    source_frames = {s.name: (s.frame_current, s.frame_subframe) for s in bpy.data.scenes}
    for side in ('REFERENCE', 'CANDIDATE'):
        scene = preview.preview_failure(bpy.context, report, 0, side)
        assert scene.name == report['review_scene']
        assert [list(r) for r in rig.matrix_world] == [list(r) for r in inactive_rig.matrix_world]
        preview.clear_preview(bpy.context)
    assert before == (window.scene, window.view_layer, bpy.context.view_layer.objects.active,
                      tuple(bpy.context.selected_objects), bpy.context.mode)
    assert source_frames == {s.name: (s.frame_current, s.frame_subframe) for s in bpy.data.scenes}
    print('CLOTHING_INACTIVE_PREVIEW_REOPEN_OK')


def main():
    rig = fixture.ik_fixture.fixture('ActiveRig', roll=37, short_tails=True)
    body, candidate = [fixture.mesh(name, rig, offset) for name, offset in [('InactiveBody', 0), ('InactiveAfter', .03)]]
    inactive = bpy.data.scenes.new('Inactive Source Scene')
    inactive.use_fake_user = True
    inactive.frame_current = 9
    inactive_rig = bpy.data.objects.new('InactiveRig', rig.data.copy())
    inactive.collection.objects.link(inactive_rig)
    inactive_rig.rotation_euler.x = 1.6292e-7
    reference = bpy.data.objects.new('InactiveBefore', candidate.data.copy())
    inactive.collection.objects.link(reference)
    reference.modifiers.new('Armature', 'ARMATURE').object = inactive_rig
    reference.vertex_groups.new(name='hips').add([0, 1, 2], 1, 'REPLACE')
    rig.rotation_euler.x = 1.6292e-7
    bpy.context.scene.frame_current = 17
    bpy.context.view_layer.objects.active = candidate
    bpy.context.view_layer.update()
    assert [list(r) for r in rig.matrix_world] != [list(r) for r in inactive_rig.matrix_world]
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / 'inactive-source.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        command = [bpy.app.binary_path, '--background', '--factory-startup', str(path), '--python-exit-code', '1',
                   '--python', str(Path(__file__)), '--', '--child']
        if '--installed-extension' in sys.argv:
            command.append('--installed-extension')
        result = subprocess.run(command, capture_output=True, text=True)
        assert result.returncode == 0 and 'CLOTHING_INACTIVE_SOURCE_REOPEN_OK' in result.stdout, result.stdout + result.stderr
        assert 'CLOTHING_INACTIVE_PREVIEW_REOPEN_OK' in result.stdout
        print('CLOTHING_INACTIVE_PREVIEW_REOPEN_OK')
        print('CLOTHING_INACTIVE_SOURCE_REOPEN_OK')


if __name__ == '__main__':
    if '--preview-child' in sys.argv:
        preview_child()
    elif '--child' in sys.argv:
        child()
    else:
        main()
