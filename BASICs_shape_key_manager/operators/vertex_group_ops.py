import bpy
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty

class VERTEXGROUP_OT_combine_groups(Operator):
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


class VERTEXGROUP_OT_remove_empty(Operator):
    """Remove all empty vertex groups (with no vertices or zero weights) from selected meshes"""
    bl_idname = "vertexgroup.remove_empty"
    bl_label = "Remove Empty Vertex Groups"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and (obj.type == 'MESH' or obj.type == 'ARMATURE')
    
    def execute(self, context):
        active_obj = context.active_object
        objects_to_process = []
        
        # Determine which objects to process
        if active_obj.type == 'ARMATURE':
            # Process all mesh children of the armature
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and obj.parent == active_obj:
                    objects_to_process.append(obj)
            if not objects_to_process:
                self.report({'WARNING'}, "No mesh objects are parented to this armature")
                return {'CANCELLED'}
        else:
            # Process all selected mesh objects
            for obj in context.selected_objects:
                if obj.type == 'MESH':
                    objects_to_process.append(obj)
        
        if not objects_to_process:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}
        
        total_removed = 0
        processed_objects = 0
        
        # Process each object
        for obj in objects_to_process:
            if not obj.vertex_groups:
                continue
                
            removed_count = self._remove_empty_groups(obj)
            
            if removed_count > 0:
                processed_objects += 1
                total_removed += removed_count
        
        # Report results
        if total_removed > 0:
            self.report({'INFO'}, f"Removed {total_removed} empty vertex groups from {processed_objects} objects")
        else:
            self.report({'INFO'}, "No empty vertex groups found")
            
        return {'FINISHED'}
    
    def _remove_empty_groups(self, obj):
        """Remove empty vertex groups from an object and return count of removed groups"""
        # Get count of vertices in mesh
        vertex_count = len(obj.data.vertices)
        empty_groups = []
        
        # First pass: identify empty groups
        for group in obj.vertex_groups:
            # Check if this vertex group has any vertices with weight > 0
            has_vertices = False
            
            # Sample approach: check each vertex
            for v_idx in range(vertex_count):
                try:
                    # If we can get weight and it's greater than 0, group is not empty
                    if group.weight(v_idx) > 0:
                        has_vertices = True
                        break
                except RuntimeError:
                    # Vertex not in this group
                    continue
            
            if not has_vertices:
                empty_groups.append(group)
        
        # Second pass: remove the empty groups (can't remove while iterating)
        removed_count = 0
        for group in empty_groups:
            obj.vertex_groups.remove(group)
            removed_count += 1
            
        return removed_count


# Registration
def register():
    bpy.utils.register_class(VERTEXGROUP_OT_combine_groups)
    bpy.utils.register_class(VERTEXGROUP_OT_remove_empty)

def unregister():
    bpy.utils.unregister_class(VERTEXGROUP_OT_remove_empty)
    bpy.utils.unregister_class(VERTEXGROUP_OT_combine_groups)

if __name__ == "__main__":
    register()