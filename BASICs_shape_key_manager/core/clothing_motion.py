"""Versioned synthetic trajectories and bounded deterministic sampling, no Blender."""
from copy import deepcopy
from hashlib import sha256
import json
from math import isfinite, sin, pi, sqrt
from itertools import product

LIBRARY_VERSION = 'synthetic-native-4-independent-coverage'
PROFILES = ('HEAD_HANDS', 'FULL_BODY')
# Rotations use calibrated avatar axes, never assumed bone-local Euler axes.
# (canonical bone, axis, degrees). Values are conservative test choices.
MOTIONS = {
    'neutral': ('neutral', [('chest', 'right', 0)]),
    'reach_forward': ('reach', [('upper_arm', 'up', -70), ('forearm', 'bend', 35), ('chest', 'right', -8)]),
    'reach_overhead': ('reach', [('upper_arm', 'elevation', 135, 15), ('forearm', 'bend', 25)]),
    'reach_lateral': ('reach', [('upper_arm', 'elevation', 75, 15), ('forearm', 'bend', 20)]),
    'reach_across': ('reach', [('upper_arm', 'up', -105), ('forearm', 'bend', 65), ('chest', 'up', -15)]),
    'hand_head': ('reach', [('upper_arm', 'forward', 30), ('forearm', 'bend', 110)]),
    'hand_waist': ('reach', [('upper_arm', 'forward', -30), ('forearm', 'bend', 75)]),
    'arm_roll': ('arm', [('upper_arm', 'up', -55), ('forearm', 'bend', 70), ('forearm', 'bone', 60), ('hand', 'right', -35)]),
    'torso_bend': ('torso', [('hips', 'right', -10), ('spine', 'right', -20), ('chest', 'right', -20), ('forearm', 'bend', 40)]),
    'torso_extend': ('torso', [('spine', 'right', 7), ('chest', 'right', 8), ('forearm', 'bend', 30)]),
    'torso_lean': ('torso', [('spine', 'forward', -10), ('chest', 'forward', -10), ('forearm', 'bend', 35)]),
    'turn_reach': ('coordination', [('spine', 'up', -20), ('chest', 'up', -25), ('upper_arm', 'up', -65), ('forearm', 'bend', 40)]),
    'squat': ('lower_body', [('thigh', 'right', 55), ('shin', 'bend', 95), ('foot', 'right', 20), ('chest', 'right', -15), ('forearm', 'bend', 60)]),
    'sit': ('lower_body', [('thigh', 'right', 85), ('shin', 'bend', 90), ('chest', 'right', -8), ('forearm', 'bend', 75)]),
    'step': ('coordination', [('left_thigh', 'right', 30), ('left_shin', 'bend', 45), ('right_upper_arm', 'up', 40), ('left_forearm', 'bend', 30)]),
    'lunge': ('lower_body', [('left_thigh', 'right', 50), ('left_shin', 'bend', 80), ('right_thigh', 'right', -15), ('chest', 'right', -10)]),
    'knee_lift': ('lower_body', [('left_thigh', 'right', 85), ('left_shin', 'bend', 100), ('right_forearm', 'bend', 40)]),
    'ankle': ('lower_body', [('left_foot', 'right', -25), ('left_shin', 'bend', 20), ('left_thigh', 'right', 15)]),
    'accessory_flex': ('accessory', [('chest', 'right', 0)]),
}
# A fourth rotation field is its starting angle, allowing an entire down-to-up
# sweep instead of repeatedly sampling the rest-to-raised interval.
for _name, _elbow, _twist, _torso in (
        ('arm_side_sweep', 10, 0, 0), ('arm_side_bent', 85, 0, 0),
        ('arm_side_twist_in', 35, -40, 0), ('arm_side_twist_out', 35, 40, 0),
        ('arm_side_lean', 35, 0, 15), ('arm_side_turn', 35, 30, 0)):
    MOTIONS[_name] = ('shoulder', [
        ('shoulder', 'forward', 15), ('upper_arm', 'elevation', 135, 15),
        ('forearm', 'bend', _elbow), ('upper_arm', 'bone', 0, _twist),
        ('chest', 'right', _torso),
        ('chest', 'up', 20 if _name == 'arm_side_turn' else 0)])
