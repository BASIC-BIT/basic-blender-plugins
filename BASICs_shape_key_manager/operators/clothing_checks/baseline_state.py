"""Immutable owned baseline closure, accepted only by explicit capture."""
import json
from .fingerprints import fingerprint_inputs
from .identities import capture_source_ids

ERROR = 'modified retained baseline; preserve it and capture a new independent baseline'


def _state(scene, identities):
    return {'format': 'BASIC-CLOTHING-BASELINE-1',
            'frame': [scene.frame_current, scene.frame_subframe],
            'unit_scale': scene.unit_settings.scale_length,
            'objects': fingerprint_inputs(list(identities), identities, review=True)}


def capture_baseline_state(scene):
    identities = capture_source_ids(scene.objects)
    scene['_basic_clothing_baseline_objects'] = {identity: obj for obj, identity in identities.items()}
    scene['_basic_clothing_baseline_state'] = json.dumps(_state(scene, identities), sort_keys=True, allow_nan=False)


def validate_baseline_state(scene):
    bindings, accepted = scene.get('_basic_clothing_baseline_objects'), scene.get('_basic_clothing_baseline_state')
    if not bindings or not accepted:
        raise ValueError('baseline integrity state is missing; recapture an independent baseline from frozen geometry')
    if any(obj is None for obj in bindings.values()) or set(bindings.values()) != set(scene.objects):
        raise ValueError(ERROR)
    identities = {obj: identity for identity, obj in bindings.items()}
    if any(obj.type not in {'MESH', 'ARMATURE'} or obj.data is None for obj in identities):
        raise ValueError(ERROR)
    try:
        saved = json.loads(accepted)
    except (ValueError, TypeError):
        raise ValueError(ERROR) from None
    if saved != _state(scene, identities):
        raise ValueError(ERROR)
