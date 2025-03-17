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
from bpy.props import FloatProperty, BoolProperty, EnumProperty, PointerProperty, StringProperty
from mathutils import Vector

# Octree implementation for efficient 3D point search
class OctreeNode:
    """Node for Octree spatial partitioning structure"""
    def __init__(self, center, size, max_points=10, depth=0, max_depth=10):
        self.center = center  # Center of this node's cube
        self.size = size      # Half-width of the cube
        self.max_points = max_points  # Max points before subdivision
        self.max_depth = max_depth    # Maximum tree depth
        self.depth = depth    # Current depth
        self.points = []      # Points contained in this node
        self.vertex_indices = []  # Vertex indices for these points
        self.children = None  # Octants (will be list of 8 nodes if subdivided)
        self.is_leaf = True   # Whether this is a leaf node
    
    def get_octant_index(self, point):
        """Determine which octant the point belongs in"""
        # Return an index 0-7 for the correct octant
        index = 0
        if point[0] >= self.center[0]: index |= 4
        if point[1] >= self.center[1]: index |= 2
        if point[2] >= self.center[2]: index |= 1
        return index
    
    def subdivide(self):
        """Split this node into 8 child octants"""
        if not self.is_leaf:
            return
            
        # Create 8 child nodes
        self.is_leaf = False
        self.children = []
        new_size = self.size / 2
        
        # Create child nodes for all 8 octants
        for x_dir in [-1, 1]:
            for y_dir in [-1, 1]:
                for z_dir in [-1, 1]:
                    new_center = [
                        self.center[0] + x_dir * new_size,
                        self.center[1] + y_dir * new_size,
                        self.center[2] + z_dir * new_size
                    ]
                    self.children.append(OctreeNode(
                        new_center, new_size,
                        self.max_points, self.depth + 1, self.max_depth
                    ))
        
        # Re-insert points into children
        points = self.points
        vertex_indices = self.vertex_indices
        self.points = []
        self.vertex_indices = []
        
        # Insert existing points into child nodes
        for i, point in enumerate(points):
            self._insert_point_in_children(point, vertex_indices[i])
    
    def _insert_point_in_children(self, point, vertex_idx):
        """Insert point into the appropriate child node"""
        octant = self.get_octant_index(point)
        self.children[octant].insert(point, vertex_idx)
    
    def insert(self, point, vertex_idx):
        """Insert a point and its vertex index into the octree"""
        # If leaf node and not full, just add it
        if self.is_leaf:
            self.points.append(point)
            self.vertex_indices.append(vertex_idx)
            
            # Check if we need to subdivide
            if len(self.points) > self.max_points and self.depth < self.max_depth:
                self.subdivide()
                
            return True
        
        # If not a leaf, pass to appropriate child
        self._insert_point_in_children(point, vertex_idx)
        return True
    
    def find_nearest(self, query_point, max_dist=float('inf')):
        """Find the nearest point to query_point within max_dist"""
        if self.is_leaf:
            best_dist = float('inf')
            best_idx = None
            
            # Check all points in this leaf
            for i, point in enumerate(self.points):
                dist = sum((query_point[j] - point[j])**2 for j in range(3))
                if dist < best_dist and dist <= max_dist**2:
                    best_dist = dist
                    best_idx = i
            
            if best_idx is not None:
                return (best_dist**0.5, self.vertex_indices[best_idx])
            return (float('inf'), None)
        
        # Find best child to descend into
        octant = self.get_octant_index(query_point)
        best_dist, best_idx = self.children[octant].find_nearest(query_point, max_dist)
        
        # Check if we need to look in other octants
        if best_dist < max_dist:
            max_dist = best_dist
        
        # Check if we might need to search other octants
        if max_dist > self.size:
            # Check other children
            for i, child in enumerate(self.children):
                if i != octant:
                    # Calculate min possible distance to this octant
                    min_dist_to_octant = 0
                    for j in range(3):
                        diff = abs(query_point[j] - child.center[j]) - child.size
                        if diff > 0:
                            min_dist_to_octant += diff**2
                    
                    min_dist_to_octant = min_dist_to_octant**0.5
                    
                    # If this octant could contain closer points, search it
                    if min_dist_to_octant < max_dist:
                        dist, idx = child.find_nearest(query_point, max_dist)
                        if dist < best_dist:
                            best_dist = dist
                            best_idx = idx
                            max_dist = best_dist
        
        return (best_dist, best_idx)
        
