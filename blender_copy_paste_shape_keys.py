bl_info = {
    "name": "Shape Key Manager",
    "author": "AI Assistant",
    "version": (1, 1),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > Shape Keys",
    "description": "Copy, cut, paste and mirror shape keys between objects",
    "category": "Mesh",
}

import bpy
import json
import numpy as np
from bpy.props import FloatProperty, BoolProperty, EnumProperty, PointerProperty

# Global variable to store copied shape key data
copied_shape_keys = {}

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

def unregister_properties():
    del bpy.types.Scene.shapekey_transfer_strength
    del bpy.types.Scene.shapekey_transfer_clear_existing
    del bpy.types.Scene.shapekey_transfer_skip_minimal
    del bpy.types.Scene.shapekey_transfer_threshold

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
    bl_label = "Execute Transfer"
    bl_options = {'REGISTER', 'UNDO'}
    
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
    
    def calculate_deformation_amount(self, obj, basis_coords, deformed_coords):
        """Calculate how much the mesh has deformed from basis to deformed state"""
        if len(basis_coords) != len(deformed_coords):
            return 0.0
            
        # Calculate max displacement across all vertices
        max_displacement = 0.0
        total_displacement = 0.0
        
        for i in range(len(basis_coords)):
            base = basis_coords[i]
            deformed = deformed_coords[i]
            
            # Calculate distance between base and deformed positions
            displacement = np.linalg.norm(np.array(deformed) - np.array(base))
            max_displacement = max(max_displacement, displacement)
            total_displacement += displacement
            
        avg_displacement = total_displacement / len(basis_coords) if basis_coords else 0
        
        return max_displacement, avg_displacement
    
    def execute(self, context):
        target = context.active_object
        sources = [obj for obj in context.selected_objects if obj != target and obj.type == 'MESH' and obj.data.shape_keys]
        
        if not sources:
            self.report({'ERROR'}, "No valid source objects with shape keys selected")
            return {'CANCELLED'}
            
        source = sources[0]  # Use the first valid source
        
        # Get the transfer settings from the scene properties
        strength = context.scene.shapekey_transfer_strength
        clear_existing = context.scene.shapekey_transfer_clear_existing
        skip_minimal_effect = context.scene.shapekey_transfer_skip_minimal
        deformation_threshold = context.scene.shapekey_transfer_threshold
        
        # Clear existing shape keys if needed
        if clear_existing and target.data.shape_keys:
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
            
            # Make sure to update the mesh after resetting all keys to zero
            context.view_layer.update()
        
        # Remember original target state
        original_target_modifiers = []
        for mod in target.modifiers:
            original_target_modifiers.append((mod.name, mod.show_viewport))
            # Disable all modifiers to avoid interference
            mod.show_viewport = False
        
        # Store the original vertex positions of the target mesh before any deformation
        original_coords = [v.co.copy() for v in target.data.vertices]
        
        # Add Surface Deform modifier to target
        surface_deform = target.modifiers.new(name="SurfaceDeform", type='SURFACE_DEFORM')
        surface_deform.target = source
        surface_deform.show_viewport = True
        
        # Make sure all vertex groups are cleared to avoid binding issues
        for vg in target.vertex_groups:
            target.vertex_groups.remove(vg)
        
        # We need to ensure we're in object mode for this
        original_mode = context.object.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Make sure both objects are visible and selectable
        source_hide = source.hide_get()
        source_select = source.hide_select
        target_hide = target.hide_get()
        target_select = target.hide_select
        
        source.hide_set(False)
        source.hide_select = False
        target.hide_set(False)
        target.hide_select = False
        
        # Force a scene update before binding
        context.view_layer.update()
        
        # Set the right context for binding - using the new temp_override system for Blender 4.x
        bind_success = False
        try:
            # First attempt with the new context override system (Blender 4.x+)
            with context.temp_override(
                object=target,
                active_object=target,
                selected_objects=[target],
                selected_editable_objects=[target]
            ):
                bpy.ops.object.surfacedeform_bind(modifier=surface_deform.name)
                bind_success = True
        except Exception as e:
            self.report({'WARNING'}, f"Error binding Surface Deform: {str(e)}")
            # Try a fallback method - sometimes binding directly works
            try:
                # Set active object
                context.view_layer.objects.active = target
                # Select only the target
                for obj in context.selected_objects:
                    obj.select_set(False)
                target.select_set(True)
                
                # Try binding again
                bpy.ops.object.surfacedeform_bind(modifier=surface_deform.name)
                bind_success = True
            except Exception as fallback_error:
                self.report({'ERROR'}, f"Fallback binding also failed: {str(fallback_error)}")
                bind_success = False
        
        # Restore visibility and selectability
        source.hide_set(source_hide)
        source.hide_select = source_select
        target.hide_set(target_hide)
        target.hide_select = target_select
        
        # If binding failed, clean up and exit
        if not bind_success:
            # Clean up
            target.modifiers.remove(surface_deform)
            # Restore modifier visibility
            for mod_name, mod_visibility in original_target_modifiers:
                if mod_name in target.modifiers:
                    target.modifiers[mod_name].show_viewport = mod_visibility
            # Restore original shape key values on source
            for key_name, value in stored_values.items():
                if key_name in source.data.shape_keys.key_blocks:
                    source.data.shape_keys.key_blocks[key_name].value = value
            # Return to original mode
            bpy.ops.object.mode_set(mode=original_mode)
            return {'CANCELLED'}
        
        # Force immediate mesh update to capture binding
        context.view_layer.update()
        context.view_layer.depsgraph.update()
        
        # Transfer each shape key
        transferred_count = 0
        skipped_count = 0
        
        # If there's a shape key, get the basis shape for correct comparison
        if target.data.shape_keys:
            basis_key = target.data.shape_keys.key_blocks['Basis']
        
        for key in source.data.shape_keys.key_blocks:
            if key.name != 'Basis':
                # Reset all shape keys to zero first
                for reset_key in source.data.shape_keys.key_blocks:
                    if reset_key.name != 'Basis':
                        reset_key.value = 0.0
                
                # Set only this shape key to maximum value
                key.value = strength
                
                # Force update to ensure the modifier has updated the mesh
                context.view_layer.update()
                context.view_layer.depsgraph.update()
                
                # Evaluate if this shape key causes deformation
                skip_this_key = False
                deformed_verts = None
                
                if skip_minimal_effect:
                    # Get current deformed vertex coordinates
                    # We need the actual data from the depsgraph for accurate evaluation
                    depsgraph = context.evaluated_depsgraph_get()
                    evaluated_obj = target.evaluated_get(depsgraph)
                    
                    # Get deformed coordinates
                    deformed_coords = [evaluated_obj.data.vertices[i].co.copy() for i in range(len(target.data.vertices))]
                    
                    # Store for later use
                    deformed_verts = deformed_coords
                    
                    # Calculate deformation metrics against original coordinates
                    max_displacement, avg_displacement = self.calculate_deformation_amount(
                        target, original_coords, deformed_coords)
                    
                    # Skip if below threshold
                    if max_displacement < deformation_threshold:
                        self.report({'INFO'}, f"Skipping shape key {key.name} (max displacement: {max_displacement:.6f})")
                        key.value = 0.0
                        skipped_count += 1
                        skip_this_key = True
                else:
                    # Get the deformed vertices for capture
                    depsgraph = context.evaluated_depsgraph_get()
                    evaluated_obj = target.evaluated_get(depsgraph)
                    deformed_verts = [evaluated_obj.data.vertices[i].co.copy() for i in range(len(target.data.vertices))]
                
                if not skip_this_key:
                    # Use direct mesh data manipulation for more reliable shape key creation
                    # First create a new shape key
                    new_key = target.shape_key_add(name=f"temp_{key.name}")
                    new_key.interpolation = 'KEY_LINEAR'
                    
                    # Then manually set its vertex positions from the evaluated mesh
                    for i, co in enumerate(deformed_verts):
                        new_key.data[i].co = co
                    
                    # Rename to match source
                    new_key.name = key.name
                    
                    transferred_count += 1
                
                # Reset source shape key value
                key.value = 0.0
                
                # Force update again
                context.view_layer.update()
        
        # Restore original shape key values on source
        for key_name, value in stored_values.items():
            if key_name in source.data.shape_keys.key_blocks:
                source.data.shape_keys.key_blocks[key_name].value = value
        
        # Remove the Surface Deform modifier
        target.modifiers.remove(surface_deform)
        
        # Restore original modifier visibility
        for mod_name, mod_visibility in original_target_modifiers:
            if mod_name in target.modifiers:
                target.modifiers[mod_name].show_viewport = mod_visibility
        
        # Return to original mode
        bpy.ops.object.mode_set(mode=original_mode)
        
        if skipped_count > 0:
            self.report({'INFO'}, f"Transferred {transferred_count} shape keys from {source.name} to {target.name} (skipped {skipped_count} with minimal effect)")
        else:
            self.report({'INFO'}, f"Transferred {transferred_count} shape keys from {source.name} to {target.name}")
        
        return {'FINISHED'}

