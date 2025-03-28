import bpy
import numpy as np
from bpy.types import Operator

class SHAPEKEY_OT_transfer_with_surface_deform(Operator):
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
        
 