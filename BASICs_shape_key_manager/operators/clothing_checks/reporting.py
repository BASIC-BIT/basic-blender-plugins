"""Bounded JSON evidence and native retained report storage."""
import json
import hashlib
import bpy
from ...core.clothing_checks import audit_weights, coverage_status, summarize_absolute


def compact_analysis(analysis):
    result = dict(analysis)
    result['evidence_hash'] = hashlib.sha256(json.dumps(analysis, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    for key in ('triangle_pairs', 'contact_triangle_pairs', 'polygon_pairs',
                'contact_polygon_pairs', 'contained_polygon_pairs'):
        values = result.get(key, [])
        result[key + '_count'] = len(values)
        result[key + '_truncated'] = len(values) > 32
        result[key] = values[:32]
    if 'policy' in result:
        result['policy'] = dict(result['policy'])
        for key in ('allowed', 'actionable'):
            values = result['policy'][key]
            result['policy'][key + '_truncated'] = len(values) > 32
            result['policy'][key] = values[:32]
    return result


def compact_finding(finding):
    result = dict(finding)
    result.pop('candidate_absolute', None)
    for key in ('new', 'existing', 'resolved', 'unclassified'):
        grouped = {}
        for row in result.get(key, []):
            grouped.setdefault(row['object_id'], []).append(row['face'])
        result[key] = grouped
    if 'actionable' in result:
        full = result['actionable']
        face_keys = ('new', 'existing', 'resolved', 'unclassified', 'worsened')
        result['actionable'] = {key: value for key, value in full.items()
                                if key not in (*face_keys, 'candidate_absolute')}
        result['actionable'].update({key + '_count': face_count(full.get(key, [])) for key in face_keys})
        result['actionable']['evidence_hash'] = hashlib.sha256(json.dumps(full, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    for key in ('reference', 'candidate'):
        result[key] = compact_analysis(result[key])
    return result


def face_count(rows):
    """Count grouped source faces and legacy per-face report records."""
    return sum(len(faces) for faces in rows.values()) if isinstance(rows, dict) else len(rows)


def weight_report(reference, candidate, rig, utility_groups=()):
    deform = {b.name for b in rig.data.bones if b.use_deform}
    nondeform = {b.name for b in rig.data.bones if not b.use_deform}
    if (not isinstance(utility_groups, (list, tuple)) or
            any(not isinstance(name, str) or not name for name in utility_groups)):
        raise ValueError('utility groups require a list of exact group names')
    utility = set(utility_groups)
    available = {g.name for obj in (reference, candidate) for g in obj.vertex_groups}
    if utility & (deform | nondeform) or utility - available:
        raise ValueError('utility groups must name existing non-bone groups')
    def rows(obj):
        names = {g.index: g.name for g in obj.vertex_groups}
        return [{names[g.group]: g.weight for g in v.groups
                 if names[g.group] not in nondeform | utility} for v in obj.data.vertices]
    locked_before = {g.name for g in reference.vertex_groups if g.lock_weight and g.name in deform}
    locked_after = {g.name for g in candidate.vertex_groups if g.lock_weight and g.name in deform}
    report = audit_weights(rows(candidate), deform, locked_before | locked_after, rows(reference), cap=4)
    report['lock_state_changes'] = [{'name': name, 'reference_locked': name in locked_before,
                                    'candidate_locked': name in locked_after}
                                   for name in sorted(locked_before ^ locked_after)]
    report['valid'] &= not report['lock_state_changes']
    report['excluded_utility_groups'] = sorted(utility)
    return report


def summarize(report):
    results = report['results']
    unknown = sum(r['candidate']['absolute_fit'] == 'INDETERMINATE' for r in results)
    invalid = sum(not p['valid'] or bool(p.get('body_self_crossings_new')) for p in report['poses'])
    completed = len(report['cases'])
    pending = len(report['coverage'].get('uncovered_cases', [])) + len(report['coverage'].get('truncated_intervals', []))
    if report['status'] != 'COMPLETED':
        pending = max(1, pending)
    summary = coverage_status(completed, pending, int(invalid), unknown)
    absolute = summarize_absolute(results)
    summary.update(absolute)
    policies = [r['candidate']['policy'] for r in results if 'policy' in r['candidate']]
    if policies:
        actionable_unknown = sum(r.get('actionable', {}).get('absolute_fit') == 'INDETERMINATE'
                                 for r in results)
        summary['actionable_unknown'] = actionable_unknown
        summary['allowed_findings'] = sum(p['allowed_count'] for p in policies)
        summary['actionable_findings'] = sum(p['actionable_count'] for p in policies)
        summary['actionable_fit'] = ('CLIPPING' if any(r.get('actionable', {}).get('absolute_fit') == 'CLIPPING'
                                    for r in results) else 'INDETERMINATE' if actionable_unknown or unknown or pending or invalid
                                    else 'NO_ACTIONABLE_CLIPPING')
    summary.update(regression=('REGRESSION' if any(r['regression'] == 'REGRESSION' for r in results)
                               else 'INDETERMINATE' if any(r['regression'] == 'INDETERMINATE' for r in results)
                               else 'NO_DETECTED_REGRESSION'),
                   absolute_fit=('CLIPPING' if absolute['candidate_clipping_pairs']
                                 else 'INDETERMINATE' if unknown or pending or invalid or not results
                                 else 'CLEAR'),
                   new_faces=sum(face_count(r['new']) for r in results),
                   existing_faces=sum(face_count(r['existing']) for r in results),
                   worsened_faces=sum(face_count(r['worsened']) for r in results))
    report['summary'] = summary


def report_digest(report):
    payload = {key: value for key, value in report.items() if key != 'report_hash'}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def validate_report(report):
    if (not isinstance(report, dict) or not isinstance(report.get('report_hash'), str)
            or report['report_hash'] != report_digest(report)):
        raise ValueError('report integrity mismatch or missing hash; rerun clothing checks')
    return report


def persist(report, scene):
    if scene:
        report['review_scene'] = scene.name
    # Validate before allocating a retained datablock. Roll back partial persistence.
    json.dumps(report, allow_nan=False)
    text = bpy.data.texts.new('BASIC Clothing Report ' + report['id'][:8])
    try:
        text.use_fake_user = True
        report['text'] = text.name
        report['report_hash'] = report_digest(report)
        text.write(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
        saved = json.loads(text.as_string())
        validate_report(saved)
        if scene:
            scene['basic_clothing_report'] = text.name
        return text
    except Exception:
        bpy.data.texts.remove(text)
        report.pop('text', None)
        raise
