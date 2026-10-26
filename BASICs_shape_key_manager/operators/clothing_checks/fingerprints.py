"""Full source fingerprints with bulk native numeric reads and binary hashing."""
from array import array
import hashlib
import json
import sys
import bpy

FINGERPRINT_FORMAT = 'BASIC-CLOTHING-BINARY-2'


def _block_ids(source_ids):
    identities = dict(source_ids or {})
    for obj, identity in (source_ids or {}).items():
        identities[obj.data] = identity + ':data'
        if obj.type == 'MESH' and obj.data.shape_keys:
            identities[obj.data.shape_keys] = identity + ':keys'
    return identities


def _reference(block, identities):
    if block is not None and isinstance(block, bpy.types.Action):
        return _action_state(block)
    return identities.get(block, block.name_full) if block else None


def evaluate_sources(objects):
    """Materialize owning graphs without switching windows, selection or frames."""
    choices, updated = [], set()
    def update(scene, layer):
        if (scene, layer) not in updated:
            with bpy.context.temp_override(scene=scene, view_layer=layer):
                layer.update()
            updated.add((scene, layer))
    for obj in dict.fromkeys(objects):
        owners = list(obj.users_scene)
        if not owners:
            raise ValueError('source object is not linked to an owning scene: ' + obj.name)
        scene = bpy.context.scene if bpy.context.scene in owners else owners[0]
        candidates = list(dict.fromkeys(([bpy.context.view_layer] if scene == bpy.context.scene else []) + list(scene.view_layers)))
        choices.append((obj, scene, candidates))
    # Layer object membership is itself lazy immediately after native linking.
    for _, scene, candidates in choices:
        update(scene, candidates[0])
    for obj, scene, candidates in choices:
        for layer in candidates:
            update(scene, layer)
            if obj.name in layer.objects:
                break
        else:
            raise ValueError('source object has no evaluable owning view layer: ' + obj.name)


def _properties(block, identities):
    def plain(value):
        if isinstance(value, bpy.types.ID):
            return {'id': _reference(value, identities), 'type': value.bl_rna.identifier}
        if hasattr(value, 'items'):
            return {str(k): plain(v) for k, v in value.items()}
        if hasattr(value, 'to_list'):
            return value.to_list()
        return value
    return {k: plain(v) for k, v in block.items()}


def _rna_settings(value, exclude=()):
    """Native curve/driver modifier authoring fields, including envelope collections."""
    result = {}
    for prop in value.bl_rna.properties:
        if (prop.identifier in exclude or prop.identifier == 'rna_type' or prop.type == 'POINTER' or
                prop.is_readonly and prop.type != 'COLLECTION'):
            continue
        item = getattr(value, prop.identifier)
        if prop.type == 'COLLECTION':
            result[prop.identifier] = [_rna_settings(entry) for entry in item]
        elif getattr(prop, 'is_array', False):
            result[prop.identifier] = list(item)
        elif isinstance(item, set):
            result[prop.identifier] = sorted(item)
        elif isinstance(item, (str, bool, int, float)):
            result[prop.identifier] = item
    return result


def bone_deformation_state(data):
    """Rest/deformation semantics shared by captured-rig compatibility and staleness.

    Writable Bone RNA includes inheritance, envelopes and B-Bone authoring fields.
    Ignore creator display/selection/collection state; keep named handle references
    without object/datablock identity so independently labelled copies still match.
    """
    display = {'name', 'children', 'collections', 'color', 'display_type', 'show_wire',
               'hide', 'hide_select', 'select', 'select_head', 'select_tail', 'layers', 'bbone_x', 'bbone_z'}
    return [{'name': bone.name, 'parent': bone.parent.name if bone.parent else None,
             'matrix_local': [list(row) for row in bone.matrix_local], 'length': bone.length,
             'use_connect': bone.use_connect, 'settings': _rna_settings(bone, display),
             'handles': {end: handle.name if (handle := getattr(bone, 'bbone_custom_handle_' + end, None)) else None
                         for end in ('start', 'end')}}
            for bone in sorted(data.bones, key=lambda item: item.name)]


