"""Inspect and repair armature modifiers."""
import bpy
from bpy.props import BoolProperty


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
