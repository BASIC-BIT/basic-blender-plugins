"""Accepted owned-copy state, separate from immutable source/report evidence."""
import json
from .fingerprints import fingerprint_inputs
from .identities import capture_source_ids, resolve_review_objects

FORMAT = 'BASIC-CLOTHING-REVIEW-2'
ERROR = 'modified retained review scene; preserve your edits and rerun clothing checks'


def _identities(scene):
    bindings = scene.get('_basic_clothing_review_bindings')
    if not bindings:
        raise ValueError('retained review integrity state is missing; rerun clothing checks')
    objects = list(bindings.values())
    if any(obj is None for obj in objects) or set(objects) != set(scene.objects):
        raise ValueError(ERROR)
    return {obj: identity for identity, obj in bindings.items()}


def _state(scene, identities):
    if any(obj.type not in {'MESH', 'ARMATURE'} or obj.data is None for obj in identities):
        raise ValueError(ERROR)
    return {'format': FORMAT, 'frame': [scene.frame_current, scene.frame_subframe],
            'unit_scale': scene.unit_settings.scale_length,
            'report_objects': {key: identities[obj] for obj, key in resolve_review_objects(scene).items()},
            'objects': fingerprint_inputs(list(identities), identities, review=True)}


def accept_review_state(scene, *, initialize=False):
    """Only call after complete successful controlled evaluation/replay writes."""
    if initialize:
        identities = capture_source_ids(scene.objects)
        scene['_basic_clothing_review_bindings'] = {identity: obj for obj, identity in identities.items()}
    else:
        identities = _identities(scene)
    scene['_basic_clothing_review_state'] = json.dumps(_state(scene, identities), sort_keys=True, allow_nan=False)


def validate_review_state(scene):
    identities = _identities(scene)
    try:
        accepted = json.loads(scene.get('_basic_clothing_review_state', ''))
    except (TypeError, ValueError):
        raise ValueError('retained review integrity state is missing; rerun clothing checks') from None
    if accepted != _state(scene, identities):
        raise ValueError(ERROR)
