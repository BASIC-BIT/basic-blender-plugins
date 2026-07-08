import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty
from bpy.types import Operator

from ..core.polyloop_reduction import find_loop_candidates
from ..core.polyloop_dissolve import (
    DissolveError,
    dissolve_loop,
    reduce_to_target,
)


class MESH_OT_preview_polyloop_reduction(Operator):
    """Analyze the active mesh and select the best edge-loop reduction candidates"""
    bl_idname = "mesh.preview_polyloop_reduction"
    bl_label = "Preview Poly Loop Candidates"
    bl_options = {'REGISTER', 'UNDO'}

    candidate_count: IntProperty(
        name="Candidate Count",
        description="Number of best-scoring loop candidates to select",
        default=1,
        min=1,
        max=25,
    )

    min_edges: IntProperty(
        name="Minimum Edges",
        description="Ignore traced loops shorter than this many edges",
        default=8,
        min=2,
        max=500,
    )

    max_turn_degrees: FloatProperty(
        name="Max Turn Degrees",
        description="Stop tracing when a loop would turn more sharply than this at a vertex",
        default=75.0,
        min=5.0,
        max=180.0,
        precision=1,
    )

    max_plane_deviation_ratio: FloatProperty(
        name="Max Plane Deviation",
        description="Only select loops whose RMS plane deviation divided by loop scale is at or below this value",
        default=0.005,
        min=0.0,
        max=0.25,
        precision=4,
    )

    include_weight_penalty: BoolProperty(
        name="Weight-Aware Score",
        description="Penalize loops whose vertex group weights vary heavily across the loop",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        original_mode = obj.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        mesh = obj.data
        vertices = [tuple(v.co) for v in mesh.vertices]
        edges = [tuple(e.vertices) for e in mesh.edges]
        faces = [tuple(p.vertices) for p in mesh.polygons]
        vertex_weights = self._collect_vertex_weights(obj) if self.include_weight_penalty else None

        candidates = find_loop_candidates(
            vertices, edges, faces, vertex_weights=vertex_weights,
            min_edges=self.min_edges, max_turn_degrees=self.max_turn_degrees)
        candidates = [c for c in candidates
                      if c.normalized_plane_deviation <= self.max_plane_deviation_ratio]

        if not candidates:
            if original_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=original_mode)
            self.report({'INFO'}, "No poly loop candidates matched the current thresholds")
            return {'FINISHED'}

        selected = candidates[:self.candidate_count]
        self._select_candidate_edges(context, mesh, selected)

        best = selected[0]
        self.report(
            {'INFO'},
            f"Selected {len(selected)} candidate loop(s); best edges={best.edge_count}, "
            f"score={best.score:.5f}, plane={best.normalized_plane_deviation:.5f}, "
            f"weight={best.weight_variation:.3f}")
        return {'FINISHED'}

    def _collect_vertex_weights(self, obj):
        group_names = {vg.index: vg.name for vg in obj.vertex_groups}
        weights = {}
        for vertex in obj.data.vertices:
            groups = {}
            for group in vertex.groups:
                name = group_names.get(group.group)
                if name is not None and group.weight > 0.0:
                    groups[name] = group.weight
            if groups:
                weights[vertex.index] = groups
        return weights

    def _select_candidate_edges(self, context, mesh, candidates):
        for vertex in mesh.vertices:
            vertex.select = False
        for edge in mesh.edges:
            edge.select = False
        for polygon in mesh.polygons:
            polygon.select = False

        selected_edges = set()
        for candidate in candidates:
            selected_edges.update(candidate.edge_indices)
        for edge_index in selected_edges:
            mesh.edges[edge_index].select = True

        mesh.update()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='EDGE')


# --------------------------------------------------------------------------- #
# Shared bpy <-> tuple-mesh glue.
#
# NOTE: everything below is the thin, UNTESTED Blender operator layer. All the
# tested logic lives in ``core/polyloop_reduction.py`` (tracing + scoring) and
# ``core/polyloop_dissolve.py`` (dissolve + iterate-to-target). These operators
# only (1) read the active mesh into the pure tuple representation, (2) call the
# tested core, and (3) mirror the returned tuple mesh back into Blender. Keep it
# that way: no topology math here.
# --------------------------------------------------------------------------- #

