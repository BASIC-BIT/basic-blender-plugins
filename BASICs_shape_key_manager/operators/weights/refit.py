"""Stage explicit clothing refits before changing the artist's weight data."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator

from ...core.vertex_group_utils import snapshot_vertex_groups, restore_vertex_groups
from ...core.weight_refit import refit_vertex_weights


def weight_rows(obj):
    names = {g.index: g.name for g in obj.vertex_groups}
    return [{names[g.group]: g.weight for g in v.groups} for v in obj.data.vertices]


def deform_groups(obj):
    modifiers = [m for m in obj.modifiers if m.type == 'ARMATURE' and m.object]
    if len(modifiers) != 1:
        raise ValueError(f'{obj.name} needs exactly one Armature modifier with a rig')
    rig = modifiers[0].object
    if rig.data.pose_position != 'REST':
        if any(abs(p.matrix[r][c] - p.bone.matrix_local[r][c]) > 1e-5
               for p in rig.pose.bones for r in range(4) for c in range(4)):
            raise ValueError(f'{rig.name} must be in its fitted rest pose before refitting')
    return {b.name for b in rig.data.bones if b.use_deform} & set(obj.vertex_groups.keys())


def transfer_body_weights(context, source, staged, *, vert_mapping,
                          use_max_distance, max_distance):
    with context.temp_override(object=source, active_object=source,
                               selected_objects=[source, staged],
                               selected_editable_objects=[source, staged]):
        return bpy.ops.object.data_transfer(
            data_type='VGROUP_WEIGHTS', use_create=True, vert_mapping=vert_mapping,
            use_max_distance=use_max_distance, max_distance=max_distance,
            layers_select_src='ALL', layers_select_dst='NAME',
            mix_mode='REPLACE', mix_factor=1.0)


def refit_clothing_weights(context, source, target, *, vert_mapping='POLYINTERP_NEAREST',
                            use_max_distance=True, max_distance=0.05,
                            max_influences=None):
    """Refit bone weights atomically; rigs, mesh geometry and shape keys stay intact."""
    if source == target or source.type != 'MESH' or target.type != 'MESH':
        raise ValueError('Choose a separate body and clothing mesh')
    if target.mode not in {'OBJECT', 'WEIGHT_PAINT'} or source.mode != 'OBJECT':
        raise ValueError('Use Object Mode, or Weight Paint on clothing, before refitting')
    if target.data.users != 1:
        raise ValueError('Clothing mesh data must be single-user before refitting')
    if target.library or target.data.library:
        raise ValueError('Clothing must be locally editable')
    original_deform = deform_groups(target)
    source_deform = deform_groups(source)
    if not source_deform:
        raise ValueError('The body has no deform-bone weight groups')
    preserved = {g.name for g in target.vertex_groups
                 if g.lock_weight and g.name in original_deform}
    utilities = set(target.vertex_groups.keys()) - original_deform
    collisions = utilities & source_deform
    if collisions:
        raise ValueError('Body bones conflict with clothing utility groups: '
                         + ', '.join(sorted(collisions)))
    original = snapshot_vertex_groups(target, set(target.vertex_groups.keys()))
    original_rows = weight_rows(target)
    active_name = target.vertex_groups.active.name if target.vertex_groups.active else None
    old_mode = target.mode
    source_hidden, source_unselectable = source.hide_get(), source.hide_select
    staged = staged_mesh = None
    try:
        if old_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        staged = target.copy()
        staged_mesh = target.data.copy()
        staged.data = staged_mesh
        staged.name = 'BASIC Refitting (temporary)'
        context.scene.collection.objects.link(staged)
        staged.hide_viewport = False
        staged.hide_set(False)
        staged.hide_select = False
        for group in list(staged.vertex_groups):
            if group.name in original_deform:
                staged.vertex_groups.remove(group)
        source.hide_set(False)
        source.hide_select = False
        context.view_layer.update()
        status = transfer_body_weights(
            context, source, staged, vert_mapping=vert_mapping,
            use_max_distance=use_max_distance, max_distance=max_distance)
        if 'FINISHED' not in status:
            raise RuntimeError('Body weight transfer was cancelled; clothing was not changed')

        planned_rows = []
        for index, (old, transferred) in enumerate(zip(original_rows, weight_rows(staged))):
            body = {name: weight for name, weight in transferred.items() if name in source_deform}
            try:
                planned_rows.append(refit_vertex_weights(
                    old, body, original_deform, preserved, max_influences))
            except ValueError as error:
                raise ValueError(f'Vertex {index}: {error}. Clothing was not changed') from error

        names = utilities | preserved | source_deform
        ordered = [entry['name'] for entry in original if entry['name'] in names]
        ordered += [g.name for g in source.vertex_groups if g.name in names and g.name not in ordered]
        locks = {entry['name']: entry['lock_weight'] for entry in original}
        planned = [{'name': name, 'lock_weight': locks.get(name, False), 'weights': {}}
                   for name in ordered]
        by_name = {entry['name']: entry for entry in planned}
        for index, row in enumerate(planned_rows):
            for name, weight in row.items():
                by_name[name]['weights'][index] = weight

        try:
            target.vertex_groups.clear()
            restore_vertex_groups(target, planned)
            actual = weight_rows(target)
            if any(set(written) != set(expected) or
                   any(abs(written[name] - weight) > 1e-6 for name, weight in expected.items())
                   for written, expected in zip(actual, planned_rows)):
                raise RuntimeError('Refit weight verification failed')
        except Exception:
            target.vertex_groups.clear()
            restore_vertex_groups(target, original)
            raise
        finally:
            if active_name and active_name in target.vertex_groups:
                target.vertex_groups.active_index = target.vertex_groups[active_name].index
        return {'preserved': len(preserved), 'vertices': len(planned_rows),
                'body_groups': len(source_deform - preserved)}
    finally:
        if staged:
            bpy.data.objects.remove(staged, do_unlink=True)
        if staged_mesh and staged_mesh.users == 0:
            bpy.data.meshes.remove(staged_mesh)
        source.hide_set(source_hidden)
        source.hide_select = source_unselectable
        if old_mode != 'OBJECT':
            context.view_layer.objects.active = target
            bpy.ops.object.mode_set(mode=old_mode)


class VERTEXGROUP_OT_refit_clothing_weights(Operator):
    """Replace clothing bone weights with body weights, preserving locked bone influence shares"""
    bl_idname = 'vertexgroup.refit_clothing_weights'
    bl_label = 'Refit Clothing Weights'
    bl_options = {'REGISTER', 'UNDO'}

    vert_mapping: EnumProperty(name='Vertex Mapping', items=[
        ('POLYINTERP_NEAREST', 'Nearest Face Interpolated', 'Interpolate the nearest body face'),
        ('POLYINTERP_VNORPROJ', 'Projected Face Interpolated', 'Project along vertex normals'),
        ('POLY_NEAREST', 'Nearest Face', 'Copy the nearest body face'),
        ('NEAREST', 'Nearest Vertex', 'Copy the nearest body vertex'),
    ], default='POLYINTERP_NEAREST')
    use_max_distance: BoolProperty(name='Use Max Distance', default=True)
    max_distance: FloatProperty(name='Max Distance', default=0.05, min=0.0001, max=10,
                                subtype='DISTANCE')
    limit_influences: BoolProperty(name='Limit Influences', default=False)
    max_influences: IntProperty(name='Max Influences', default=4, min=1, max=32)

    @classmethod
    def poll(cls, context):
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        return (context.object is not None and context.object.type == 'MESH'
                and context.object.mode in {'OBJECT', 'WEIGHT_PAINT'}
                and len(meshes) == 2)

    def execute(self, context):
        target = context.object
        sources = [o for o in context.selected_objects if o.type == 'MESH' and o != target]
        if target is None or len(sources) != 1:
            self.report({'ERROR'}, 'Select exactly one body and active clothing mesh')
            return {'CANCELLED'}
        try:
            result = refit_clothing_weights(
                context, sources[0], target, vert_mapping=self.vert_mapping,
                use_max_distance=self.use_max_distance, max_distance=self.max_distance,
                max_influences=self.max_influences if self.limit_influences else None)
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        self.report({'INFO'}, f"Refitted {result['vertices']} vertices; "
                    f"preserved {result['preserved']} locked bone groups. "
                    'Check the destination rig before posing.')
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=460)

    def draw(self, context):
        layout = self.layout
        target = context.object
        sources = [o for o in context.selected_objects if o.type == 'MESH' and o != target]
        layout.label(text=f'Body: {sources[0].name if len(sources) == 1 else "Choose one body"}')
        layout.label(text=f'Clothing: {target.name}')
        rig = target.find_armature()
        deform = {b.name for b in rig.data.bones if b.use_deform} if rig else set()
        locked = [g.name for g in target.vertex_groups if g.lock_weight and g.name in deform]
        layout.label(text=f'Preserve {len(locked)} locked bone groups:')
        for name in locked:
            layout.label(text=name, icon='LOCKED')
        if not locked:
            layout.label(text='None. All anatomical weights will be replaced.', icon='INFO')
        layout.label(text='Preserves influence shares; stored values may normalize.')
        layout.prop(self, 'vert_mapping')
        layout.prop(self, 'use_max_distance')
        if self.use_max_distance:
            layout.prop(self, 'max_distance')
        layout.prop(self, 'limit_influences')
        if self.limit_influences:
            layout.prop(self, 'max_influences')
