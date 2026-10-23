"""Read-only preflight, content fingerprints and owned dependency copies."""
import re
import threading
from math import sqrt
import bpy
from .fingerprints import fingerprint, fingerprint_inputs, evaluate_sources, bone_deformation_state, FINGERPRINT_FORMAT
from .identities import logical_id, resolve_bindings, read_source_ids
from .baseline_state import validate_baseline_state


def main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('clothing checks must run on the Blender main thread')


def data_blocks(objects):
    blocks = list(objects)
    for obj in objects:
        blocks.append(obj.data)
        if obj.type == 'MESH' and obj.data.shape_keys:
            blocks.append(obj.data.shape_keys)
    return list(dict.fromkeys(blocks))


def envelope_factor(bone, point):
    """Blender 5.1.2 armature_deform.cc unscaled distfactor_to_bone."""
    if not bone.use_envelope_multiply:
        return bone.evaluate_envelope(point)
    # RNA evaluate_envelope scales radii by envelope_weight with MULT_VG_ENV;
    # native modifier deformation uses unscaled radii in both influence paths.
    axis = bone.tail_local - bone.head_local
    length = axis.length
    if length:
        axis /= length
    offset = point - bone.head_local
    height = offset.dot(axis)
    if height < 0:
        distance_squared, radius = offset.length_squared, bone.head_radius
    elif height > length:
        distance_squared, radius = (point - bone.tail_local).length_squared, bone.tail_radius
    else:
        distance_squared = offset.length_squared - height * height
        radius = bone.head_radius + (bone.tail_radius - bone.head_radius) * (height / length if length else 0)
    if distance_squared < radius * radius:
        return 1.
    falloff = bone.envelope_distance
    if falloff == 0 or distance_squared >= (radius + falloff) ** 2:
        return 0.
    return 1. - (sqrt(distance_squared) - radius) ** 2 / (falloff * falloff)


def body_deforms(body, rig, posed_bones=None):
    """Require native positive influence, querying envelopes in rig rest space."""
    deform = {bone.name: bone for bone in rig.data.bones if bone.use_deform}
    eligible = set(deform)
    if posed_bones is not None:
        eligible = {name for name, bone in deform.items()
                    if any(parent.name in posed_bones for parent in (bone, *bone.parent_recursive))}
    groups = {group.index: deform[group.name] for group in body.vertex_groups if group.name in deform}
    unsupported = False
    for mod in body.modifiers:
        if mod.type != 'ARMATURE' or mod.object != rig or not mod.show_viewport:
            continue
        mask = body.vertex_groups.get(mod.vertex_group)
        for vertex in body.data.vertices:
            if mask:
                amount = next((g.weight for g in vertex.groups if g.group == mask.index), 0.)
                if (1 - amount if mod.invert_vertex_group else amount) <= 0:
                    continue
            weights = [(groups[g.group], g.weight) for g in vertex.groups
                       if mod.use_vertex_groups and g.group in groups]
            base = [(bone, weight) for bone, weight in weights if not bone.use_envelope_multiply]
            contribution = sum(weight for bone, weight in base)
            influence = sum(weight for bone, weight in base if bone.name in eligible)
            if contribution > .0001 and influence > 0:  # Native total contribution threshold.
                return True
            # Preserve every real VG assignment: even unposed assignments suppress fallback.
            if weights and not any(weight > 0 and bone.name in eligible for bone, weight in weights):
                continue
            needed = any(bone.use_envelope_multiply and weight > 0 for bone, weight in weights)
            if not needed and (weights or not mod.use_bone_envelopes):
                continue
            if body.data.shape_keys or mod.use_multi_modifier:
                unsupported = True
                continue
            point = rig.matrix_world.inverted() @ body.matrix_world @ vertex.co
            if weights:
                factors = [(bone, weight * envelope_factor(bone, point))
                           for bone, weight in weights if bone.use_envelope_multiply]
                contribution += sum(weight for bone, weight in factors)
                influence += sum(weight for bone, weight in factors if bone.name in eligible)
            else:
                factors = [(bone, bone.envelope_weight * envelope_factor(bone, point)) for bone in deform.values()]
                contribution = sum(weight for bone, weight in factors)
                influence = sum(weight for bone, weight in factors if bone.name in eligible)
            if contribution > .0001 and influence > 0:
                return True
    if unsupported:
        raise ValueError('body envelope reach with shape keys or multi-modifier input is unsupported; '
                         'use positive deform weights without envelope multiplication')
    return False


