bl_info = {
    "name": "Shape Key Manager",
    "author": "AI Assistant",
    "version": (1, 0),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > Shape Keys",
    "description": "Copy, cut and paste shape key values between objects",
    "category": "Mesh",
}

import bpy
import json
from bpy.props import FloatProperty, BoolProperty, EnumProperty, PointerProperty

# Global variable to store copied shape key data
copied_shape_keys = {}

class SHAPEKEY_OT_copy(bpy.types.Operator):
    """Copy all shape key values from selected object"""
    bl_idname = "shapekey.copy_values"
    bl_label = "Copy Shape Key Values"
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.data.shape_keys
    
    def execute(self, context):
        global copied_shape_keys
        obj = context.active_object
        
        # Clear previous data
        copied_shape_keys = {}
        
        # Store shape key values
        if obj.data.shape_keys:
            for key in obj.data.shape_keys.key_blocks:
                # Skip the basis shape key (always at index 0)
                if key.name != 'Basis':
                    copied_shape_keys[key.name] = key.value
        
        self.report({'INFO'}, f"Copied {len(copied_shape_keys)} shape key values")
        return {'FINISHED'}

class SHAPEKEY_OT_cut(bpy.types.Operator):
    """Cut all shape key values from selected object (copy and set to zero)"""
    bl_idname = "shapekey.cut_values"
    bl_label = "Cut Shape Key Values"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.data.shape_keys
    
    def execute(self, context):
        global copied_shape_keys
        obj = context.active_object
        
        # Clear previous data
        copied_shape_keys = {}
        
        # Store shape key values and set to zero
        if obj.data.shape_keys:
            for key in obj.data.shape_keys.key_blocks:
                # Skip the basis shape key
                if key.name != 'Basis':
                    copied_shape_keys[key.name] = key.value
                    key.value = 0.0
        
        self.report({'INFO'}, f"Cut {len(copied_shape_keys)} shape key values")
        return {'FINISHED'}

class SHAPEKEY_OT_paste(bpy.types.Operator):
    """Paste copied shape key values to selected object"""
    bl_idname = "shapekey.paste_values"
    bl_label = "Paste Shape Key Values"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.data.shape_keys and copied_shape_keys
    
    def execute(self, context):
        obj = context.active_object
        pasted_count = 0
        
        if obj.data.shape_keys:
            for key in obj.data.shape_keys.key_blocks:
                if key.name in copied_shape_keys:
                    key.value = copied_shape_keys[key.name]
                    pasted_count += 1
        
        self.report({'INFO'}, f"Pasted {pasted_count} shape key values")
        return {'FINISHED'}

