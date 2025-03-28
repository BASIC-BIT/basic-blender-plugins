import bpy
from bpy.props import BoolProperty

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
    bpy.utils.register_class(ARMATURE_OT_check_fix_modifiers)

def unregister():
    bpy.utils.unregister_class(ARMATURE_OT_check_fix_modifiers)
    bpy.utils.unregister_class(ARMATURE_OT_delete_other_bones)

if __name__ == "__main__":
    register()