"""Destructive edge-loop dissolve for smart polycount reduction.

This is the "apply" half of the smart polyloop reduction workflow. The
scoring/tracing half lives in :mod:`polyloop_reduction`; this module takes a
scored :class:`~polyloop_reduction.LoopCandidate` (or a raw set of edge
indices) and performs the destructive mesh edit on the same bpy-free tuple
mesh representation used everywhere else in this package:

* ``vertices`` -- list of ``(x, y, z)`` coordinate tuples.
* ``edges``    -- list of ``(a, b)`` vertex-index pairs.
* ``faces``    -- list of vertex-index tuples (any arity; quads in practice).
* ``vertex_weights`` -- optional ``{vertex_index: {group_name: weight}}``.

Keeping this pure Python (only NumPy, transitively, via the scorer) means the
whole dissolve + iterate + re-score loop can be unit tested outside Blender,
exactly like the scorer. The Blender operator only has to mirror the same edit
into ``bmesh``.

Dissolve semantics mirror ``bmesh.ops.dissolve_edges`` on a coherent edge
loop:

1. Every loop edge shared by two faces is removed, and the two faces that
   shared it are merged into one polygon (the classic "dissolve edge" edit).
2. Loop vertices that become valence-2 and interior after the edge removals
   are dissolved out of the merged face boundary (the "dissolve verts" step),
   so a dissolved quad-strip loop leaves clean quads behind rather than n-gons
   with redundant collinear vertices.

Guardrails match the simplification literature the design spec cites: boundary
and non-manifold loop edges are refused (a dissolve there would create holes or
ambiguous topology), and the result is re-indexed so downstream code never sees
orphaned vertices.
"""

from dataclasses import dataclass

from . import polyloop_reduction


@dataclass(frozen=True)
class DissolveResult:
    """Outcome of dissolving a single loop.

    ``vertices``/``edges``/``faces``/``vertex_weights`` are the new mesh. The
    counters describe the edit so an operator (or a test) can assert on it
    without re-deriving topology.
    """

    vertices: list
    edges: list
    faces: list
    vertex_weights: dict
    removed_edges: int
    removed_vertices: int
    merged_faces: int
    faces_before: int
    faces_after: int


class DissolveError(ValueError):
    """Raised when a loop cannot be safely dissolved.

    The message names the guardrail that fired (boundary edge, non-manifold
    edge, or a loop that would delete a face outright) so callers can report a
    useful reason instead of silently skipping.
    """


def _edge_key(a, b):
    return (a, b) if a <= b else (b, a)


def _build_edge_faces(edges, faces):
    """Map each undirected edge key to the list of face indices touching it."""
    edge_faces = {}
    for face_index, face in enumerate(faces):
        n = len(face)
        for i in range(n):
            key = _edge_key(face[i], face[(i + 1) % n])
            edge_faces.setdefault(key, []).append(face_index)
    return edge_faces


def _merge_faces_across_edge(face_a, face_b, a, b):
    """Splice two polygons that share the boundary edge ``{a, b}``.

    Returns the merged vertex loop with the shared edge removed. Both faces are
    simple polygons; manifold neighbours wind in opposite directions along the
    shared edge. We take each face's arc that avoids the direct ``a-b`` segment
    and join them so the shared edge disappears from the merged boundary.

    ``chain_a`` runs ``b -> ... -> a`` (face_a the long way) and ``chain_b``
    runs ``a -> ... -> b`` (face_b the long way); concatenating and dropping the
    duplicated ``a`` and ``b`` endpoints yields the merged loop.
    """
    chain_a = _arc_excluding_edge(face_a, b, a)   # b ... a
    chain_b = _arc_excluding_edge(face_b, a, b)   # a ... b
    merged = list(chain_a) + list(chain_b)[1:-1]
    return merged