class SHAPEKEY_OT_mirror(bpy.types.Operator):
    """Mirror the selected shape key to create a new shape key for the opposite side"""
    bl_idname = "shapekey.mirror"
    bl_label = "Mirror Shape Key"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        # Check if an object is selected, it's a mesh, has shape keys, and an active shape key is selected
        return (obj and obj.type == 'MESH' and obj.data.shape_keys
                and obj.active_shape_key_index > 0)  # Index 0 is Basis
    
    def execute(self, context):
        obj = context.active_object
        shape_keys = obj.data.shape_keys.key_blocks
        active_key = obj.active_shape_key
        active_key_name = active_key.name
        
        # Check if we have a Basis shape key
        if 'Basis' not in shape_keys:
            self.report({'ERROR'}, "No Basis shape key found")
            return {'CANCELLED'}
        
        basis_key = shape_keys['Basis']
        
        # Determine if the active key name has L/R designation
        # Check for common patterns: NameL, Name_L, Name.L, Name-L, NameLeft, etc.
        import re
        
        # Try to detect side designation
        left_patterns = [r'([a-zA-Z0-9]+)L$', r'([a-zA-Z0-9]+)[._-]L$', r'([a-zA-Z0-9]+)Left$', r'([a-zA-Z0-9]+)[._-]Left$']
        right_patterns = [r'([a-zA-Z0-9]+)R$', r'([a-zA-Z0-9]+)[._-]R$', r'([a-zA-Z0-9]+)Right$', r'([a-zA-Z0-9]+)[._-]Right$']
        
        base_name = None
        from_side = None
        to_side = None
        
        # Check if it's a left-side shape key
        for pattern in left_patterns:
            match = re.match(pattern, active_key_name)
            if match:
                base_name = match.group(1)
                from_side = 'L'
                to_side = 'R'
                break
                
        # If not found, check if it's a right-side shape key
        if not base_name:
            for pattern in right_patterns:
                match = re.match(pattern, active_key_name)
                if match:
                    base_name = match.group(1)
                    from_side = 'R'
                    to_side = 'L'
                    break
        
        # If we couldn't determine the side, ask user to name it properly
        if not base_name:
            self.report({'WARNING'}, "Could not determine side from shape key name. Use naming like 'SmileL' or 'Smile_R'")
            # Still proceed with X-axis mirroring but keep same name with "Mirror" suffix
            base_name = active_key_name
            new_key_name = f"{active_key_name}_Mirror"
        else:
            # Create the name for the new shape key (same pattern as original)
            if active_key_name.endswith(from_side):
                new_key_name = base_name + to_side
            elif '_' in active_key_name:
                new_key_name = base_name + '_' + to_side
            elif '.' in active_key_name:
                new_key_name = base_name + '.' + to_side
            elif '-' in active_key_name:
                new_key_name = base_name + '-' + to_side
            elif 'Left' in active_key_name:
                new_key_name = base_name + 'Right'
            elif 'Right' in active_key_name:
                new_key_name = base_name + 'Left'
            else:
                new_key_name = base_name + to_side
        
        # Check if the shape key with the new name already exists
        if new_key_name in shape_keys:
            # Ask user if they want to overwrite
            self.report({'WARNING'}, f"Shape key '{new_key_name}' already exists. Using suffix to create a unique name.")
            new_key_name = f"{new_key_name}_Mirror"
            # Check again with the modified name
            if new_key_name in shape_keys:
                i = 1
                while f"{new_key_name}_{i}" in shape_keys:
                    i += 1
                new_key_name = f"{new_key_name}_{i}"
        
        # Create a new shape key
        new_key = obj.shape_key_add(name=new_key_name, from_mix=False)
        new_key.interpolation = active_key.interpolation
        
        # Access the mesh vertices directly
        mesh = obj.data
        
        # First, copy the basis shape key to the new shape key
        for i in range(len(mesh.vertices)):
            new_key.data[i].co = basis_key.data[i].co
        
        # Create a lookup dictionary for mirrored vertices
        # Strategy: Find vertices that have the opposite X coordinate but similar Y,Z coordinates
        # This approach handles non-perfectly mirrored meshes better
        
        # First, create a dictionary of all vertices with their coordinates
        from mathutils import Vector
        
        # Group vertices by their X sign (left/right of the center)
        left_vertices = []  # X < 0
        right_vertices = []  # X > 0
        center_vertices = []  # X ≈ 0
        
        # Small threshold for center vertices
        center_threshold = 0.0001
        
        # Sorting vertices based on X coordinate sign
        for i in range(len(mesh.vertices)):
            x_coord = basis_key.data[i].co.x
            if abs(x_coord) < center_threshold:
                center_vertices.append(i)
            elif x_coord < 0:
                left_vertices.append(i)
            else:
                right_vertices.append(i)
        
        # Build the mirror mapping
        mirror_map = {}
        
        # Center vertices mirror to themselves
        for i in center_vertices:
            mirror_map[i] = i
        
        # Find matches between left and right vertices
        source_vertices = left_vertices if from_side == 'L' else right_vertices
        target_vertices = right_vertices if from_side == 'L' else left_vertices
        
        for src_idx in source_vertices:
            src_co = basis_key.data[src_idx].co
            
            # Find the vertex on the other side with mirrored X and similar Y/Z
            best_match_idx = None
            best_match_distance = float('inf')
            
            for tgt_idx in target_vertices:
                tgt_co = basis_key.data[tgt_idx].co
                
                # Check if this is a potential mirror (opposite X, similar Y,Z)
                y_z_distance = ((src_co.y - tgt_co.y) ** 2 + (src_co.z - tgt_co.z) ** 2) ** 0.5
                x_mirror_distance = abs(abs(src_co.x) - abs(tgt_co.x))
                
                # Combined distance metric (prioritize Y,Z match)
                total_distance = y_z_distance * 10 + x_mirror_distance
                
                if total_distance < best_match_distance:
                    best_match_distance = total_distance
                    best_match_idx = tgt_idx
            
            # If we found a match, add it to the mapping
            if best_match_idx is not None:
                mirror_map[src_idx] = best_match_idx
        
        # Count vertices we'll be mirroring
        mapped_count = len([k for k, v in mirror_map.items() if k != v])
        self.report({'INFO'}, f"Found {mapped_count} vertices to mirror from {len(source_vertices)} source vertices")
        
        # Only modify vertices on the TARGET side of the mesh
        # This is critical to ensure we're not changing the entire mesh
        modified_vertices = set()  # Keep track of vertices we've modified
        mirrored_count = 0
        
        # For each vertex on the target side, check if we need to update it
        for tgt_idx in target_vertices:
            # Find the corresponding source vertex (if any)
            src_idx = None
            for s, t in mirror_map.items():
                if t == tgt_idx:
                    src_idx = s
                    break
            
            if src_idx is not None:
                # Get the displacement from basis in the original shape key
                basis_co = basis_key.data[src_idx].co
                active_co = active_key.data[src_idx].co
                displacement = active_co - basis_co
                
                # Skip vertices with no displacement (not affected by shape key)
                if displacement.length < 0.0001:
                    continue
                    
                # Mirror the displacement - we flip the X component for mirroring
                mirrored_displacement = Vector((-displacement.x, displacement.y, displacement.z))
                
                # Target basis coordinate
                target_basis_co = basis_key.data[tgt_idx].co
                
                # Apply the mirrored displacement to the target vertex
                new_key.data[tgt_idx].co = target_basis_co + mirrored_displacement
                modified_vertices.add(tgt_idx)
                mirrored_count += 1
        
        # Set the new shape key as active
        obj.active_shape_key_index = obj.data.shape_keys.key_blocks.find(new_key_name)
        
        self.report({'INFO'}, f"Created mirrored shape key '{new_key_name}' (mirrored {mirrored_count} vertices)")
        
        self.report({'INFO'}, f"Created mirrored shape key: {new_key_name}")
        return {'FINISHED'}

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
                
                # Add mirror button if there's an active shape key
                if obj.active_shape_key_index > 0:  # Index 0 is Basis
                    row = col.row()
                    row.operator(SHAPEKEY_OT_mirror.bl_idname)
                
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
            box.label(text="Shape Key Transfer")
            
            # Source & target info
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
                    
                    # Show transfer settings in the panel
                    col = box.column(align=True)
                    col.prop(context.scene, "shapekey_transfer_strength", slider=True)
                    col.prop(context.scene, "shapekey_transfer_clear_existing")
                    col.prop(context.scene, "shapekey_transfer_skip_minimal")
                    
                    # Only show threshold if skip_minimal_effect is enabled
                    if context.scene.shapekey_transfer_skip_minimal:
                        col.prop(context.scene, "shapekey_transfer_threshold", slider=True)
                    
                    # Transfer button
                    col = box.column(align=True)
                    has_sources_with_shapekeys = any(s.data.shape_keys for s in sources if s.type == 'MESH')
                    if has_sources_with_shapekeys:
                        col.operator(SHAPEKEY_OT_transfer_with_surface_deform.bl_idname)
                    else:
                        col.label(text="Source has no shape keys")
        else:
            layout.label(text="Select a mesh object")

classes = (
    SHAPEKEY_OT_copy,
    SHAPEKEY_OT_cut,
    SHAPEKEY_OT_paste,
    SHAPEKEY_OT_save,
    SHAPEKEY_OT_load,
    SHAPEKEY_OT_mirror,
    SHAPEKEY_OT_transfer_with_surface_deform,
    SHAPEKEY_PT_manager,
)

def register():
    register_properties()
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    unregister_properties()

if __name__ == "__main__":
    register()