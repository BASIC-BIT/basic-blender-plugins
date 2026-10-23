"""Native IK checks. Run only with --background --factory-startup."""
from pathlib import Path
import importlib
import json
import sys
from collections import defaultdict
from math import radians, degrees
import bpy
from mathutils import Vector, Matrix, Quaternion

ROOT = Path(__file__).resolve().parents[1]
if '--installed-extension' not in sys.argv:
    sys.path.insert(0, str(ROOT))
PACKAGE = ('bl_ext.user_default.basics_shape_key_manager' if '--installed-extension' in sys.argv
           else 'BASICs_shape_key_manager')
native = importlib.import_module(PACKAGE + '.operators.clothing_checks.rig')
motion = importlib.import_module(PACKAGE + '.core.clothing_motion')
assert bpy.app.background, 'fixture must never run in an interactive user scene'


def fixture(name, roll=0, collinear=False, short_tails=False, backward_knees=False):
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bones = [('hips', (0, 0, 1), (0, 0, 1.1), None),
             ('spine', (0, 0, 1.1), (0, 0, 1.3), 'hips'),
             ('chest', (0, 0, 1.3), (0, 0, 1.5), 'spine'),
             ('head', (0, 0, 1.6), (0, 0, 1.8), 'chest')]
    bones.extend([('SecondaryA', (.1, 0, 1), (.1, 0, 1.1), 'hips'),
                  ('SecondaryB', (-.1, 0, 1), (-.1, 0, 1.1), 'hips')])
    for side, sign in [('left', 1), ('right', -1)]:
        elbow_y = 0 if collinear else -.06
        knee_y = 0 if collinear else (.04 if backward_knees else -.04)
        bones.extend([(side + '_upper_arm', (sign * .2, 0, 1.45), (sign * .5, elbow_y, 1.45), 'chest'),
                      (side + '_forearm', (sign * .5, elbow_y, 1.45), (sign * .8, 0, 1.45), side + '_upper_arm'),
                      (side + '_hand', (sign * .8, 0, 1.45), (sign * .9, 0, 1.45), side + '_forearm'),
                      (side + '_thigh', (sign * .1, 0, 1), (sign * .1, knee_y, .55), 'hips'),
                      (side + '_shin', (sign * .1, knee_y, .55), (sign * .1, 0, .1), side + '_thigh'),
                      (side + '_foot', (sign * .1, 0, .1), (sign * .1, .2, .1), side + '_shin')])
    for bone_name, head, tail, parent in bones:
        bone = data.edit_bones.new(bone_name)
        bone.head, bone.tail = head, tail
        bone.roll = radians(roll * (1 if bone_name.startswith('left') else -1))
        if parent:
            bone.parent = data.edit_bones[parent]
        if short_tails and any(k in bone_name for k in ('upper_arm', 'forearm', 'thigh', 'shin')):
            bone.tail = bone.head + (bone.tail - bone.head) * .65
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(False)
    return obj


def confirmed(obj):
    return {name: name for name in native.CANONICAL_BONES}


def skinned_probe(rig):
    bones = list(rig.data.bones)
    points = [b.matrix_local @ Vector((.013, .03, .017)) for b in bones]
    data = bpy.data.meshes.new('PoseReadbackProbe')
    data.from_pydata(points, [], [])
    obj = bpy.data.objects.new('PoseReadbackProbe', data)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = rig.matrix_world.copy()
    obj.modifiers.new('Rig', 'ARMATURE').object = rig
    for index, bone in enumerate(bones):
        obj.vertex_groups.new(name=bone.name).add([index], 1, 'REPLACE')
    return obj, bones


