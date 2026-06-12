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
from .mesh_mirror_ops import MESH_OT_force_mirror
from .armature_ops import (
    ARMATURE_OT_delete_other_bones,
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
    MESH_OT_force_mirror,
    ARMATURE_OT_delete_other_bones,
    ARMATURE_OT_check_fix_modifiers,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()