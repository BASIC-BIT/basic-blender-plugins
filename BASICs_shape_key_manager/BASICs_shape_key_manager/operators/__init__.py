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
from .vertex_group_ops import VERTEXGROUP_OT_combine_groups
from .mesh_mirror_ops import MESH_OT_force_mirror

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
    VERTEXGROUP_OT_combine_groups,
    MESH_OT_force_mirror,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