class Octree:
    """Wrapper for OctreeNode that makes usage simpler"""
    def __init__(self, points=None, vertex_indices=None, max_points_per_node=10):
        if points:
            # Find the bounding box
            min_coords = [float('inf'), float('inf'), float('inf')]
            max_coords = [float('-inf'), float('-inf'), float('-inf')]
            
            for point in points:
                for i in range(3):
                    min_coords[i] = min(min_coords[i], point[i])
                    max_coords[i] = max(max_coords[i], point[i])
            
            # Calculate center and size
            center = [(min_coords[i] + max_coords[i])/2 for i in range(3)]
            size = max(max_coords[i] - min_coords[i] for i in range(3)) / 2
            
            # Add a small buffer to ensure all points fit
            size *= 1.01
            
            # Create the root node
            self.root = OctreeNode(center, size, max_points_per_node)
            
            # Insert all points
            for i, point in enumerate(points):
                vertex_idx = vertex_indices[i] if vertex_indices else i
                self.root.insert(point, vertex_idx)
        else:
            # Create an empty octree
            self.root = None
    
    def insert(self, point, vertex_idx):
        """Insert a point and its vertex index into the octree"""
        if not self.root:
            # Initialize with this first point
            self.root = OctreeNode([point[0], point[1], point[2]], 1.0)
        self.root.insert(point, vertex_idx)
    
    def find_nearest(self, query_point, max_dist=float('inf')):
        """Find the nearest point to query_point within max_dist
           Returns (distance, vertex_index) or (inf, None) if not found
        """
        if not self.root:
            return (float('inf'), None)
        return self.root.find_nearest(query_point, max_dist)

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

# Helper functions for shape key mirroring operations
def detect_shape_key_side(key_name):
    """Detect if a shape key name has L/R designation and return pattern info"""
    import re
    
    # Store information about the match for better name creation
    pattern_info = {
        'base_name': None,
        'from_side': None,
        'to_side': None,
        'separator': None   # Will store separator like '_', '.', '-' or '' (empty for direct suffix)
    }
    
    # Regular expression patterns for different naming conventions
    left_patterns = [
        (r'([a-zA-Z0-9]+)L$', ''),               # Direct suffix, e.g., "SmileL"
        (r'([a-zA-Z0-9]+)[._-]L$', None),        # With separator (will be extracted)
        (r'([a-zA-Z0-9]+)Left$', ''),            # Direct suffix, e.g., "SmileLeft"
        (r'([a-zA-Z0-9]+)[._-]Left$', None)      # With separator
    ]
    
    right_patterns = [
        (r'([a-zA-Z0-9]+)R$', ''),               # Direct suffix, e.g., "SmileR"
        (r'([a-zA-Z0-9]+)[._-]R$', None),        # With separator (will be extracted)
        (r'([a-zA-Z0-9]+)Right$', ''),           # Direct suffix, e.g., "SmileRight"
        (r'([a-zA-Z0-9]+)[._-]Right$', None)     # With separator
    ]
    
    # Check if it's a left-side shape key
    for pattern, sep in left_patterns:
        match = re.match(pattern, key_name)
        if match:
            pattern_info['base_name'] = match.group(1)
            pattern_info['from_side'] = 'L'
            pattern_info['to_side'] = 'R'
            
            # If separator needs to be extracted
            if sep is None:
                # Find which separator was used
                if '_L' in key_name:
                    pattern_info['separator'] = '_'
                elif '.L' in key_name:
                    pattern_info['separator'] = '.'
                elif '-L' in key_name:
                    pattern_info['separator'] = '-'
                # For names like "Smile_Left"
                elif '_Left' in key_name:
                    pattern_info['separator'] = '_'
                elif '.Left' in key_name:
                    pattern_info['separator'] = '.'
                elif '-Left' in key_name:
                    pattern_info['separator'] = '-'
            else:
                pattern_info['separator'] = sep
            
            break
            
    # If not found, check if it's a right-side shape key
    if not pattern_info['base_name']:
        for pattern, sep in right_patterns:
            match = re.match(pattern, key_name)
            if match:
                pattern_info['base_name'] = match.group(1)
                pattern_info['from_side'] = 'R'
                pattern_info['to_side'] = 'L'
                
                # If separator needs to be extracted
                if sep is None:
                    # Find which separator was used
                    if '_R' in key_name:
                        pattern_info['separator'] = '_'
                    elif '.R' in key_name:
                        pattern_info['separator'] = '.'
                    elif '-R' in key_name:
                        pattern_info['separator'] = '-'
                    # For names like "Smile_Right"
                    elif '_Right' in key_name:
                        pattern_info['separator'] = '_'
                    elif '.Right' in key_name:
                        pattern_info['separator'] = '.'
                    elif '-Right' in key_name:
                        pattern_info['separator'] = '-'
                else:
                    pattern_info['separator'] = sep
                
                break
            
    return pattern_info

