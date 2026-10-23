import bpy
from .panels import SHAPEKEY_PT_manager
from .clothing_checks_panel import classes as clothing_classes

# List of all panel classes
classes = (
    SHAPEKEY_PT_manager,
)

def register():
    for cls in (*classes, *clothing_classes):
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed((*classes, *clothing_classes)):
        bpy.utils.unregister_class(cls)