MOTIONS['shoulder_shrug'] = ('shoulder', [('shoulder', 'forward', 25),
    ('upper_arm', 'elevation', 0, 25), ('forearm', 'bend', 20)])
MOTIONS['shoulder_protract'] = ('shoulder', [('shoulder', 'up', -20),
    ('upper_arm', 'up', -65), ('forearm', 'bend', 30)])
for _motion in ('step', 'lunge', 'knee_lift', 'ankle'):
    _family, _rotations = MOTIONS[_motion]
    MOTIONS[_motion + '_right'] = (_family, [
        (('right_' + name[5:]) if name.startswith('left_') else
         ('left_' + name[6:]) if name.startswith('right_') else name,
         axis, -angle if axis in {'up', 'forward'} else angle)
        for name, axis, angle in _rotations])

# Each asymmetric path has its own native FK targets, not a mirrored arm pair.
for _side, _other in (('left', 'right'), ('right', 'left')):
    _sign = 1 if _side == 'left' else -1
    for _name, _arm, _elbow in (('overhead_across', 140, 75),
                               ('behind_back', 30, 100), ('opposite_hip', 35, 35)):
        MOTIONS[_name + '_' + _side] = ('coordination', [
            (_side + '_upper_arm', 'elevation', _arm),
            (_side + '_upper_arm', 'up', _sign * (35 if _name == 'behind_back' else
                                                -135 if _name == 'opposite_hip' else 0)),
            (_side + '_forearm', 'bend', 25),
            (_other + '_upper_arm', 'up', _sign * -1 * (30 if _name == 'behind_back' else -105)),
            (_other + '_forearm', 'bend', _elbow)])
MOTIONS.update({
    'independent_arm': ('shoulder', [('chest', 'right', 0)]),
    'crouch_reach': ('coordination', [('thigh', 'right', 55), ('shin', 'bend', 95),
        ('chest', 'right', -15), ('left_upper_arm', 'up', -70), ('left_forearm', 'bend', 25)]),
    'seated_twist': ('coordination', [('thigh', 'right', 85), ('shin', 'bend', 90),
        ('chest', 'up', -25), ('right_upper_arm', 'up', -65)]),
    'kneel': ('lower_body', [('left_thigh', 'right', 30), ('left_shin', 'bend', 130),
        ('right_thigh', 'right', 65), ('right_shin', 'bend', 95)]),
    'crossed_legs': ('lower_body', [('left_thigh', 'forward', -15),
        ('right_thigh', 'forward', 15), ('thigh', 'right', 70), ('shin', 'bend', 95)]),
    'heel_roll': ('lower_body', [('foot', 'right', -20), ('shin', 'bend', 15)]),
    'toe_roll': ('lower_body', [('foot', 'right', 25), ('shin', 'bend', 15)]),
    'dance_loop': ('coordination', [('chest', 'up', 20), ('left_upper_arm', 'up', -45),
        ('right_upper_arm', 'up', 25), ('forearm', 'bend', 45)]),
    'rapid_turn': ('coordination', [('hips', 'up', 45), ('chest', 'up', 25), ('forearm', 'bend', 60)]),
    'stop': ('coordination', [('chest', 'right', -15), ('forearm', 'bend', 60)]),
    'settle': ('coordination', [('chest', 'right', -5), ('forearm', 'bend', 15)]),
})
FACTORS = (('upper_arm', 'elevation', (35, 140)), ('shoulder', 'forward', (0, 15)),
           ('shoulder', 'up', (0, -15)), ('upper_arm', 'bone', (-35, 35)),
           ('forearm', 'bend', (20, 90)), ('forearm', 'bone', (-45, 45)))
