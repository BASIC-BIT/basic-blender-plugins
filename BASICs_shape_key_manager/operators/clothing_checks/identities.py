"""Persistent source bindings live only on owned native scenes, never sources."""
import bpy


def capture_source_ids(objects):
    """Capture-local identities; native pointers are persisted only on owned scenes."""
    return {obj: 'input:' + str(index) for index, obj in enumerate(dict.fromkeys(objects))}


def retain_source_ids(scene, identities):
    scene['_basic_clothing_sources'] = {identity: obj for obj, identity in identities.items()}


def read_source_ids(scene):
    captured = scene.get('_basic_clothing_sources')
    if not captured or any(obj is None for obj in captured.values()):
        raise ValueError('captured source bindings are missing; recapture the baseline and rerun')
    return {obj: identity for identity, obj in captured.items()}


def retained_review_scene(report, *, required=True):
    matches = [scene for scene in bpy.data.scenes if report.get('id') and
               scene.get('_basic_clothing_owner') == report['id'] and
               scene.get('_basic_clothing_kind') == 'REVIEW']
    if len(matches) > 1 or required and not matches:
        raise ValueError('retained native review scene is missing or ownership is ambiguous')
    return matches[0] if matches else None


def resolve_review_objects(scene, report=None):
    """Captured report keys bind distinct native clones across rename and reopen."""
    captured = scene.get('_basic_clothing_report_objects')
    rows = list(captured.values()) if hasattr(captured, 'values') else []
    if (not rows or len(rows) != len(scene.objects) or any(not hasattr(row, 'get') for row in rows) or
            any(not isinstance(row.get('key'), str) or not row['key'] for row in rows) or
            len({row['key'] for row in rows}) != len(rows) or
            any(row.get('object') is None for row in rows) or
            {row['object'] for row in rows} != set(scene.objects)):
        raise ValueError('retained review object bindings are missing; rerun clothing checks')
    if report is not None and {row['key'] for row in rows} != set(report['objects']):
        raise ValueError('retained review object bindings disagree with this report; rerun clothing checks')
    return {row['object']: row['key'] for row in rows}


def logical_id(obj):
    return str(obj.get('_basic_clothing_id') or f'object:{obj.session_uid}')


def resolve_bindings(body, pairs):
    body_ids = {row['reference'].get('_basic_clothing_baseline_body_id') for row in pairs
                if row.get('reference') and row['reference'].get('_basic_clothing_baseline_body_id')}
    if len(body_ids) > 1:
        raise ValueError('selected baselines refer to different captured bodies')
    owned = [scene.get('_basic_clothing_bindings') for scene in bpy.data.scenes
             if scene.get('_basic_clothing_kind') in {'BASELINE', 'REVIEW', 'JOB'}]
    owned = [entry for entry in owned if entry and entry.get('body') == body]
    body_id = next(iter(body_ids), owned[0]['body_id'] if owned else logical_id(body))
    identities = []
    for pair in pairs:
        ref, candidate = pair['reference'], pair['candidate']
        identity = ref.get('_basic_clothing_id')
        if not identity:
            matches = [row['id'] for entry in owned for row in entry.get('pairs', {}).values()
                       if row.get('reference') == ref and row.get('candidate') == candidate]
            identity = matches[0] if matches else logical_id(candidate)
        identities.append(str(identity))
    return str(body_id), identities


def retain_bindings(scene, body, body_id, rows):
    """Native pointers survive rename/reopen; JSON carries the captured identities."""
    scene['_basic_clothing_bindings'] = {'body': body, 'body_id': body_id, 'pairs': {
        str(index): {'reference': ref, 'candidate': candidate, 'id': identity}
        for index, (ref, candidate, identity) in enumerate(rows)}}
    return {'body': {'source': body.name_full, 'id': body_id}, 'pairs': [
        {'reference': ref.name_full, 'candidate': candidate.name_full, 'id': identity}
        for ref, candidate, identity in rows]}
