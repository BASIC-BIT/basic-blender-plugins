import bpy
from bpy.props import BoolProperty


def _get_driven_meshes(armature):
    """Get meshes parented to this armature or using it in an Armature modifier."""
    meshes = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        has_armature_modifier = any(
            mod.type == 'ARMATURE' and mod.object == armature
            for mod in obj.modifiers
        )
        if obj.parent == armature or has_armature_modifier:
            meshes.append(obj)
    return meshes


class ARMATURE_OT_delete_other_bones(bpy.types.Operator):
    bl_idname = "armature.delete_other_bones"
    bl_label = "Delete Other Bones"
    bl_description = "Delete all bones except the selected ones and their parent/child chains"
    bl_options = {'REGISTER', 'UNDO'}
    
    preserve_children: bpy.props.BoolProperty(
        name="Preserve Children",
        description="Preserve all child bones of the selected bones",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and 
                context.active_object.type == 'ARMATURE' and
                context.mode == 'EDIT')
    
    def execute(self, context):
        armature = context.active_object
        armature_data = armature.data
        
        # Get all selected bones in edit mode
        selected_bones = [bone for bone in armature_data.edit_bones if bone.select]
        
        if not selected_bones:
            self.report({'WARNING'}, "No bones selected")
            return {'CANCELLED'}
        
        # Collect bones to preserve (selected bones and their parent/child chains)
        bones_to_preserve = set()
        for bone in selected_bones:
            # Add the selected bone
            bones_to_preserve.add(bone.name)
            
            # Add all parent bones to preserve the chain
            parent = bone.parent
            while parent:
                bones_to_preserve.add(parent.name)
                parent = parent.parent
            
            # If preserve_children is enabled, add all child bones
            if self.preserve_children:
                self.add_children_recursive(bone, bones_to_preserve)
        
        # Delete all bones that are not in the bones_to_preserve set
        bones_to_delete = [bone for bone in armature_data.edit_bones if bone.name not in bones_to_preserve]
        
        # Report the number of bones that will be deleted
        self.report({'INFO'}, f"Deleting {len(bones_to_delete)} bones")
        
        # Delete the bones
        for bone in bones_to_delete:
            armature_data.edit_bones.remove(bone)
        
        return {'FINISHED'}
    
    def add_children_recursive(self, bone, bones_to_preserve):
        """Add all children of the given bone to the bones_to_preserve set recursively"""
        for child in bone.children:
            bones_to_preserve.add(child.name)
            self.add_children_recursive(child, bones_to_preserve)


class ARMATURE_OT_remove_unweighted_bones(bpy.types.Operator):
    bl_idname = "armature.remove_unweighted_bones"
    bl_label = "Remove Unweighted Bones"
    bl_description = "Delete bones on the selected armature that have no positive weights on its driven meshes"
    bl_options = {'REGISTER', 'UNDO'}

    preserve_parent_chains: BoolProperty(
        name="Preserve Parent Chains",
        description="Keep unweighted parent bones needed to preserve the hierarchy above weighted bones",
        default=True
    )

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'ARMATURE')

    def execute(self, context):
        armature = context.active_object
        initial_mode = armature.mode

        try:
            context.view_layer.objects.active = armature
            if armature.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')

            meshes = _get_driven_meshes(armature)
            if not meshes:
                self.report({'WARNING'}, "No mesh objects are driven by this armature")
                return {'CANCELLED'}

            bone_names = {bone.name for bone in armature.data.bones}
            weighted_bones = self._collect_weighted_group_names(meshes) & bone_names
            if not weighted_bones:
                self.report({'WARNING'}, "No weighted bones found; cancelled to avoid deleting the armature")
                return {'CANCELLED'}

            bpy.ops.object.mode_set(mode='EDIT')
            bones_to_preserve = set(weighted_bones)
            if self.preserve_parent_chains:
                self._add_parent_chains(armature.data.edit_bones, weighted_bones, bones_to_preserve)

            bones_to_delete = [
                bone for bone in armature.data.edit_bones
                if bone.name not in bones_to_preserve
            ]

            if not bones_to_delete:
                self.report({'INFO'}, f"No unweighted bones to remove across {len(meshes)} driven meshes")
                return {'FINISHED'}

            deleted_count = len(bones_to_delete)
            parent_chain_count = len(bones_to_preserve - weighted_bones)
            for bone in bones_to_delete:
                armature.data.edit_bones.remove(bone)

            self.report(
                {'INFO'},
                f"Removed {deleted_count} unweighted bones; kept {len(weighted_bones)} weighted bones"
                f" and {parent_chain_count} parent-chain bones"
            )
            return {'FINISHED'}
        finally:
            if armature.name in bpy.data.objects and armature.mode != initial_mode:
                try:
                    bpy.ops.object.mode_set(mode=initial_mode)
                except RuntimeError:
                    pass

    def _collect_weighted_group_names(self, meshes):
        """Return vertex group names that have at least one positive weight."""
        weighted_names = set()
        for mesh in meshes:
            group_names_by_index = {group.index: group.name for group in mesh.vertex_groups}
            for vertex in mesh.data.vertices:
                for group_ref in vertex.groups:
                    if group_ref.weight <= 0.0:
                        continue
                    group_name = group_names_by_index.get(group_ref.group)
                    if group_name:
                        weighted_names.add(group_name)
        return weighted_names

    def _add_parent_chains(self, edit_bones, weighted_bones, bones_to_preserve):
        for bone_name in weighted_bones:
            bone = edit_bones.get(bone_name)
            while bone and bone.parent:
                bone = bone.parent
                bones_to_preserve.add(bone.name)


