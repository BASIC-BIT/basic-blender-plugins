"""Fresh-process assertion helper for generated clothing review fixtures."""
from pathlib import Path
import importlib
import json
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PACKAGE = ('bl_ext.user_default.basics_shape_key_manager' if '--installed-extension' in sys.argv
           else 'BASICs_shape_key_manager')
native = importlib.import_module(PACKAGE + '.operators.clothing_checks.session')
preview = importlib.import_module(PACKAGE + '.operators.clothing_checks.preview')
evidence = json.loads(Path(sys.argv[sys.argv.index('--evidence') + 1]).read_text())


def points(scene, obj):
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        scene.view_layers[0].update()
        graph = bpy.context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        try:
            return [list(evaluated.matrix_world @ v.co) for v in mesh.vertices]
        finally:
            evaluated.to_mesh_clear()


for entry in evidence:
    report = json.loads(bpy.data.texts[entry['text']].as_string())
    body = bpy.data.objects[report['bindings']['body']['source']]
    rig = bpy.data.objects[next(info['source'] for info in report['objects'].values() if info['role'] == 'RIG')]
    pairs = [dict(reference=bpy.data.objects[row['reference']], candidate=bpy.data.objects[row['candidate']],
                  confirmed=True) for row in report['bindings']['pairs']]
    originals = [body, rig, *[o for pair in pairs for o in (pair['reference'], pair['candidate'])]]
    unchanged = native.fingerprint_inputs(originals)
    replay = native.run_validation(bpy.context, body, rig, pairs, report['mapping'],
        dict(report['settings'], cases=report['cases'], replay_coverage=report['coverage']))
    assert replay['status'] == 'COMPLETED', replay['errors']
    assert replay['cases'] == report['cases']
    assert replay['bindings'] == report['bindings']
    assert native.fingerprint_inputs(originals) == unchanged
    for side in ('REFERENCE', 'CANDIDATE'):
        scene = preview.preview_failure(bpy.context, report, 0, side)
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            graph = bpy.context.evaluated_depsgraph_get()
            copied_rig = next(o for o in scene.objects if o.get('_basic_clothing_role') == 'RIG')
            evaluated = copied_rig.evaluated_get(graph)
            matrices = report['poses'][0]['matrices']
            assert max(abs(evaluated.pose.bones[name].matrix[i][j] - expected[i][j])
                       for name, expected in matrices.items() for i in range(4) for j in range(4)) < 1e-4
        for obj in scene.objects:
            role = obj.get('_basic_clothing_role')
            if role == 'DEPENDENCY':
                assert obj.hide_get(view_layer=scene.view_layers[0])
            elif role == side:
                got, expected = points(scene, obj), entry['expected'][side]
                assert max(abs(a[i] - b[i]) for a, b in zip(got, expected) for i in range(3)) < 1e-4
        preview.clear_preview(bpy.context)
print('CLOTHING_EXTERNAL_AND_NONNEUTRAL_REOPEN_OK')
