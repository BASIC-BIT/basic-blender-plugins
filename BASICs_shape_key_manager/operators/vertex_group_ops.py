import bpy
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatProperty, IntProperty
from ..core.vertex_group_utils import (
    collect_protected_group_names,
    parse_protected_prefixes,
    snapshot_vertex_groups,
    restore_vertex_groups,
    compute_snapshot_drift,
    limit_vertex_influences,
    lock_aware_renormalize,
)

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


class VERTEXGROUP_OT_robust_weight_transfer(Operator):
    """Transfer weights from a source body mesh to the active clothing mesh while protected vertex groups (locked groups and PhysBone/dynamics name prefixes) are preserved exactly"""
    bl_idname = "vertexgroup.robust_weight_transfer"
    bl_label = "Robust Weight Transfer (Protected Groups)"
    bl_options = {'REGISTER', 'UNDO'}

    vert_mapping: EnumProperty(
        name="Vertex Mapping",
        description="How target vertices find weights on the source mesh",
        items=[
            ('POLYINTERP_NEAREST', "Nearest Face Interpolated",
             "Interpolate weights within the nearest source face (closest built-in to robust transfer)"),
            ('POLYINTERP_VNORPROJ', "Projected Face Interpolated",
             "Project along vertex normals onto the source and interpolate"),
            ('POLY_NEAREST', "Nearest Face", "Copy weights from the nearest source face"),
            ('NEAREST', "Nearest Vertex", "Copy weights from the nearest source vertex"),
        ],
        default='POLYINTERP_NEAREST'
    )

    only_bone_deform: BoolProperty(
        name="Deform Bone Groups Only",
        description="Only transfer source groups that belong to deform bones of the source's armature",
        default=False
    )

    respect_lock_weight: BoolProperty(
        name="Protect Locked Groups",
        description="Treat vertex groups with locked weights (lock_weight) as protected",
        default=True
    )

    use_max_distance: BoolProperty(
        name="Use Max Distance",
        description="Leave target vertices untouched when they are further than Max Distance from the source mesh",
        default=True
    )

    max_distance: FloatProperty(
        name="Max Distance",
        description="Maximum mapping distance between a target vertex and the source (in Blender units)",
        default=0.05,
        min=0.0001,
        max=10.0,
        precision=4
    )

    limit_influences: BoolProperty(
        name="Limit Influences",
        description="Prune the smallest unprotected weights so vertices stay within the influence cap (protected groups are never pruned)",
        default=True
    )

    max_influences: IntProperty(
        name="Max Influences",
        description="Maximum bone influences per vertex (4 matches typical VRChat/FBX import limits)",
        default=4,
        min=1,
        max=32
    )

    @classmethod
    def poll(cls, context):
        # Active object is the target, at least one other selected mesh has vertex groups
        target = context.active_object
        if not target or target.type != 'MESH':
            return False
        for obj in context.selected_objects:
            if obj != target and obj.type == 'MESH' and len(obj.vertex_groups) > 0:
                return True
        return False

    def execute(self, context):
        target = context.active_object
        sources = [obj for obj in context.selected_objects
                   if obj != target and obj.type == 'MESH' and len(obj.vertex_groups) > 0]

        if not sources:
            self.report({'ERROR'}, "No source mesh with vertex groups selected")
            return {'CANCELLED'}

        source = sources[0]  # Use the first valid source

        # (a) Collect the protected vertex group set on the target:
        # lock_weight groups + user-editable name prefixes (PhysBone/dynamics chains)
        prefixes = parse_protected_prefixes(
            getattr(context.scene, "weight_transfer_protected_prefixes", ""))
        protected_names = collect_protected_group_names(
            target, respect_lock_weight=self.respect_lock_weight, prefixes=prefixes)

        # (b) Snapshot the protected groups before anything destructive happens
        snapshot = snapshot_vertex_groups(target, protected_names)

        # We need to be in object mode for the data transfer
        original_mode = context.object.mode if context.object else 'OBJECT'
        if original_mode != 'OBJECT':
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

        # Force a scene update before transferring
        context.view_layer.update()

        # (c) Weight transfer source -> target. Protected names may be
        # transiently overwritten here; step (d) restores them verbatim, so
        # the net effect is a transfer of the non-protected groups only.
        layers_src = 'BONE_DEFORM' if self.only_bone_deform else 'ALL'
        transfer_args = dict(
            data_type='VGROUP_WEIGHTS',
            use_create=True,
            vert_mapping=self.vert_mapping,
            use_max_distance=self.use_max_distance,
            max_distance=self.max_distance,
            layers_select_src=layers_src,
            layers_select_dst='NAME',
            mix_mode='REPLACE',
            mix_factor=1.0,
        )

        transfer_success = False
        try:
            # data_transfer reads active object as source, other selected as destination
            with context.temp_override(
                object=source,
                active_object=source,
                selected_objects=[source, target],
                selected_editable_objects=[source, target]
            ):
                bpy.ops.object.data_transfer(**transfer_args)
            transfer_success = True
        except Exception as e:
            self.report({'WARNING'}, f"Error transferring weights: {str(e)}")
            # Fallback: set up the selection state manually
            try:
                for obj in context.selected_objects:
                    obj.select_set(False)
                source.select_set(True)
                target.select_set(True)
                context.view_layer.objects.active = source

                bpy.ops.object.data_transfer(**transfer_args)
                transfer_success = True
            except Exception as fallback_error:
                self.report({'ERROR'}, f"Fallback weight transfer also failed: {str(fallback_error)}")
            finally:
                context.view_layer.objects.active = target

        # Restore visibility and selectability
        source.hide_set(source_hide)
        source.hide_select = source_select
        target.hide_set(target_hide)
        target.hide_select = target_select

        if not transfer_success:
            # Put the protected groups back in case the transfer partially ran
            restore_vertex_groups(target, snapshot)
            if original_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=original_mode)
            return {'CANCELLED'}

        # (d) Restore protected groups verbatim (weights + lock flags)
        restore_vertex_groups(target, snapshot)
        drift = compute_snapshot_drift(target, snapshot) if snapshot else 0.0

        # Influence cap (never prunes protected groups), then
        # (e) lock-aware renormalize: scale only unprotected weights so vertex
        # totals reach 1.0 while protected weights stay exact
        pruned_vertices = set()
        if self.limit_influences:
            pruned_vertices = limit_vertex_influences(target, protected_names, self.max_influences)
        rescaled, unfillable = lock_aware_renormalize(target, protected_names, pruned_vertices)

        # (f) Report counts
        protected_indices = {vg.index for vg in target.vertex_groups if vg.name in protected_names}
        verts_touched = 0
        unweighted = 0
        for v in target.data.vertices:
            if len(v.groups) == 0:
                unweighted += 1
            elif any(g.group not in protected_indices for g in v.groups):
                verts_touched += 1
        transferred_groups = len([vg for vg in target.vertex_groups if vg.name not in protected_names])

        # Return to original mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=original_mode)

        self.report({'INFO'},
                    f"Transferred weights from {source.name} to {target.name}: "
                    f"{transferred_groups} groups written, {len(snapshot)} protected, "
                    f"{verts_touched} verts weighted, {rescaled} renormalized, "
                    f"{len(pruned_vertices)} influence-capped, {unfillable} unfillable, "
                    f"{unweighted} unweighted")

        if drift > 0.0:
            self.report({'ERROR'}, f"Protected weight drift detected after restore: {drift:.8f} (this is a bug, please report it)")

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "vert_mapping")
        layout.prop(self, "only_bone_deform")
        layout.prop(self, "respect_lock_weight")
        if hasattr(context.scene, "weight_transfer_protected_prefixes"):
            layout.prop(context.scene, "weight_transfer_protected_prefixes")
        layout.prop(self, "use_max_distance")
        if self.use_max_distance:
            layout.prop(self, "max_distance")
        layout.prop(self, "limit_influences")
        if self.limit_influences:
            layout.prop(self, "max_influences")


# Registration
def register():
    bpy.utils.register_class(VERTEXGROUP_OT_combine_groups)
    bpy.utils.register_class(VERTEXGROUP_OT_remove_empty)
    bpy.utils.register_class(VERTEXGROUP_OT_robust_weight_transfer)

def unregister():
    bpy.utils.unregister_class(VERTEXGROUP_OT_robust_weight_transfer)
    bpy.utils.unregister_class(VERTEXGROUP_OT_remove_empty)
    bpy.utils.unregister_class(VERTEXGROUP_OT_combine_groups)

if __name__ == "__main__":
    register()