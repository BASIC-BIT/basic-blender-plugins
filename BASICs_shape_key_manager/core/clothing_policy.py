"""Explicit endpoint-region contact policy. Raw evidence is never filtered."""
from copy import deepcopy
import hashlib
import json


KINDS = ('CROSSING', 'CONTACT', 'CONTAINED')


def evidence_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def validate_policy(regions, allowances):
    if not isinstance(regions, dict) or not isinstance(allowances, list):
        raise ValueError('regions must be a dictionary and allowances a list')
    for identity, named in regions.items():
        if not isinstance(identity, str) or not identity or not isinstance(named, dict):
            raise ValueError('regions require captured object IDs and named face sets')
        for name, faces in named.items():
            if (not isinstance(name, str) or not name or not isinstance(faces, list) or not faces
                    or any(isinstance(f, bool) or not isinstance(f, int) or f < 0 for f in faces)):
                raise ValueError('region faces must be nonnegative integer lists')
    for rule in allowances:
        if not isinstance(rule, dict) or rule.get('kind') not in KINDS:
            raise ValueError('allowance requires an explicit finding kind')
        for side in ('a', 'b'):
            endpoint = rule.get(side, {})
            if (not isinstance(endpoint, dict) or endpoint.get('object_id') not in regions
                    or endpoint.get('region') not in regions[endpoint['object_id']]):
                raise ValueError('allowance endpoint names a missing object or FACE region')
    return allowances


def apply_policy(analysis, regions, allowances):
    """Match complete polygon pairs before examples are truncated by reporting."""
    validate_policy(regions, allowances)
    ids = analysis['pair']
    allowed, actionable = [], []
    for kind, key in [('CROSSING', 'polygon_pairs'), ('CONTACT', 'contact_polygon_pairs'),
                      ('CONTAINED', 'contained_polygon_pairs')]:
        for evidence in analysis.get(key, []):
            faces = evidence['faces'] if kind == 'CONTAINED' else evidence
            source_id = evidence['source_id'] if kind == 'CONTAINED' else None
            if kind == 'CONTAINED' and source_id not in ids:
                raise ValueError('contained finding source must belong to the object pair')
            def matches(rule, reverse):
                endpoints = [rule['b'], rule['a']] if reverse else [rule['a'], rule['b']]
                return rule['kind'] == kind and all(
                    endpoint['object_id'] == identity and face in regions[identity][endpoint['region']]
                    for endpoint, identity, face in zip(endpoints, ids, faces))
            accepted = any(matches(rule, False) or matches(rule, True) for rule in allowances)
            record = {'kind': kind, 'faces': list(faces)}
            if kind == 'CONTAINED':
                record['source_id'] = source_id
            (allowed if accepted else actionable).append(record)
    def face_sets(rows, kind):
        return {identity: sorted({face for row in rows if row['kind'] == kind
                                 for owner, face in zip(ids, row['faces']) if owner == identity
                                 and (kind != 'CONTAINED' or owner == row['source_id'])})
                for identity in dict.fromkeys(ids)}
    result = dict(analysis)
    result['policy'] = {'allowed_count': len(allowed), 'actionable_count': len(actionable),
                        'allowed': allowed, 'actionable': actionable,
                        'actionable_crossing_faces': face_sets(actionable, 'CROSSING'),
                        'actionable_contained_faces': face_sets(actionable, 'CONTAINED'),
                        'raw_evidence_hash': evidence_hash(analysis)}
    return result


def actionable_analysis(analysis):
    result = deepcopy(analysis)
    policy = analysis['policy']
    for name in ('crossing_faces', 'contained_faces'):
        result[name] = policy['actionable_' + name]
    owners = [analysis['primary_id']] if analysis.get('primary_id') else analysis['pair']
    if any(result[key].get(owner) for key in ('crossing_faces', 'contained_faces') for owner in owners):
        result['absolute_fit'] = 'CLIPPING'
    elif analysis['absolute_fit'] == 'CLIPPING':
        result['absolute_fit'] = 'INDETERMINATE'
    return result


def regional_plausibility(regions, body_crossings, baseline_pairs=(), body_contacts=None):
    """Local screening does not upgrade global volume support or anatomical validity."""
    contacts = body_crossings if body_contacts is None else body_contacts
    return {name: {'status': 'LOCAL_CROSSINGS' if any(set(pair) & set(faces) for pair in body_crossings)
                            else 'LOCAL_CONTACTS' if any(set(pair) & set(faces) for pair in contacts)
                            else 'NO_LOCAL_CROSSINGS',
                   'body_face_pairs': [list(pair) for pair in contacts if set(pair) & set(faces)],
                   'baseline_crossing_pairs': [list(pair) for pair in baseline_pairs if set(pair) & set(faces)],
                   'new_crossing_pairs': [list(pair) for pair in body_crossings
                                          if pair not in baseline_pairs and set(pair) & set(faces)],
                   'global_crossing_count': len(body_crossings),
                   'global_contact_pair_count': len(contacts), 'containment': 'UNCHANGED'}
            for name, faces in regions.items()}
