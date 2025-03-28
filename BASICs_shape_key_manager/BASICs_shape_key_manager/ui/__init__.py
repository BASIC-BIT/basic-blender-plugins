import bpy
from .panels import SHAPEKEY_PT_manager

# List of all panel classes
classes = (
    SHAPEKEY_PT_manager,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