class ARMATURE_OT_roll_selected_weights_to_parent(bpy.types.Operator):
    bl_idname = "armature.roll_selected_weights_to_parent"
    bl_label = "Roll Selected Weights To Parent"
    bl_description = "Merge selected bone vertex-group weights into the nearest unselected parent, then delete those bones"
    bl_options = {'REGISTER', 'UNDO'}

    remove_rolled_vertex_groups: BoolProperty(
        name="Remove Rolled Vertex Groups",
        description="Remove each deleted bone's vertex group after its weights are merged into the parent group",
        default=True
    )

    reparent_children: BoolProperty(
        name="Reparent Children",
        description="Reparent unselected child bones of deleted bones to the same roll-up parent",
        default=True
    )

    respect_locked_groups: BoolProperty(
        name="Respect Locked Groups",
        description="Cancel if a source or target vertex group is locked instead of modifying it",
        default=True
    )

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'ARMATURE')

    def execute(self, context):
        armature = context.active_object
        initial_mode = armature.mode
        selected_names = self._get_selected_bone_names(context, armature)

        if not selected_names:
            self.report({'WARNING'}, "No bones selected")
            return {'CANCELLED'}

        try:
            context.view_layer.objects.active = armature
            if armature.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')

            target_by_bone, rootless_bones = self._build_roll_targets(armature, selected_names)
            if rootless_bones:
                names = ", ".join(sorted(rootless_bones)[:5])
                if len(rootless_bones) > 5:
                    names += f" and {len(rootless_bones) - 5} more"
                self.report({'WARNING'}, f"Selected bones need an unselected parent: {names}")
                return {'CANCELLED'}

            if not self.reparent_children:
                blocking_children = self._find_unselected_children(armature, selected_names)
                if blocking_children:
                    child_names = ", ".join(sorted(blocking_children)[:5])
                    if len(blocking_children) > 5:
                        child_names += f" and {len(blocking_children) - 5} more"
                    self.report({'WARNING'}, f"Selected bones have unselected children: {child_names}")
                    return {'CANCELLED'}

            meshes = _get_driven_meshes(armature)
            if not meshes:
                self.report({'WARNING'}, "No mesh objects are driven by this armature")
                return {'CANCELLED'}

            if self.respect_locked_groups:
                locked_groups = self._find_locked_roll_groups(meshes, target_by_bone)
                if locked_groups:
                    names = ", ".join(sorted(locked_groups)[:5])
                    if len(locked_groups) > 5:
                        names += f" and {len(locked_groups) - 5} more"
                    self.report({'WARNING'}, f"Locked vertex groups involved: {names}")
                    return {'CANCELLED'}

            reference_count = self._count_bone_references(armature, selected_names)
            stats = self._roll_mesh_weights(meshes, target_by_bone)

            bpy.ops.object.mode_set(mode='EDIT')
            if self.reparent_children:
                self._reparent_unselected_children(
                    armature.data.edit_bones,
                    selected_names,
                    target_by_bone
                )
            deleted_count = self._delete_edit_bones(armature.data.edit_bones, selected_names)

            self.report(
                {'INFO'},
                f"Rolled {stats['vertices']} vertex weights from {len(target_by_bone)} bones "
                f"into parents; deleted {deleted_count} bones and removed {stats['removed_groups']} groups"
            )
            if stats['created_groups']:
                self.report({'INFO'}, f"Created {stats['created_groups']} missing parent vertex groups")
            if stats['clamped_weights']:
                self.report({'WARNING'}, f"Clamped {stats['clamped_weights']} rolled weights at 1.0")
            if reference_count:
                self.report({'WARNING'}, f"Deleted bones may still be referenced by {reference_count} constraints/actions/drivers")
            return {'FINISHED'}
        finally:
            if armature.name in bpy.data.objects and armature.mode != initial_mode:
                try:
                    bpy.ops.object.mode_set(mode=initial_mode)
                except RuntimeError:
                    pass

    def _get_selected_bone_names(self, context, armature):
        if armature.mode == 'EDIT':
            return {bone.name for bone in armature.data.edit_bones if bone.select}
        if armature.mode == 'POSE':
            return {
                bone.name for bone in context.selected_pose_bones
                if bone.id_data == armature
            }
        return {bone.name for bone in armature.data.bones if bone.select}

    def _build_roll_targets(self, armature, selected_names):
        target_by_bone = {}
        rootless_bones = set()
        for bone_name in selected_names:
            bone = armature.data.bones.get(bone_name)
            parent = bone.parent if bone else None
            while parent and parent.name in selected_names:
                parent = parent.parent
            if parent is None:
                rootless_bones.add(bone_name)
            else:
                target_by_bone[bone_name] = parent.name
        return target_by_bone, rootless_bones

    def _find_unselected_children(self, armature, selected_names):
        children = set()
        for bone_name in selected_names:
            bone = armature.data.bones.get(bone_name)
            if not bone:
                continue
            for child in bone.children:
                if child.name not in selected_names:
                    children.add(child.name)
        return children

    def _find_locked_roll_groups(self, meshes, target_by_bone):
        locked_groups = set()
        for mesh in meshes:
            for source_name, target_name in target_by_bone.items():
                source_group = mesh.vertex_groups.get(source_name)
                target_group = mesh.vertex_groups.get(target_name)
                if source_group and source_group.lock_weight:
                    locked_groups.add(f"{mesh.name}:{source_name}")
                if target_group and target_group.lock_weight:
                    locked_groups.add(f"{mesh.name}:{target_name}")
        return locked_groups

    def _roll_mesh_weights(self, meshes, target_by_bone):
        stats = {
            'vertices': 0,
            'removed_groups': 0,
            'created_groups': 0,
            'clamped_weights': 0,
        }
        for mesh in meshes:
            for source_name, target_name in target_by_bone.items():
                source_group = mesh.vertex_groups.get(source_name)
                if source_group is None:
                    continue

                source_index = source_group.index
                target_group = mesh.vertex_groups.get(target_name)
                target_index = target_group.index if target_group else None
                weights_to_roll = []

                for vertex in mesh.data.vertices:
                    source_weight = 0.0
                    target_weight = 0.0
                    for group_ref in vertex.groups:
                        if group_ref.group == source_index:
                            source_weight = group_ref.weight
                        elif target_index is not None and group_ref.group == target_index:
                            target_weight = group_ref.weight
                    if source_weight > 0.0:
                        weights_to_roll.append((vertex.index, source_weight, target_weight))

                if weights_to_roll and target_group is None:
                    target_group = mesh.vertex_groups.new(name=target_name)
                    stats['created_groups'] += 1

                for vertex_index, source_weight, target_weight in weights_to_roll:
                    new_weight = target_weight + source_weight
                    if new_weight > 1.0:
                        new_weight = 1.0
                        stats['clamped_weights'] += 1
                    target_group.add([vertex_index], new_weight, 'REPLACE')
                    stats['vertices'] += 1

                if self.remove_rolled_vertex_groups:
                    mesh.vertex_groups.remove(source_group)
                    stats['removed_groups'] += 1
        return stats

    def _reparent_unselected_children(self, edit_bones, selected_names, target_by_bone):
        for bone_name, target_name in target_by_bone.items():
            bone = edit_bones.get(bone_name)
            target = edit_bones.get(target_name)
            if not bone or not target:
                continue
            for child in list(bone.children):
                if child.name in selected_names:
                    continue
                child.use_connect = False
                child.parent = target

    def _delete_edit_bones(self, edit_bones, selected_names):
        depths = {}
        for bone_name in selected_names:
            bone = edit_bones.get(bone_name)
            depth = 0
            parent = bone.parent if bone else None
            while parent:
                depth += 1
                parent = parent.parent
            depths[bone_name] = depth

        deleted_count = 0
        for bone_name in sorted(selected_names, key=lambda name: depths[name], reverse=True):
            bone = edit_bones.get(bone_name)
            if bone:
                edit_bones.remove(bone)
                deleted_count += 1
        return deleted_count

    def _count_bone_references(self, armature, selected_names):
        count = 0
        for obj in bpy.data.objects:
            count += self._count_constraint_refs(obj.constraints, armature, selected_names)
            if obj.type == 'ARMATURE' and obj.pose:
                for pose_bone in obj.pose.bones:
                    if pose_bone.name not in selected_names:
                        count += self._count_constraint_refs(pose_bone.constraints, armature, selected_names)

        quoted_names = [name.replace('\\', '\\\\').replace('"', '\\"') for name in selected_names]
        bone_paths = [f'pose.bones["{name}"]' for name in quoted_names]
        for action in bpy.data.actions:
            for fcurve in action.fcurves:
                if any(path in fcurve.data_path for path in bone_paths):
                    count += 1
        for obj in bpy.data.objects:
            animation_data = obj.animation_data
            if animation_data and animation_data.drivers:
                for driver in animation_data.drivers:
                    if any(path in driver.data_path for path in bone_paths):
                        count += 1
        return count

    def _count_constraint_refs(self, constraints, armature, selected_names):
        count = 0
        for constraint in constraints:
            if (hasattr(constraint, 'target') and constraint.target == armature and
                    hasattr(constraint, 'subtarget') and constraint.subtarget in selected_names):
                count += 1
        return count


