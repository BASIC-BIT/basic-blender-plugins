import bpy
from bpy.types import Operator
from bpy.props import BoolProperty

class SHAPEKEY_OT_remove_selected_vertices(Operator):
    """Remove selected vertices from shape keys by resetting them to basis position"""
    bl_idname = "shapekey.remove_selected_vertices"
    bl_label = "Remove Selected Vertices"
    bl_options = {'REGISTER', 'UNDO'}
    
    all_shape_keys: BoolProperty(
        name="All Shape Keys",
        description="Remove selected vertices from all shape keys",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        # Check if in edit mode, object is a mesh, and has shape keys
        return (obj and obj.type == 'MESH' and obj.mode == 'EDIT'
                and obj.data.shape_keys and len(obj.data.shape_keys.key_blocks) > 1)
    
    def execute(self, context):
        obj = context.active_object
        shape_keys = obj.data.shape_keys.key_blocks
        
        # Get the basis shape key
        basis_key = shape_keys[0]
        if basis_key.name != 'Basis':
            self.report({'ERROR'}, "First shape key is not named 'Basis'")
            return {'CANCELLED'}
        
        # Get selected vertices
        bpy.ops.object.mode_set(mode='OBJECT')  # Need to be in object mode to access selection
        selected_vertices = [v.index for v in obj.data.vertices if v.select]
        
        if not selected_vertices:
            bpy.ops.object.mode_set(mode='EDIT')  # Return to edit mode
            self.report({'WARNING'}, "No vertices selected")
            return {'CANCELLED'}
        
        # Determine which shape keys to process
        if self.all_shape_keys:
            keys_to_process = [key for key in shape_keys if key.name != 'Basis']
        else:
            # Only process the active shape key if it's not the basis
            active_key = obj.active_shape_key
            if active_key and active_key.name != 'Basis':
                keys_to_process = [active_key]
            else:
                bpy.ops.object.mode_set(mode='EDIT')  # Return to edit mode
                self.report({'WARNING'}, "Active shape key is Basis or not set")
                return {'CANCELLED'}
        
        # Reset selected vertices in each shape key to their basis position
        modified_count = 0
        for key in keys_to_process:
            for v_idx in selected_vertices:
                # Copy the basis position to the shape key
                key.data[v_idx].co = basis_key.data[v_idx].co
            modified_count += 1
        
        # Return to edit mode
        bpy.ops.object.mode_set(mode='EDIT')
        
        if self.all_shape_keys:
            self.report({'INFO'}, f"Removed selected vertices from {modified_count} shape keys")
        else:
            self.report({'INFO'}, f"Removed selected vertices from '{keys_to_process[0].name}'")
        
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "all_shape_keys") 