TEMPORAL_PHASES = ('dance_loop', 'rapid_turn', 'stop', 'settle')


def _controls(controls):
    if not isinstance(controls, dict):
        raise ValueError('controls must map sided canonical bones to axis/degrees dictionaries')
    sided = {side + '_' + part for side in ('left', 'right')
             for part in ('shoulder', 'upper_arm', 'forearm', 'hand', 'thigh', 'shin', 'foot')}
    for bone, axes in controls.items():
        if bone not in sided or not isinstance(axes, dict) or not axes:
            raise ValueError('controls require sided canonical bones and nonempty axes')
        for axis, value in axes.items():
            allowed = {'right', 'forward', 'up', 'bone'}
            if bone.endswith(('forearm', 'shin')):
                allowed.add('bend')
            if bone.endswith('upper_arm'):
                allowed.add('elevation')
            if axis not in allowed or abs(_number(value, 'control angle')) > 180:
                raise ValueError('unsupported control axis or angle outside [-180,180]')


def targeted_cases(failure, budget=8, radius=5):
    """Sample three failure controls, preferring elevation/protraction/twist."""
    failure = interpolate_case(failure, failure['t'])
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        raise ValueError('targeted budget must be nonnegative')
    radius = _number(radius, 'target radius')
    if not 0 < radius <= 30:
        raise ValueError('target radius must be in (0,30]')
    priority = {('upper_arm', 'elevation'): 0, ('shoulder', 'up'): 1, ('upper_arm', 'bone'): 2}
    factors = [(bone, axis, value) for bone, axes in failure.get('controls', {}).items()
               for axis, value in axes.items()]
    factors.sort(key=lambda f: (priority.get((f[0].split('_', 1)[1], f[1]), 3), f[0], f[1]))
    factors = factors[:3]
    if len(factors) != 3:
        raise ValueError('targeted triples require at least three failure controls')
    result = []
    for offsets in product((-radius, radius), repeat=3):
        case = deepcopy(failure)
        for (bone, axis, value), delta in zip(factors, offsets):
            case['controls'][bone][axis] = max(-180., min(180., value + delta))
        case['coverage_kind'] = 'TARGETED_TRIPLE'
        result.append(interpolate_case(case, case['t']))
    return result[:budget]


def _templates():
    templates = [{'motion': name} for name in MOTIONS if name != 'independent_arm']
    # Nonzero GF(2)^3 columns give every binary pair in eight deterministic rows.
    for row in range(8):
        for side in ('left', 'right'):
            controls = {}
            for column, (bone, axis, levels) in enumerate(FACTORS, 1):
                controls.setdefault(side + '_' + bone, {})[axis] = levels[(row & column).bit_count() % 2]
            templates.append({'motion': 'independent_arm', 'controls': controls, 'coverage_kind': 'PAIRWISE'})
    return templates


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise ValueError(f'{name} must be finite')
    return float(value)


def _shape_values(values):
    if not isinstance(values, dict):
        raise ValueError('shape values must be a dictionary')
    for name, value in values.items():
        if not isinstance(name, str) or not name:
            raise ValueError('shape object IDs and key names must be nonempty strings')
        if isinstance(value, dict):
            for key, amount in value.items():
                if not isinstance(key, str) or not key:
                    raise ValueError('shape key names must be nonempty strings')
                _number(amount, 'shape value')
        else:
            _number(value, 'shape value')


