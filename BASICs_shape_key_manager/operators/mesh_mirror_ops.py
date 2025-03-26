import bpy
import bmesh
from bpy.types import Operator
from bpy.props import FloatProperty, BoolProperty
from mathutils import Vector
from ..core import Octree
from ..core.mirror_utils import build_mirror_vertex_mapping, create_vertex_mirror_mapping

# Helper functions for mesh mirroring operations
def get_selected_vertices(obj):
    """Get indices of selected vertices in edit mode"""
    # We need to get the selection status from the BMesh in edit mode
    bm = bmesh.from_edit_mesh(obj.data)
    selected_verts = [v.index for v in bm.verts if v.select]
    return selected_verts

def find_mirrors_of_selected(selected_verts, reverse_map):
    """Find the mirror vertices of selected vertices"""
    mirror_verts = []
    for v_idx in selected_verts:
        mirror_idx = reverse_map.get(v_idx)
        if mirror_idx is not None:
            mirror_verts.append(mirror_idx)
    return mirror_verts

def apply_mirror_transformation(mesh, mirror_map, from_side='L'):
    """Apply precise mirroring to vertices based on mapping"""
    modified_vertices = set()
    
    for src_idx, tgt_idx in mirror_map.items():
        if src_idx != tgt_idx:  # Skip center vertices that map to themselves
            src_co = mesh.vertices[src_idx].co
            
            # Mirror coordinates (flip X component)
            mirrored_co = Vector((-src_co.x, src_co.y, src_co.z))
            
            # Apply to target vertex
            mesh.vertices[tgt_idx].co = mirrored_co
            modified_vertices.add(tgt_idx)
    
    return modified_vertices

def handle_center_vertices(mesh, center_vertices, move_to_center=True, center_tolerance=0.0001):
    """Process vertices near the center line"""
    modified_vertices = set()
    
    # Find vertices within the center tolerance
    near_center = []
    for v_idx in range(len(mesh.vertices)):
        if abs(mesh.vertices[v_idx].co.x) <= center_tolerance:
            near_center.append(v_idx)
    
    # Process center vertices if requested
    if move_to_center:
        for v_idx in near_center:
            # Force vertex exactly to center (X=0)
            mesh.vertices[v_idx].co.x = 0.0
            modified_vertices.add(v_idx)
    
    return modified_vertices, near_center

def create_failed_vertex_group(obj, failed_vertices):
    """Create a vertex group containing vertices that couldn't be mirrored"""
    group_name = "Mirror_Failed_Vertices"
    
    # Remove existing group if it exists
    if group_name in obj.vertex_groups:
        vg = obj.vertex_groups[group_name]
        obj.vertex_groups.remove(vg)
    
    # Only create if we have failed vertices
    if failed_vertices:
        # Create new group
        vg = obj.vertex_groups.new(name=group_name)
        for v_idx in failed_vertices:
            vg.add([v_idx], 1.0, 'REPLACE')
        return vg
    
    return None

