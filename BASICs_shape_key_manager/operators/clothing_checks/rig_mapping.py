"""Explicit humanoid mapping and native rest-frame calibration."""
import json
from math import isfinite
from mathutils import Vector

CANONICAL_BONES = ('hips', 'spine', 'chest', 'head') + tuple(
    f'{side}_{part}' for side in ('left', 'right')
    for part in ('upper_arm', 'forearm', 'hand', 'thigh', 'shin', 'foot'))
OPTIONAL_BONES = ('left_shoulder', 'right_shoulder')
CHAINS = {f'{side}_{limb}': tuple(f'{side}_{p}' for p in parts)
          for side in ('left', 'right')
          for limb, parts in [('arm', ('upper_arm', 'forearm', 'hand')),
                              ('leg', ('thigh', 'shin', 'foot'))]}


def suggest_mapping(rig):
    """Unique aliases are suggestions only. Never silently confirm a mapping."""
    aliases = {'upper_arm': ('arm', 'upperarm'), 'forearm': ('elbow', 'lowerarm'),
               'hand': ('hand', 'wrist'), 'thigh': ('leg', 'upperleg'),
               'shin': ('knee', 'lowerleg'), 'foot': ('ankle', 'foot'),
               'shoulder': ('shoulder', 'clavicle', 'collar')}
    normalize = lambda name: ''.join(c for c in name.lower() if c.isalnum())
    result = {}
    for canonical in CANONICAL_BONES + OPTIONAL_BONES:
        tokens = {normalize(canonical)}
        if '_' in canonical:
            side, part = canonical.split('_', 1)
            for alias in aliases[part]:
                tokens.update({side + alias, alias + side, alias + side[0], side[0] + alias})
        matches = [bone.name for bone in rig.data.bones if normalize(bone.name) in tokens]
        if len(matches) == 1:
            result[canonical] = matches[0]
    return result


def resolve_mapping(rig, overrides=None):
    if rig is None or rig.type != 'ARMATURE':
        raise ValueError('mapping requires an armature')
    if not isinstance(overrides, dict) or any(k not in overrides for k in CANONICAL_BONES):
        raise ValueError('confirm all canonical humanoid mapping entries explicitly')
    result = {k: overrides[k] for k in CANONICAL_BONES}
    result.update({k: overrides[k] for k in OPTIONAL_BONES if overrides.get(k)})
    if any(not isinstance(v, str) or v not in rig.data.bones for v in result.values()):
        raise ValueError('mapped bone does not exist')
    if len(set(result.values())) != len(result):
        raise ValueError('humanoid mapping must use unique bones')
    for side in ('left', 'right'):
        shoulder = result.get(side + '_shoulder')
        if shoulder:
            arm = rig.data.bones[result[side + '_upper_arm']]
            if arm.parent is None or arm.parent.name != shoulder:
                raise ValueError('mapped shoulder must be the corresponding upper arm parent')
            ancestor = rig.data.bones[shoulder].parent
            while ancestor and ancestor.name != result['chest']:
                ancestor = ancestor.parent
            if ancestor is None:
                raise ValueError('mapped shoulder must descend from chest')
    for chain in CHAINS.values():
        for parent, child in zip(chain, chain[1:]):
            bone = rig.data.bones[result[child]]
            if bone.parent is None or bone.parent.name != result[parent]:
                raise ValueError(f'unsupported non-direct limb chain: {parent}/{child}')
    for parent, child in [('hips', 'spine'), ('spine', 'chest'), ('chest', 'head')]:
        ancestors = set()
        bone = rig.data.bones[result[child]].parent
        while bone:
            ancestors.add(bone.name)
            bone = bone.parent
        if result[parent] not in ancestors:
            raise ValueError(f'unsupported torso ancestry: {parent}/{child}')
    return result


def calibrate(rig, mapping):
    rest = {k: rig.data.bones[v].matrix_local.copy() for k, v in mapping.items()}
    heads = {k: matrix.translation for k, matrix in rest.items()}
    up = heads['head'] - heads['hips']
    right = heads['right_upper_arm'] - heads['left_upper_arm']
    if up.length < 1e-6 or right.length < 1e-6 or up.cross(right).length < 1e-6:
        raise ValueError('degenerate humanoid calibration axes')
    up.normalize()
    right = (right - up * right.dot(up)).normalized()
    forward = up.cross(right).normalized()
    raw = rig.get('basic_clothing_bend_directions', '{}')
    try:
        directions = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (ValueError, TypeError):
        raise ValueError('invalid explicit bend direction JSON') from None
    if not isinstance(directions, dict) or any(key not in CHAINS for key in directions):
        raise ValueError('bend directions must name canonical arm/leg chains')
    for direction in directions.values():
        if not isinstance(direction, (list, tuple)) or len(direction) != 3 or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in direction):
            raise ValueError('bend directions require three finite numbers')
    poles, hinges = {}, {}
    for key, (a, b, c) in CHAINS.items():
        axis = heads[c] - heads[a]
        first = heads[b] - heads[a]
        if min(axis.length, first.length, (heads[c] - heads[b]).length) < 1e-6:
            raise ValueError(f'degenerate joint heads in {key}')
        axis.normalize()
        bend = first - axis * first.dot(axis)
        if key in directions:
            try:
                bend = Vector(directions[key])
                bend -= axis * bend.dot(axis)
            except (ValueError, TypeError):
                raise ValueError(f'invalid bend direction: {key}') from None
        elif bend.length < 1e-5:
            raise ValueError(f'collinear {key} requires explicit bend direction')
        if bend.length < 1e-6:
            raise ValueError(f'bend direction parallel to {key}')
        poles[key] = bend.normalized()
        hinges[key] = bend.normalized().cross(first.normalized()).normalized()
    return {'axes': {'up': up, 'right': right, 'forward': forward},
            'height': (heads['head'] - heads['hips']).length * 2.5,
            'poles': poles, 'hinges': hinges, 'rest': rest}
