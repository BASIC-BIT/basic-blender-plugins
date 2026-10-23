"""Verify the complete extension remains registered on normal startup."""

import sys

import bpy


module_name = "bl_ext.user_default.basics_shape_key_manager"
checks = {
    "clothing_panel": hasattr(bpy.types, "BASIC_PT_clothing_pose_checks"),
    "clothing_properties": hasattr(bpy.types.Scene, "clothing_checks"),
    "clothing_capture": hasattr(bpy.ops.basic, "capture_clothing_baseline"),
    "clothing_run": hasattr(bpy.ops.basic, "run_clothing_checks"),
    "clothing_cancel": hasattr(bpy.ops.basic, "cancel_clothing_checks"),
    "clothing_preview": hasattr(bpy.ops.basic, "preview_clothing_failure"),
    "clothing_restore": hasattr(bpy.ops.basic, "clear_clothing_preview"),
    "clothing_export": hasattr(bpy.ops.basic, "export_clothing_report"),
    "enabled": module_name in bpy.context.preferences.addons.keys(),
    "module_loaded": module_name in sys.modules,
    "panel": hasattr(bpy.types, "SHAPEKEY_PT_manager"),
    "mesh_preview": hasattr(bpy.ops.mesh, "preview_polyloop_reduction"),
    "mesh_apply": hasattr(bpy.ops.mesh, "dissolve_polyloop_candidate"),
    "bone_cleanup": hasattr(bpy.ops.armature, "remove_unweighted_bones"),
    "modifier_repair": hasattr(bpy.ops.armature, "check_fix_modifiers"),
    "weight_transfer": hasattr(
        bpy.ops.vertexgroup, "robust_weight_transfer"),
    "clothing_refit": hasattr(bpy.ops.vertexgroup, "refit_clothing_weights"),

}
for name in ('capture_clothing_baseline', 'edit_clothing_inputs', 'run_clothing_checks',
             'cancel_clothing_checks', 'preview_clothing_failure', 'clear_clothing_preview',
             'export_clothing_report', 'remove_clothing_review'):
    try:
        checks['rna_' + name] = bool(getattr(bpy.ops.basic, name).get_rna_type())
    except RuntimeError:
        checks['rna_' + name] = False
checks['clothing_settings_rna'] = bool(bpy.types.Scene.bl_rna.properties.get('clothing_checks'))
checks['clothing_developer_parent'] = (
    getattr(bpy.types.BASIC_PT_clothing_pose_checks, 'bl_parent_id', '') == 'BASIC_PT_developer')
print("BASIC_REGISTRATION_CHECKS=" + repr(checks))
failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise RuntimeError("Extension registration failed: " + ", ".join(failed))
print("BASIC_PLUGIN_STARTUP_SMOKE_PASS")
