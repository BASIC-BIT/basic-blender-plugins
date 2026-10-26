"""Owned native control armature creation and cleanup."""
from math import atan2, radians
import uuid
import bpy
from .rig_mapping import CHAINS


def pole_angle(root, end, pole):
    """Map the source rest roll to Blender's IK pole angle."""
    return pole_angle_frame(root.matrix_local, end, pole)


def pole_angle_frame(matrix, end, pole):
    axis = matrix.to_3x3().col[1].normalized()
    normal = (end - matrix.translation).cross(pole - matrix.translation)
    projected = normal.cross(axis).normalized()
    x = matrix.to_3x3().col[0].normalized()
    return -atan2(axis.dot(x.cross(projected)), x.dot(projected))


class NativeControls:
    def __init__(self, source, mapping, scene, calibration):
        self.objects, self.constraints = [], []
        self.scene, self.layer = scene, scene.view_layers[0]
        self.rig = None
        self.data = None
        self.targets, self.poles = {}, {}
        self.iks = {}
        prefix = 'BASIC_ClothingIK_' + uuid.uuid4().hex[:10]
        try:
            self.data = source.data.copy()
            self.rig = bpy.data.objects.new(prefix, self.data)
            self.rig.matrix_world = source.matrix_world.copy()
            scene.collection.objects.link(self.rig)
            self.objects.append(self.rig)
            active = self.layer.objects.active
            try:
                self.layer.objects.active = self.rig
                self.rig.select_set(True, view_layer=self.layer)
                with bpy.context.temp_override(scene=scene, view_layer=self.layer,
                                               object=self.rig, active_object=self.rig):
                    bpy.ops.object.mode_set(mode='EDIT')
                    for a, b, c in CHAINS.values():
                        for first, second in ((a, b), (b, c)):
                            bone = self.data.edit_bones[mapping[first]]
                            bone.tail = self.data.edit_bones[mapping[second]].head
                            bone.align_roll(source.data.bones[mapping[first]].matrix_local.to_3x3().col[2])
                    bpy.ops.object.mode_set(mode='OBJECT')
            finally:
                self.rig.select_set(False, view_layer=self.layer)
                self.layer.objects.active = active
            for bone in self.rig.pose.bones:
                bone.ik_stretch = 0
            for key, (a, b, c) in CHAINS.items():
                target = self.empty(prefix + '_' + c)
                target.parent = self.rig
                pole = self.empty(prefix + '_' + key + '_pole')
                self.targets[c], self.poles[key] = target, pole
                rest = self.data.bones[mapping[a]]
                end = self.data.bones[mapping[c]].head_local
                pole_point = rest.head_local + calibration['poles'][key]
                constraint = self.rig.pose.bones[mapping[b]].constraints.new('IK')
                constraint.target, constraint.pole_target = target, pole
                constraint.chain_count = 2
                constraint.use_stretch = False
                constraint.iterations = 128
                constraint.pole_angle = pole_angle(rest, end, pole_point)
                self.constraints.append(constraint)
                self.iks[key] = constraint
                for canonical in (a, b):
                    pose = self.rig.pose.bones[mapping[canonical]]
                    maximum = (145 if key.endswith('arm') else 135) if canonical == b else (150 if key.endswith('arm') else 110)
                    for axis in 'xyz':
                        setattr(pose, 'use_ik_limit_' + axis, True)
                        setattr(pose, 'ik_min_' + axis, -radians(maximum))
                        setattr(pose, 'ik_max_' + axis, radians(maximum))
                orientation = self.rig.pose.bones[mapping[c]].constraints.new('COPY_ROTATION')
                orientation.target = target
                # Pose/local spaces avoid introducing shear under object scale.
                orientation.owner_space = 'POSE'
                orientation.target_space = 'LOCAL'
                self.constraints.append(orientation)
            self.layer.update()
        except BaseException:
            self.close()
            raise

    def empty(self, name):
        obj = bpy.data.objects.new(name, None)
        self.scene.collection.objects.link(obj)
        self.objects.append(obj)
        return obj

    def update(self):
        self.layer.update()
        return self.rig.evaluated_get(self.layer.depsgraph)

    def close(self):
        for obj in reversed(self.objects):
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        self.objects.clear()
        if self.data is not None and self.data.name in bpy.data.armatures and self.data.users == 0:
            bpy.data.armatures.remove(self.data)
        self.data = None
