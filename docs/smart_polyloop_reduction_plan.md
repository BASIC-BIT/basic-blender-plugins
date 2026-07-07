# Smart Polyloop Reduction Plan

## Goal

Add an avatar-friendly polycount reduction workflow to the Blender addon. The tool should find coherent edge loops that are cheap to dissolve, rank them, and eventually dissolve loops until a selected mesh reaches a target polygon count.

This is not a replacement for Blender's Decimate modifier. It is a safer avatar/clothing workflow that keeps the edit primitive understandable: select a coherent loop, score it, dissolve it, then re-score.

## Initial Definition

A v1 coherent loop is an edge path that:

- Starts from a mesh edge.
- Continues through vertices by choosing the outgoing edge most collinear with the incoming edge.
- Stops at branches, boundaries, non-manifold topology, or turns above the configured threshold.
- Has enough edges to be a meaningful reduction candidate.

This intentionally approximates Blender edge-loop selection. Exact alt-click parity can be added later if the approximation misses important clothing topology.

## Candidate Score

Lower score is better.

- Plane fit: PCA best-fit plane over loop vertices; RMS distance normalized by loop scale.
- Face angle: mean dihedral angle across candidate edges where two adjacent faces exist.
- Weight variation: max weight range across vertex groups used by loop vertices.

The score starts as:

```text
normalized_plane_deviation + 0.25 * mean_face_angle/pi + 0.50 * weight_variation
```

The constants are starting weights, not final truth. They should be tuned with real avatar/clothing meshes.

## Non-Destructive First Slice

The first addon operation is `mesh.preview_polyloop_reduction`.

- It analyzes the active mesh.
- It filters candidates by normalized plane deviation.
- It selects the best-scoring candidate edge loop(s) in Edit Mode.
- It does not dissolve anything.

## Destructive Dissolve (Stages 2-3, implemented)

The apply half lives in `core/polyloop_dissolve.py`, pure Python on the same
tuple mesh as the scorer, so the whole dissolve + iterate + re-score loop is
unit tested outside Blender (`tests/test_polyloop_dissolve.py`).

- `dissolve_loop(vertices, edges, faces, loop_edge_indices, vertex_weights=None)`
  performs a single loop dissolve with `bmesh.ops.dissolve_edges` semantics:
  merge the two faces sharing each loop edge, then dissolve the collinear
  valence-2 loop vertices left behind, re-index, and remap weights. Boundary
  and non-manifold loop edges are refused with `DissolveError` (guardrails from
  the simplification literature: never open a hole or edit non-manifold
  topology).
- `reduce_to_target(...)` is stage 3: re-score the current mesh, dissolve the
  single safest candidate, repeat until a target face count, a score quality
  floor, or no dissolvable candidate remains. Re-scoring every iteration is
  required because each dissolve changes adjacency, planarity, face angles, and
  weights. Deterministic (candidates come back in stable score order).

Blender operators `mesh.dissolve_polyloop_candidate` (single) and
`mesh.reduce_polyloop_to_target` (iterate) in `operators/polyloop_ops.py` are
thin glue: read the mesh into tuples, call the tested core, mirror the rebuilt
mesh back via `mesh.clear_geometry()` + `from_pydata` and re-apply remapped
weights. That glue is intentionally untested (no topology math in it).

## Next Steps

1. Add a `dry_run` report panel or CSV/JSON export with top candidates and scores.
2. Add bridge-pair scoring for loops between two nearly matching neighboring loops.
3. Add stronger armature awareness: bone-chain hot spots, protected joint zones, and optional shape-key delta penalties.
4. Add validation guards for UV seams, material boundaries, boundaries, non-manifold edges, and inverted normals.
5. Visual validation gate: before/after screenshots on real avatar/clothing meshes before trusting automated reductions (stage 5).

## Research References

- Blender Decimate Modifier, especially Planar mode and delimiter settings.
- Blender mesh selection/dissolve operators: `loop_multi_select`, `dissolve_edges`, and BMesh dissolve operations.
- Garland and Heckbert, `Surface Simplification Using Quadric Error Metrics`, SIGGRAPH 1997.
- Garland and Heckbert, `Simplifying Surfaces with Color and Texture using Quadric Error Metrics`, IEEE Visualization 1998.