def generate_mirrored_name(shape_key_name, pattern_info, shape_keys):
    """Generate a mirrored name for a shape key based on pattern info"""
    # If we couldn't determine the side, use _Mirror suffix
    if not pattern_info['base_name']:
        new_key_name = f"{shape_key_name}_Mirror"
    else:
        # Create the new name using the pattern information
        base_name = pattern_info['base_name']
        to_side = pattern_info['to_side']
        separator = pattern_info['separator']
        
        # Handle special cases for "Left" and "Right"
        if to_side == 'L' and 'Right' in shape_key_name:
            if separator:
                new_key_name = base_name + separator + 'Left'
            else:
                new_key_name = base_name + 'Left'
        elif to_side == 'R' and 'Left' in shape_key_name:
            if separator:
                new_key_name = base_name + separator + 'Right'
            else:
                new_key_name = base_name + 'Right'
        else:
            # Standard L/R naming
            if separator:
                new_key_name = base_name + separator + to_side
            else:
                new_key_name = base_name + to_side
    
    # Check if the shape key with the new name already exists
    if new_key_name in shape_keys:
        new_key_name = f"{new_key_name}_Mirror"
        # Check again with the modified name
        if new_key_name in shape_keys:
            i = 1
            while f"{new_key_name}_{i}" in shape_keys:
                i += 1
            new_key_name = f"{new_key_name}_{i}"
    
    return new_key_name

def build_mirror_vertex_mapping(mesh, basis_key):
    """Build a mapping between vertices on opposite sides of the mesh"""
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
    
    return left_vertices, right_vertices, center_vertices

def create_vertex_mirror_mapping(mesh, basis_key, from_side, left_vertices, right_vertices, center_vertices):
    """Create a detailed mapping between source and target vertices for mirroring"""
    # Build the mirror mapping
    mirror_map = {}
    
    # Center vertices mirror to themselves
    for i in center_vertices:
        mirror_map[i] = i
    
    # Find matches between left and right vertices
    source_vertices = left_vertices if from_side == 'L' else right_vertices
    target_vertices = right_vertices if from_side == 'L' else left_vertices
    
    # Create an octree with the target vertices for efficient searching
    octree = Octree()
    
    # Populate the octree with target vertices
    for tgt_idx in target_vertices:
        tgt_co = basis_key.data[tgt_idx].co
        search_point = (tgt_co.x, tgt_co.y, tgt_co.z)
        octree.insert(search_point, tgt_idx)
        
    # For each source vertex, find the best match in the octree
    for src_idx in source_vertices:
        src_co = basis_key.data[src_idx].co
        
        # Create a query point with the mirrored X coordinate
        query_point = (-src_co.x, src_co.y, src_co.z)
        
        # Find the nearest vertex in the octree
        distance, best_match_idx = octree.find_nearest(query_point)
        
        # If we found a match, add it to the mapping
        if best_match_idx is not None:
            mirror_map[src_idx] = best_match_idx
    
    # Create a reverse mapping for efficient lookup: target_idx -> source_idx
    reverse_map = {}
    for src_idx, tgt_idx in mirror_map.items():
        if src_idx != tgt_idx:  # Only include actual mappings (skip self-mapping for center vertices)
            reverse_map[tgt_idx] = src_idx
            
    return source_vertices, target_vertices, mirror_map, reverse_map