def preflight(body, rig, pairs, *, capturing=False, posed_bones=None):
    main_thread()
    if body is None or body.type != 'MESH' or rig is None or rig.type != 'ARMATURE':
        raise ValueError('choose a mesh body and an armature rig')
    if not isinstance(pairs, (list, tuple)) or not pairs:
        raise ValueError('select at least one reference/candidate pair')
    normalized, candidates, references = [], set(), set()
    for pair in pairs:
        if not isinstance(pair, dict):
            raise ValueError('pair requires reference, candidate and explicit confirmation')
        ref, candidate = pair.get('reference'), pair.get('candidate')
        if not ref or not candidate or ref.type != 'MESH' or candidate.type != 'MESH':
            raise ValueError('pair objects must be meshes')
        captured = ref.get('_basic_clothing_id') and ref.get('_basic_clothing_id') == candidate.get('_basic_clothing_id')
        if not captured and pair.get('confirmed') is not True:
            raise ValueError('confirm external object pairing explicitly')
        used = candidates | references
        if candidate in used or ref in used or body in (ref, candidate):
            raise ValueError('duplicate pair or body used as clothing')
        candidates.add(candidate)
        references.add(ref)
        topology = lambda o: (len(o.data.vertices), [tuple(p.vertices) for p in o.data.polygons])
        if topology(ref) != topology(candidate):
            raise ValueError('reference/candidate topology mismatch')
        normalized.append((ref, candidate, logical_id(ref) if ref.get('_basic_clothing_id') else logical_id(candidate)))
    _, identities = resolve_bindings(body, pairs)
    normalized = [(ref, candidate, identity) for (ref, candidate, _), identity in zip(normalized, identities)]
    if len({row[2] for row in normalized}) != len(normalized):
        raise ValueError('duplicate stable garment identities across pairs')
    baseline_scenes, checked = {}, set()
    if not capturing:
        for ref in references:
            owners = [s for s in ref.users_scene if s.get('_basic_clothing_kind') == 'BASELINE']
            retained = owners or any(ref.get(key) for key in ('_basic_clothing_baseline_body',
                '_basic_clothing_baseline_body_id', '_basic_clothing_fingerprint_format')) or (
                ref.get('_basic_clothing_owner') and ref.get('_basic_clothing_role') == 'REFERENCE')
            if not retained:
                continue
            scene = next((s for s in owners if s.get('_basic_clothing_owner') == ref.get('_basic_clothing_owner')), None)
            if (scene is None or not ref.get('_basic_clothing_baseline_body') or
                    ref.get('_basic_clothing_fingerprint_format') != FINGERPRINT_FORMAT):
                raise ValueError('retained baseline owner or metadata is missing/legacy; recapture an independent baseline')
            if scene not in checked:
                validate_baseline_state(scene)
                checked.add(scene)
            baseline_scenes[ref] = scene
    objects = list(dict.fromkeys([body, rig, *[o for row in normalized for o in row[:2]]]))
    baseline_dependencies = set()
    # A captured key driver may depend on the independently frozen body/rig.
    for ref in references:
        owner = ref.get('_basic_clothing_owner')
        if owner:
            for scene in ref.users_scene:
                if scene.get('_basic_clothing_kind') == 'BASELINE' and scene.get('_basic_clothing_owner') == owner:
                    for dependency in scene.objects:
                        if dependency.get('_basic_clothing_role') in {'BODY', 'RIG'} and dependency not in objects:
                            objects.append(dependency)
                            baseline_dependencies.add(dependency)
    rig_targets = set()
    for obj in list(objects):
        for mod in obj.modifiers:
            target = mod.object if mod.type == 'ARMATURE' else None
            if target and target != rig:
                if obj not in references and obj not in baseline_dependencies:
                    raise ValueError('reference Armature modifier has incompatible rig rest frames')
                rig_targets.add(target)
                if target not in objects:
                    objects.append(target)
    data_owners = {}
    for obj in objects:
        dependencies = [obj.data]
        if obj.type == 'MESH' and obj.data.shape_keys:
            dependencies.append(obj.data.shape_keys)
        for block in dependencies:
            if block in data_owners and data_owners[block] != obj:
                raise ValueError('shared source ' + block.bl_rna.identifier + ' data between ' +
                                 data_owners[block].name + ' and ' + obj.name + ' is unsupported; make the captured '
                                 'mesh/armature data single-user before capture')
            data_owners[block] = obj
    blocks = data_blocks(objects)
    for obj in objects:
        if obj.mode != 'OBJECT':
            raise ValueError('finish native mesh/pose editing in Object mode before capture')
        if obj.parent and obj.parent not in objects:
            raise ValueError('parent dependency is outside the captured closure')
        if obj.constraints or (obj.type == 'ARMATURE' and any(p.constraints for p in obj.pose.bones)):
            raise ValueError('source object and bone constraints are unsupported')
        if obj.instance_type != 'NONE' or obj.instance_collection or obj.particle_systems:
            raise ValueError('instances and particle dependencies are unsupported')
        for mod in obj.modifiers:
            if mod.type != 'ARMATURE' or mod.object not in objects:
                raise ValueError('only Armature modifiers targeting the selected rig are supported')
        if obj.type == 'MESH' and obj.data.shape_keys and not obj.data.shape_keys.use_relative:
            raise ValueError('absolute shape key evaluation is unsupported')
        if obj.type == 'MESH' and obj.data.shape_keys and obj.show_only_shape_key:
            raise ValueError('unpin the shape key on ' + obj.name +
                             ' before capture or validation; CURRENT uses the evaluated numeric blend')
        if obj.type == 'ARMATURE' and any(b.bbone_segments > 1 for b in obj.data.bones):
            raise ValueError('segmented B-Bone deformation is unsupported')
    for block in blocks:
        animation = block.animation_data
        if not animation:
            continue
        if animation.nla_tracks:
            raise ValueError('NLA animation dependencies are unsupported')
        for curve in animation.drivers:
            if (curve.driver.type == 'SCRIPTED' or isinstance(block, bpy.types.Armature) or
                    isinstance(block, bpy.types.Object) and block.type == 'ARMATURE'):
                raise ValueError('scripted or rig drivers are unsupported')
            for variable in curve.driver.variables:
                if variable.type not in {'SINGLE_PROP', 'TRANSFORMS'}:
                    raise ValueError('unsupported driver variable')
                for target in variable.targets:
                    if target.id not in blocks:
                        raise ValueError('driver target is outside the copied closure')
                    if variable.type == 'SINGLE_PROP':
                        try:
                            value = target.id.path_resolve(target.data_path)
                        except (ValueError, TypeError):
                            raise ValueError('unresolved driver target path') from None
                        direct = r'\["(?:[^"\\]|\\.)+"\]'
                        transform = r'(?:location|rotation_euler|rotation_quaternion|scale)(?:\[[0-3]\]|\.[xyzw])'
                        shape = r'key_blocks\["(?:[^"\\]|\\.)+"\]\.value'
                        if (not re.fullmatch(f'(?:{direct}|{transform}|{shape})', target.data_path) or
                                not isinstance(value, (int, float))):
                            raise ValueError('driver path requires a supported direct numeric property')
    # Native world matrices of freshly opened inactive scenes are lazy caches.
    # Validate supported dependencies first, then materialize before any comparison.
    evaluate_sources(objects)
    if not body_deforms(body, rig, posed_bones):
        raise ValueError('body requires a viewport-enabled Armature modifier targeting the selected rig '
                         'with positive deform weights or enabled bone envelopes' +
                         (' contributing to the posed mapping or its descendants' if posed_bones is not None else ''))
    rig_signature = lambda r: ([list(row) for row in r.matrix_world], r.data.pose_position,
                               bone_deformation_state(r.data))
    signature = rig_signature(rig)
    if any(rig_signature(target) != signature for target in rig_targets):
        raise ValueError('reference Armature modifier has incompatible rig deformation/rest data; recapture the baseline')
    validated = {}
    for ref, scene in baseline_scenes.items():
        if scene not in validated:
            validated[scene] = fingerprint(body, read_source_ids(scene))
        # Incremental captures each retain their own identity context.
        if ref['_basic_clothing_baseline_body'] != validated[scene]:
            raise ValueError('body changed after baseline capture; capture a separate body comparison')
    return normalized, objects