def _arc_excluding_edge(face, start, end):
    """Return the vertex arc of ``face`` from ``start`` to ``end`` that does NOT
    traverse the direct ``start-end`` edge (i.e. the long way around).

    ``face`` is a cyclic polygon containing the adjacent pair {start, end}. The
    result begins at ``start`` and ends at ``end``.
    """
    n = len(face)
    si = face.index(start)
    # Two directions; pick the one whose immediate next vertex is NOT ``end``.
    forward_next = face[(si + 1) % n]
    if forward_next == end:
        # Going forward hits the shared edge immediately; go backward instead.
        arc = [face[(si - k) % n] for k in range(n)]
    else:
        arc = [face[(si + k) % n] for k in range(n)]
    # arc starts at start; truncate at first occurrence of end.
    out = []
    for v in arc:
        out.append(v)
        if v == end:
            break
    return out


def dissolve_loop(vertices, edges, faces, loop_edge_indices,
                  vertex_weights=None, dissolve_verts=True):
    """Dissolve a coherent edge loop from the tuple mesh.

    Parameters
    ----------
    vertices, edges, faces:
        The tuple mesh (see module docstring).
    loop_edge_indices:
        Indices into ``edges`` naming the loop to dissolve. These are the same
        indices a :class:`~polyloop_reduction.LoopCandidate` reports in
        ``edge_indices``.
    vertex_weights:
        Optional ``{vertex_index: {group: weight}}``; re-indexed to match the
        surviving vertices in the result.
    dissolve_verts:
        When true (default) collinear loop vertices left with valence 2 are
        removed from the merged faces, matching Blender's dissolve behaviour.

    Returns
    -------
    DissolveResult

    Raises
    ------
    DissolveError
        If any loop edge is on a boundary (touches <2 faces) or is non-manifold
        (touches >2 faces).
    """
    edges = [tuple(e) for e in edges]
    faces = [list(f) for f in faces]
    faces_before = len(faces)

    loop_edge_keys = []
    for ei in loop_edge_indices:
        a, b = edges[ei]
        loop_edge_keys.append(_edge_key(a, b))
    loop_edge_key_set = set(loop_edge_keys)

    edge_faces = _build_edge_faces(edges, faces)

    # Guardrail: refuse boundary / non-manifold loop edges up front.
    for key in loop_edge_keys:
        touching = edge_faces.get(key, [])
        if len(touching) < 2:
            raise DissolveError(
                f"loop edge {key} is on a boundary (touches {len(touching)} "
                f"face(s)); dissolving it would open a hole")
        if len(touching) > 2:
            raise DissolveError(
                f"loop edge {key} is non-manifold (touches {len(touching)} "
                f"faces); refusing to dissolve")

    # Collect the loop vertices (endpoints of the loop edges).
    loop_vertices = set()
    for key in loop_edge_keys:
        loop_vertices.update(key)

    # --- Step 1: merge faces across each loop edge. ---------------------------
    # Union-find over faces so a run of shared loop edges collapses the whole
    # strip of quads into one merged polygon deterministically.
    parent = list(range(len(faces)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    for key in loop_edge_keys:
        fa, fb = edge_faces[key]
        union(fa, fb)

    # Group faces by their merged component.
    groups = {}
    for fi in range(len(faces)):
        groups.setdefault(find(fi), []).append(fi)

    merged_faces_count = sum(1 for members in groups.values() if len(members) > 1)

    new_faces = []
    for root, members in sorted(groups.items()):
        if len(members) == 1:
            new_faces.append(list(faces[members[0]]))
            continue
        merged = _merge_face_group(faces, members, loop_edge_key_set)
        new_faces.append(merged)

    # --- Step 2: dissolve interior loop vertices left at valence 2. -----------
    removed_vertices = set()
    if dissolve_verts:
        new_faces, removed_vertices = _dissolve_interior_vertices(
            new_faces, loop_vertices)

    # --- Step 3: rebuild edges from the surviving faces. ----------------------
    new_edges = _edges_from_faces(new_faces)

    # --- Step 4: re-index vertices, dropping any now unused. ------------------
    used = set()
    for face in new_faces:
        used.update(face)
    # Any loop vertex that was dissolved is not used; any wholly orphaned
    # vertex is also dropped.
    remap = {}
    new_vertices = []
    for old_index in range(len(vertices)):
        if old_index in used:
            remap[old_index] = len(new_vertices)
            new_vertices.append(tuple(vertices[old_index]))

    reindexed_faces = [tuple(remap[v] for v in face) for face in new_faces]
    reindexed_edges = [(remap[a], remap[b]) for (a, b) in new_edges]

    new_weights = None
    if vertex_weights is not None:
        new_weights = {}
        for old_index, groups_map in vertex_weights.items():
            if old_index in remap:
                new_weights[remap[old_index]] = dict(groups_map)

    removed_edge_count = len(edges) - len(reindexed_edges)

    return DissolveResult(
        vertices=new_vertices,
        edges=reindexed_edges,
        faces=reindexed_faces,
        vertex_weights=new_weights,
        removed_edges=removed_edge_count,
        removed_vertices=len(removed_vertices),
        merged_faces=merged_faces_count,
        faces_before=faces_before,
        faces_after=len(reindexed_faces),
    )


def _merge_face_group(faces, members, loop_edge_key_set):
    """Merge a connected group of faces into one polygon.

    The faces are connected through shared loop edges; repeatedly splice a face
    that shares a boundary loop edge with the accumulated polygon.
    """
    remaining = [list(faces[m]) for m in members]
    merged = remaining.pop(0)

    progress = True
    while remaining and progress:
        progress = False
        for i, face in enumerate(remaining):
            shared = _shared_loop_edge(merged, face, loop_edge_key_set)
            if shared is not None:
                a, b = shared
                merged = _merge_faces_across_edge(merged, face, a, b)
                remaining.pop(i)
                progress = True
                break

    # If some faces could not be spliced (unexpected topology), fall back to
    # keeping them separate is not possible in one polygon; raise so the caller
    # sees the guardrail rather than emitting a broken face.
    if remaining:
        raise DissolveError(
            "could not merge a connected face group; loop topology is not a "
            "simple manifold strip")
    return merged


def _shared_loop_edge(face_a, face_b, loop_edge_key_set):
    """Return a directed ``(a, b)`` edge shared by both faces that is a loop
    edge, oriented as it appears in ``face_a``; or ``None``."""
    n = len(face_a)
    set_b = set(face_b)
    for i in range(n):
        a = face_a[i]
        b = face_a[(i + 1) % n]
        if a in set_b and b in set_b and _edge_key(a, b) in loop_edge_key_set:
            return (a, b)
    return None


def _dissolve_interior_vertices(faces, loop_vertices):
    """Remove valence-2 loop vertices left collinear after face merging.

    A loop vertex is dissolved when, across every face that still contains it,
    it is flanked by exactly two *distinct* neighbours in total (i.e. it has
    become a valence-2 vertex sitting mid-edge of the merged topology). This
    covers three cases uniformly:

    * a boundary loop vertex now interior to one merged face (one face, two
      neighbours);
    * a fully interior loop vertex sitting on the shared edge between two merged
      faces (two faces, same two neighbours) -- it is removed from *both* so the
      shared edge ``x-v-y`` becomes ``x-y`` on both sides, staying manifold.

    Vertices whose neighbour set is not exactly two (a T-junction or a corner
    where the loop bends) are kept, so we never open a hole or fold a face.
    """
    # For each loop vertex, gather the faces containing it and its neighbours
    # within each such face.
    membership = {}
    neighbours = {}
    for fi, face in enumerate(faces):
        n = len(face)
        for i, v in enumerate(face):
            if v not in loop_vertices:
                continue
            membership.setdefault(v, []).append(fi)
            prev_v = face[(i - 1) % n]
            next_v = face[(i + 1) % n]
            neighbours.setdefault(v, set()).update((prev_v, next_v))

    removed = set()
    for v, face_list in membership.items():
        # A vertex appearing twice in one face (pinched) is unsafe -> keep.
        if any(faces[fi].count(v) != 1 for fi in face_list):
            continue
        # Removing from a triangle would degenerate it -> keep.
        if any(len(faces[fi]) <= 3 for fi in face_list):
            continue
        distinct = neighbours.get(v, set()) - {v}
        if len(distinct) == 2:
            removed.add(v)

    if not removed:
        return faces, removed

    new_faces = []
    for face in faces:
        new_face = [v for v in face if v not in removed]
        if len(new_face) >= 3:
            new_faces.append(new_face)
    return new_faces, removed


def _edges_from_faces(faces):
    """Derive the undirected edge list implied by the faces (deduplicated)."""
    seen = set()
    edges = []
    for face in faces:
        n = len(face)
        for i in range(n):
            a = face[i]
            b = face[(i + 1) % n]
            key = _edge_key(a, b)
            if key not in seen:
                seen.add(key)
                edges.append((a, b))
    return edges


def reduce_to_target(vertices, edges, faces, vertex_weights=None,
                     target_faces=None, max_score=None, max_iterations=1000,
                     min_edges=4, max_turn_degrees=75.0,
                     max_plane_deviation_ratio=None, score_with_weights=True):
    """Iteratively dissolve the safest loop until a target is met.

    This is stage 3 of the design spec: repeatedly re-score the *current* mesh,
    pick the single safest candidate, dissolve it, and repeat. Re-scoring every
    iteration is required because each dissolve changes adjacency, planarity,
    face angles, and weights (the spec's "Polygon target mode must be
    iterative" open question).

    Stopping conditions (whichever is hit first):

    * ``target_faces`` -- stop once ``len(faces) <= target_faces``.
    * ``max_score``    -- stop when the safest remaining candidate scores above
      this quality floor (never dissolve a risky loop just to hit a count).
    * ``max_plane_deviation_ratio`` -- skip candidates whose normalized plane
      deviation exceeds this (mirrors the preview operator's filter).
    * no dissolvable candidate remains, or ``max_iterations`` reached.

    Deterministic: candidates come back sorted by score, ties broken by the
    scorer's stable ordering, so the same input always yields the same
    reduction sequence.

    Returns
    -------
    dict with ``vertices``, ``edges``, ``faces``, ``vertex_weights``,
    ``iterations`` (number of dissolves applied), ``faces_before``,
    ``faces_after``, and ``stopped_reason``.
    """
    vertices = [tuple(v) for v in vertices]
    edges = [tuple(e) for e in edges]
    faces = [tuple(f) for f in faces]
    # ``weights`` are always preserved through the dissolves (remapped each
    # iteration); ``score_with_weights=False`` only drops them from the *scoring*
    # penalty, so disabling weight-aware ranking never destroys deformation
    # weights on a rigged mesh.
    weights = dict(vertex_weights) if vertex_weights is not None else None

    faces_before = len(faces)
    iterations = 0
    stopped_reason = "target_reached"

    while True:
        if target_faces is not None and len(faces) <= target_faces:
            stopped_reason = "target_reached"
            break
        if iterations >= max_iterations:
            stopped_reason = "max_iterations"
            break

        candidates = polyloop_reduction.find_loop_candidates(
            vertices, edges, faces,
            vertex_weights=(weights if score_with_weights else None),
            min_edges=min_edges, max_turn_degrees=max_turn_degrees)

        if max_plane_deviation_ratio is not None:
            candidates = [c for c in candidates
                          if c.normalized_plane_deviation <= max_plane_deviation_ratio]

        if not candidates:
            stopped_reason = "no_candidates"
            break

        best = candidates[0]
        if max_score is not None and best.score > max_score:
            stopped_reason = "quality_floor"
            break

        # Try candidates in score order until one dissolves cleanly; a boundary
        # or non-manifold loop is skipped rather than aborting the whole run.
        applied = False
        for candidate in candidates:
            if max_score is not None and candidate.score > max_score:
                break
            try:
                result = dissolve_loop(
                    vertices, edges, faces, candidate.edge_indices,
                    vertex_weights=weights)
            except DissolveError:
                continue
            if result.faces_after >= len(faces):
                # No progress (degenerate); skip to avoid an infinite loop.
                continue
            vertices = result.vertices
            edges = result.edges
            faces = result.faces
            weights = result.vertex_weights
            iterations += 1
            applied = True
            break

        if not applied:
            stopped_reason = "no_dissolvable_candidate"
            break

    return {
        "vertices": vertices,
        "edges": edges,
        "faces": faces,
        "vertex_weights": weights,
        "iterations": iterations,
        "faces_before": faces_before,
        "faces_after": len(faces),
        "stopped_reason": stopped_reason,
    }
