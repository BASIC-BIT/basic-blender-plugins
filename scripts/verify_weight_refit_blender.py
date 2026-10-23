"""Exercise explicit refits against real Blender objects, without user files."""

from pathlib import Path
import importlib
import sys
from unittest.mock import patch

import bpy
import bmesh

ROOT = Path(__file__).resolve().parents[1]
installed = '--installed-extension' in sys.argv
if not installed:
    sys.path.insert(0, str(ROOT))
package = ('bl_ext.user_default.basics_shape_key_manager' if installed
           else 'BASICs_shape_key_manager')
addon = importlib.import_module(package)
refit = importlib.import_module(package + '.operators.weights.refit')
snapshot_vertex_groups = importlib.import_module(
    package + '.core.vertex_group_utils').snapshot_vertex_groups


def rig(name, bones):
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for name in bones:
        bone = data.edit_bones.new(name)
        bone.head = (0, 0, 0)
        bone.tail = (0, 0, 1)
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(False)
    return obj


def mesh(name, armature, weights, z=0):
    data = bpy.data.meshes.new(name)
    data.from_pydata([(0, 0, z), (1, 0, z), (0, 1, z)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    for group_name, weight in weights.items():
        group = obj.vertex_groups.new(name=group_name)
        group.add([0, 1, 2], weight, 'REPLACE')
    obj.modifiers.new('Armature', 'ARMATURE').object = armature
    return obj


def select(source, target):
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    source.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.context.view_layer.update()


def fixture():
    body_rig = rig('BodyRig', ['Left arm', 'Chest'])
    old_rig = rig('OutfitRig', ['Arm_L', 'Bow'])
    source = mesh('Body', body_rig, {'Left arm': 0.3, 'Chest': 0.7, 'Mask': 0.9})
    target = mesh('Clothing', old_rig, {'Arm_L': 0.8, 'Bow': 0.6, 'Mask': 0.27}, z=0.01)
    target.vertex_groups['Bow'].lock_weight = True
    target.shape_key_add(name='Basis')
    target.shape_key_add(name='Fit').data[0].co.x += 0.03
    select(source, target)
    return source, target


def snapshot(obj):
    return snapshot_vertex_groups(obj, {g.name for g in obj.vertex_groups})


def assert_unchanged(obj, before, counts):
    assert snapshot(obj) == before
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == counts


def test_success():
    source, target = fixture()
    before_source = snapshot(source)
    keys = [(k.name, [tuple(v.co) for v in k.data]) for k in target.data.shape_keys.key_blocks]
    counts = (len(bpy.data.objects), len(bpy.data.meshes))
    result = bpy.ops.vertexgroup.refit_clothing_weights()
    assert result == {'FINISHED'}, result
    assert snapshot(source) == before_source
    assert keys == [(k.name, [tuple(v.co) for v in k.data])
                    for k in target.data.shape_keys.key_blocks]
    assert 'Arm_L' not in target.vertex_groups
    assert target.vertex_groups['Bow'].lock_weight
    assert target.modifiers[0].object.name.startswith('OutfitRig')
    for vertex in target.data.vertices:
        row = {target.vertex_groups[g.group].name: g.weight for g in vertex.groups}
        assert abs(row['Bow'] - 0.6 / 1.4) < 1e-6, row
        assert abs(row['Mask'] - 0.27) < 1e-6, row
        assert abs(row['Left arm'] + row['Chest'] - 0.8 / 1.4) < 1e-6, row
    assert (len(bpy.data.objects), len(bpy.data.meshes)) == counts


def failure_test(options=None, transfer_result=None, commit_failure=False):
    source, target = fixture()
    before = snapshot(target)
    counts = (len(bpy.data.objects), len(bpy.data.meshes))
    if transfer_result is not None:
        with patch.object(refit, 'transfer_body_weights', return_value=transfer_result):
            try:
                refit.refit_clothing_weights(bpy.context, source, target, **(options or {}))
            except (ValueError, RuntimeError):
                pass
            else:
                raise AssertionError('Cancellation should fail')
    elif commit_failure:
        real_restore = refit.restore_vertex_groups
        calls = []

        def fail_once(obj, values):
            calls.append(True)
            if len(calls) == 1:
                raise RuntimeError('Injected commit failure')
            return real_restore(obj, values)

        with patch.object(refit, 'restore_vertex_groups', side_effect=fail_once):
            try:
                refit.refit_clothing_weights(bpy.context, source, target)
            except RuntimeError:
                pass
            else:
                raise AssertionError('Commit should fail')
    else:
        try:
            refit.refit_clothing_weights(bpy.context, source, target, **(options or {}))
        except (ValueError, RuntimeError):
            pass
        else:
            raise AssertionError('Invalid transfer should fail')
    assert_unchanged(target, before, counts)


def test_cancelled_native_transfer():
    failure_test(transfer_result={'CANCELLED'})


def test_hidden_source_restored():
    source, target = fixture()
    source.hide_set(True)
    refit.refit_clothing_weights(bpy.context, source, target)
    assert source.hide_get()


def test_unmapped_vertices():
    failure_test(options={'max_distance': 0.0001})


def test_cap_conflict():
    failure_test(options={'max_influences': 1})


def test_commit_rollback():
    failure_test(commit_failure=True)


def test_shared_mesh_refused():
    source, target = fixture()
    linked = target.copy()
    bpy.context.scene.collection.objects.link(linked)
    before = snapshot(target)
    try:
        refit.refit_clothing_weights(bpy.context, source, target)
    except ValueError as error:
        assert 'single-user' in str(error)
    else:
        raise AssertionError('Shared mesh should fail')
    assert snapshot(target) == before


def test_mask_name_collision():
    source, target = fixture()
    target.vertex_groups.new(name='Left arm').add([0], 0.4, 'REPLACE')
    before = snapshot(target)
    try:
        refit.refit_clothing_weights(bpy.context, source, target)
    except ValueError as error:
        assert 'utility' in str(error)
    else:
        raise AssertionError('Utility collision should fail')
    assert snapshot(target) == before


def test_edit_mode_preserves_unsynchronized_weights():
    source, target = fixture()
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(target.data)
    layer = bm.verts.layers.deform.verify()
    bm.verts.ensure_lookup_table()
    bm.verts[0][layer][target.vertex_groups['Bow'].index] = 0.2
    bm.verts[0][layer][target.vertex_groups['Mask'].index] = 0.91
    try:
        refit.refit_clothing_weights(bpy.context, source, target)
    except ValueError as error:
        assert 'Object' in str(error)
    else:
        raise AssertionError('Edit Mode must be rejected without losing BMesh edits')
    assert target.mode == 'EDIT'
    bpy.ops.object.mode_set(mode='OBJECT')
    assert abs(target.vertex_groups['Mask'].weight(0) - 0.91) < 1e-6
    assert abs(target.vertex_groups['Bow'].weight(0) - 0.2) < 1e-6


def test_weight_paint_state_restored():
    source, target = fixture()
    bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
    before_selection = set(bpy.context.selected_objects)
    refit.refit_clothing_weights(bpy.context, source, target)
    assert target.mode == 'WEIGHT_PAINT'
    assert bpy.context.object == target
    assert set(bpy.context.selected_objects) == before_selection
    bpy.ops.object.mode_set(mode='OBJECT')


def test_repeated_refit_after_rig_integration():
    source, target = fixture()
    refit.refit_clothing_weights(bpy.context, source, target)
    before = snapshot(target)
    body_rig = source.find_armature()
    select(source, body_rig)
    bpy.ops.object.mode_set(mode='EDIT')
    bone = body_rig.data.edit_bones.new('Bow')
    bone.head, bone.tail = (0, 0, 0), (0, 0, 1)
    bpy.ops.object.mode_set(mode='OBJECT')
    target.modifiers[0].object = body_rig
    select(source, target)
    refit.refit_clothing_weights(bpy.context, source, target)
    after = snapshot(target)
    for old, new in zip(before, after):
        assert old['name'] == new['name']
        for index, weight in old['weights'].items():
            assert abs(new['weights'][index] - weight) < 1e-6


def test_fully_locked_vertex_without_mapping():
    source, target = fixture()
    target.vertex_groups['Arm_L'].lock_weight = True
    refit.refit_clothing_weights(bpy.context, source, target, max_distance=0.0001)
    for vertex in target.data.vertices:
        row = {target.vertex_groups[g.group].name: g.weight for g in vertex.groups}
        assert abs(row['Bow'] + row['Arm_L'] - 1) < 1e-6


if not installed:
    addon.register()
for name, function in sorted(list(globals().items())):
    if name.startswith('test_') and callable(function):
        function()
        print('PASS', name)
if not installed:
    addon.unregister()
print('WEIGHT_REFIT_BLENDER_PASS')