def owned_copies(scene, objects, owner):
    """Copy all native data and retarget every supported evaluating reference."""
    copies, blocks = {}, {}
    for obj in objects:
        clone = obj.copy()
        clone.data = obj.data.copy()
        clone.name = f'Clothing {owner[:8]} {obj.name}'
        clone['_basic_clothing_owner'] = owner
        clone['_basic_clothing_source'] = obj.name_full
        scene.collection.objects.link(clone)
        clone.hide_viewport, clone.hide_render = False, False
        clone.hide_set(False, view_layer=scene.view_layers[0])
        copies[obj], blocks[obj], blocks[obj.data] = clone, clone, clone.data
        if obj.type == 'MESH' and obj.data.shape_keys:
            blocks[obj.data.shape_keys] = clone.data.shape_keys
    for obj, clone in copies.items():
        world = obj.matrix_world.copy()
        clone.parent = copies.get(obj.parent)
        clone.matrix_world = world
        for mod in clone.modifiers:
            mod.object = copies[mod.object]
    for source, clone in blocks.items():
        retained = clone.get('basic_clothing_action')
        if isinstance(retained, bpy.types.Action):
            action = retained.copy()
            action['_basic_clothing_owner'] = owner
            clone['basic_clothing_action'] = action
        if not clone.animation_data:
            continue
        if clone.animation_data.action:
            # Preserve a native action copy for review, but evaluate captured current values.
            action = clone.animation_data.action.copy()
            action['_basic_clothing_owner'] = owner
            clone.animation_data.action = action
            clone['basic_clothing_action'] = action
            clone.animation_data.action = None
        for curve in clone.animation_data.drivers:
            for variable in curve.driver.variables:
                for target in variable.targets:
                    target.id = blocks[target.id]
    return copies


def remove_scene(scene, owner):
    """Delete only this session's generated data, including unused native actions."""
    for obj in list(scene.objects):
        if obj.get('_basic_clothing_owner') == owner:
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data and data.users == 0:
                (bpy.data.meshes if isinstance(data, bpy.types.Mesh) else bpy.data.armatures).remove(data)
    bpy.data.scenes.remove(scene)
    for action in list(bpy.data.actions):
        if action.get('_basic_clothing_owner') == owner and action.users == 0:
            bpy.data.actions.remove(action)
