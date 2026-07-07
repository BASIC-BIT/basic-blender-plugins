import bpy
import numpy as np
from bpy.types import Operator
from bpy.props import BoolProperty, FloatProperty, IntProperty
from mathutils import Vector
from ..core.mirror_utils import build_mirror_vertex_mapping, create_vertex_mirror_mapping

# Flip an X-mirrored delta
_MIRROR_X = np.array([-1.0, 1.0, 1.0])


class SHAPEKEY_OT_heuristic_smooth(Operator):
    """Detect pinching/stretching artifacts on the active shape key by comparing each vertex's delta against its 1-ring and 2-ring neighborhood, then smooth only the flagged vertices"""
    bl_idname = "shapekey.heuristic_smooth"
    bl_label = "Heuristic Blendshape Smoothing"
    bl_options = {'REGISTER', 'UNDO'}

    sensitivity_k: FloatProperty(
        name="Sensitivity (k)",
        description="Flag a vertex when its delta deviates from the neighborhood mean by more than mean + k * stddev of the local neighborhood difference distribution (lower = more aggressive)",
        default=2.0,
        min=0.1,
        max=10.0,
        precision=2
    )

    direction_weight: FloatProperty(
        name="Direction Weight",
        description="Extra flagging weight for deltas whose direction diverges from the neighborhood mean (asymmetric stretching)",
        default=0.5,
        min=0.0,
        max=2.0,
        precision=2
    )

    min_deviation: FloatProperty(
        name="Min Deviation",
        description="Absolute deviation floor (in Blender units) below which vertices are never flagged, to avoid flagging numeric noise in flat regions",
        default=0.0001,
        min=0.0,
        max=1.0,
        precision=5
    )

    iterations: IntProperty(
        name="Iterations",
        description="Number of smoothing passes applied to flagged vertices",
        default=2,
        min=1,
        max=20
    )

    strength: FloatProperty(
        name="Strength",
        description="How far each pass blends a flagged vertex's delta toward the neighborhood weighted mean",
        default=0.6,
        min=0.0,
        max=1.0,
        precision=2
    )

    use_mirror: BoolProperty(
        name="Mirror Symmetric",
        description="When the mesh is X-symmetric, flag and smooth artifacts symmetrically across the X axis so left/right errors cancel instead of multiplying",
        default=True
    )

    preview_only: BoolProperty(
        name="Preview Only (Select Artifacts)",
        description="Only select the flagged artifact vertices in Edit Mode for inspection; the shape key is not modified",
        default=False
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (obj and obj.type == 'MESH' and obj.data.shape_keys
                and obj.active_shape_key_index > 0)  # Index 0 is Basis

    def execute(self, context):
        obj = context.active_object
        key = obj.active_shape_key
        shape_keys = obj.data.shape_keys.key_blocks

        # Resolve the key this shape key is relative to (normally Basis)
        basis_key = key.relative_key
        if basis_key is None or basis_key == key:
            basis_key = shape_keys[0]
        if basis_key == key:
            self.report({'ERROR'}, "Shape key has no valid relative key")
            return {'CANCELLED'}

        original_mode = obj.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        mesh = obj.data
        vertex_count = len(mesh.vertices)

        # Pull basis and key coordinates into numpy via foreach_get
        # (fast batched access on avatar-sized meshes)
        buffer = np.empty(vertex_count * 3, dtype=np.float32)
        basis_key.data.foreach_get('co', buffer)
        basis_co = buffer.reshape(vertex_count, 3).astype(np.float64)
        buffer = np.empty(vertex_count * 3, dtype=np.float32)
        key.data.foreach_get('co', buffer)
        key_co = buffer.reshape(vertex_count, 3).astype(np.float64)

        # Per-vertex deltas of the shape key
        deltas = key_co - basis_co

        # Build 1-ring and 2-ring neighbor sets from mesh edges (once per run)
        neighbors, second_ring = self._build_neighborhoods(mesh)

        # Flag artifact vertices against their local neighborhood distribution
        flagged = self._flag_artifacts(deltas, neighbors, second_ring)

        # Mirror handling: symmetrize the flag set across X when the mesh is symmetric
        mirror_pairs = []
        center_vertices = []
        if self.use_mirror:
            tolerance = getattr(context.scene, "shapekey_mirror_tolerance", 0.001)
            mirror_pairs, center_vertices = self._build_mirror_pairs(basis_key, tolerance)
            for src_idx, tgt_idx in mirror_pairs:
                if flagged[src_idx] or flagged[tgt_idx]:
                    flagged[src_idx] = True
                    flagged[tgt_idx] = True

        flagged_indices = np.nonzero(flagged)[0]

        if len(flagged_indices) == 0:
            if original_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=original_mode)
            self.report({'INFO'}, f"No artifact vertices found on '{key.name}'")
            return {'FINISHED'}

        if self.preview_only:
            # Select only the flagged vertices so the user can inspect them in Edit Mode
            self._select_vertices(context, mesh, flagged)
            bpy.ops.object.mode_set(mode='EDIT')
            self.report({'INFO'},
                        f"Flagged {len(flagged_indices)} artifact vertices on '{key.name}' (preview only, shape key unchanged)")
            return {'FINISHED'}

        # Smooth flagged deltas toward the neighborhood weighted mean;
        # unflagged vertices are never touched
        deltas = self._smooth_deltas(deltas, flagged_indices, neighbors, second_ring)

        # Enforce X symmetry on the smoothed result so left/right errors cancel
        if mirror_pairs:
            for src_idx, tgt_idx in mirror_pairs:
                if flagged[src_idx]:
                    average = 0.5 * (deltas[src_idx] + deltas[tgt_idx] * _MIRROR_X)
                    deltas[src_idx] = average
                    deltas[tgt_idx] = average * _MIRROR_X
            # Center-seam vertices must not drift off the mirror plane
            for center_idx in center_vertices:
                if flagged[center_idx]:
                    deltas[center_idx][0] = 0.0

        # Write back the flagged vertices only
        for i in flagged_indices:
            co = basis_co[i] + deltas[i]
            key.data[i].co = Vector((co[0], co[1], co[2]))

        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=original_mode)

        mirror_note = f", {len(mirror_pairs)} mirror pairs" if mirror_pairs else ""
        self.report({'INFO'},
                    f"Smoothed {len(flagged_indices)} artifact vertices on '{key.name}' "
                    f"({self.iterations} iterations, strength {self.strength:.2f}{mirror_note})")
        return {'FINISHED'}

    def _build_neighborhoods(self, mesh):
        """Build 1-ring adjacency from mesh edges, plus the 2-ring
        (neighbors-of-neighbors minus self and the 1-ring)."""
        vertex_count = len(mesh.vertices)
        neighbors = [[] for _ in range(vertex_count)]
        for edge in mesh.edges:
            a, b = edge.vertices
            neighbors[a].append(b)
            neighbors[b].append(a)

        second_ring = []
        for i in range(vertex_count):
            ring = set()
            for j in neighbors[i]:
                ring.update(neighbors[j])
            ring.discard(i)
            ring.difference_update(neighbors[i])
            second_ring.append(list(ring))

        return neighbors, second_ring

    def _neighborhood_mean(self, deltas, ring1, ring2):
        """Weighted mean delta of a neighborhood (1-ring weight 1.0, 2-ring weight 0.5)."""
        total_weight = len(ring1) + 0.5 * len(ring2)
        mean = deltas[ring1].sum(axis=0)
        if ring2:
            mean = mean + 0.5 * deltas[ring2].sum(axis=0)
        return mean / total_weight

    def _flag_artifacts(self, deltas, neighbors, second_ring):
        """Flag vertices whose delta deviates from the neighborhood mean by more
        than mean + k * stddev of the local neighborhood difference distribution,
        with extra weight on direction divergence (asymmetric stretching)."""
        vertex_count = len(neighbors)
        flagged = np.zeros(vertex_count, dtype=bool)
        for i in range(vertex_count):
            ring1 = neighbors[i]
            ring2 = second_ring[i]
            if len(ring1) + len(ring2) < 3:
                continue

            mean_delta = self._neighborhood_mean(deltas, ring1, ring2)

            # Local difference distribution: how much the neighborhood disagrees internally
            local_norms = np.linalg.norm(deltas[ring1 + ring2] - mean_delta, axis=1)
            local_mean = local_norms.mean()
            local_std = local_norms.std()

            deviation = np.linalg.norm(deltas[i] - mean_delta)

            # Extra weight on asymmetric stretching: deltas pointing away from
            # the neighborhood direction get their deviation amplified
            own_length = np.linalg.norm(deltas[i])
            mean_length = np.linalg.norm(mean_delta)
            if own_length > 1e-9 and mean_length > 1e-9:
                cosine = np.dot(deltas[i], mean_delta) / (own_length * mean_length)
                deviation *= 1.0 + self.direction_weight * (1.0 - cosine)

            if deviation > local_mean + self.sensitivity_k * local_std and deviation > self.min_deviation:
                flagged[i] = True
        return flagged

    def _smooth_deltas(self, deltas, flagged_indices, neighbors, second_ring):
        """Blend flagged deltas toward the neighborhood weighted mean.
        Double-buffered so each iteration reads a consistent state."""
        for _ in range(self.iterations):
            new_deltas = deltas.copy()
            for i in flagged_indices:
                ring1 = neighbors[i]
                ring2 = second_ring[i]
                if len(ring1) + len(ring2) == 0:
                    continue
                mean_delta = self._neighborhood_mean(deltas, ring1, ring2)
                new_deltas[i] = deltas[i] + self.strength * (mean_delta - deltas[i])
            deltas = new_deltas
        return deltas

    def _build_mirror_pairs(self, basis_key, tolerance):
        """Detect X-mirror vertex pairs using the addon's octree matching helpers.
        Returns ([], center_vertices) when the mesh is not sufficiently symmetric."""
        left_vertices, right_vertices, center_vertices = build_mirror_vertex_mapping(basis_key)
        if not left_vertices or not right_vertices:
            return [], center_vertices
        _, _, mirror_map, _ = create_vertex_mirror_mapping(
            basis_key, 'L', left_vertices, right_vertices, center_vertices, tolerance)
        pairs = [(src, tgt) for src, tgt in mirror_map.items() if src != tgt]
        # Require most of the smaller side to be matched before trusting symmetry
        min_side = min(len(left_vertices), len(right_vertices))
        if min_side == 0 or len(pairs) / min_side < 0.8:
            return [], center_vertices
        return pairs, center_vertices

    def _select_vertices(self, context, mesh, flagged):
        """Select exactly the flagged vertices (and nothing else) in object mode data."""
        mesh.vertices.foreach_set('select', flagged)
        mesh.edges.foreach_set('select', np.zeros(len(mesh.edges), dtype=bool))
        mesh.polygons.foreach_set('select', np.zeros(len(mesh.polygons), dtype=bool))
        context.tool_settings.mesh_select_mode = (True, False, False)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "sensitivity_k")
        layout.prop(self, "direction_weight")
        layout.prop(self, "min_deviation")
        layout.prop(self, "iterations")
        layout.prop(self, "strength")
        layout.prop(self, "use_mirror")
        layout.prop(self, "preview_only")
