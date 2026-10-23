"""Native report pose replay, face selection and source-view restoration."""
import bpy
from .inputs import fingerprint_inputs, main_thread
from .rig import apply_pose_matrices
from .shapes import effective_shapes
from .reporting import validate_report
from .identities import read_source_ids
from .fingerprints import FINGERPRINT_FORMAT

_views = {}


def preview_failure(context, report, result_index=0, side='CANDIDATE'):
    main_thread()
    if side not in {'REFERENCE', 'CANDIDATE'}:
        raise ValueError('preview side must be REFERENCE or CANDIDATE')
    validate_report(report)
    scene = bpy.data.scenes.get(report.get('review_scene', ''))
    if scene is None:
        raise ValueError('retained native review scene is missing')
    if report.get('fingerprint_format') != FINGERPRINT_FORMAT:
        raise ValueError('legacy report fingerprints; recapture the baseline and rerun')
    source_ids = read_source_ids(scene)
    if fingerprint_inputs(list(source_ids), source_ids) != report['inputs']:
        raise ValueError('stale preview: a source input changed or is missing')
    if not 0 <= result_index < len(report['results']):
        raise ValueError('choose a saved pair finding')
    if context.mode != 'OBJECT':
        raise ValueError('leave native Edit/Pose mode before preview')
    result = report['results'][result_index]
    pose = report['poses'][result['pose_index']]
    rig = next(o for o in scene.objects if o.get('_basic_clothing_role') == 'RIG')
    apply_pose_matrices(rig, pose['matrices'])
    for obj in scene.objects:
        role = obj.get('_basic_clothing_role')
        obj.hide_set(role == 'DEPENDENCY' or role in {'REFERENCE', 'CANDIDATE'} and role != side,
                     view_layer=scene.view_layers[0])
        if obj.type != 'MESH':
            continue
        info = report['objects'].get(obj.name, {})
        if obj.data.shape_keys:
            current = info.get('shape_current', {})
            values = pose['case']['shape_values'].get(info.get('id'), {})
            for key in obj.data.shape_keys.key_blocks:
                key.value = values.get(key.name, current.get(key.name, key.value))
        identity = info.get('id')
        analysis = result['reference' if side == 'REFERENCE' else 'candidate']
        faces = set(analysis['crossing_faces'].get(identity, [])) | set(analysis['contained_faces'].get(identity, []))
        for polygon in obj.data.polygons:
            polygon.select = polygon.index in faces
        obj.show_wire = bool(faces)
        obj.show_all_edges = bool(faces)
    window = context.window
    if window is None:
        raise ValueError('a native window is required for review preview')
    token = window.as_pointer()
    if token not in _views:
        _views[token] = (window.scene, window.view_layer, context.view_layer.objects.active,
                         list(context.selected_objects))
    window.scene = scene
    window.view_layer = scene.view_layers[0]
    for obj in scene.objects:
        obj.select_set(False)
    candidates = [o for o in scene.objects if o.type == 'MESH' and o.get('_basic_clothing_role') == side
                  and o.get('_basic_clothing_id') in result['pair']]
    for obj in candidates:
        obj.select_set(True)
    if candidates:
        window.view_layer.objects.active = candidates[0]
    scene.view_layers[0].update()
    effective = effective_shapes(context, scene, scene.objects)
    for name, keys in pose.get('effective_shape_values', {}).items():
        if any(abs(effective.get(name, {}).get(key, float('inf')) - value) > 1e-6 for key, value in keys.items()):
            clear_preview(context)
            raise ValueError('saved effective shape state could not be replayed for ' + name)
    return scene


def clear_preview(context):
    main_thread()
    window = context.window
    state = _views.pop(window.as_pointer(), None) if window else None
    if state:
        scene, layer, active, selection = state
        window.scene, window.view_layer = scene, layer
        for obj in layer.objects:
            obj.select_set(obj in selection)
        layer.objects.active = active


def clear_all_previews():
    for window in bpy.context.window_manager.windows:
        with bpy.context.temp_override(window=window):
            clear_preview(bpy.context)
