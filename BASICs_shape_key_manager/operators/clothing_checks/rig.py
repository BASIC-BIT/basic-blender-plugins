"""Native constrained synthetic IK on owned copies, with measured validity."""
import threading
from math import degrees, radians, isfinite, atan2, asin, acos, hypot, pi, sin, cos
import bpy
from mathutils import Matrix, Quaternion, Vector
from ...core.clothing_motion import motion_commands, interpolate_case
from .rig_mapping import CANONICAL_BONES, OPTIONAL_BONES, CHAINS, resolve_mapping, suggest_mapping, calibrate
from .rig_controls import NativeControls, pole_angle_frame


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Blender IK must run on the main thread')


def _rows(matrix):
    return [[float(value) for value in row] for row in matrix]


def _vector(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 3 or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in value):
        raise ValueError(f'{label} requires three finite numbers')
    return Vector(value)


def apply_pose_matrices(rig, matrices):
    """Apply complete armature-space poses without reading stale parent poses.

    The caller updates its owned view layer once after this operation.
    """
    _main_thread()
    if rig is None or rig.type != 'ARMATURE' or not isinstance(matrices, dict):
        raise ValueError('pose matrices require an armature and a dictionary')
    if set(matrices) != set(rig.pose.bones.keys()):
        raise ValueError('pose matrices must match every rig bone exactly')
    desired = {}
    for name, values in matrices.items():
        try:
            matrix = Matrix(values)
        except (TypeError, ValueError):
            raise ValueError(f'invalid pose matrix: {name}') from None
        if len(matrix) != 4 or any(len(row) != 4 or any(not isfinite(v) for v in row) for row in matrix):
            raise ValueError(f'pose matrix must be finite 4x4: {name}')
        if abs(matrix.determinant()) < 1e-12:
            raise ValueError(f'pose matrix must be invertible: {name}')
        desired[name] = matrix
    bases = {}
    for pose in rig.pose.bones:
        parent = ({'parent_matrix': desired[pose.parent.name],
                   'parent_matrix_local': pose.parent.bone.matrix_local} if pose.parent else {})
        bases[pose.name] = pose.bone.convert_local_to_pose(
            desired[pose.name], pose.bone.matrix_local, invert=True, **parent)
    for name, matrix in bases.items():
        rig.pose.bones[name].matrix_basis = matrix


