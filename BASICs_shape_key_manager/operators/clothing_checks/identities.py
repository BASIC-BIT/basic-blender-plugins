"""Persistent source bindings live only on owned native scenes, never sources."""
import bpy


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
