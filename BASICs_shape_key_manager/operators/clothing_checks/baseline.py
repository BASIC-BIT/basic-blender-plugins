"""Immutable native baseline capture, independent of the creator's editable data."""
import uuid
import bpy
from .inputs import preflight, owned_copies, remove_scene, fingerprint_inputs, logical_id, fingerprint
from .identities import resolve_bindings, retain_bindings, capture_source_ids, retain_source_ids
from .fingerprints import FINGERPRINT_FORMAT
from .baseline_state import capture_baseline_state


def capture_baseline(context, body, rig, clothing):
    pairs, objects = preflight(body, rig, [dict(reference=o, candidate=o, confirmed=True) for o in clothing], capturing=True)
    owner = uuid.uuid4().hex
    scene = bpy.data.scenes.new('BASIC Clothing Baseline ' + owner[:8])
    scene['_basic_clothing_owner'], scene['_basic_clothing_kind'] = owner, 'BASELINE'
    scene.use_fake_user = True
    try:
        source_ids = capture_source_ids(objects)
        retain_source_ids(scene, source_ids)
        copies = owned_copies(scene, objects, owner)
        body_id, _ = resolve_bindings(body, [dict(reference=o, candidate=o) for o in clothing])
        rows = []
        for ref, candidate, identity in pairs:
            copies[ref]['_basic_clothing_id'] = identity
            copies[ref]['_basic_clothing_role'] = 'REFERENCE'
            copies[ref]['_basic_clothing_baseline_body'] = fingerprint(body, source_ids)
            copies[ref]['_basic_clothing_fingerprint_format'] = FINGERPRINT_FORMAT
            copies[ref]['_basic_clothing_baseline_body_id'] = body_id
            rows.append({'id': identity, 'reference': copies[ref].name,
                         'candidate': candidate.name_full, 'confirmed': True})
        copies[body]['_basic_clothing_id'] = body_id
        copies[body]['_basic_clothing_role'] = 'BODY'
        copies[rig]['_basic_clothing_role'] = 'RIG'
        retain_bindings(scene, body, body_id, [(copies[ref], candidate, identity) for ref, candidate, identity in pairs])
        capture_baseline_state(scene)
        return {'scene': scene.name, 'owner': owner, 'body': copies[body].name,
                'rig': copies[rig].name, 'pairs': rows, 'inputs': fingerprint_inputs(objects, source_ids)}
    except Exception:
        remove_scene(scene, owner)
        raise