def mirror_shape_key(obj, source_key, new_key_name, basis_key, target_vertices, reverse_map):
    """Apply mirroring to create a new shape key"""
    # Create a new shape key
    new_key = obj.shape_key_add(name=new_key_name, from_mix=False)
    new_key.interpolation = source_key.interpolation
    
    # First, copy the basis shape key to the new shape key
    for i in range(len(obj.data.vertices)):
        new_key.data[i].co = basis_key.data[i].co
    
    # Only modify vertices on the TARGET side of the mesh
    modified_vertices = set()  # Keep track of vertices we've modified
    mirrored_count = 0
    
    # For each vertex on the target side, check if we need to update it
    for tgt_idx in target_vertices:
        # Efficient lookup using the reverse mapping
        src_idx = reverse_map.get(tgt_idx)
        
        if src_idx is not None:
            # Get the displacement from basis in the original shape key
            basis_co = basis_key.data[src_idx].co
            active_co = source_key.data[src_idx].co
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
    
    return new_key, mirrored_count

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
        
        # Detect the side of the shape key
        pattern_info = detect_shape_key_side(active_key_name)
        
        # If we couldn't determine the side, inform the user
        if not pattern_info['base_name']:
            self.report({'WARNING'}, "Could not determine side from shape key name. Use naming like 'SmileL' or 'Smile_R'")
            
        # Generate the mirrored name
        new_key_name = generate_mirrored_name(active_key_name, pattern_info, shape_keys)
        
        # Build initial vertex mappings
        left_vertices, right_vertices, center_vertices = build_mirror_vertex_mapping(obj.data, basis_key)
        
        # Create detailed vertex mapping
        from_side = pattern_info.get('from_side')
        source_vertices, target_vertices, mirror_map, reverse_map = create_vertex_mirror_mapping(
            obj.data, basis_key, from_side, left_vertices, right_vertices, center_vertices)
        
        # Count vertices we'll be mirroring
        mapped_count = len([k for k, v in mirror_map.items() if k != v])
        self.report({'INFO'}, f"Found {mapped_count} vertices to mirror from {len(source_vertices)} source vertices")
        
        # Create the mirrored shape key
        new_key, mirrored_count = mirror_shape_key(
            obj, active_key, new_key_name, basis_key, target_vertices, reverse_map)
        
        # Set the new shape key as active
        obj.active_shape_key_index = obj.data.shape_keys.key_blocks.find(new_key_name)
        
        self.report({'INFO'}, f"Created mirrored shape key '{new_key_name}' (mirrored {mirrored_count} vertices)")
        return {'FINISHED'}