def _curve_settings(curve):
    return [_rna_settings(curve), [[modifier.type, _rna_settings(modifier)] for modifier in curve.modifiers]]


def action_curves(action):
    """Read Blender 4.3 legacy actions and newer layered channelbags."""
    layers = getattr(action, 'layers', ())
    if not layers:
        return list(getattr(action, 'fcurves', ()))
    curves = []
    for layer in layers:
        for strip in layer.strips:
            for slot in action.slots:
                bag = strip.channelbag(slot)
                if bag:
                    curves.extend(bag.fcurves)
    return curves


def _curve_state(curve):
    return [curve.data_path, curve.array_index, curve.extrapolation, _curve_settings(curve),
            bool(getattr(getattr(curve, 'group', None), 'mute', False)),
            [[list(k.co), list(k.handle_left), list(k.handle_right), k.interpolation]
             for k in curve.keyframe_points]]


def _action_state(action):
    """Semantic Action payload v2, independent of creator labels and native handles."""
    slots = list(getattr(action, 'slots', ()))
    layers = getattr(action, 'layers', ())
    return {'format': 'BASIC-CLOTHING-ACTION-2',
            'settings': [getattr(action, name, None) for name in
                         ('use_frame_range', 'frame_start', 'frame_end', 'use_cyclic')],
            'slot_types': [slot.target_id_type for slot in slots],
            'layers': [{'settings': [getattr(layer, name, None) for name in ('influence', 'mix_mode')],
                        'strips': [[[_curve_state(curve) for curve in bag.fcurves] if
                         (bag := strip.channelbag(slot)) else [] for slot in slots]
                        for strip in layer.strips]} for layer in layers],
            'legacy_curves': [] if layers else [_curve_state(curve) for curve in action_curves(action)]}


def _animation(block, identities):
    animation = block.animation_data
    if not animation:
        return None
    drivers = []
    for curve in animation.drivers:
        drivers.append([curve.data_path, curve.array_index, curve.mute, curve.driver.type,
                        curve.driver.expression, curve.driver.use_self, _curve_settings(curve), [[v.name, v.type, [[
                            _reference(t.id, identities), t.data_path,
                            t.bone_target, t.transform_type, t.transform_space, t.rotation_mode]
                            for t in v.targets]] for v in curve.driver.variables]])
    action, state = animation.action, None
    if action:
        state = _action_state(action)
        slots, slot = list(getattr(action, 'slots', ())), getattr(animation, 'action_slot', None)
        state['assignment'] = [slots.index(slot) if slot in slots else None] + [
            getattr(animation, name, None) for name in
            ('action_blend_type', 'action_extrapolation', 'action_influence', 'use_nla')]
    return [state, [], drivers]


def _feed(digest, label, values):
    if sys.byteorder != 'little':
        values.byteswap()
    payload = memoryview(values).cast('B')
    digest.update(label.encode() + b'\0' + len(payload).to_bytes(8, 'little'))
    digest.update(payload)


def _bulk(digest, label, collection, attribute, width, code='f'):
    values = array(code, [0]) * (len(collection) * width)
    collection.foreach_get(attribute, values)
    _feed(digest, label, values)


