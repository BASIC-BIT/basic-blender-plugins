"""Session settings and finite deterministic refinement in the shared budget."""
from copy import deepcopy
from math import isfinite
from ...core.clothing_motion import (LIBRARY_VERSION, MOTIONS, PROFILES, seed_cases, interpolate_case,
                                     refinement_candidates, trajectory_key, uncovered_strata, coverage_warnings)


def prepare(settings):
    if not isinstance(settings, dict):
        raise ValueError('settings must be a dictionary')
    result = deepcopy(settings)
    utility = result.setdefault('utility_groups', {})
    if (not isinstance(utility, dict) or any(
            not isinstance(identity, str) or not identity or not isinstance(names, list) or
            any(not isinstance(name, str) or not name for name in names)
            for identity, names in utility.items())):
        raise ValueError('utility groups require captured garment ID -> list of exact group names')
    if ('cases' in result or 'replay_coverage' in result) and 'motion_library_version' not in result:
        raise ValueError('legacy or authored cases require an explicit motion library version')
    if result.get('motion_library_version', LIBRARY_VERSION) != LIBRARY_VERSION:
        raise ValueError('motion library changed; generate a new run')
    result['motion_library_version'] = LIBRARY_VERSION
    for name, default in [('budget', 512), ('sample_limit', 512), ('refinement_depth', 3), ('steps', 3)]:
        value = result.setdefault(name, default)
        minimum = 0 if name == 'refinement_depth' else 2 if name == 'steps' else 1
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= 100000:
            raise ValueError(f'{name} must be an integer between {minimum} and 100000')
    for name, default in [('contact_m', .0001), ('clearance_m', .001), ('worsening_m', .0005)]:
        value = result.setdefault(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
            raise ValueError(f'{name} must be a finite nonnegative number')
    profiles = result.setdefault('profiles', list(PROFILES))
    if not profiles or any(p not in PROFILES for p in profiles):
        raise ValueError('select supported tracking profiles')
    shapes = result.setdefault('shape_cases', [{'id': 'current', 'values': {}}])
    if not any(s.get('id') == 'current' for s in shapes):
        shapes.insert(0, {'id': 'current', 'values': {}})
    if any(not isinstance(s.get('values'), dict) for s in shapes):
        raise ValueError('shape cases require values by logical object ID')
    for shape in shapes:
        for identity, keys in shape['values'].items():
            if not isinstance(identity, str) or not isinstance(keys, dict):
                raise ValueError('shape values require logical object ID -> key -> value')
            if any(not isinstance(k, str) or isinstance(v, bool) or not isinstance(v, (int, float))
                   or not isfinite(v) for k, v in keys.items()):
                raise ValueError('shape values must be finite named values')
    defaults = {v[0] for v in MOTIONS.values()}
    if not result.get('accessory_bones'):
        defaults.discard('accessory')
    families = result.get('families', sorted(defaults))
    if not families or any(f not in {v[0] for v in MOTIONS.values()} for f in families):
        raise ValueError('select supported motion families')
    result['families'] = families
    expected = seed_cases(profiles, shapes, 100000000, result['steps'])
    expected = [c for c in expected if c['family'] in families]
    # Keep the stratified prefix, but leave a quarter of the cap for adaptive search.
    reserve = result['budget'] // 4 if result['refinement_depth'] else 0
    result['seed_case_budget'] = min(len(expected), result['budget'] - reserve)
    if 'cases' in result:
        cases = [interpolate_case(c, c['t']) for c in result['cases']]
        if not cases or len(cases) > result['budget'] or len({c['id'] for c in cases}) != len(cases):
            raise ValueError('saved case replay must be unique, nonempty and within budget')
        if any(c['profile'] not in profiles or c['family'] not in families for c in cases):
            raise ValueError('saved cases do not match selected profile/family')
    else:
        cases = expected[:result['seed_case_budget']]
    return result, cases, expected


def refinements(measurements, depth, settings):
    if depth >= settings['refinement_depth']:
        return []
    maximum = len(measurements) * 10
    candidates = refinement_candidates(measurements, maximum, clearance_m=settings['clearance_m'])
    minimum = 1 / ((settings['steps'] - 1) * 2 ** settings['refinement_depth'])
    return [c for c in candidates if all(
        abs(c['t'] - m['case']['t']) >= minimum - 1e-8
        for m in measurements if trajectory_key(m['case']) == trajectory_key(c))]


def coverage(cases, expected, pending, settings):
    ids = {c['id'] for c in cases}
    missing = [c for c in expected if c['id'] not in ids]
    return {'status': 'INCOMPLETE' if missing or pending else 'SAMPLED',
            'expected_seed_cases': len(expected), 'evaluated_cases': len(cases),
            'uncovered_cases': missing, 'truncated_intervals': pending,
            'uncovered_strata': uncovered_strata(cases, expected),
            'coverage_warnings': coverage_warnings(cases),
            'continuous_coverage': False, 'budget': settings['budget'],
            'seed_case_budget': settings['seed_case_budget'],
            'refinement_case_capacity': settings['budget'] - settings['seed_case_budget']
                                        if settings['refinement_depth'] else 0,
            'refinement_depth': settings['refinement_depth'],
            'minimum_time_resolution': 1 / ((settings['steps'] - 1) * 2 ** settings['refinement_depth'])}
