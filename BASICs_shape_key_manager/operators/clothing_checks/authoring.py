"""Native baseline, pair, mapping and shape case authoring commands."""
import json
import bpy
from ...utils.clothing_checks_properties import mapping_signature
from .baseline import capture_baseline
from .inputs import logical_id
from .identities import resolve_bindings
from .reporting import parse_report
from .rig import CANONICAL_BONES, OPTIONAL_BONES, suggest_mapping
from ...core.clothing_motion import LIBRARY_VERSION


def read_report(settings):
    text = bpy.data.texts.get(settings.report_text)
    if text is None:
        raise ValueError('choose an existing report Text datablock')
    return parse_report(text.as_string())


def inputs_from_ui(context):
    options = context.scene.clothing_checks
    if (not options.mapping_confirmed or options.confirmed_rig != options.rig or
            options.confirmed_mapping != mapping_signature(options)):
        raise ValueError('confirm the mapping before running')
    mapping = {row.canonical: row.bone for row in options.mapping}
    pairs = [dict(reference=r.reference, candidate=r.candidate, confirmed=r.confirmed) for r in options.pairs]
    if options.replay:
        previous = read_report(options)
        settings = previous['settings']
        if settings.get('motion_library_version') != LIBRARY_VERSION:
            raise ValueError('motion library changed; start a new run instead of replaying legacy cases')
        settings.setdefault('utility_groups', {})
        settings['cases'] = previous['cases']
        settings['replay_coverage'] = previous['coverage']
        return options.body, options.rig, pairs, mapping, settings
    valid_pairs = [pair for pair in pairs if pair['reference'] and pair['candidate']]
    body_id, pair_ids = resolve_bindings(options.body, valid_pairs) if options.body else (None, [])
    identities = {obj: identity for pair, identity in zip(valid_pairs, pair_ids)
                  for obj in (pair['reference'], pair['candidate'])}
    if options.body:
        identities[options.body] = body_id
    shapes = {}
    for row in options.shapes:
        if row.object is None or not row.key or not row.case or row.case == 'current':
            raise ValueError('shape row requires a mesh, key and non-current combination name')
        shapes.setdefault(row.case, {}).setdefault(identities.get(row.object, logical_id(row.object)), {})[row.key] = row.value
    settings = {key: getattr(options, key) for key in ('budget', 'refinement_depth', 'contact_m',
                'clearance_m', 'worsening_m', 'sample_limit')}
    settings.update(profiles=[name for name, enabled in [('HEAD_HANDS', options.head_hands),
                    ('FULL_BODY', options.full_body)] if enabled], families=sorted(options.families),
                    bend_directions=json.loads(options.bend_directions),
                    accessory_bones=json.loads(options.accessory_bones),
                    region_definitions=json.loads(options.region_definitions),
                    contact_allowances=json.loads(options.contact_allowances),
                    utility_groups=json.loads(options.utility_groups),
                    shape_cases=[{'id': 'current', 'values': {}}] +
                                [{'id': name, 'values': values} for name, values in shapes.items()])
    settings['motion_library_version'] = LIBRARY_VERSION
    return options.body, options.rig, pairs, mapping, settings


class BASIC_OT_capture_clothing_baseline(bpy.types.Operator):
    bl_idname = 'basic.capture_clothing_baseline'
    bl_label = 'Capture selected outfit baseline'
    bl_description = 'Freeze independent native copies of selected garments before editing'

    def execute(self, context):
        options = context.scene.clothing_checks
        clothing = [o for o in context.selected_objects if o.type == 'MESH' and o != options.body]
        try:
            result = capture_baseline(context, options.body, options.rig, clothing)
            options.pairs.clear()
            for pair in result['pairs']:
                row = options.pairs.add()
                row.reference, row.candidate = bpy.data.objects[pair['reference']], bpy.data.objects[pair['candidate']]
                row.confirmed = True
            self.report({'INFO'}, 'Baseline captured in ' + result['scene'])
            return {'FINISHED'}
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class BASIC_OT_edit_clothing_inputs(bpy.types.Operator):
    bl_idname = 'basic.edit_clothing_inputs'
    bl_label = 'Edit clothing inputs'
    action: bpy.props.EnumProperty(items=[('PAIR', 'Add pair', ''), ('REMOVE_PAIR', 'Remove pair', ''),
                ('SUGGEST', 'Suggest mapping', ''), ('SHAPE', 'Add shape endpoint', ''),
                ('REMOVE_SHAPE', 'Remove shape', '')])
    index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        settings = context.scene.clothing_checks
        if self.action == 'PAIR':
            settings.pairs.add()
        elif self.action == 'REMOVE_PAIR' and 0 <= self.index < len(settings.pairs):
            settings.pairs.remove(self.index)
        elif self.action == 'SUGGEST':
            if not settings.rig:
                self.report({'ERROR'}, 'Choose a rig first')
                return {'CANCELLED'}
            suggestions = suggest_mapping(settings.rig)
            settings.mapping.clear()
            for name in CANONICAL_BONES + OPTIONAL_BONES:
                row = settings.mapping.add()
                row.canonical, row.bone = name, suggestions.get(name, '')
            settings.mapping_confirmed = False
        elif self.action == 'SHAPE':
            obj = context.object
            if not obj or obj.type != 'MESH' or not obj.active_shape_key or obj.active_shape_key_index == 0:
                self.report({'ERROR'}, 'Select a garment or body shape key endpoint')
                return {'CANCELLED'}
            row = settings.shapes.add()
            row.object, row.key = obj, obj.active_shape_key.name
            row.value = obj.active_shape_key.slider_max
            row.case = obj.name + ':' + row.key
        elif self.action == 'REMOVE_SHAPE' and 0 <= self.index < len(settings.shapes):
            settings.shapes.remove(self.index)
        return {'FINISHED'}


classes = (BASIC_OT_capture_clothing_baseline, BASIC_OT_edit_clothing_inputs)