def _fingerprint(obj, identities, *, review=False):
    digest = hashlib.sha256(FINGERPRINT_FORMAT.encode() + b'\0')
    values = {'type': obj.type, 'matrix': [list(r) for r in obj.matrix_world],
              'properties': _properties(obj, identities), 'data_properties': _properties(obj.data, identities),
              'parent': _reference(obj.parent, identities),
              'parent_type': obj.parent_type, 'parent_bone': obj.parent_bone,
              'parent_inverse': [list(r) for r in obj.matrix_parent_inverse],
              'animation': _animation(obj, identities),
              'modifiers': [[m.type, m.show_viewport, m.show_render,
                             _reference(m.object, identities) if m.type == 'ARMATURE' else None,
                             m.use_vertex_groups if m.type == 'ARMATURE' else None,
                             m.use_bone_envelopes if m.type == 'ARMATURE' else None,
                             m.use_deform_preserve_volume if m.type == 'ARMATURE' else None,
                             m.vertex_group if m.type == 'ARMATURE' else None,
                             m.invert_vertex_group if m.type == 'ARMATURE' else None,
                             m.use_multi_modifier if m.type == 'ARMATURE' else None] for m in obj.modifiers],
              'constraints': [c.type for c in obj.constraints]}
    if obj.type == 'MESH':
        mesh = obj.data
        _bulk(digest, 'vertices', mesh.vertices, 'co', 3)
        _bulk(digest, 'edges', mesh.edges, 'vertices', 2, 'i')
        _bulk(digest, 'loop_vertices', mesh.loops, 'vertex_index', 1, 'i')
        _bulk(digest, 'polygon_starts', mesh.polygons, 'loop_start', 1, 'i')
        _bulk(digest, 'polygon_sizes', mesh.polygons, 'loop_total', 1, 'i')
        face_attributes = [a for a in mesh.attributes if a.domain == 'FACE' and
                           not (review and a.name in {'.select_poly', '.hide_poly'})]
        values['face_attributes'] = [[a.name, a.domain, a.data_type] for a in face_attributes]
        for attribute in face_attributes:
            if attribute.domain == 'FACE' and attribute.data_type in {'BOOLEAN', 'INT'}:
                _bulk(digest, 'face:' + attribute.name, attribute.data, 'value', 1, 'i')
        counts, groups, weights = array('i'), array('i'), array('f')
        for vertex in mesh.vertices:
            counts.append(len(vertex.groups))
            for group in vertex.groups:
                groups.append(group.group)
                weights.append(group.weight)
        for label, payload in [('weight_counts', counts), ('weight_groups', groups), ('weights', weights)]:
            _feed(digest, label, payload)
        values.update(groups=[[g.name, g.lock_weight] for g in obj.vertex_groups], data_animation=_animation(mesh, identities))
        if mesh.shape_keys:
            values['shape_display'] = [obj.show_only_shape_key,
                obj.active_shape_key_index if obj.show_only_shape_key or not review else None]
            animation = mesh.shape_keys.animation_data
            driven = {curve.data_path for curve in animation.drivers if not curve.mute} if animation else set()
            # Active driver outputs are derived state; their authored inputs are hashed above/below.
            values['keys'] = [[k.name, None if k.path_from_id('value') in driven else k.value,
                               k.mute, k.slider_min, k.slider_max,
                               k.relative_key.name, k.vertex_group] for k in mesh.shape_keys.key_blocks]
            for index, key in enumerate(mesh.shape_keys.key_blocks):
                _bulk(digest, f'shape:{index}', key.data, 'co', 3)
            values['key_animation'] = _animation(mesh.shape_keys, identities)
            values['key_properties'] = _properties(mesh.shape_keys, identities)
            values['relative'] = mesh.shape_keys.use_relative
    if obj.type == 'ARMATURE':
        values['bones'] = bone_deformation_state(obj.data)
        values['pose'] = [[p.name, [list(r) for r in p.matrix_basis], p.bbone_curveinx, p.bbone_curveoutx,
                           p.bbone_curveinz, p.bbone_curveoutz, p.bbone_rollin, p.bbone_rollout,
                           list(p.bbone_scalein), list(p.bbone_scaleout), [c.type for c in p.constraints]]
                          for p in obj.pose.bones]
        values['data_animation'] = _animation(obj.data, identities)
        values['pose_position'] = obj.data.pose_position
    digest.update(json.dumps(values, sort_keys=True, allow_nan=False).encode())
    return digest.hexdigest()


def fingerprint(obj, source_ids=None):
    evaluate_sources([obj])
    return _fingerprint(obj, _block_ids(source_ids))


def fingerprint_inputs(objects, source_ids=None, *, review=False):
    objects = list(dict.fromkeys(objects))
    evaluate_sources(objects)
    identities = _block_ids(source_ids)
    return {source_ids[obj] if source_ids is not None else obj.name_full: _fingerprint(obj, identities, review=review)
            for obj in objects}