class IKMotionRig:
    """Own controls only; the supplied evaluation armature must be a session copy."""
    def __init__(self, evaluation_rig, mapping, owner_scene, unit_scale=1.0):
        _main_thread()
        if not isinstance(unit_scale, (int, float)) or not isfinite(unit_scale) or unit_scale <= 0:
            raise ValueError('unit scale must be positive meters per Blender unit')
        if evaluation_rig.name not in owner_scene.objects:
            raise ValueError('evaluation rig must belong to the owned scene')
        self.mapping = resolve_mapping(evaluation_rig, mapping)
        if evaluation_rig.animation_data and (evaluation_rig.animation_data.action or evaluation_rig.animation_data.drivers):
            raise ValueError('evaluation rig action/drivers must be removed from the owned evaluation copy')
        if evaluation_rig.constraints or any(p.constraints for p in evaluation_rig.pose.bones):
            raise ValueError('source constraints are unsupported')
        if abs(evaluation_rig.matrix_world.determinant()) < 1e-12:
            raise ValueError('singular rig transform')
        self.rig, self.scene, self.scale = evaluation_rig, owner_scene, float(unit_scale)
        self.calibration = calibrate(evaluation_rig, self.mapping)
        self.original_basis = {p.name: p.matrix_basis.copy() for p in self.rig.pose.bones}
        self.controls = NativeControls(self.rig, self.mapping, owner_scene, self.calibration)
        self.control_rig = self.controls.rig
        self.rest = {p.name: p.bone.matrix_local.copy() for p in self.control_rig.pose.bones}
        self.accessory_names = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _authored_pose(self, command, case):
        for constraint in self.controls.constraints:
            constraint.mute = True
        for pose in self.control_rig.pose.bones:
            pose.matrix_basis = Matrix.Identity(4)
        rotations = {}
        elevations = {item['bone']: item['degrees'] for item in command['rotations']
                      if item['axis'] == 'elevation'}
        for item in command['rotations']:
            if item['axis'] == 'elevation' or item['bone'] in elevations and item['axis'] == 'bone':
                continue
            if item['bone'] in OPTIONAL_BONES and item['bone'] not in self.mapping:
                continue
            name = self.mapping[item['bone']]
            bone = self.control_rig.data.bones[name]
            if item['axis'] == 'bone':
                axis = bone.matrix_local.to_3x3().col[1]
            elif item['axis'] == 'bend':
                side = item['bone'].split('_')[0]
                chain = side + ('_arm' if item['bone'].endswith('forearm') else '_leg')
                axis = self.calibration['hinges'][chain]
            else:
                axis = self.calibration['axes'][item['axis']]
            local_axis = bone.matrix_local.to_quaternion().inverted() @ axis
            rotations[name] = rotations.get(name, Quaternion()) @ Quaternion(local_axis, radians(item['degrees']))
        for name, rotation in rotations.items():
            self.control_rig.pose.bones[name].rotation_mode = 'QUATERNION'
            self.control_rig.pose.bones[name].rotation_quaternion = rotation
        hips = self.control_rig.pose.bones[self.mapping['hips']]
        fraction = command['pelvis_height_fractions']
        offset = sum((self.calibration['axes'][axis] * f for axis, f in zip(
            ('right', 'forward', 'up'), fraction)), Vector()) * self.calibration['height']
        hips.location = hips.bone.matrix_local.to_quaternion().inverted() @ offset
        # Accessory selection is explicit, never inferred from names.
        selected = self.rig.get('basic_clothing_accessory_bones', '[]')
        import json
        try:
            selected = json.loads(selected)
        except (TypeError, ValueError):
            raise ValueError('invalid accessory-bone selection JSON') from None
        if not isinstance(selected, list) or any(name not in self.control_rig.pose.bones for name in selected):
            raise ValueError('accessory selection contains missing bones')
        if 'accessory_bones' in case:
            subset = case['accessory_bones']
            if case['family'] != 'accessory' or not isinstance(subset, list) or any(
                    not isinstance(name, str) or name not in selected for name in subset):
                raise ValueError('per-case accessory bones must be an explicitly allowed subset')
            selected = list(dict.fromkeys(subset))
        axis = case.get('accessory_axis', 'X')
        if axis not in {'X', 'Y', 'Z'}:
            raise ValueError('accessory axis must be X, Y or Z')
        for name in selected:
            if name in self.mapping.values():
                raise ValueError('accessory selection cannot contain mapped humanoid bones')
            pose = self.control_rig.pose.bones[name]
            pose.rotation_mode = 'QUATERNION'
            pose.rotation_quaternion = Quaternion(Vector([int(axis == a) for a in 'XYZ']), radians(command['accessory_degrees']))
        self.accessory_names = selected
        self.accessory_axis = axis
        if elevations:
            self._apply_elevations(elevations, command)
        return self.controls.update()

    def _apply_elevations(self, elevations, command):
        """Aim relative to the torso, independently of the source T/A rest pose."""
        evaluated = self.controls.update()
        chest = evaluated.pose.bones[self.mapping['chest']]
        torso = (chest.matrix @ chest.bone.matrix_local.inverted()).to_quaternion()
        axes = self.calibration['axes']
        bases = {}
        for canonical, elevation in elevations.items():
            name = self.mapping[canonical]
            pose = evaluated.pose.bones[name]
            bone = self.control_rig.data.bones[name]
            outward = axes['right'] * (-1 if canonical.startswith('left_') else 1)
            target = -axes['up'] * cos(radians(elevation)) + outward * sin(radians(elevation))
            for rotation in command['rotations']:
                if rotation['bone'] == canonical and rotation['axis'] in axes:
                    target = Quaternion(axes[rotation['axis']], radians(rotation['degrees'])) @ target
            rest_axis = bone.matrix_local.to_3x3().col[1].normalized()
            orientation = torso @ rest_axis.rotation_difference(target) @ bone.matrix_local.to_quaternion()
            twist = sum(r['degrees'] for r in command['rotations']
                        if r['bone'] == canonical and r['axis'] == 'bone')
            orientation = orientation @ Quaternion((0, 1, 0), radians(twist))
            desired = Matrix.LocRotScale(pose.head, orientation, pose.matrix.to_scale())
            bases[name] = bone.convert_local_to_pose(desired, bone.matrix_local, invert=True,
                parent_matrix=pose.parent.matrix, parent_matrix_local=bone.parent.matrix_local)
        for name, basis in bases.items():
            self.control_rig.pose.bones[name].matrix_basis = basis

    def apply(self, case):
        _main_thread()
        if self.closed:
            raise RuntimeError('IK rig is closed')
        case = interpolate_case(case, case['t'])
        command = motion_commands(case)
        authored = self._authored_pose(command, case)
        world = self.control_rig.matrix_world.copy()
        # Freeze FK target tracks before enabling native constraints.
        target_matrices = {canonical: world @ authored.pose.bones[self.mapping[canonical]].matrix
                           for canonical in ('head', 'hips', 'left_hand', 'right_hand', 'left_foot', 'right_foot')}
        root_matrices, joint_heads = {}, {}
        for chain, (a, b, c) in CHAINS.items():
            root = authored.pose.bones[self.mapping[a]].head.copy()
            joint = authored.pose.bones[self.mapping[b]].head.copy()
            root_matrices[chain] = authored.pose.bones[self.mapping[a]].matrix.copy()
            joint_heads[chain] = joint.copy()
        for canonical, target in self.controls.targets.items():
            matrix = target_matrices[canonical]
            if command['contacts'].get(canonical):
                # Fixed standing contact, independent of evaluation order.
                rest = world @ self.rest[self.mapping[canonical]]
                matrix.translation = rest.translation
                # Contact fixes the ankle position; preserve authored foot orientation.
            offsets = case.get('target_offsets_m', {})
            if not isinstance(offsets, dict) or any(k not in self.controls.targets for k in offsets):
                raise ValueError('target offsets must name mapped hands/feet')
            if canonical in offsets:
                matrix.translation += _vector(offsets[canonical], 'target offset') / self.scale
            target.matrix_world = matrix
            target_matrices[canonical] = matrix.copy()
        inverse_world = world.inverted()
        for chain, pole in self.controls.poles.items():
            root_matrix = root_matrices[chain]
            root = root_matrix.translation
            end = inverse_world @ target_matrices[CHAINS[chain][2]].translation
            axis = (end - root).normalized()
            bend = joint_heads[chain] - root
            bend -= axis * bend.dot(axis)
            if bend.length < 1e-6:
                bend = self.calibration['poles'][chain].copy()
            pole_point = root + bend.normalized() * self.calibration['height']
            pole.location = world @ pole_point
            self.controls.iks[chain].pole_angle = pole_angle_frame(root_matrix, end, pole_point)
        for constraint in self.controls.constraints:
            constraint.mute = False
        solved = self.controls.update()
        desired = {}
        for pose in self.rig.pose.bones:
            ctrl = solved.pose.bones[pose.name]
            desired[pose.name] = ctrl.matrix @ self.rest[pose.name].inverted() @ pose.bone.matrix_local
        apply_pose_matrices(self.rig, desired)
        self.scene.view_layers[0].update()
        evaluated = self.rig.evaluated_get(self.scene.view_layers[0].depsgraph)
        matrices = {pose.name: pose.matrix.copy() for pose in evaluated.pose.bones}
        residuals, violations, targets = {}, [], {}
        if case['family'] == 'shoulder':
            required = {name for name in OPTIONAL_BONES if not case.get('controls') or name in case['controls']}
            for name in required:
                if name not in self.mapping:
                    violations.append({'kind': 'missing_shoulder_mapping', 'bone': name})
        application_error = max(abs(matrix[i][j] - desired[name][i][j])
                                for name, matrix in matrices.items() for i in range(4) for j in range(4))
        if application_error > .00005:
            violations.append({'kind': 'pose_retarget_mismatch', 'matrix_max_error': application_error,
                               'limit': .00005})
        for canonical, target in target_matrices.items():
            name = self.mapping[canonical]
            actual = evaluated.matrix_world @ matrices[name]
            # Control/deform rest offsets differ for nonconnected tails and rolls.
            calibrated_actual = actual @ self.rig.data.bones[name].matrix_local.inverted() @ self.rest[name]
            position_error = (actual.translation - target.translation).length * self.scale
            orientation_error = degrees(calibrated_actual.to_quaternion().rotation_difference(target.to_quaternion()).angle)
            orientation_error = min(orientation_error, 360 - orientation_error)
            contact = bool(command['contacts'].get(canonical))
            residuals[canonical] = {'position_m': position_error, 'orientation_degrees': orientation_error,
                                    'foot_sliding_m': position_error if contact else None}
            targets[canonical] = {'position_m': list(target.translation * self.scale),
                                  'orientation_wxyz': list(target.to_quaternion()), 'contact': contact,
                                  'orientation_frame_offset': _rows(self.rig.data.bones[name].matrix_local.inverted() @ self.rest[name])}
            if position_error > .002:
                violations.append({'kind': 'position_residual', 'bone': canonical, 'value_m': position_error, 'limit_m': .002})
            if orientation_error > 2:
                violations.append({'kind': 'orientation_residual', 'bone': canonical, 'value_degrees': orientation_error, 'limit_degrees': 2})
        joint_limits = self._joint_checks(evaluated, violations)
        if case['family'] == 'accessory' and not self.accessory_names:
            violations.append({'kind': 'unsupported_accessory_selection', 'reason': 'no explicit accessory bones selected'})
        metadata = dict(command['metadata'], unit_scale=self.scale,
                        object_matrix_world=_rows(world), matrix_space='ARMATURE',
                        matrix_source='evaluated deform rig after parent-aware local-basis application',
                        pose_application_matrix_max_error=application_error,
                        target_offsets='mapped joint heads; foot contact is ankle-head position, not sole geometry',
                        shoulder_limits='elevation weighted by forward/lateral azimuth in the calibrated torso frame',
                        stretch_tolerance='max(0.00001 m, segment length m * 0.0001); native stretch disabled',
                        joint_segment_source='mapped joint heads; deform rest-frame delta retarget',
                        bend_directions={k: list(v) for k, v in self.calibration['poles'].items()},
                        avatar_axes={k: list(v) for k, v in self.calibration['axes'].items()},
                        accessory_bones=list(self.accessory_names),
                        accessory_axis=self.accessory_axis,
                        accessory_degrees=command['accessory_degrees'],
                        unmapped_bones=[p.name for p in self.rig.pose.bones if p.name not in self.mapping.values()],
                        shoulder_mapping={k: self.mapping[k] for k in OPTIONAL_BONES if k in self.mapping},
                        plausibility_reason='body self-crossing screen required by geometry adapter')
        return {'case': case, 'matrices': {name: _rows(matrix) for name, matrix in matrices.items()},
                'targets': targets, 'residuals': residuals, 'joint_limits': joint_limits,
                'violations': violations, 'valid': not violations,
                'validity': 'INVALID' if violations else 'VALID', 'plausibility': 'UNCERTAIN',
                'metadata': metadata}

    def _joint_checks(self, solved, violations):
        result = []
        def check(bone, kind, angle, minimum, maximum):
            excess = max(0, minimum - angle, angle - maximum)
            item = {'bone': bone, 'kind': kind, 'degrees': angle,
                    'minimum_degrees': minimum, 'maximum_degrees': maximum,
                    'excess_degrees': excess}
            result.append(item)
            if excess > .5:
                violations.append(dict(item, kind='joint_limit', measured_kind=kind))

        deltas = {}
        for canonical, name in self.mapping.items():
            pose = solved.pose.bones[name]
            parent_delta = (pose.parent.matrix @ pose.parent.bone.matrix_local.inverted()
                            if pose.parent else Matrix.Identity(4))
            delta = parent_delta.inverted() @ pose.matrix @ pose.bone.matrix_local.inverted()
            deltas[canonical] = delta.to_quaternion()
        axes = self.calibration['axes']
        chest = solved.pose.bones[self.mapping['chest']]
        torso = (chest.matrix @ chest.bone.matrix_local.inverted()).to_quaternion()
        up = torso @ axes['up']
        check('chest', 'torso_forward', degrees(atan2(up.dot(axes['forward']), up.dot(axes['up']))), -15, 50)
        check('chest', 'torso_lateral', degrees(atan2(up.dot(axes['right']), up.dot(axes['up']))), -20, 20)
        basis = Matrix((axes['right'], axes['forward'], axes['up'])).transposed().to_quaternion()
        _, twist = (basis.inverted() @ torso @ basis).to_swing_twist('Z')
        check('chest', 'torso_twist', degrees(twist), -45, 45)
        for chain, (a, b, c) in CHAINS.items():
            first = solved.pose.bones[self.mapping[b]].head - solved.pose.bones[self.mapping[a]].head
            second = solved.pose.bones[self.mapping[c]].head - solved.pose.bones[self.mapping[b]].head
            angle = degrees(first.angle(second))
            maximum = 145 if chain.endswith('arm') else 135
            check(b, 'flexion', angle, 0, maximum)
            distal_delta = min(degrees(deltas[c].angle), 360 - degrees(deltas[c].angle))
            check(c, 'rest_frame_rotation', distal_delta, 0, 60 if chain.endswith('arm') else 25)
            if chain.endswith('leg'):
                rest_axis = self.control_rig.data.bones[self.mapping[a]].matrix_local.to_3x3().col[1].normalized()
                moved = deltas[a] @ rest_axis
                flex = atan2(moved.dot(axes['forward']), -moved.dot(axes['up']))
                rest_flex = atan2(rest_axis.dot(axes['forward']), -rest_axis.dot(axes['up']))
                flex = degrees((flex - rest_flex + pi) % (2 * pi) - pi)
                abduction = degrees(asin(max(-1, min(1, moved.dot(axes['right'])))) -
                                    asin(max(-1, min(1, rest_axis.dot(axes['right'])))))
                check(a, 'hip_flexion', flex, -20, 110)
                check(a, 'hip_abduction', abduction, -35, 35)
            else:
                swing = min(degrees(deltas[a].angle), 360 - degrees(deltas[a].angle))
                check(a, 'shoulder_rest_frame_rotation', swing, 0, 150)
                rest_axis = self.control_rig.data.bones[self.mapping[a]].matrix_local.to_3x3().col[1].normalized()
                moved = deltas[a] @ rest_axis
                forward, side = moved.dot(axes['forward']), moved.dot(axes['right'])
                elevation = degrees(acos(max(-1, min(1, -moved.dot(axes['up'])))))
                horizontal = hypot(forward, side)
                sagittal = elevation * forward / horizontal if horizontal > 1e-6 else elevation
                lateral = elevation * abs(side) / horizontal if horizontal > 1e-6 else 0
                check(a, 'shoulder_forward', sagittal, -35, 170)
                check(a, 'shoulder_lateral', lateral, 0, 170)
                local = self.control_rig.data.bones[self.mapping[b]].matrix_local.to_quaternion()
                local_delta = local.inverted() @ deltas[b] @ local
                _, twist = local_delta.to_swing_twist('Y')
                check(b, 'forearm_roll', degrees(twist), -75, 75)
            for canonical in (a, b):
                pose = solved.pose.bones[self.mapping[canonical]]
                stretch = abs(pose.length - pose.bone.length) * self.scale
                tolerance = max(.00001, pose.bone.length * self.scale * .0001)
                if stretch > tolerance:
                    violations.append({'kind': 'chain_stretch', 'bone': canonical, 'value_m': stretch, 'limit_m': tolerance})
            for parent, child in ((a, b), (b, c)):
                p, q = (solved.pose.bones[self.mapping[key]] for key in (parent, child))
                rest_length = (q.bone.head_local - p.bone.head_local).length * self.scale
                stretch = abs((q.head - p.head).length * self.scale - rest_length)
                tolerance = max(.00001, rest_length * .0001)
                if stretch > tolerance:
                    violations.append({'kind': 'joint_segment_stretch', 'bone': parent,
                                       'value_m': stretch, 'limit_m': tolerance})
        return result

    def close(self):
        _main_thread()
        if self.closed:
            return
        self.controls.close()
        for name, matrix in self.original_basis.items():
            self.rig.pose.bones[name].matrix_basis = matrix
        self.scene.view_layers[0].update()
        self.closed = True
