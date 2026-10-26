"""Pure face-regression, coverage and deform-weight audit policy.

Weight rows contain deform-intended assignments only. Callers must omit masks
and other intentionally non-deforming vertex groups before auditing.
"""
import math


def _number(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a finite number')
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f'{name} must be finite and >= {minimum}')
    return value


def _pair(report):
    if not isinstance(report, dict):
        raise ValueError('pair report must be a dictionary')
    pair = report.get('pair', [])
    if (not isinstance(pair, (list, tuple)) or len(pair) != 2
            or any(not isinstance(i, str) or not i for i in pair)
            or pair[0] == pair[1] and report.get('kind') != 'SELF'):
        raise ValueError('pair must contain two distinct captured object IDs')
    return tuple(sorted(pair))


def _faces(report, pair):
    affected = set()
    for key in ('crossing_faces', 'contained_faces'):
        if not isinstance(report.get(key, {}), dict):
            raise ValueError('face findings must be dictionaries')
        for object_id, faces in report.get(key, {}).items():
            if object_id not in pair:
                raise ValueError('face object is outside pair')
            if not isinstance(faces, (list, tuple)):
                raise ValueError('source faces must be a list')
            for face in faces:
                if isinstance(face, bool) or not isinstance(face, int) or face < 0:
                    raise ValueError('source face must be a nonnegative integer')
                affected.add((object_id, face))
    return affected


def _depths(report, pair):
    values = report.get('depths_m', {})
    if not isinstance(values, dict):
        raise ValueError('depths must be dictionaries')
    for object_id, faces in values.items():
        if object_id not in pair or not isinstance(faces, dict):
            raise ValueError('depth object must belong to pair with face dictionary')
        for face, depth in faces.items():
            if not isinstance(face, str) or not face.isdecimal():
                raise ValueError('depth source face keys must be decimal strings')
            _number(depth, 'sampled depth')


def _records(faces):
    return [{'object_id': obj, 'face': face} for obj, face in sorted(faces)]


def absolute_findings(report: dict) -> dict:
    """Candidate evidence is independent of baseline and regression categories."""
    pair = _pair(report)
    _faces(report, pair)
    primary = report.get('primary_id')
    if primary is not None and primary not in pair:
        raise ValueError('primary face owner must belong to pair')
    owners = (primary,) if primary else pair
    crossing = {(obj, face) for obj in owners
                for face in report.get('crossing_faces', {}).get(obj, [])}
    contained = {(obj, face) for obj in owners
                 if report.get('containment', {}).get(obj) in {'SUPPORTED', 'AMBIGUOUS'}
                 for face in report.get('contained_faces', {}).get(obj, [])}
    return {'crossing': _records(crossing), 'contained': _records(contained),
            'affected': _records(crossing | contained)}


def summarize_absolute(results: list[dict]) -> dict:
    """Count observations and retain unique pair/object/source-face identities."""
    unique, crossing_count, contained_count, clipping_pairs = set(), 0, 0, 0
    for result in results:
        candidate = result['candidate']
        findings = absolute_findings(candidate)
        pair = _pair(candidate)
        crossing_count += len(findings['crossing'])
        contained_count += len(findings['contained'])
        clipping_pairs += bool(findings['affected'])
        unique.update((pair, row['object_id'], row['face']) for row in findings['affected'])
    return {'candidate_clipping_pairs': clipping_pairs,
            'absolute_crossing_faces': crossing_count,
            'absolute_contained_faces': contained_count,
            'absolute_unique_faces': len(unique),
            'absolute_faces': [{'pair': list(pair), 'object_id': obj, 'face': face}
                               for pair, obj, face in sorted(unique)]}


