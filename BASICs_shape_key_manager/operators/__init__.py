import bpy
from .basic_ops import (
    SHAPEKEY_OT_copy,
    SHAPEKEY_OT_cut,
    SHAPEKEY_OT_paste,
    SHAPEKEY_OT_save,
    SHAPEKEY_OT_load
)
from .mirror_ops import (
    SHAPEKEY_OT_mirror,
    SHAPEKEY_OT_mirror_all_missing
)
from .transfer_ops import SHAPEKEY_OT_transfer_with_surface_deform
from .edit_ops import SHAPEKEY_OT_remove_selected_vertices
from .smooth_ops import SHAPEKEY_OT_heuristic_smooth
from .vertex_group_ops import (
    VERTEXGROUP_OT_combine_groups,
    VERTEXGROUP_OT_remove_empty,
    VERTEXGROUP_OT_robust_weight_transfer
)
from .weights.refit import VERTEXGROUP_OT_refit_clothing_weights
from .clothing_checks.operators import classes as clothing_classes, cleanup_jobs
from .mesh_mirror_ops import MESH_OT_force_mirror
from .mesh_select_ops import MESH_OT_select_nearby_vertices
from .polyloop_ops import (
    MESH_OT_preview_polyloop_reduction,
    MESH_OT_dissolve_polyloop_candidate,
    MESH_OT_reduce_polyloop_to_target,
)
from .armature_ops import (
    ARMATURE_OT_delete_other_bones,
    ARMATURE_OT_remove_unweighted_bones,
    ARMATURE_OT_roll_selected_weights_to_parent,
    ARMATURE_OT_check_fix_modifiers
)

# List of all operator classes
classes = (
    SHAPEKEY_OT_copy,
    SHAPEKEY_OT_cut,
    SHAPEKEY_OT_paste,
    SHAPEKEY_OT_save,
    SHAPEKEY_OT_load,
    SHAPEKEY_OT_mirror,
    SHAPEKEY_OT_mirror_all_missing,
    SHAPEKEY_OT_transfer_with_surface_deform,
    SHAPEKEY_OT_remove_selected_vertices,
    SHAPEKEY_OT_heuristic_smooth,
    VERTEXGROUP_OT_combine_groups,
    VERTEXGROUP_OT_remove_empty,
    VERTEXGROUP_OT_robust_weight_transfer,
    VERTEXGROUP_OT_refit_clothing_weights,
    MESH_OT_force_mirror,
    MESH_OT_select_nearby_vertices,
    MESH_OT_preview_polyloop_reduction,
    MESH_OT_dissolve_polyloop_candidate,
    MESH_OT_reduce_polyloop_to_target,
    ARMATURE_OT_delete_other_bones,
    ARMATURE_OT_remove_unweighted_bones,
    ARMATURE_OT_roll_selected_weights_to_parent,
    ARMATURE_OT_check_fix_modifiers,
)

def register():
    for cls in (*classes, *clothing_classes):
        bpy.utils.register_class(cls)
    if cleanup_jobs not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(cleanup_jobs)

def unregister():
    cleanup_jobs()
    if cleanup_jobs in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(cleanup_jobs)
    for cls in reversed((*classes, *clothing_classes)):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