class ARMATURE_OT_check_fix_modifiers(bpy.types.Operator):
    bl_idname = "armature.check_fix_modifiers"
    bl_label = "Check/Fix Armature Modifiers"
    bl_description = "Ensure all child meshes have exactly one armature modifier pointing to this armature"
    bl_options = {'REGISTER', 'UNDO'}
    
    fix_modifiers: BoolProperty(
        name="Fix Issues",
        description="Automatically fix incorrect modifiers",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and 
                context.active_object.type == 'ARMATURE')
    
    def execute(self, context):
        armature = context.active_object
        child_meshes = self._get_child_meshes(armature)
        
        if not child_meshes:
            self.report({'WARNING'}, "No mesh objects are parented to this armature")
            return {'CANCELLED'}
        
        fixed_count = 0
        already_correct = 0
        
        for mesh in child_meshes:
            status = self._check_and_fix_modifiers(mesh, armature)
            if status == 'FIXED':
                fixed_count += 1
            elif status == 'CORRECT':
                already_correct += 1
        
        if fixed_count > 0:
            self.report({'INFO'}, f"Fixed armature modifiers on {fixed_count} meshes")
        elif already_correct == len(child_meshes):
            self.report({'INFO'}, f"All {already_correct} meshes already have correct armature modifiers")
        else:
            self.report({'WARNING'}, "Issues found but Fix Issues option is disabled")
            
        return {'FINISHED'}
    
    def _get_child_meshes(self, armature):
        """Get all mesh objects parented to this armature"""
        child_meshes = []
        for obj in bpy.data.objects:
            if (obj.type == 'MESH' and 
                obj.parent == armature):
                child_meshes.append(obj)
        return child_meshes
    
    def _check_and_fix_modifiers(self, mesh, armature):
        """Check and fix armature modifiers on a mesh"""
        # Find all armature modifiers
        armature_modifiers = [mod for mod in mesh.modifiers if mod.type == 'ARMATURE']
        
        # Check if we already have exactly one correct modifier
        if len(armature_modifiers) == 1 and armature_modifiers[0].object == armature:
            return 'CORRECT'
        
        if not self.fix_modifiers:
            return 'ISSUE_FOUND'
        
        # Remove all armature modifiers
        for mod in armature_modifiers:
            mesh.modifiers.remove(mod)
        
        # Add a new armature modifier
        mod = mesh.modifiers.new(name="Armature", type='ARMATURE')
        mod.object = armature
        
        # Ensure the modifier is first in the stack for best results
        while mesh.modifiers[0] != mod:
            bpy.ops.object.modifier_move_up({"object": mesh}, modifier=mod.name)
        
        return 'FIXED'

# Registration
def register():
    bpy.utils.register_class(ARMATURE_OT_delete_other_bones)
    bpy.utils.register_class(ARMATURE_OT_remove_unweighted_bones)
    bpy.utils.register_class(ARMATURE_OT_roll_selected_weights_to_parent)
    bpy.utils.register_class(ARMATURE_OT_check_fix_modifiers)

def unregister():
    bpy.utils.unregister_class(ARMATURE_OT_check_fix_modifiers)
    bpy.utils.unregister_class(ARMATURE_OT_roll_selected_weights_to_parent)
    bpy.utils.unregister_class(ARMATURE_OT_remove_unweighted_bones)
    bpy.utils.unregister_class(ARMATURE_OT_delete_other_bones)

if __name__ == "__main__":
    register()