def _destructive_rebuild_blockers(obj):
    """Inventory data the ``clear_geometry()``/``from_pydata`` rebuild cannot
    preserve, split by severity.

    Returns ``(hard_blockers, lossy_layers)`` lists of human-readable strings:

    - ``hard_blockers``: shape keys. Key blocks are per-vertex data, so a
      reindexed rebuild would corrupt or lose every blendshape. The operators
      refuse outright; shape-key-aware remapping is stage-4 roadmap
      (``docs/molt_design.md``).
    - ``lossy_layers``: UV maps, color attributes, and per-face material
      assignments. These are discarded by the rebuild; the operators only
      proceed when the user explicitly opts in via ``allow_attribute_loss``.
    """
    mesh = obj.data

    hard_blockers = []
    if mesh.shape_keys is not None and len(mesh.shape_keys.key_blocks) > 0:
        hard_blockers.append(
            f"{len(mesh.shape_keys.key_blocks)} shape key(s)")

    lossy_layers = []
    if len(mesh.uv_layers) > 0:
        lossy_layers.append(f"{len(mesh.uv_layers)} UV map(s)")
    if len(mesh.color_attributes) > 0:
        lossy_layers.append(
            f"{len(mesh.color_attributes)} color attribute(s)")
    if len(mesh.materials) > 1:
        lossy_layers.append(
            f"per-face assignments across {len(mesh.materials)} material slots")
    return hard_blockers, lossy_layers


def _refuse_unpreservable_data(operator, obj, allow_attribute_loss):
    """Shared guard for the destructive operators. Reports and returns True
    when the rebuild must not run on this mesh."""
    hard_blockers, lossy_layers = _destructive_rebuild_blockers(obj)
    if hard_blockers:
        operator.report(
            {'ERROR'},
            "Cannot rebuild mesh with " + ", ".join(hard_blockers)
            + ": shape keys would be lost or corrupted. Apply or remove "
              "them first (shape-key-aware reduction is roadmap).")
        return True
    if lossy_layers and not allow_attribute_loss:
        operator.report(
            {'ERROR'},
            "Rebuild would discard " + ", ".join(lossy_layers)
            + ". Enable 'Allow Attribute Loss' to proceed anyway.")
        return True
    return False


def _mesh_to_tuples(obj):
    """Read the active mesh into the pure ``(vertices, edges, faces, weights)``
    representation the core operates on.

    Weights are ALWAYS collected: the dissolve rebuilds the mesh geometry from
    scratch, so they must be threaded through and remapped to avoid destroying
    a rigged mesh's deformation weights. Whether they also feed the *scoring*
    penalty is a separate decision the operator makes with ``include_weight_penalty``.
    """
    mesh = obj.data
    vertices = [tuple(v.co) for v in mesh.vertices]
    edges = [tuple(e.vertices) for e in mesh.edges]
    faces = [tuple(p.vertices) for p in mesh.polygons]
    weights = _collect_vertex_weights(obj)
    return vertices, edges, faces, weights


def _collect_vertex_weights(obj):
    """``{vertex_index: {group_name: weight}}`` for the mesh's vertex groups."""
    group_names = {vg.index: vg.name for vg in obj.vertex_groups}
    weights = {}
    for vertex in obj.data.vertices:
        groups = {}
        for group in vertex.groups:
            name = group_names.get(group.group)
            if name is not None and group.weight > 0.0:
                groups[name] = group.weight
        if groups:
            weights[vertex.index] = groups
    return weights


def _write_tuples_to_mesh(obj, vertices, faces, vertex_weights):
    """Replace the object's geometry with the reduced tuple mesh.

    The core returns a fully rebuilt, re-indexed mesh, so the faithful mirror is
    to clear the geometry and rebuild from pydata, then re-apply the remapped
    vertex-group weights. Runs in OBJECT mode.
    """
    mesh = obj.data
    mesh.clear_geometry()
    mesh.from_pydata([list(v) for v in vertices], [], [list(f) for f in faces])
    mesh.update()

    if vertex_weights:
        # Ensure every referenced group exists, then re-apply remapped weights.
        existing = {vg.name: vg for vg in obj.vertex_groups}
        needed = set()
        for groups in vertex_weights.values():
            needed.update(groups.keys())
        for name in needed:
            if name not in existing:
                existing[name] = obj.vertex_groups.new(name=name)
        for new_index, groups in vertex_weights.items():
            for name, weight in groups.items():
                existing[name].add([new_index], weight, 'REPLACE')


