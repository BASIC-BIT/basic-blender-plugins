import bpy
import re
from bpy.types import Operator
from bpy.props import FloatProperty, BoolProperty
from mathutils import Vector
from ..core import Octree
from ..core.mirror_utils import detect_shape_key_side, generate_mirrored_name, build_mirror_vertex_mapping, create_vertex_mirror_mapping

# Helper functions for shape key mirroring operations
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

class SHAPEKEY_OT_mirror(Operator):
    """Mirror the selected shape key to create a new shape key for the opposite side"""
    bl_idname = "shapekey.mirror"
    bl_label = "Mirror Shape Key"
    bl_options = {'REGISTER', 'UNDO'}
    
    use_custom_tolerance: BoolProperty(
        name="Use Custom Tolerance",
        description="Use a custom tolerance value instead of the global setting",
        default=False
    )
    
    custom_tolerance: FloatProperty(
        name="Custom Tolerance",
        description="Maximum distance allowed between mirrored vertices (in Blender units)",
        default=0.001,
        min=0.0001,
        max=1.0,
        precision=4
    )
    
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
        
        # Get the tolerance value to use
        tolerance = self.custom_tolerance if self.use_custom_tolerance else context.scene.shapekey_mirror_tolerance
        
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
        
        # Build initial vertex mappings using common function
        left_vertices, right_vertices, center_vertices = build_mirror_vertex_mapping(basis_key)
        
        # Create detailed vertex mapping using common function
        from_side = pattern_info.get('from_side')
        source_vertices, target_vertices, mirror_map, reverse_map = create_vertex_mirror_mapping(
            basis_key, from_side, left_vertices, right_vertices, center_vertices, tolerance)
        
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
        
    def invoke(self, context, event):
        # Initialize custom_tolerance with the global setting
        self.custom_tolerance = context.scene.shapekey_mirror_tolerance
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "use_custom_tolerance")
        if self.use_custom_tolerance:
            layout.prop(self, "custom_tolerance")

class SHAPEKEY_OT_mirror_all_missing(Operator):
    """Mirror all shape keys that don't have a mirrored version yet"""
    bl_idname = "shapekey.mirror_all_missing"
    bl_label = "Mirror All Missing"
    bl_options = {'REGISTER', 'UNDO'}
    
    use_custom_tolerance: BoolProperty(
        name="Use Custom Tolerance",
        description="Use a custom tolerance value instead of the global setting",
        default=False
    )
    
    custom_tolerance: FloatProperty(
        name="Custom Tolerance",
        description="Maximum distance allowed between mirrored vertices (in Blender units)",
        default=0.001,
        min=0.0001,
        max=1.0,
        precision=4
    )
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        # Check if an object is selected, it's a mesh, and has shape keys
        return obj and obj.type == 'MESH' and obj.data.shape_keys and len(obj.data.shape_keys.key_blocks) > 1
    
    def execute(self, context):
        obj = context.active_object
        shape_keys = obj.data.shape_keys.key_blocks
        
        # Get the tolerance value to use
        tolerance = self.custom_tolerance if self.use_custom_tolerance else context.scene.shapekey_mirror_tolerance
        
        # Check if we have a Basis shape key
        if 'Basis' not in shape_keys:
            self.report({'ERROR'}, "No Basis shape key found")
            return {'CANCELLED'}
        
        basis_key = shape_keys['Basis']
        
        # Build initial vertex mappings (only need to do this once)
        left_vertices, right_vertices, center_vertices = build_mirror_vertex_mapping(basis_key)
        
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
                basis_key, pattern_info['from_side'], left_vertices, right_vertices, center_vertices, tolerance)
            
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
                basis_key, 'L', left_vertices, right_vertices, center_vertices, tolerance)
                
            # R->L mapping
            source_vertices_r, target_vertices_r, mirror_map_r, reverse_map_r = create_vertex_mirror_mapping(
                basis_key, 'R', left_vertices, right_vertices, center_vertices, tolerance)
            
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
        
    def invoke(self, context, event):
        # Initialize custom_tolerance with the global setting
        self.custom_tolerance = context.scene.shapekey_mirror_tolerance
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "use_custom_tolerance")
        if self.use_custom_tolerance:
            layout.prop(self, "custom_tolerance") 