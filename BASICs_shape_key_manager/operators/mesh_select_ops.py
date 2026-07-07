import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty
from bpy.types import Operator
from mathutils.kdtree import KDTree


class MESH_OT_select_nearby_vertices(Operator):
    """Select vertices that have another vertex within the merge-by-distance threshold"""
    bl_idname = "mesh.select_nearby_vertices"
    bl_label = "Select Nearby Vertices"
    bl_description = "Select vertices that would be candidates for Merge by Distance without merging them"
    bl_options = {'REGISTER', 'UNDO'}

    distance: FloatProperty(
        name="Distance",
        description="Maximum distance between vertices to flag as nearby",
        default=0.0001,
        min=0.0,
        max=1.0,
        precision=6,
    )

    use_selection_scope: BoolProperty(
        name="Use Current Selection",
        description="When vertices are already selected in Edit Mode, only compare within that selection like Merge by Distance",
        default=True,
    )

    extend_selection: BoolProperty(
        name="Extend Selection",
        description="Add nearby vertices to the current selection instead of replacing it",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        mesh = obj.data
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        bpy.ops.mesh.select_mode(type='VERT')
        bm = bmesh.from_edit_mesh(mesh)
        bm.verts.ensure_lookup_table()

        visible_verts = [vert for vert in bm.verts if not vert.hide]
        selected_verts = [vert for vert in visible_verts if vert.select]
        if self.use_selection_scope and selected_verts:
            candidate_verts = selected_verts
            scope_label = "selected"
        else:
            candidate_verts = visible_verts
            scope_label = "visible"

        nearby_verts = self._find_nearby_vertices(candidate_verts, self.distance)

        if not self.extend_selection:
            for vert in bm.verts:
                vert.select_set(False)
            for edge in bm.edges:
                edge.select_set(False)
            for face in bm.faces:
                face.select_set(False)

        for vert in nearby_verts:
            vert.select_set(True)

        bmesh.update_edit_mesh(mesh)

        if not nearby_verts:
            self.report({'INFO'}, f"No nearby vertices found among {len(candidate_verts)} {scope_label} vertices")
        else:
            self.report(
                {'INFO'},
                f"Selected {len(nearby_verts)} nearby vertices among {len(candidate_verts)} {scope_label} vertices"
            )
        return {'FINISHED'}

    def _find_nearby_vertices(self, vertices, distance):
        if len(vertices) < 2:
            return set()

        tree = KDTree(len(vertices))
        for index, vert in enumerate(vertices):
            tree.insert(vert.co, index)
        tree.balance()

        nearby_indices = set()
        for index, vert in enumerate(vertices):
            for _co, other_index, _dist in tree.find_range(vert.co, distance):
                if other_index != index:
                    nearby_indices.add(index)
                    nearby_indices.add(other_index)

        return {vertices[index] for index in nearby_indices}