def classify_pair(reference: dict, candidate: dict, worsening_m=0.0005) -> dict:
    """Compare affected source faces within exactly one captured object pair.

    A partner triangle change is supporting evidence, not a new affected face.
    Depths are unsigned sampled interior distances, never exact deepest depths.
    """
    _number(worsening_m, 'worsening_m')
    pair = _pair(reference)
    if pair != _pair(candidate):
        raise ValueError('reference and candidate object pair must match')
    _depths(reference, pair)
    _depths(candidate, pair)
    before, after = _faces(reference, pair), _faces(candidate, pair)
    primary = reference.get('primary_id')
    if primary != candidate.get('primary_id') or (primary is not None and primary not in pair):
        raise ValueError('primary face owner must match within pair')
    if primary is not None:
        before = {face for face in before if face[0] == primary}
        after = {face for face in after if face[0] == primary}
    owners = (primary,) if primary else pair
    new, resolved, uncertain = after - before, before - after, set()
    for added, removed, opposite in ((new, False, reference), (resolved, True, candidate)):
        measured = reference if removed else candidate
        for obj, face in tuple(added):
            crossing_face = face in measured.get('crossing_faces', {}).get(obj, [])
            known_absence = (opposite.get('containment', {}).get(obj) == 'SUPPORTED'
                             and opposite.get('sampling_complete', True))
            if not crossing_face and not known_absence:
                added.remove((obj, face))
                uncertain.add((obj, face))
    supported = all(report.get('containment', {}).get(obj) == 'SUPPORTED'
                    for report in (reference, candidate) for obj in owners)
    depth_supported = supported
    worsened = []
    for obj, face in sorted(before & after):
        if all(report.get('containment', {}).get(obj) == 'SUPPORTED'
               for report in (reference, candidate)):
            old = reference.get('depths_m', {}).get(obj, {}).get(str(face))
            current = candidate.get('depths_m', {}).get(obj, {}).get(str(face))
            if old is None or current is None:
                depth_supported = False
                continue
            _number(old, 'reference depth')
            _number(current, 'candidate depth')
            if current - old > worsening_m:
                worsened.append({'object_id': obj, 'face': face,
                                 'reference_m': old, 'candidate_m': current,
                                 'delta_m': current - old})
    candidate_absolute = absolute_findings(candidate)
    self_clear = (candidate.get('kind') == 'SELF'
                  and candidate.get('scope') == 'NONADJACENT_TRIANGLE_CROSSINGS'
                  and candidate.get('sampling_complete') is True)
    absolute = ('CLIPPING' if candidate_absolute['affected'] else
                'CLEAR' if candidate.get('absolute_fit') == 'CLEAR'
                and (self_clear or all(candidate.get('containment', {}).get(obj) == 'SUPPORTED' for obj in owners))
                else 'INDETERMINATE')
    return {'pair': list(pair), 'primary_id': primary, 'new': _records(new),
            'existing': _records(after & before), 'resolved': _records(resolved),
            'unclassified': _records(uncertain),
            'worsened': worsened,
            'regression': 'REGRESSION' if new or worsened else 'INDETERMINATE' if uncertain
                          else 'NO_DETECTED_REGRESSION',
            'absolute_fit': absolute, 'depth_status': 'SUPPORTED' if depth_supported else 'UNKNOWN',
            'candidate_absolute': candidate_absolute,
            'reference': reference, 'candidate': candidate}


def coverage_status(completed: int, pending: int, invalid: int, unknown: int) -> dict:
    """Coverage is independent of collision/regression results."""
    counts = dict(completed=completed, pending=pending, invalid=invalid, unknown=unknown)
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in counts.values()):
        raise ValueError('coverage counts must be nonnegative integers')
    complete = completed > 0 and pending == 0 and invalid == 0
    return {**counts, 'coverage': 'COMPLETE' if complete else 'INCOMPLETE',
            'absolute_fit': 'ELIGIBLE' if complete and unknown == 0 else 'INDETERMINATE'}


def audit_weights(rows: list[dict], deform_names: set, locked_names: set,
                  baseline_rows=None, cap=4) -> dict:
    """Audit without mutating. Protected deltas compare normalized deform shares."""
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise ValueError('cap must be a positive integer')
    if not locked_names <= deform_names:
        raise ValueError('locked names must be deform bones')
    if baseline_rows is not None and len(rows) != len(baseline_rows):
        raise ValueError('baseline vertex count must match')
    unnormalized, missing, over_cap, protected = [], [], [], []
    for index, row in enumerate(rows):
        for name, weight in row.items():
            if not isinstance(name, str) or not name:
                raise ValueError('weight names must be nonempty strings')
            _number(weight, 'weight')
            if name not in deform_names and weight > 0:
                missing.append({'vertex': index, 'name': name, 'weight': weight})
        total = sum(w for name, w in row.items() if name in deform_names)
        if abs(total - 1) > 1e-6:
            unnormalized.append(index)
        if sum(w > 0 for name, w in row.items() if name in deform_names) > cap:
            over_cap.append(index)
        if baseline_rows is not None:
            original = baseline_rows[index]
            for weight in original.values():
                _number(weight, 'baseline weight')
            old_total = sum(w for name, w in original.items() if name in deform_names)
            for name in sorted(locked_names):
                old = original.get(name, 0) / old_total if old_total else 0
                new = row.get(name, 0) / total if total else 0
                if abs(new - old) > 1e-6:
                    protected.append({'vertex': index, 'name': name,
                                      'reference_share': old, 'candidate_share': new})
    return {'vertex_count': len(rows), 'cap': cap, 'unnormalized': unnormalized,
            'missing_bones': missing, 'cap_violations': over_cap,
            'protected_changes': protected,
            'valid': not (unnormalized or missing or over_cap or protected)}