class SHAPEKEY_OT_save(bpy.types.Operator):
    """Save shape key values to a JSON file"""
    bl_idname = "shapekey.save_values"
    bl_label = "Save Shape Keys to File"
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.data.shape_keys
    
    def execute(self, context):
        obj = context.active_object
        data_to_save = {}
        
        if obj.data.shape_keys:
            for key in obj.data.shape_keys.key_blocks:
                if key.name != 'Basis':
                    data_to_save[key.name] = key.value
        
        with open(self.filepath, 'w') as f:
            json.dump(data_to_save, f, indent=4)
            
        self.report({'INFO'}, f"Saved {len(data_to_save)} shape keys to {self.filepath}")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class SHAPEKEY_OT_load(bpy.types.Operator):
    """Load shape key values from a JSON file"""
    bl_idname = "shapekey.load_values"
    bl_label = "Load Shape Keys from File"
    bl_options = {'REGISTER', 'UNDO'}
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and obj.data.shape_keys
    
    def execute(self, context):
        obj = context.active_object
        
        try:
            with open(self.filepath, 'r') as f:
                loaded_data = json.load(f)
            
            pasted_count = 0
            if obj.data.shape_keys:
                for key in obj.data.shape_keys.key_blocks:
                    if key.name in loaded_data:
                        key.value = loaded_data[key.name]
                        pasted_count += 1
            
            self.report({'INFO'}, f"Loaded {pasted_count} shape key values from file")
            
        except Exception as e:
            self.report({'ERROR'}, f"Error loading shape keys: {str(e)}")
            
        return {'FINISHED'}
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class SHAPEKEY_OT_transfer_with_surface_deform(bpy.types.Operator):
    """Transfer shape keys from source mesh to target mesh using Surface Deform modifier"""
    bl_idname = "shapekey.transfer_with_surface_deform"
    bl_label = "Transfer Shape Keys (Surface Deform)"
    bl_options = {'REGISTER', 'UNDO'}
    
    strength: FloatProperty(
        name="Shape Key Strength",
        description="Strength to apply when creating shape keys",
        default=1.0,
        min=0.0,
        max=10.0
    )
    
    clear_existing: BoolProperty(
        name="Clear Existing Shape Keys",
        description="Remove existing shape keys on target mesh before transfer",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        # We need at least two objects selected, both must be meshes
        if len(context.selected_objects) < 2:
            return False
        
        # Active object should be target
        target = context.active_object
        if not target or target.type != 'MESH':
            return False
            
        # Check at least one source has shape keys
        for obj in context.selected_objects:
            if obj != target and obj.type == 'MESH' and obj.data.shape_keys:
                return True
                
        return False
    
    def execute(self, context):
        target = context.active_object
        sources = [obj for obj in context.selected_objects if obj != target and obj.type == 'MESH' and obj.data.shape_keys]
        
        if not sources:
            self.report({'ERROR'}, "No valid source objects with shape keys selected")
            return {'CANCELLED'}
            
        source = sources[0]  # Use the first valid source
        
        # Clear existing shape keys if needed
        if self.clear_existing and target.data.shape_keys:
            # Store original active shape key index
            original_active_index = target.active_shape_key_index
            
            # Remove all shape keys
            while target.data.shape_keys:
                target.shape_key_remove(target.data.shape_keys.key_blocks[0])
        
        # Make sure target has basis shape key
        if not target.data.shape_keys:
            basis = target.shape_key_add(name="Basis")
            basis.interpolation = 'KEY_LINEAR'
        
        # Reset source shape keys to zero
        stored_values = {}
        if source.data.shape_keys:
            for key in source.data.shape_keys.key_blocks:
                if key.name != 'Basis':
                    stored_values[key.name] = key.value
                    key.value = 0.0
        
        # Add Surface Deform modifier to target
        surface_deform = target.modifiers.new(name="SurfaceDeform", type='SURFACE_DEFORM')
        surface_deform.target = source
        
        # Bind the Surface Deform modifier
        # We need to ensure we're in object mode for this
        original_mode = context.object.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Set the right context for binding
        override = context.copy()
        override["object"] = target
        override["active_object"] = target
        override["selected_objects"] = [target]
        override["selected_editable_objects"] = [target]
        
        # Bind the modifier
        bpy.ops.object.surfacedeform_bind(override, modifier=surface_deform.name)
        
        # Transfer each shape key
        transferred_count = 0
        
        for key in source.data.shape_keys.key_blocks:
            if key.name != 'Basis':
                # Set this shape key to maximum value
                key.value = self.strength
                
                # Apply as shape key on target
                new_key = target.shape_key_add(name=f"temp_{key.name}", from_mix=True)
                new_key.interpolation = 'KEY_LINEAR'
                
                # Rename to match source
                new_key.name = key.name
                
                # Reset source shape key value
                key.value = 0.0
                
                transferred_count += 1
        
        # Restore original shape key values on source
        for key_name, value in stored_values.items():
            if key_name in source.data.shape_keys.key_blocks:
                source.data.shape_keys.key_blocks[key_name].value = value
        
        # Remove the Surface Deform modifier
        target.modifiers.remove(surface_deform)
        
        # Return to original mode
        bpy.ops.object.mode_set(mode=original_mode)
        
        self.report({'INFO'}, f"Transferred {transferred_count} shape keys from {source.name} to {target.name}")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class SHAPEKEY_PT_manager(bpy.types.Panel):
    """Shape Key Manager Panel"""
    bl_label = "Shape Key Manager"
    bl_idname = "SHAPEKEY_PT_manager"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Shape Keys"
    
    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        
        if obj and obj.type == 'MESH':
            # Basic shape key operations section
            box = layout.box()
            box.label(text="Basic Operations")
            
            if obj.data.shape_keys:
                col = box.column(align=True)
                row = col.row(align=True)
                row.operator(SHAPEKEY_OT_copy.bl_idname)
                row.operator(SHAPEKEY_OT_cut.bl_idname)
                
                row = col.row()
                row.operator(SHAPEKEY_OT_paste.bl_idname)
                
                col.separator()
                
                row = col.row()
                row.operator(SHAPEKEY_OT_save.bl_idname)
                
                row = col.row()
                row.operator(SHAPEKEY_OT_load.bl_idname)
                
                # Display number of active shape keys
                num_keys = len(obj.data.shape_keys.key_blocks) - 1  # Subtract 1 for the Basis shape
                col.label(text=f"Active Shape Keys: {num_keys}")
            else:
                box.label(text="No Shape Keys on selected object")
            
            # Advanced shape key operations section
            box = layout.box()
            box.label(text="Advanced Operations")
            
            # Transfer shape keys section
            row = box.row()
            row.operator(SHAPEKEY_OT_transfer_with_surface_deform.bl_idname)
            
            # Help text for transfer
            if len(context.selected_objects) < 2:
                box.label(text="Select source then target (active)")
            else:
                sources = [o for o in context.selected_objects if o != obj and o.type == 'MESH']
                if sources:
                    source_names = ", ".join([s.name for s in sources[:3]])
                    if len(sources) > 3:
                        source_names += f" and {len(sources) - 3} more"
                    box.label(text=f"Source: {source_names}")
                    box.label(text=f"Target: {obj.name} (active)")
        else:
            layout.label(text="Select a mesh object")

classes = (
    SHAPEKEY_OT_copy,
    SHAPEKEY_OT_cut,
    SHAPEKEY_OT_paste,
    SHAPEKEY_OT_save,
    SHAPEKEY_OT_load,
    SHAPEKEY_OT_transfer_with_surface_deform,
    SHAPEKEY_PT_manager,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()