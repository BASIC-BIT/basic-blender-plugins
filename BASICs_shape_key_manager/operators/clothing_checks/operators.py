"""Cancellable native commands, retained report navigation and JSON export."""
from pathlib import Path
import json
import bpy
from bpy.app.handlers import persistent
from bpy_extras.io_utils import ExportHelper
from ...core.clothing_motion import seed_cases
from .authoring import inputs_from_ui, read_report, classes as authoring_classes
from .session import ValidationSession
from .preview import preview_failure, clear_preview, clear_all_previews
from .inputs import remove_scene
from .reporting import persist
from .identities import retained_review_scene

_jobs = {}


class BASIC_OT_run_clothing_checks(bpy.types.Operator):
    bl_idname = 'basic.run_clothing_checks'
    bl_label = 'Run clothing pose checks'
    calibration: bpy.props.BoolProperty(default=False)

    def _start(self, context):
        if _jobs:
            raise ValueError('a clothing check is already running')
        body, rig, pairs, mapping, settings = inputs_from_ui(context)
        if self.calibration:
            settings.pop('replay_coverage', None)
            settings['cases'] = [case for case in seed_cases(['HEAD_HANDS'], budget=1000, steps=3)
                if case['shape_case'] == 'current' and
                (case['motion'], case['t']) in [('neutral', 0), ('reach_forward', .5), ('torso_bend', .5)]]
            settings['budget'], settings['profiles'] = 3, ['HEAD_HANDS']
            settings['families'] = ['neutral', 'reach', 'torso']
        self._source_scene = context.scene
        self._worker = ValidationSession(context, body, rig, pairs, mapping, settings)
        self._timer = None
        _jobs[self.as_pointer()] = self

    def _finish(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        report = self._worker.report
        if 'text' not in report:
            persist(report, None)
        settings = self._source_scene.clothing_checks
        settings.report_text = report['text']
        settings.status = report['status']
        scene = retained_review_scene(report, required=False)
        if scene:
            scene.clothing_checks.report_text = report['text']
        _jobs.pop(self.as_pointer(), None)
        if self.calibration and report['status'] == 'COMPLETED':
            preview_failure(context, report)
        return {'FINISHED'} if report['status'] == 'COMPLETED' else {'CANCELLED'}

    def execute(self, context):
        try:
            self._start(context)
            while not self._worker.step():
                pass
            return self._finish(context)
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

    def invoke(self, context, event):
        try:
            self._start(context)
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self._timer = context.window_manager.event_timer_add(.05, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self._worker.cancel()
            return self._finish(context)
        if event.type == 'TIMER':
            if self._worker.step():
                return self._finish(context)
            report = self._worker.report
            self._source_scene.clothing_checks.status = (
                f"{len(report['cases'])}/{self._worker.settings['budget']} cases, "
                f"{len(self._worker.queue)} queued, {report['summary']['invalid']} invalid")
            for area in context.screen.areas:
                area.tag_redraw()
        return {'PASS_THROUGH'}

    def cancel(self, context):
        self._worker.cancel()
        self._finish(context)


class BASIC_OT_cancel_clothing_checks(bpy.types.Operator):
    bl_idname = 'basic.cancel_clothing_checks'
    bl_label = 'Cancel clothing checks'

    def execute(self, context):
        for job in list(_jobs.values()):
            job._worker.cancel()
        return {'FINISHED'}


class BASIC_OT_preview_clothing_failure(bpy.types.Operator):
    bl_idname = 'basic.preview_clothing_failure'
    bl_label = 'Preview saved pair pose and affected faces'

    def execute(self, context):
        options = context.scene.clothing_checks
        try:
            report = read_report(options)
            scene = preview_failure(context, report, options.result_index, options.preview_side)
            scene.clothing_checks.report_text = report['text']
            scene.clothing_checks.result_index = options.result_index
            scene.clothing_checks.preview_side = options.preview_side
            return {'FINISHED'}
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class BASIC_OT_clear_clothing_preview(bpy.types.Operator):
    bl_idname = 'basic.clear_clothing_preview'
    bl_label = 'Return to source view'

    def execute(self, context):
        clear_preview(context)
        return {'FINISHED'}


class BASIC_OT_export_clothing_report(bpy.types.Operator, ExportHelper):
    bl_idname = 'basic.export_clothing_report'
    bl_label = 'Export clothing JSON report'
    filename_ext = '.json'
    filter_glob: bpy.props.StringProperty(default='*.json', options={'HIDDEN'})

    def execute(self, context):
        try:
            report = read_report(context.scene.clothing_checks)
            Path(bpy.path.abspath(self.filepath)).write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
            return {'FINISHED'}
        except (ValueError, OSError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class BASIC_OT_remove_clothing_review(bpy.types.Operator):
    bl_idname = 'basic.remove_clothing_review'
    bl_label = 'Remove this generated review'
    bl_description = 'Explicitly delete this report and its owned review scene, preserving all sources and other reviews'

    def execute(self, context):
        try:
            report = read_report(context.scene.clothing_checks)
            clear_preview(context)
            scene = retained_review_scene(report, required=False)
            if scene:
                if context.window.scene == scene:
                    raise ValueError('return to a source scene before removing the review')
                if scene.get('_basic_clothing_owner') != report['id']:
                    raise ValueError('review ownership does not match this report')
                remove_scene(scene, report['id'])
            text = bpy.data.texts.get(report['text'])
            if text:
                bpy.data.texts.remove(text)
            return {'FINISHED'}
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


@persistent
def cleanup_jobs(*_):
    clear_all_previews()
    for job in list(_jobs.values()):
        job.cancel(bpy.context)
    for scene in list(bpy.data.scenes):
        if scene.get('_basic_clothing_kind') == 'JOB':
            remove_scene(scene, scene['_basic_clothing_owner'])


classes = authoring_classes + (BASIC_OT_run_clothing_checks, BASIC_OT_cancel_clothing_checks,
    BASIC_OT_preview_clothing_failure, BASIC_OT_clear_clothing_preview,
    BASIC_OT_export_clothing_report, BASIC_OT_remove_clothing_review)