def _inputs(profiles, shape_cases, steps):
    if not profiles or any(p not in PROFILES for p in profiles):
        raise ValueError('select HEAD_HANDS and/or FULL_BODY')
    if not isinstance(steps, int) or isinstance(steps, bool) or steps < 2:
        raise ValueError('steps must be an integer >= 2')
    shapes = deepcopy(shape_cases) if shape_cases is not None else [{'id': 'current', 'values': {}}]
    if not shapes or not isinstance(shapes, list):
        raise ValueError('shape cases must be a nonempty list')
    ids = set()
    for shape in shapes:
        if not isinstance(shape, dict) or not isinstance(shape.get('id'), str) or not shape['id']:
            raise ValueError('shape case requires a stable id')
        if shape['id'] in ids or not isinstance(shape.get('values'), dict):
            raise ValueError('duplicate shape id or missing values')
        ids.add(shape['id'])
        _shape_values(shape['values'])
    return [p for p in PROFILES if p in profiles], shapes


def interpolate_case(case, t):
    """Copy a case at a deterministic time; caller owns shape-value application."""
    t = _number(t, 'time')
    if not 0 <= t <= 1:
        raise ValueError('time must be in [0,1]')
    if not isinstance(case, dict) or case.get('profile') not in PROFILES or case.get('motion') not in MOTIONS:
        raise ValueError('invalid pose case')
    if not isinstance(case.get('shape_case'), str) or not isinstance(case.get('shape_values'), dict):
        raise ValueError('invalid shape case')
    _shape_values(case['shape_values'])
    _controls(case.get('controls', {}))
    if case.get('partition', 'TRAINING') not in {'TRAINING', 'HELDOUT'}:
        raise ValueError('partition must be TRAINING or HELDOUT')
    result = deepcopy(case)
    result.update(t=t, family=MOTIONS[case['motion']][0])
    result['id'] = f"{case['profile']}:{case['motion']}:{case['shape_case']}:{t:.12g}"
    extras = {k: case[k] for k in ('accessory_bones', 'accessory_axis', 'target_offsets_m',
              'controls', 'sequence', 'phase') if k in case}
    if case['shape_values']:
        extras['shape_values'] = case['shape_values']
    if case.get('partition') == 'HELDOUT':
        extras['partition'] = 'HELDOUT'
    if result['family'] != 'accessory' and any(k in extras for k in ('accessory_bones', 'accessory_axis')):
        raise ValueError('per-case accessory controls require an accessory motion')
    if 'accessory_axis' in extras and extras['accessory_axis'] not in {'X', 'Y', 'Z'}:
        raise ValueError('accessory axis must be X, Y or Z')
    if 'accessory_bones' in extras and (not isinstance(extras['accessory_bones'], list) or
            any(not isinstance(name, str) or not name for name in extras['accessory_bones'])):
        raise ValueError('accessory bone subset must contain names')
    if extras:
        encoded = json.dumps(extras, sort_keys=True, allow_nan=False, separators=(',', ':'))
        result['id'] += ':' + sha256(encoded.encode()).hexdigest()[:16]
    return result


def trajectory_key(case):
    """Stable replay grouping, including controls, shapes and heldout identity."""
    return interpolate_case(case, 0)['id']


def seed_cases(profiles, shape_cases=None, budget=512, steps=5):
    """Reserve each profile/shape/family/partition before adding more samples."""
    profiles, shapes = _inputs(profiles, shape_cases, steps)
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        raise ValueError('budget must be a nonnegative integer')
    if budget == 0:
        return []
    times = [0, 1] + [i / (steps - 1) for i in range(1, steps - 1)]
    groups = {}
    for time_index, t in enumerate(times):
        for template in _templates():
            motion = template['motion']
            family = MOTIONS[motion][0]
            for shape in shapes:
                for partition in ('TRAINING', 'HELDOUT'):
                    if partition == 'HELDOUT' and motion == 'neutral':
                        continue  # A constant baseline supplies no independent heldout evidence.
                    for profile in profiles:
                        case = dict(template, profile=profile, family=family, partition=partition,
                                    shape_case=shape['id'], shape_values=shape['values'])
                        if partition == 'HELDOUT':
                            # Irrationally staggered times avoid training-grid points and periodic mirrors.
                            sample_t = (time_index + sqrt(2) - 1) / steps
                            if 'controls' in case:
                                case['controls'] = {bone: {axis: value * .83 for axis, value in axes.items()}
                                                    for bone, axes in case['controls'].items()}
                        else:
                            sample_t = 1 - t if 'controls' in case and t in (0, 1) else t
                        stratum = motion if motion in TEMPORAL_PHASES else family
                        if 'controls' in case:
                            stratum = 'independent_' + next(iter(case['controls'])).split('_')[0]
                        key = (stratum, shape['id'], partition, profile)
                        groups.setdefault(key, []).append(interpolate_case(case, sample_t))
    result = []
    maximum = max(map(len, groups.values()))
    for index in range(maximum):
        for group in groups.values():
            if index < len(group):
                result.append(group[index])
                if len(result) == budget:
                    return result
    return result


