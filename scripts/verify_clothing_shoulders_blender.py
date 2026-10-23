"""Shoulder coverage must move evaluated clavicles and actual skinned probes."""
from pathlib import Path
import importlib.util
import importlib
import sys
from math import radians, degrees, acos
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
if '--installed-extension' not in sys.argv:
    sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('shoulder_fixture', ROOT / 'scripts/verify_clothing_ik_blender.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
assert bpy.app.background


def run():
    scene = bpy.context.scene
    rig = fixture.fixture('ShoulderFixture', roll=37, short_tails=True)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for side in ('left', 'right'):
        arm = rig.data.edit_bones[side + '_upper_arm']
        shoulder = rig.data.edit_bones.new(side + '_shoulder')
        shoulder.head = (0, 0, 1.45)
        shoulder.tail = arm.head
        shoulder.parent = rig.data.edit_bones['chest']
        arm.parent = shoulder
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.select_set(False)
    mapping = fixture.confirmed(rig)
    mapping.update({side + '_shoulder': side + '_shoulder' for side in ('left', 'right')})
    resolved = fixture.native.resolve_mapping(rig, mapping)
    assert resolved == mapping, 'explicit shoulder mappings were discarded'
    suggestions = fixture.native.suggest_mapping(rig)
    assert suggestions['left_shoulder'] == 'left_shoulder'
    try:
        fixture.native.resolve_mapping(rig, dict(mapping, left_shoulder='right_shoulder'))
        raise AssertionError('contralateral shoulder accepted')
    except ValueError:
        pass
    source = {p.name: p.matrix_basis.copy() for p in rig.pose.bones}
    probe, bones = fixture.skinned_probe(rig)
    cases = [c for c in fixture.motion.seed_cases(['FULL_BODY'], budget=10000, steps=9)
             if c['family'] == 'shoulder' and not c.get('controls')]
    with fixture.native.IKMotionRig(rig, mapping, scene) as worker:
        poses = {}
        for case in cases:
            result = worker.apply(case)
            assert result['valid'], (case['id'], result['violations'])
            fixture.assert_evaluated_pose(rig, probe, bones, result, scene, worker.control_rig)
            poses[case['id']] = result
        end = poses['FULL_BODY:arm_side_sweep:current:1']
        start = poses['FULL_BODY:arm_side_sweep:current:0']
        for side in ('left', 'right'):
            a = Matrix(start['matrices'][side + '_hand']).translation
            b = Matrix(end['matrices'][side + '_hand']).translation
            assert b.z - a.z > .6, 'sweep must pass through a large elevation range'
            rest = rig.data.bones[side + '_shoulder'].matrix_local
            posed = Matrix(end['matrices'][side + '_shoulder'])
            assert rest.to_quaternion().rotation_difference(posed.to_quaternion()).angle > .1
        worker.apply(next(c for c in fixture.motion.seed_cases(['FULL_BODY']) if c['motion'] == 'neutral'))
        for side in ('left', 'right'):
            pose = rig.evaluated_get(scene.view_layers[0].depsgraph).pose.bones[side + '_shoulder']
            assert pose.matrix.translation.z < Matrix(end['matrices'][side + '_upper_arm']).translation.z
    assert all(p.matrix_basis == source[p.name] for p in rig.pose.bones)
    # An A-pose rig must reach the same anatomical elevations as a T-pose rig.
    angled = fixture.fixture('AngledRestFixture', roll=29, short_tails=True)
    bpy.context.view_layer.objects.active = angled
    angled.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for side, sign in (('left', 1), ('right', -1)):
        root = angled.data.edit_bones[side + '_upper_arm'].head.copy()
        rotation = Matrix.Rotation(radians(45 * sign), 3, 'Y')
        for part in ('upper_arm', 'forearm', 'hand'):
            bone = angled.data.edit_bones[side + '_' + part]
            bone.head = root + rotation @ (bone.head - root)
            bone.tail = root + rotation @ (bone.tail - root)
    bpy.ops.object.mode_set(mode='OBJECT')
    angled.select_set(False)
    with fixture.native.IKMotionRig(angled, fixture.confirmed(angled), scene) as worker:
        for t, desired in ((0, 15), (1, 150)):
            case = next(c for c in cases if c['motion'] == 'arm_side_sweep' and c['t'] == t)
            result = worker.apply(case)
            a = Matrix(result['matrices']['left_upper_arm']).translation
            b = Matrix(result['matrices']['left_forearm']).translation
            measured = degrees(acos(max(-1, min(1, -(b - a).normalized().z))))
            assert abs(measured - desired) < .1, (t, measured, desired)
    with fixture.native.IKMotionRig(rig, fixture.confirmed(rig), scene) as worker:
        result = worker.apply(cases[-1])
        assert not result['valid'], 'unmapped shoulders must not count as tested coverage'
        assert any(v['kind'] == 'missing_shoulder_mapping' for v in result['violations'])
    # A down-to-up sweep starts arms-down, not at the neutral reference pose.
    session = importlib.import_module(fixture.PACKAGE + '.operators.clothing_checks.session')
    def mesh(name):
        data = bpy.data.meshes.new(name)
        data.from_pydata([(0, 0, 1), (.1, 0, 1), (0, .1, 1)], [], [(0, 1, 2)])
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.modifiers.new('Rig', 'ARMATURE').object = rig
        obj.vertex_groups.new(name='hips').add([0, 1, 2], 1, 'REPLACE')
        return obj
    body, before, after = [mesh(name) for name in ('Body', 'Before', 'After')]
    case = next(c for c in cases if c['motion'] == 'arm_side_sweep' and c['t'] == 0)
    worker = session.ValidationSession(bpy.context, body, rig,
        [{'reference': before, 'candidate': after, 'confirmed': True}], mapping,
        {'profiles': ['FULL_BODY'], 'families': ['shoulder'], 'cases': [case], 'budget': 1,
         'motion_library_version': fixture.motion.LIBRARY_VERSION})
    applied = []
    original = worker.motion.apply
    def apply(case):
        applied.append(case['motion'])
        return original(case)
    worker.motion.apply = apply
    try:
        worker.step()
        assert 'neutral' in applied, 'sweep start was incorrectly treated as neutral'
    finally:
        worker.cancel()
    sampling = importlib.import_module(fixture.PACKAGE + '.operators.clothing_checks.sampling')
    try:
        sampling.prepare({'cases': [case], 'replay_coverage': {}})
        raise AssertionError('unversioned legacy replay accepted')
    except ValueError as exc:
        assert 'legacy' in str(exc)
    try:
        sampling.prepare({'cases': [case]})
        raise AssertionError('versionless saved cases accepted without coverage')
    except ValueError as exc:
        assert 'version' in str(exc)
    addon = importlib.import_module(fixture.PACKAGE)
    addon.register()
    prop = bpy.context.scene.clothing_checks.bl_rna.properties['families']
    assert {item.identifier: item.value for item in prop.enum_items} == {
        'neutral': 1, 'reach': 2, 'arm': 4, 'torso': 8, 'lower_body': 16,
        'coordination': 32, 'accessory': 64, 'shoulder': 128}
    verify_independent_controls(rig, mapping, angled, scene)
    verify_pose_induced_crossing(rig, mapping, scene)
    print('CLOTHING_SHOULDERS_OK', len(cases))


def verify_independent_controls(rig, mapping, angled, scene):
    neutral = fixture.motion.seed_cases(['FULL_BODY'])[0]
    for target, target_mapping in ((rig, mapping), (angled, fixture.confirmed(angled))):
        target.matrix_world = Matrix.Translation((.2, -.3, .1)) @ Matrix.Rotation(.31, 4, 'Z')
        probe, bones = fixture.skinned_probe(target)
        with fixture.native.IKMotionRig(target, target_mapping, scene) as worker:
            original = worker.apply(neutral)
            case = dict(neutral, controls={'left_upper_arm': {'elevation': 120, 'bone': 25},
                                          'left_forearm': {'bend': 65, 'bone': 35}})
            moved = worker.apply(dict(case, t=1))
            fixture.assert_evaluated_pose(target, probe, bones, moved, scene, worker.control_rig)
            assert moved['matrices']['left_hand'] != original['matrices']['left_hand']
            for bone in ('right_upper_arm', 'right_forearm', 'right_hand'):
                assert max(abs(moved['matrices'][bone][i][j] - original['matrices'][bone][i][j])
                           for i in range(4) for j in range(4)) < .0001, bone
            assert moved['case']['controls'] == case['controls']
            across = worker.apply(dict(neutral, t=1, controls={
                'left_upper_arm': {'elevation': 120, 'bone': 25, 'up': -35},
                'left_forearm': {'bend': 65, 'bone': 35}}))
            assert across['matrices']['left_hand'] != moved['matrices']['left_hand'], 'elevation discarded azimuth control'
            for bone, axis, angle in (('left_upper_arm', 'elevation', 120),
                                      ('left_upper_arm', 'bone', 25),
                                      ('left_forearm', 'bend', 65), ('left_forearm', 'bone', 35),
                                      ('left_shoulder', 'forward', 12), ('left_shoulder', 'up', -12)):
                if bone not in target_mapping:
                    continue
                controlled = worker.apply(dict(neutral, t=1, controls={bone: {axis: angle}}))
                fixture.assert_evaluated_pose(target, probe, bones, controlled, scene, worker.control_rig)
                assert max(abs(controlled['matrices'][bone][i][j] - original['matrices'][bone][i][j])
                           for i in range(4) for j in range(4)) > .01, (bone, axis, 'control lost')
            heel = worker.apply(dict(neutral, t=1, controls={'left_foot': {'right': 20}}))
            assert heel['valid'], heel['violations']
            fixture.assert_evaluated_pose(target, probe, bones, heel, scene, worker.control_rig)
            assert heel['matrices']['left_foot'] != original['matrices']['left_foot'], 'foot orientation discarded by contact'
            assert heel['targets']['left_foot']['position_m'] == original['targets']['left_foot']['position_m']
            assert heel['targets']['left_foot']['orientation_wxyz'] != original['targets']['left_foot']['orientation_wxyz']


def verify_pose_induced_crossing(rig, mapping, scene):
    geometry = importlib.import_module(fixture.PACKAGE + '.operators.clothing_checks.geometry')
    neutral = fixture.motion.seed_cases(['FULL_BODY'])[0]
    case = dict(neutral, t=1, controls={'left_upper_arm': {'elevation': 150},
                                      'left_forearm': {'bend': 25}})
    def mesh(name, points, bone):
        data = bpy.data.meshes.new(name)
        data.from_pydata(points, [], [(0, 1, 2)])
        data.update()
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.matrix_world = rig.matrix_world.copy()
        obj['_basic_clothing_id'] = name
        obj.modifiers.new('Rig', 'ARMATURE').object = rig
        obj.vertex_groups.new(name=bone).add([0, 1, 2], 1, 'REPLACE')
        return obj
    with fixture.native.IKMotionRig(rig, mapping, scene) as worker:
        posed = worker.apply(case)
        inverse = rig.data.bones['left_upper_arm'].matrix_local @ Matrix(posed['matrices']['left_upper_arm']).inverted()
        body = mesh('ArmpitBody', [(.32, -.08, 1.50), (.32, .08, 1.50), (.32, 0, 1.72)], 'chest')
        shirt = mesh('ArmpitGarment', [inverse @ Vector(p) for p in
                     ((.27, -.04, 1.58), (.37, -.04, 1.58), (.32, .04, 1.66))], 'left_upper_arm')
        original = [tuple(v.co) for v in shirt.data.vertices]
        def findings():
            scene.view_layers[0].update()
            depsgraph = scene.view_layers[0].depsgraph
            return geometry.analyze_pair(geometry.snapshot_mesh(body, depsgraph),
                                         geometry.snapshot_mesh(shirt, depsgraph))
        worker.apply(neutral)
        rest = findings()
        assert not any(rest['crossing_faces'].values()), rest
        worker.apply(case)
        raised = findings()
        assert raised['absolute_fit'] == 'CLIPPING', raised
        assert raised['crossing_faces'] == {'ArmpitBody': [0], 'ArmpitGarment': [0]}, raised
        worker.apply(neutral)
        fixture.native.apply_pose_matrices(rig, posed['matrices'])
        replay = findings()
        assert replay['crossing_faces'] == raised['crossing_faces'], replay
        assert [tuple(v.co) for v in shirt.data.vertices] == original
        print('ARMPIT_POSE_CROSSING_OK neutral=0 raised=1 replay=1')


if __name__ == '__main__':
    run()
