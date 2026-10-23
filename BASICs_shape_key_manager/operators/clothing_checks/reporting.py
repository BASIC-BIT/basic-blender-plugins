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
    for key in ('reference', 'candidate'):
        result[key] = compact_analysis(result[key])
    return result


def weight_report(reference, candidate, rig):
    deform = {b.name for b in rig.data.bones if b.use_deform}
    nondeform = {b.name for b in rig.data.bones if not b.use_deform}
    def rows(obj):
        names = {g.index: g.name for g in obj.vertex_groups}
        return [{names[g.group]: g.weight for g in v.groups
                 if names[g.group] not in nondeform} for v in obj.data.vertices]
    return audit_weights(rows(candidate), deform,
                         {g.name for g in candidate.vertex_groups if g.lock_weight and g.name in deform},
                         rows(reference), cap=4)


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
        summary['allowed_findings'] = sum(p['allowed_count'] for p in policies)
        summary['actionable_findings'] = sum(p['actionable_count'] for p in policies)
        summary['actionable_fit'] = ('CLIPPING' if any(r.get('actionable', {}).get('absolute_fit') == 'CLIPPING'
                                    for r in results) else 'INDETERMINATE' if unknown or pending or invalid
                                    else 'NO_ACTIONABLE_CLIPPING')
    summary.update(regression=('REGRESSION' if any(r['regression'] == 'REGRESSION' for r in results)
                               else 'INDETERMINATE' if any(r['regression'] == 'INDETERMINATE' for r in results)
                               else 'NO_DETECTED_REGRESSION'),
                   absolute_fit=('CLIPPING' if absolute['candidate_clipping_pairs']
                                 else 'INDETERMINATE' if unknown or pending or invalid or not results
                                 else 'CLEAR'),
                   new_faces=sum(len(r['new']) for r in results),
                   existing_faces=sum(len(r['existing']) for r in results),
                   worsened_faces=sum(len(r['worsened']) for r in results))
    report['summary'] = summary


def persist(report, scene):
    if scene:
        report['review_scene'] = scene.name
    # Validate before allocating a retained datablock. Roll back partial persistence.
    json.dumps(report, allow_nan=False)
    text = bpy.data.texts.new('BASIC Clothing Report ' + report['id'][:8])
    try:
        text.use_fake_user = True
        report['text'] = text.name
        report['report_hash'] = hashlib.sha256(json.dumps(report, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        text.write(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
        saved = json.loads(text.as_string())
        expected = saved.pop('report_hash')
        actual = hashlib.sha256(json.dumps(saved, sort_keys=True, separators=(',', ':'),
                                          allow_nan=False).encode()).hexdigest()
        if expected != actual:
            raise ValueError('retained report readback hash mismatch')
        if scene:
            scene['basic_clothing_report'] = text.name
        return text
    except Exception:
        bpy.data.texts.remove(text)
        report.pop('text', None)
        raise