def coverage_summary(cases, profiles, shape_cases=None, steps=5):
    """Explicit omissions, including shape variants, rather than implied coverage."""
    profiles, shapes = _inputs(profiles, shape_cases, steps)
    expected = seed_cases(profiles, shapes, 100000000, steps)
    present = {c['id'] for c in cases}
    missing = [c for c in expected if c['id'] not in present]
    return {'status': 'INCOMPLETE' if missing else 'SAMPLED', 'expected_seed_cases': len(expected),
            'evaluated_cases': len(cases), 'uncovered_cases': missing,
            'uncovered_strata': uncovered_strata(cases, expected),
            'coverage_warnings': coverage_warnings(cases),
            'continuous_coverage': False, 'library_version': LIBRARY_VERSION}


def uncovered_strata(cases, expected):
    fields = ('profile', 'shape_case', 'family', 'partition')
    present = {tuple(c.get(k, 'TRAINING') for k in fields) for c in cases}
    wanted = {tuple(c.get(k, 'TRAINING') for k in fields) for c in expected}
    return [dict(zip(fields, values)) for values in sorted(wanted - present)]


def coverage_warnings(cases):
    return [{'kind': 'unsupported_contact_pivot', 'status': 'UNKNOWN', 'motion': motion}
            for motion in ('heel_roll', 'toe_roll') if any(c['motion'] == motion for c in cases)]


def refinement_candidates(measurements, remaining, clearance_m=.001):
    """Bisect related sampled intervals near changes, clearance or displacement."""
    if not isinstance(remaining, int) or isinstance(remaining, bool) or remaining < 0:
        raise ValueError('remaining must be a nonnegative integer')
    if _number(clearance_m, 'clearance_m') < 0:
        raise ValueError('clearance_m must be nonnegative')
    groups, seen = {}, set()
    ordered_measurements = sorted(measurements, key=lambda item: interpolate_case(item['case'], item['case']['t'])['id'])
    for item in ordered_measurements:
        case = interpolate_case(item['case'], item['case']['t'])
        if case.get('partition') == 'HELDOUT':
            continue
        key = trajectory_key(case)
        groups.setdefault(key, []).append((case['t'], item, case))
        seen.add(case['id'])
    result = []
    for key in sorted(groups):
        ordered = sorted(groups[key], key=lambda entry: entry[0])
        for a, b in zip(ordered, ordered[1:]):
            if b[0] - a[0] < 1e-6:
                continue
            changes = a[1].get('collision') != b[1].get('collision')
            near = min(a[1].get('clearance_m', float('inf')), b[1].get('clearance_m', float('inf'))) < clearance_m
            displacement = max(a[1].get('displacement_m', 0), b[1].get('displacement_m', 0)) > .02
            if changes or near or displacement:
                case = interpolate_case(a[2], (a[0] + b[0]) / 2)
                if case['id'] not in seen:
                    result.append(case)
                    seen.add(case['id'])
    for item in ordered_measurements:
        case = item['case']
        if (item.get('collision') and case.get('partition') != 'HELDOUT'
                and sum(len(axes) for axes in case.get('controls', {}).values()) >= 3
                and case.get('coverage_kind') != 'TARGETED_TRIPLE'):
            for targeted in targeted_cases(case):
                if targeted['id'] not in seen:
                    result.append(targeted)
                    seen.add(targeted['id'])
    return result[:remaining]


