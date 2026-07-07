bl_info = {
    "name": "BASICs Shape Key Manager",
    "author": "BASICBIT",
    "version": (1, 2),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > Shape Keys",
    "description": "Copy, cut, paste and mirror shape keys between objects",
    "category": "Mesh",
}

import bpy
from .globals import copied_shape_keys
from . import core
from . import operators
from . import ui
from . import utils

def register():
    utils.register_properties()
    operators.register()
    ui.register()

def unregister():
    ui.unregister()
    operators.unregister()
    utils.unregister_properties()

if __name__ == "__main__":
    register()