class SHAPEKEY_OT_mirror_all_missing(bpy.types.Operator):
    """Mirror all shape keys that don't have a mirrored version yet"""
    bl_idname = "shapekey.mirror_all_missing"
    bl_label = "Mirror All Missing"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        # Check if an object is selected, it's a mesh, and has shape keys
        return obj and obj.type == 'MESH' and obj.data.shape_keys and len(obj.data.shape_keys.key_blocks) > 1
    
    def execute(self, context):
        obj = context.active_object
        shape_keys = obj.data.shape_keys.key_blocks
        
        # Check if we have a Basis shape key
        if 'Basis' not in shape_keys:
            self.report({'ERROR'}, "No Basis shape key found")
            return {'CANCELLED'}
        
        basis_key = shape_keys['Basis']
        
        # Build initial vertex mappings (only need to do this once)
        left_vertices, right_vertices, center_vertices = build_mirror_vertex_mapping(obj.data, basis_key)
        
        # Keep track of which keys we've seen and created
        mirrored_keys = []
        skipped_keys = []
        
        # Create a list of shape keys to process (except Basis)
        keys_to_process = [key for key in shape_keys if key.name != 'Basis']
        
        # First pass - identify shape keys with L/R designation
        side_identified_keys = []
        ambiguous_keys = []
        
        for key in keys_to_process:
            pattern_info = detect_shape_key_side(key.name)
            if pattern_info['base_name'] and pattern_info['from_side']:
                side_identified_keys.append((key, pattern_info))
            else:
                ambiguous_keys.append(key)
        
        # Process keys that have side designation
        for key, pattern_info in side_identified_keys:
            # Generate the opposite side name
            expected_mirror_name = generate_mirrored_name(key.name, pattern_info, {})  # Empty dict to get clean name
            
            # Check if a mirror already exists
            mirror_exists = False
            for existing_key in shape_keys:
                # Compare with the base name only
                if existing_key.name == expected_mirror_name:
                    mirror_exists = True
                    break
            
            if mirror_exists:
                skipped_keys.append(key.name)
                continue
            
            # Get the final name (handling potential conflicts)
            new_key_name = generate_mirrored_name(key.name, pattern_info, shape_keys)
            
            # Create detailed vertex mapping
            source_vertices, target_vertices, mirror_map, reverse_map = create_vertex_mirror_mapping(
                obj.data, basis_key, pattern_info['from_side'], left_vertices, right_vertices, center_vertices)
            
            # Create the mirrored shape key
            new_key, mirrored_count = mirror_shape_key(
                obj, key, new_key_name, basis_key, target_vertices, reverse_map)
            
            mirrored_keys.append((key.name, new_key_name))
            
        # Handle the ambiguous keys (no clear L/R designation)
        for key in ambiguous_keys:
            # For ambiguous keys, we'll try both L->R and R->L mappings
            # and use the one that produces more significant deformation
            
            # Skip keys that seem to be mirrors we just created
            if any(mirror_name == key.name for _, mirror_name in mirrored_keys):
                skipped_keys.append(key.name)
                continue
            
            # Try both directions and see which produces more deformation
            test_l_to_r_info = {'from_side': 'L', 'to_side': 'R', 'base_name': key.name}
            test_r_to_l_info = {'from_side': 'R', 'to_side': 'L', 'base_name': key.name}
            
            # L->R mapping
            source_vertices_l, target_vertices_l, mirror_map_l, reverse_map_l = create_vertex_mirror_mapping(
                obj.data, basis_key, 'L', left_vertices, right_vertices, center_vertices)
                
            # R->L mapping
            source_vertices_r, target_vertices_r, mirror_map_r, reverse_map_r = create_vertex_mirror_mapping(
                obj.data, basis_key, 'R', left_vertices, right_vertices, center_vertices)
            
            # Count deformation on both sides
            l_side_deformation = 0
            r_side_deformation = 0
            
            # Check L side deformation (vertices affecting R side when mirrored)
            for tgt_idx in target_vertices_l:
                src_idx = reverse_map_l.get(tgt_idx)
                if src_idx is not None:
                    basis_co = basis_key.data[src_idx].co
                    active_co = key.data[src_idx].co
                    displacement = active_co - basis_co
                    if displacement.length > 0.0001:
                        l_side_deformation += 1
            
            # Check R side deformation (vertices affecting L side when mirrored)
            for tgt_idx in target_vertices_r:
                src_idx = reverse_map_r.get(tgt_idx)
                if src_idx is not None:
                    basis_co = basis_key.data[src_idx].co
                    active_co = key.data[src_idx].co
                    displacement = active_co - basis_co
                    if displacement.length > 0.0001:
                        r_side_deformation += 1
            
            # Choose the side with more deformation
            if l_side_deformation > r_side_deformation:
                from_side = 'L'
                pattern_info = test_l_to_r_info
                target_vertices = target_vertices_l
                reverse_map = reverse_map_l
            else:
                from_side = 'R'
                pattern_info = test_r_to_l_info
                target_vertices = target_vertices_r
                reverse_map = reverse_map_r
            
            # Generate name with the detected side
            pattern_info['separator'] = '_'  # Use underscore for ambiguous keys
            new_key_name = f"{key.name}_Mirror_{pattern_info['to_side']}"
            
            # Make sure the name is unique
            if new_key_name in shape_keys:
                i = 1
                while f"{new_key_name}_{i}" in shape_keys:
                    i += 1
                new_key_name = f"{new_key_name}_{i}"
            
            # Create the mirrored shape key
            new_key, mirrored_count = mirror_shape_key(
                obj, key, new_key_name, basis_key, target_vertices, reverse_map)
            
            mirrored_keys.append((key.name, new_key_name))
        
        if mirrored_keys:
            self.report({'INFO'}, f"Created {len(mirrored_keys)} mirrored shape keys: {', '.join([b for _, b in mirrored_keys])}")
        else:
            self.report({'INFO'}, "No shape keys needed mirroring")
        
        return {'FINISHED'}