class MESH_OT_force_mirror(Operator):
    """Force mirror vertices to create perfect symmetry across the X axis"""
    bl_idname = "mesh.force_mirror"
    bl_label = "Force Mirror Mesh"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Main parameters
    use_custom_tolerance: BoolProperty(
        name="Use Custom Tolerance",
        description="Use a custom tolerance value instead of the global setting",
        default=False
    )
    
    mirror_tolerance: FloatProperty(
        name="Mirror Tolerance",
        description="Maximum distance allowed between mirrored vertices (in Blender units)",
        default=0.001,
        min=0.0001,
        max=1.0,
        precision=4
    )
    
    fault_tolerant: BoolProperty(
        name="Fault Tolerant",
        description="Continue operation even if some vertices can't be mirrored within tolerance",
        default=True
    )
    
    create_failed_group: BoolProperty(
        name="Create Failed Vertex Group",
        description="Create a vertex group containing vertices that couldn't be mirrored",
        default=True
    )
    
    select_mirrored: BoolProperty(
        name="Select Mirrored Vertices",
        description="Select the mirrored vertices after operation",
        default=False
    )
    
    # Advanced parameters
    center_tolerance: FloatProperty(
        name="Center Tolerance",
        description="Maximum distance from center to consider a vertex as 'center' (in Blender units)",
        default=0.0001,
        min=0.00001,
        max=0.1,
        precision=5
    )
    
    move_to_center: BoolProperty(
        name="Move Center Vertices to X=0",
        description="Force vertices within center tolerance to be exactly at X=0",
        default=True
    )
    
    # Direction options
    mirror_from_left: BoolProperty(
        name="Left to Right",
        description="Mirror from left (-X) to right (+X) side",
        default=True
    )
    
    mirror_from_right: BoolProperty(
        name="Right to Left",
        description="Mirror from right (+X) to left (-X) side",
        default=False
    )
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.type == 'MESH'
    
    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        mode = obj.mode
        
        # Get the tolerance value to use
        tolerance = self.mirror_tolerance if self.use_custom_tolerance else context.scene.shapekey_mirror_tolerance
        
        # Store original mode to restore later
        original_mode = obj.mode
        
        # We need to ensure we're operating on the mesh data properly
        if original_mode == 'EDIT':
            # If in edit mode, get selected vertices
            selected_verts = get_selected_vertices(obj)
            # Switch to object mode to perform the operation
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Build initial vertex mappings using common function
        left_vertices, right_vertices, center_vertices = build_mirror_vertex_mapping(mesh)
        
        # Determine which side to mirror from based on settings
        if self.mirror_from_left and not self.mirror_from_right:
            # Mirror from left to right side
            from_side = 'L'
        elif self.mirror_from_right and not self.mirror_from_left:
            # Mirror from right to left side
            from_side = 'R'
        else:
            # Default to left to right if both or neither are selected
            from_side = 'L'
            self.mirror_from_left = True
            self.mirror_from_right = False
        
        # Create detailed vertex mapping using common function
        source_vertices, target_vertices, mirror_map, reverse_map = create_vertex_mirror_mapping(
            mesh, from_side, left_vertices, right_vertices, center_vertices, tolerance)
        
        # Handle center vertices
        center_modified, near_center_verts = handle_center_vertices(
            mesh, center_vertices, self.move_to_center, self.center_tolerance)
        
        # Process different cases based on mode
        if original_mode == 'EDIT':
            # In edit mode, we only affect mirrors of selected vertices
            if selected_verts:
                # Get the mirrors of selected vertices
                mirror_verts = find_mirrors_of_selected(selected_verts, reverse_map)
                
                # We need to filter mirror_map to only include entries affecting mirror_verts
                filtered_map = {}
                for src_idx, tgt_idx in mirror_map.items():
                    if tgt_idx in mirror_verts:
                        filtered_map[src_idx] = tgt_idx
                
                # Apply mirror transformation
                modified_vertices = apply_mirror_transformation(mesh, filtered_map, from_side)
                
                # Update selection if requested
                if self.select_mirrored:
                    # Need to switch back to edit mode and update selection
                    bpy.ops.object.mode_set(mode='EDIT')
                    bm = bmesh.from_edit_mesh(mesh)
                    
                    # Clear existing selection
                    for v in bm.verts:
                        v.select = False
                    
                    # Select the mirrored vertices
                    for v_idx in mirror_verts:
                        bm.verts[v_idx].select = True
                    
                    # Update the edit mesh
                    bmesh.update_edit_mesh(mesh)
                    bpy.ops.object.mode_set(mode='OBJECT')
            else:
                self.report({'WARNING'}, "No vertices selected in Edit Mode")
                modified_vertices = set()
        else:
            # In object mode, apply to all vertices
            modified_vertices = apply_mirror_transformation(mesh, mirror_map, from_side)
        
        # Count failed vertices (only source vertices that weren't mapped)
        failed_vertices = [v_idx for v_idx in source_vertices if v_idx not in mirror_map]
        
        # Create a vertex group for failed vertices if requested
        if self.create_failed_group and failed_vertices:
            vg = create_failed_vertex_group(obj, failed_vertices)
            self.report({'WARNING'}, f"Created vertex group '{vg.name}' with {len(failed_vertices)} vertices that could not be mirrored")
        
        # Restore original mode
        bpy.ops.object.mode_set(mode=original_mode)
        
        # Calculate success statistics
        total_affected = len(modified_vertices) + len(center_modified)
        total_attempted = len(source_vertices)
        
        self.report({'INFO'}, f"Mirrored {total_affected} vertices ({len(failed_vertices)} failed to find mirrors within tolerance)")
        
        # Handle fault intolerant mode
        if not self.fault_tolerant and failed_vertices:
            self.report({'ERROR'}, f"Mirroring failed for {len(failed_vertices)} vertices. Enable Fault Tolerant mode to ignore failures.")
            return {'CANCELLED'}
        
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # Initialize with the global mirror tolerance
        self.mirror_tolerance = context.scene.shapekey_mirror_tolerance
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        
        # Main section with common parameters
        box = layout.box()
        box.label(text="Mirroring Options")
        
        # Direction options
        row = box.row()
        row.prop(self, "mirror_from_left")
        row = box.row()
        row.prop(self, "mirror_from_right")
        
        # Tolerance settings
        row = box.row()
        row.prop(self, "use_custom_tolerance")
        if self.use_custom_tolerance:
            row = box.row()
            row.prop(self, "mirror_tolerance")
        
        # Error handling options
        row = box.row()
        row.prop(self, "fault_tolerant")
        row = box.row()
        row.prop(self, "create_failed_group")
        
        # Selection option
        row = box.row()
        row.prop(self, "select_mirrored")
        
        # Advanced section with less common parameters
        box = layout.box()
        box.label(text="Advanced Options")
        
        row = box.row()
        row.prop(self, "center_tolerance")
        row = box.row()
        row.prop(self, "move_to_center") 