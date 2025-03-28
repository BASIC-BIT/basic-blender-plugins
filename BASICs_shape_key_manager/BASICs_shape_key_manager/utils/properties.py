import bpy
from bpy.props import FloatProperty, BoolProperty

# Define scene properties for persistent settings
def register_properties():
    bpy.types.Scene.shapekey_transfer_strength = FloatProperty(
        name="Shape Key Strength",
        description="Strength to apply when creating shape keys",
        default=1.0,
        min=0.0,
        max=10.0
    )
    
    bpy.types.Scene.shapekey_transfer_clear_existing = BoolProperty(
        name="Clear Existing Shape Keys",
        description="Remove existing shape keys on target mesh before transfer",
        default=True
    )
    
    bpy.types.Scene.shapekey_transfer_skip_minimal = BoolProperty(
        name="Skip Non-Effective Shape Keys",
        description="Skip shape keys that don't meaningfully deform the target mesh",
        default=True
    )
    
    bpy.types.Scene.shapekey_transfer_threshold = FloatProperty(
        name="Deformation Threshold",
        description="Minimum vertex displacement required to consider a shape key effective (in Blender units)",
        default=0.001,
        min=0.0001,
        max=1.0,
        precision=4
    )
    
    # Mirror shape key properties
    bpy.types.Scene.shapekey_mirror_tolerance = FloatProperty(
        name="Mirror Tolerance",
        description="Maximum distance allowed between mirrored vertices (in Blender units)",
        default=0.001,
        min=0.0001,
        max=1.0,
        precision=4
    )
    
    # Mesh mirror properties
    bpy.types.Scene.mesh_mirror_show_advanced = BoolProperty(
        name="Show Advanced Options",
        description="Show or hide advanced mesh mirroring options",
        default=False
    )
    
    bpy.types.Scene.mesh_mirror_center_tolerance = FloatProperty(
        name="Center Tolerance",
        description="Maximum distance from center to consider a vertex as 'center' (in Blender units)",
        default=0.0001,
        min=0.00001,
        max=0.1,
        precision=5
    )
    
    bpy.types.Scene.mesh_mirror_move_center_vertices = BoolProperty(
        name="Move Center Vertices to X=0",
        description="Force vertices within center tolerance to be exactly at X=0",
        default=True
    )

def unregister_properties():
    del bpy.types.Scene.shapekey_transfer_strength
    del bpy.types.Scene.shapekey_transfer_clear_existing
    del bpy.types.Scene.shapekey_transfer_skip_minimal
    del bpy.types.Scene.shapekey_transfer_threshold
    del bpy.types.Scene.shapekey_mirror_tolerance
    del bpy.types.Scene.mesh_mirror_show_advanced
    del bpy.types.Scene.mesh_mirror_center_tolerance
    del bpy.types.Scene.mesh_mirror_move_center_vertices 