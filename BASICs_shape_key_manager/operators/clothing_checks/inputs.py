"""Read-only preflight, content fingerprints and owned dependency copies."""
import re
import threading
import bpy
from .fingerprints import fingerprint, fingerprint_inputs, evaluate_sources
from .identities import logical_id, resolve_bindings


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


def preflight(body, rig, pairs):
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
    rig_signature = lambda r: ([list(row) for row in r.matrix_world],
                               [(b.name, [list(row) for row in b.matrix_local], b.use_deform)
                                for b in r.data.bones])
    signature = rig_signature(rig)
    if any(rig_signature(target) != signature for target in rig_targets):
        raise ValueError('reference Armature modifier has incompatible rig rest frames')
    baselines = [ref['_basic_clothing_baseline_body'] for ref in references if ref.get('_basic_clothing_baseline_body')]
    if baselines:
        body_fingerprint = fingerprint(body)
        if any(value != body_fingerprint for value in baselines):
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