class VERTEXGROUP_OT_combine_groups(bpy.types.Operator):
    """Create a new vertex group that combines weights from all existing vertex groups"""
    bl_idname = "vertexgroup.combine_groups"
    bl_label = "Combine Vertex Groups"
    bl_options = {'REGISTER', 'UNDO'}
    
    new_group_name: StringProperty(
        name="New Group Name",
        description="Name for the new combined vertex group",
        default="Combined_Group"
    )
    
    include_locked: BoolProperty(
        name="Include Locked Groups",
        description="Include locked vertex groups in the combination",
        default=True
    )
    
    include_unlocked: BoolProperty(
        name="Include Unlocked Groups",
        description="Include unlocked vertex groups in the combination",
        default=True
    )
    
    normalize_weights: BoolProperty(
        name="Normalize Weights",
        description="Ensure weights don't exceed 1.0",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH' and len(obj.vertex_groups) > 0
    
    def execute(self, context):
        obj = context.active_object
        
        # Get filtered list of vertex groups based on lock status
        groups_to_combine = []
        for vg in obj.vertex_groups:
            if (self.include_locked and vg.lock_weight) or (self.include_unlocked and not vg.lock_weight):
                groups_to_combine.append(vg)
        
        if not groups_to_combine:
            self.report({'ERROR'}, "No vertex groups match the selected criteria")
            return {'CANCELLED'}
        
        # Create a new vertex group
        new_group = obj.vertex_groups.new(name=self.new_group_name)
        
        # Dictionary to store combined weights for each vertex
        combined_weights = {}
        
        # Iterate through all vertices
        for v in obj.data.vertices:
            vertex_idx = v.index
            total_weight = 0.0
            
            # Sum weights from all selected groups
            for vg in groups_to_combine:
                try:
                    weight = vg.weight(vertex_idx)
                    total_weight += weight
                except RuntimeError:
                    # Vertex not in this group
                    pass
            
            # Store the combined weight if it's greater than zero
            if total_weight > 0:
                combined_weights[vertex_idx] = total_weight
        
        # Apply the combined weights to the new vertex group
        for vertex_idx, weight in combined_weights.items():
            # Normalize if requested
            if self.normalize_weights and weight > 1.0:
                weight = 1.0
            new_group.add([vertex_idx], weight, 'REPLACE')
        
        self.report({'INFO'}, f"Created new vertex group '{self.new_group_name}' from {len(groups_to_combine)} groups")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # Set default name based on which groups are included
        if self.include_locked and not self.include_unlocked:
            self.new_group_name = "Combined_Locked_Groups"
        elif self.include_unlocked and not self.include_locked:
            self.new_group_name = "Combined_Unlocked_Groups"
        else:
            self.new_group_name = "Combined_All_Groups"
        
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "new_group_name")
        layout.prop(self, "include_locked")
        layout.prop(self, "include_unlocked")
        layout.prop(self, "normalize_weights")

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
                
                # Add mirror buttons if there are shape keys
                # For active shape key mirroring, require an active non-basis shape key
                if obj.active_shape_key_index > 0:  # Index 0 is Basis
                    row = col.row()
                    row.operator(SHAPEKEY_OT_mirror.bl_idname)
                
                # Mirror All Missing button - always available if any shape keys exist
                row = col.row()
                row.operator(SHAPEKEY_OT_mirror_all_missing.bl_idname)
                
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
            
            # Vertex Group operations section
            box = layout.box()
            box.label(text="Vertex Group Operations")
            
            if len(obj.vertex_groups) > 0:
                col = box.column(align=True)
                row = col.row()
                row.operator(VERTEXGROUP_OT_combine_groups.bl_idname)
                
                # Display number of vertex groups
                col.label(text=f"Vertex Groups: {len(obj.vertex_groups)}")
            else:
                box.label(text="No Vertex Groups on selected object")
            
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
    SHAPEKEY_OT_mirror_all_missing,
    SHAPEKEY_OT_transfer_with_surface_deform,
    VERTEXGROUP_OT_combine_groups,
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