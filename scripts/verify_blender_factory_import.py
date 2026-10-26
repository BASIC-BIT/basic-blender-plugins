"""Verify the installed extension can be imported from factory startup."""

import importlib


module = importlib.import_module(
    "bl_ext.user_default.basics_shape_key_manager.operators.armature_ops")
refit = importlib.import_module(
    "bl_ext.user_default.basics_shape_key_manager.operators.weights.refit")
clothing = importlib.import_module(
    "bl_ext.user_default.basics_shape_key_manager.operators.clothing_checks.session")
checks = {
    "clothing_session": hasattr(clothing, "ValidationSession"),
    "clothing_sync": hasattr(clothing, "run_validation"),
    "clothing_refit": hasattr(refit, "VERTEXGROUP_OT_refit_clothing_weights"),
    "bone_cleanup": hasattr(module, "ARMATURE_OT_remove_unweighted_bones"),
    "modifier_repair": hasattr(module, "ARMATURE_OT_check_fix_modifiers"),
}
print("BASIC_FACTORY_IMPORT_CHECKS=" + repr(checks))
failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise RuntimeError("Factory import checks failed: " + ", ".join(failed))
print("BASIC_FACTORY_IMPORT_SMOKE_PASS")