class MESH_OT_dissolve_polyloop_candidate(Operator):
    """Dissolve the single safest edge-loop reduction candidate on the active mesh"""
    bl_idname = "mesh.dissolve_polyloop_candidate"
    bl_label = "Dissolve Safest Poly Loop"
    bl_options = {'REGISTER', 'UNDO'}

    min_edges: IntProperty(
        name="Minimum Edges",
        description="Ignore traced loops shorter than this many edges",
        default=8, min=2, max=500,
    )
    max_turn_degrees: FloatProperty(
        name="Max Turn Degrees",
        description="Stop tracing when a loop would turn more sharply than this",
        default=75.0, min=5.0, max=180.0, precision=1,
    )
    max_plane_deviation_ratio: FloatProperty(
        name="Max Plane Deviation",
        description="Only dissolve loops whose normalized plane deviation is at or below this",
        default=0.005, min=0.0, max=0.25, precision=4,
    )
    include_weight_penalty: BoolProperty(
        name="Weight-Aware Score",
        description="Penalize loops whose vertex group weights vary heavily",
        default=True,
    )
    allow_attribute_loss: BoolProperty(
        name="Allow Attribute Loss",
        description="Proceed even though the rebuild discards UV maps, color "
                    "attributes, and per-face material assignments "
                    "(meshes with shape keys are always refused)",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        if _refuse_unpreservable_data(self, obj, self.allow_attribute_loss):
            return {'CANCELLED'}
        original_mode = obj.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Weights are always collected (to preserve them across the rebuild);
        # only feed them to the scorer when the penalty is enabled.
        vertices, edges, faces, weights = _mesh_to_tuples(obj)
        score_weights = weights if self.include_weight_penalty else None

        candidates = find_loop_candidates(
            vertices, edges, faces, vertex_weights=score_weights,
            min_edges=self.min_edges, max_turn_degrees=self.max_turn_degrees)
        candidates = [c for c in candidates
                      if c.normalized_plane_deviation <= self.max_plane_deviation_ratio]

        if not candidates:
            self.report({'INFO'}, "No poly loop candidates matched the thresholds")
            return {'CANCELLED'}

        # Dissolve the safest candidate that passes the manifold guardrails.
        for candidate in candidates:
            try:
                result = dissolve_loop(
                    vertices, edges, faces, candidate.edge_indices,
                    vertex_weights=weights)
            except DissolveError:
                continue
            _write_tuples_to_mesh(obj, result.vertices, result.faces,
                                  result.vertex_weights)
            self.report(
                {'INFO'},
                f"Dissolved loop: faces {result.faces_before} -> "
                f"{result.faces_after} (removed {result.removed_edges} edges, "
                f"{result.removed_vertices} verts)")
            return {'FINISHED'}

        self.report({'INFO'}, "No candidate could be safely dissolved (boundary/non-manifold)")
        return {'CANCELLED'}


class MESH_OT_reduce_polyloop_to_target(Operator):
    """Iteratively dissolve the safest loops until the mesh reaches a target face count"""
    bl_idname = "mesh.reduce_polyloop_to_target"
    bl_label = "Reduce Poly Loops To Target"
    bl_options = {'REGISTER', 'UNDO'}

    target_faces: IntProperty(
        name="Target Faces",
        description="Stop dissolving once the mesh has at most this many faces",
        default=10000, min=1, max=10_000_000,
    )
    max_score: FloatProperty(
        name="Quality Floor",
        description="Never dissolve a loop scoring above this (safety over count)",
        default=1.0, min=0.0, max=100.0, precision=4,
    )
    max_iterations: IntProperty(
        name="Max Iterations",
        description="Safety cap on the number of dissolves",
        default=1000, min=1, max=1_000_000,
    )
    min_edges: IntProperty(
        name="Minimum Edges", default=8, min=2, max=500,
    )
    max_turn_degrees: FloatProperty(
        name="Max Turn Degrees", default=75.0, min=5.0, max=180.0, precision=1,
    )
    max_plane_deviation_ratio: FloatProperty(
        name="Max Plane Deviation",
        default=0.005, min=0.0, max=0.25, precision=4,
    )
    include_weight_penalty: BoolProperty(
        name="Weight-Aware Score", default=True,
    )
    allow_attribute_loss: BoolProperty(
        name="Allow Attribute Loss",
        description="Proceed even though the rebuild discards UV maps, color "
                    "attributes, and per-face material assignments "
                    "(meshes with shape keys are always refused)",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        if _refuse_unpreservable_data(self, obj, self.allow_attribute_loss):
            return {'CANCELLED'}
        original_mode = obj.mode
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Always preserve weights across the rebuild; the penalty toggle only
        # controls whether they influence candidate *scoring*.
        vertices, edges, faces, weights = _mesh_to_tuples(obj)

        out = reduce_to_target(
            vertices, edges, faces, vertex_weights=weights,
            target_faces=self.target_faces, max_score=self.max_score,
            max_iterations=self.max_iterations, min_edges=self.min_edges,
            max_turn_degrees=self.max_turn_degrees,
            max_plane_deviation_ratio=self.max_plane_deviation_ratio,
            score_with_weights=self.include_weight_penalty)

        if out["iterations"] == 0:
            self.report(
                {'INFO'},
                f"No dissolves applied (stopped: {out['stopped_reason']})")
            return {'CANCELLED'}

        _write_tuples_to_mesh(obj, out["vertices"], out["faces"],
                              out["vertex_weights"])
        self.report(
            {'INFO'},
            f"Reduced faces {out['faces_before']} -> {out['faces_after']} in "
            f"{out['iterations']} dissolve(s) (stopped: {out['stopped_reason']})")
        return {'FINISHED'}