def assert_evaluated_pose(rig, probe, bones, result, scene, control_rig):
    depsgraph = scene.view_layers[0].depsgraph
    evaluated = rig.evaluated_get(depsgraph)
    mesh = probe.evaluated_get(depsgraph)
    for index, bone in enumerate(bones):
        reported = Matrix(result['matrices'][bone.name])
        actual = evaluated.pose.bones[bone.name].matrix
        assert max(abs(actual[i][j] - reported[i][j]) for i in range(4) for j in range(4)) < .00005, (result['case']['motion'], bone.name)
        expected = probe.matrix_world @ (reported @ bone.matrix_local.inverted() @ probe.data.vertices[index].co)
        observed = mesh.matrix_world @ mesh.data.vertices[index].co
        assert (expected - observed).length < .00005, (result['case']['motion'], bone.name, 'skinned probe')
    for canonical, target in result['targets'].items():
        matrix = rig.matrix_world @ evaluated.pose.bones[canonical].matrix
        position = (matrix.translation - Vector(target['position_m'])).length
        calibrated = matrix @ rig.data.bones[canonical].matrix_local.inverted() @ control_rig.data.bones[canonical].matrix_local
        orientation = degrees(calibrated.to_quaternion().rotation_difference(Quaternion(target['orientation_wxyz'])).angle)
        orientation = min(orientation, 360 - orientation)
        assert abs(position - result['residuals'][canonical]['position_m']) < .000001
        assert abs(orientation - result['residuals'][canonical]['orientation_degrees']) < .05, (result['case'], canonical, orientation, result['residuals'][canonical])
        if result['valid']:
            assert position <= .002 and orientation <= 2
    for chain, (a, b, c) in native.CHAINS.items():
        first = evaluated.pose.bones[b].head - evaluated.pose.bones[a].head
        second = evaluated.pose.bones[c].head - evaluated.pose.bones[b].head
        angle = degrees(first.angle(second))
        measured = next(j['degrees'] for j in result['joint_limits'] if j['bone'] == b and j['kind'] == 'flexion')
        assert abs(angle - measured) < .001


