"""BASIC Developer layout for explicit clothing checks and native evidence."""
import bpy
from functools import lru_cache
from types import MappingProxyType
from ..operators.clothing_checks.reporting import parse_report


@lru_cache(maxsize=1)
def panel_report(payload):
    """Cache one validated display projection by exact Text contents, never commands."""
    try:
        report = parse_report(payload)
        return MappingProxyType({'status': report['status'],
            'summary': MappingProxyType({key: value for key, value in report['summary'].items()
                                        if isinstance(value, (str, int, float, bool))}),
            'weight_findings': sum(not audit['valid'] for audit in report.get('weights', {}).values()),
            'errors': tuple(report.get('errors', [])),
            'results': tuple(MappingProxyType({'case_id': row['case_id'], 'pair': tuple(row['pair']),
                            'regression': row['regression'],
                            'candidate': MappingProxyType({'absolute_fit': row['candidate']['absolute_fit']})})
                             for row in report['results'])})
    except (ValueError, KeyError) as exc:
        return str(exc)


def _action(layout, text, action, index=-1, icon='NONE'):
    op = layout.operator('basic.edit_clothing_inputs', text=text, icon=icon)
    op.action, op.index = action, index


def _results(layout, settings):
    layout.prop_search(settings, 'report_text', bpy.data, 'texts')
    text = bpy.data.texts.get(settings.report_text)
    if text is None:
        panel_report.cache_clear()
        return
    try:
        report = panel_report(text.as_string())
        if isinstance(report, str):
            raise ValueError(report)
        summary = report['summary']
    except (ValueError, KeyError) as exc:
        layout.label(text='Invalid clothing report: ' + str(exc), icon='ERROR')
        return
    layout.label(text='Run: ' + report['status'])
    layout.label(text='Coverage: ' + summary['coverage'])
    layout.label(text='Regression: ' + summary['regression'])
    layout.label(text='Absolute fit: ' + summary['absolute_fit'])
    if 'actionable_fit' in summary:
        layout.label(text='Actionable fit: ' + summary['actionable_fit'])
        layout.label(text=f"{summary['allowed_findings']} allowed, {summary['actionable_findings']} actionable findings")
    if 'absolute_unique_faces' in summary:
        layout.label(text=f"{summary['absolute_unique_faces']} unique absolute pair/object/faces")
        layout.label(text=f"{summary['absolute_crossing_faces']} crossing, {summary['absolute_contained_faces']} contained face observations")
    layout.label(text=f"{summary['new_faces']} new, {summary['existing_faces']} existing, {summary['worsened_faces']} worsened faces")
    layout.label(text=f"{summary['invalid']} invalid or self-crossing poses, {summary['unknown']} unknown pair results")
    layout.label(text=f"{report['weight_findings']} garments have weight audit findings")
    for error in report.get('errors', []):
        layout.label(text=error, icon='ERROR')
    layout.prop(settings, 'result_index')
    if settings.result_index < len(report['results']):
        result = report['results'][settings.result_index]
        layout.label(text=result['case_id'])
        layout.label(text=' / '.join(result['pair']))
        layout.label(text=f"{result['regression']}, {result['candidate']['absolute_fit']}")
    layout.prop(settings, 'preview_side', expand=True)
    layout.operator('basic.preview_clothing_failure', text='Preview absolute findings in saved pose')
    layout.operator('basic.clear_clothing_preview')
    layout.operator('basic.export_clothing_report')
    layout.operator('basic.remove_clothing_review', icon='TRASH')


class BASIC_PT_developer(bpy.types.Panel):
    bl_label = 'Developer'
    bl_idname = 'BASIC_PT_developer'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BASIC'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        self.layout.label(text='Diagnostics and generated review data')


class BASIC_PT_clothing_pose_checks(bpy.types.Panel):
    bl_label = 'Clothing Pose Checks'
    bl_idname = 'BASIC_PT_clothing_pose_checks'
    bl_parent_id = 'BASIC_PT_developer'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BASIC'

    def draw(self, context):
        layout, settings = self.layout, context.scene.clothing_checks
        layout.label(text='Synthetic IK approximation. No runtime parity.')
        layout.label(text='Open volumes and sparse probes stay unknown.')
        box = layout.box()
        box.prop(settings, 'body')
        box.prop(settings, 'rig')
        box.operator('basic.capture_clothing_baseline')
        for index, pair in enumerate(settings.pairs):
            row = box.box()
            row.prop(pair, 'reference')
            row.prop(pair, 'candidate')
            row.prop(pair, 'confirmed')
            _action(row, 'Remove pair', 'REMOVE_PAIR', index, 'X')
        _action(box, 'Add external pair', 'PAIR', icon='ADD')
        box = layout.box()
        _action(box, 'Suggest mapping (requires confirmation)', 'SUGGEST')
        if settings.rig:
            for row in settings.mapping:
                box.prop_search(row, 'bone', settings.rig.data, 'bones', text=row.canonical)
        box.prop(settings, 'mapping_confirmed')
        box.prop(settings, 'bend_directions')
        box.prop(settings, 'accessory_bones')
        box.prop(settings, 'region_definitions')
        box.prop(settings, 'contact_allowances')
        box.prop(settings, 'utility_groups')
        box.label(text='Regions use captured IDs and fixed FACE attributes')
        op = box.operator('basic.run_clothing_checks', text='Preview neutral / reach / bend calibration')
        op.calibration = True
        box = layout.box()
        box.prop(settings, 'head_hands')
        box.prop(settings, 'full_body')
        box.prop(settings, 'families')
        box.label(text='Captured current shape combination always included')
        for index, row in enumerate(settings.shapes):
            shape = box.box()
            shape.prop(row, 'case')
            shape.prop(row, 'object')
            if row.object and row.object.data.shape_keys:
                shape.prop_search(row, 'key', row.object.data.shape_keys, 'key_blocks')
            shape.prop(row, 'value')
            _action(shape, 'Remove shape case', 'REMOVE_SHAPE', index, 'X')
        _action(box, 'Add active shape endpoint', 'SHAPE', icon='ADD')
        box.label(text='Use one combination name to group selected endpoints')
        for name in ('budget', 'refinement_depth', 'contact_m', 'clearance_m', 'worsening_m', 'sample_limit', 'replay'):
            box.prop(settings, name)
        layout.operator('basic.run_clothing_checks')
        layout.operator('basic.cancel_clothing_checks')
        layout.label(text=settings.status)
        _results(layout.box(), settings)


classes = (BASIC_PT_developer, BASIC_PT_clothing_pose_checks)
