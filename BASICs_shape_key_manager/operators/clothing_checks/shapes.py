"""Read effective native key values after drivers and enforce requested cases."""
from math import isclose


def effective_shapes(context, scene, objects):
    with context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        scene.view_layers[0].update()
        graph = context.evaluated_depsgraph_get()
        return {obj.name: {key.name: (0. if key.mute else float(key.value))
                           for key in obj.data.shape_keys.evaluated_get(graph).key_blocks}
                for obj in objects if obj.type == 'MESH' and obj.data.shape_keys}


def requested_mismatches(objects, requested, effective):
    mismatches = []
    for obj in objects:
        identity = obj.get('_basic_clothing_id')
        for name, value in requested.get(identity, {}).items():
            actual = effective.get(obj.name, {}).get(name)
            if actual is None or not isclose(value, actual, rel_tol=1e-6, abs_tol=1e-6):
                mismatches.append({'object': obj.name, 'object_id': identity,
                                   'role': obj.get('_basic_clothing_role'), 'key': name,
                                   'requested': value, 'effective': actual})
    return mismatches