def run():
    summaries = []
    scene = bpy.context.scene
    original = fixture('Original', roll=37, short_tails=True)
    original_matrices = {p.name: tuple(tuple(r) for r in p.matrix) for p in original.pose.bones}
    obj = original.copy()
    obj.data = original.data.copy()
    scene.collection.objects.link(obj)
    mapping = native.resolve_mapping(obj, confirmed(obj))
    try:
        native.resolve_mapping(obj)
        raise AssertionError('unconfirmed aliases accepted')
    except ValueError as exc:
        assert 'confirm' in str(exc).lower()
    before = len(bpy.data.objects)
    worker = native.IKMotionRig(obj, mapping, scene)
    assert worker.calibration['axes']['forward'].y < -.99, 'anatomical frame must face negative Y for Left=+X, Right=-X'
    assert any(c.type == 'IK' for p in worker.control_rig.pose.bones for c in p.constraints)
    for p in worker.control_rig.pose.bones:
        assert p.ik_stretch == 0
    neutral = motion.seed_cases(['FULL_BODY'])[0]
    first = worker.apply(neutral)
    assert first['valid'], first['violations']
    for name, matrix in first['matrices'].items():
        rest = obj.data.bones[name].matrix_local
        assert max(abs(matrix[i][j] - rest[i][j]) for i in range(4) for j in range(4)) < .001, name
    assert first['plausibility'] == 'UNCERTAIN'
    probe, probe_bones = skinned_probe(obj)
    scene.view_layers[0].update()
    for motion_name in ('reach_overhead', 'knee_lift', 'ankle', 'neutral', 'reach_overhead'):
        sample = next(c for c in motion.seed_cases(['FULL_BODY']) if c['motion'] == motion_name and c['t'] == 1)
        checked = worker.apply(sample)
        assert_evaluated_pose(obj, probe, probe_bones, checked, scene, worker.control_rig)
    replay = checked
    worker.apply(next(c for c in motion.seed_cases(['FULL_BODY']) if c['motion'] == 'ankle' and c['t'] == 1))
    native.apply_pose_matrices(obj, replay['matrices'])
    scene.view_layers[0].update()
    assert_evaluated_pose(obj, probe, probe_bones, replay, scene, worker.control_rig)
    basis_before = {p.name: p.matrix_basis.copy() for p in obj.pose.bones}
    for invalid in ({}, dict(replay['matrices'], hips=[[0] * 4] * 4),
                    dict(replay['matrices'], hips=[[float('nan')] * 4] * 4)):
        try:
            native.apply_pose_matrices(obj, invalid)
            raise AssertionError('invalid saved pose accepted')
        except ValueError:
            pass
        assert all(p.matrix_basis == basis_before[p.name] for p in obj.pose.bones)
    # A displaced reachable wrist proves the native solver actually moves joints.
    shifted = dict(neutral, target_offsets_m={'left_hand': [0, .03, 0]})
    result = worker.apply(shifted)
    assert result['valid'], result['violations']
    assert result['matrices']['left_forearm'] != first['matrices']['left_forearm']
    for key, residual in result['residuals'].items():
        assert residual['position_m'] <= .002, (key, residual)
        assert residual['orientation_degrees'] <= 2, (key, residual)
    assert all(v['excess_degrees'] <= .5 for v in result['joint_limits'])
    assert {'left_thigh', 'right_thigh', 'left_hand', 'right_hand', 'left_foot', 'right_foot'} <= {v['bone'] for v in result['joint_limits']}
    assert {'shoulder_forward', 'shoulder_lateral', 'torso_forward', 'torso_lateral', 'torso_twist'} <= {v['kind'] for v in result['joint_limits']}
    impossible = worker.apply(dict(neutral, target_offsets_m={'left_hand': [10, 0, 0]}))
    assert not impossible['valid']
    assert any(v['kind'] == 'position_residual' for v in impossible['violations'])
    assert json.loads(json.dumps(first)) == first
    # A returned snapshot must survive later solves.
    assert first['matrices'] != impossible['matrices']
    repeated = worker.apply(neutral)
    for name, matrix in first['matrices'].items():
        assert max(abs(matrix[i][j] - repeated['matrices'][name][i][j])
                   for i in range(4) for j in range(4)) < 1e-5, name
    roll_case = next(c for c in motion.seed_cases(['FULL_BODY']) if c['motion'] == 'arm_roll' and c['t'] == 1)
    rolled = worker.apply(roll_case)
    assert rolled['targets']['left_hand']['orientation_wxyz'] != first['targets']['left_hand']['orientation_wxyz']
    accessory = next(c for c in motion.seed_cases(['FULL_BODY']) if c['family'] == 'accessory')
    obj['basic_clothing_accessory_bones'] = '[]'
    assert not worker.apply(accessory)['valid'], 'empty accessory selection counted as coverage'
    obj['basic_clothing_accessory_bones'] = json.dumps(['SecondaryA', 'SecondaryB'])
    flex = dict(motion.interpolate_case(accessory, .5), accessory_bones=['SecondaryA'], accessory_axis='Y')
    flexed = worker.apply(flex)
    assert flexed['metadata']['accessory_bones'] == ['SecondaryA']
    assert flexed['metadata']['accessory_axis'] == 'Y'
    assert flexed['metadata']['accessory_degrees'] == 20
    assert flexed['matrices']['SecondaryA'] != first['matrices']['SecondaryA']
    for i in range(4):
        for j in range(4):
            assert abs(flexed['matrices']['SecondaryB'][i][j] - first['matrices']['SecondaryB'][i][j]) < 1e-5
    for unsupported in (dict(flex, accessory_bones=['head']), dict(flex, accessory_axis='INVALID')):
        try:
            worker.apply(unsupported)
            raise AssertionError('unsupported per-case accessory calibration accepted')
        except ValueError:
            pass
    reach_case = next(c for c in motion.seed_cases(['FULL_BODY']) if c['motion'] == 'reach_forward' and c['t'] == 1)
    reach_result = worker.apply(reach_case)
    assert reach_result['valid'], reach_result['violations']
    assert reach_result['targets']['left_hand']['position_m'][1] < -.1
    lateral_case = next(c for c in motion.seed_cases(['FULL_BODY']) if c['motion'] == 'reach_lateral' and c['t'] == 1)
    lateral_result = worker.apply(lateral_case)
    assert lateral_result['valid'], lateral_result['violations']
    a, b = reach_result['targets']['left_hand']['position_m'], reach_result['targets']['right_hand']['position_m']
    assert abs(a[0] + b[0]) < .001 and abs(a[1] - b[1]) < .001 and abs(a[2] - b[2]) < .001
    for side in ('left', 'right'):
        for part, maximum in [('forearm', 145), ('shin', 135)]:
            pose = worker.control_rig.pose.bones[side + '_' + part]
            assert all(getattr(pose, 'ik_max_' + axis) <= radians(maximum) + 1e-6 for axis in 'xyz')
    worker.close()
    worker.close()
    bpy.data.objects.remove(probe, do_unlink=True)
    assert len(bpy.data.objects) == before
    assert {p.name: tuple(tuple(r) for r in p.matrix) for p in original.pose.bones} == original_matrices
    for bad in ('{"left_leg":[0,NaN,0]}', '{"left_leg":[0,0,0]}', '{"typo":[0,1,0]}'):
        obj['basic_clothing_bend_directions'] = bad
        try:
            native.IKMotionRig(obj, mapping, scene)
            raise AssertionError('invalid bend direction accepted')
        except ValueError:
            pass
    del obj['basic_clothing_bend_directions']
    backward = fixture('BackwardStandingKnees', 38, short_tails=True, backward_knees=True)
    with native.IKMotionRig(backward, confirmed(backward), scene) as worker:
        neutral_result = worker.apply(neutral)
        assert neutral_result['valid'], neutral_result['violations']
        for name, matrix in neutral_result['matrices'].items():
            rest = backward.data.bones[name].matrix_local
            assert max(abs(matrix[i][j] - rest[i][j]) for i in range(4) for j in range(4)) < .001
        squat = next(c for c in motion.seed_cases(['FULL_BODY']) if c['motion'] == 'squat' and c['t'] == 1)
        result = worker.apply(squat)
        assert not result['valid']
        assert any(v['kind'] == 'joint_limit' for v in result['violations'])
    for collinear, roll, scale in [(False, 0, (1, 1, 1)), (False, 71, (1.1, .9, 1.2)), (True, 52, (1, 1, 1))]:
        rig = fixture('Variant', roll, collinear, True)
        rig.scale = scale
        bpy.context.view_layer.update()
        if collinear:
            try:
                native.IKMotionRig(rig, confirmed(rig), scene)
                raise AssertionError('collinear bend direction guessed')
            except ValueError as exc:
                assert 'bend' in str(exc).lower()
            rig['basic_clothing_bend_directions'] = json.dumps({
                'left_arm': [0, -1, 0], 'right_arm': [0, -1, 0],
                'left_leg': [0, -1, 0], 'right_leg': [0, -1, 0]})
        with native.IKMotionRig(rig, confirmed(rig), scene) as worker:
            probe, probe_bones = skinned_probe(rig)
            for profile in ('HEAD_HANDS', 'FULL_BODY'):
                seed = motion.seed_cases([profile])
                baseline = worker.apply(seed[0])
                assert baseline['valid'], (scale, baseline['violations'])
                good, bad = 0, 0
                counts = defaultdict(lambda: {'valid': 0, 'invalid': 0})
                for case in seed:
                    result = worker.apply(case)
                    assert_evaluated_pose(rig, probe, probe_bones, result, scene, worker.control_rig)
                    assert result['validity'] in {'VALID', 'INVALID'}
                    assert result['metadata']['synthetic']
                    if result['valid']:
                        good += 1
                        counts[case['motion']]['valid'] += 1
                        assert max(r['position_m'] for r in result['residuals'].values()) <= .002
                        assert max(r['orientation_degrees'] for r in result['residuals'].values()) <= 2
                        assert all(j['excess_degrees'] <= .5 for j in result['joint_limits'])
                        for foot in ('left_foot', 'right_foot'):
                            if result['targets'][foot]['contact']:
                                assert result['targets'][foot]['position_m'] == baseline['targets'][foot]['position_m']
                                assert result['residuals'][foot]['foot_sliding_m'] <= .002
                    else:
                        bad += 1
                        counts[case['motion']]['invalid'] += 1
                        assert result['violations']
                print('PROFILE', profile, 'collinear', collinear, 'scale', scale, 'valid', good, 'invalid', bad)
                summaries.append({'profile': profile, 'collinear': collinear, 'rest_roll': roll,
                                  'object_scale': list(scale), 'valid': good, 'invalid': bad,
                                  'motions': dict(counts)})
            bpy.data.objects.remove(probe, do_unlink=True)
    print('CLOTHING_IK_OK')
    return summaries


if __name__ == '__main__':
    summary = run()
    if '--summary-json' in sys.argv:
        Path(sys.argv[sys.argv.index('--summary-json') + 1]).write_text(json.dumps(summary, indent=2))