def profile_metadata(profile):
    if profile not in PROFILES:
        raise ValueError('unknown tracking profile')
    return {'profile': profile, 'library_version': LIBRARY_VERSION, 'synthetic': True,
            'vrchat_emulation': False, 'spine_solver': 'prescribed bounded torso',
            'tracked_targets': ['head', 'left_hand', 'right_hand'] +
                               (['hips', 'left_foot', 'right_foot'] if profile == 'FULL_BODY' else []),
            'lower_body': ('authored pelvis and stance; no runtime inference' if profile == 'HEAD_HANDS'
                           else 'authored pelvis, explicit foot contact and step phases'),
            'accessories': 'explicit local flexion only; no physics simulation'}


def motion_commands(case):
    case = interpolate_case(case, case['t'])
    t, motion = case['t'], case['motion']
    amount = sin(t * pi / 2)
    if motion == 'dance_loop':
        amount = sin(t * 2 * pi + pi / 4)
    elif motion in {'stop', 'settle'}:
        amount = (1 - t) * (sin(t * 3 * pi + pi / 2) if motion == 'settle' else 1)
    rotations = []
    paired = {'shoulder', 'upper_arm', 'forearm', 'hand', 'thigh', 'shin', 'foot'}
    for rotation in MOTIONS[motion][1]:
        name, axis, angle = rotation[:3]
        start = rotation[3] if len(rotation) == 4 else 0
        names = [('left_' + name, 1), ('right_' + name, -1 if axis in {'up', 'forward'} else 1)] if name in paired else [(name, 1)]
        rotations.extend({'bone': bone, 'axis': axis, 'degrees': (start + angle * amount) * sign}
                         for bone, sign in names)
    for bone, axes in sorted(case.get('controls', {}).items()):
        rotations = [r for r in rotations if not (r['bone'] == bone and r['axis'] in axes)]
        rotations.extend({'bone': bone, 'axis': axis, 'degrees': value * amount}
                         for axis, value in sorted(axes.items()))
    contacts = {'left_foot': True, 'right_foot': True}
    mirrored = motion.endswith('_right')
    base_motion = motion.removesuffix('_right')
    moving_foot = 'right_foot' if mirrored else 'left_foot'
    if base_motion in {'step', 'knee_lift', 'ankle'}:
        contacts[moving_foot] = t == 0
    if base_motion == 'lunge':
        contacts[moving_foot] = t == 0
    pelvis = [0., 0., 0.]
    if motion in {'squat', 'crouch_reach'}:
        pelvis = [0., -.09 * amount, -.12 * amount]
    elif motion in {'sit', 'seated_twist', 'crossed_legs'}:
        pelvis = [0., -.3 * amount, -.3 * amount]
    elif base_motion == 'lunge':
        pelvis = [0., .04 * amount, -.06 * amount]
    if motion in {'kneel', 'crossed_legs'}:
        contacts = dict.fromkeys(contacts, False)
    metadata = profile_metadata(case['profile'])
    if motion in TEMPORAL_PHASES:
        metadata.update(temporal_phase=motion, temporal_sequence='dance_turn_stop_settle',
                        temporal_evidence='kinematic samples only; no physics simulation')
    if motion in {'heel_roll', 'toe_roll'}:
        metadata.update(contact_pivot_coverage='UNKNOWN',
                        contact_pivot_reason='ankle orientation only; sole heel/toe pivots unsupported')
    return {'rotations': rotations, 'pelvis_height_fractions': pelvis, 'contacts': contacts,
            'accessory_degrees': 20 * sin(pi * t) if motion == 'accessory_flex' else 0,
            'metadata': metadata}
