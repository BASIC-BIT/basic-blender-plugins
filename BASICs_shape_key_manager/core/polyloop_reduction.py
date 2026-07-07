"""Candidate edge-loop analysis for smart polycount reduction.

This module is deliberately pure Python plus NumPy so the geometric
scoring can be unit-tested outside Blender. Blender operators should adapt
Mesh data into the simple ``vertices``, ``edges``, ``faces``, and optional
``vertex_weights`` structures used here.
"""

from dataclasses import dataclass
from math import acos, pi

import numpy as np


@dataclass(frozen=True)
class LoopCandidate:
    """A scored edge-loop candidate.

    Lower ``score`` is better. The first version intentionally reports and
    previews loops; destructive dissolve decisions should stay in later code
    that can re-score after every mesh edit.
    """

    edge_indices: tuple
    vertex_indices: tuple
    closed: bool
    edge_count: int
    length: float
    scale: float
    rms_plane_deviation: float
    max_plane_deviation: float
    normalized_plane_deviation: float
    mean_face_angle: float
    max_face_angle: float
    weight_variation: float
    score: float


def find_loop_candidates(vertices, edges, faces, vertex_weights=None,
                         min_edges=4, max_turn_degrees=75.0):
    """Find and score coherent edge-loop candidates.

    The loop tracer approximates Blender's edge-loop selection: start from an
    edge, continue through valence-4-ish vertices by choosing the outgoing edge
    that stays most collinear with the incoming edge, and stop at branches,
    boundaries, or sharp turns. This is intentionally conservative; exact
    Blender selection parity can come later if needed.
    """
    coords = np.asarray(vertices, dtype=np.float64)
    edge_pairs = tuple(tuple(edge) for edge in edges)
    adjacency = _build_vertex_edges(edge_pairs)
    edge_lookup = {frozenset(edge): i for i, edge in enumerate(edge_pairs)}
    face_normals, edge_faces = _build_face_data(coords, edge_pairs, faces)

    seen = set()
    candidates = []
    min_turn_cos = np.cos(np.deg2rad(max_turn_degrees))

    for edge_index, (a, b) in enumerate(edge_pairs):
        if edge_index in seen:
            continue

        forward_edges, forward_vertices, forward_closed = _trace_loop_direction(
            coords, edge_pairs, edge_lookup, adjacency, a, b, min_turn_cos)
        backward_edges, backward_vertices, backward_closed = _trace_loop_direction(
            coords, edge_pairs, edge_lookup, adjacency, b, a, min_turn_cos)

        edge_sequence = tuple(reversed(backward_edges[1:])) + tuple(forward_edges)
        vertex_sequence = tuple(reversed(backward_vertices[1:])) + tuple(forward_vertices)
        unique_edges = tuple(dict.fromkeys(edge_sequence))
        unique_vertices = tuple(dict.fromkeys(vertex_sequence))

        if len(unique_edges) < min_edges or unique_edges[0] in seen:
            seen.update(unique_edges)
            continue

        seen.update(unique_edges)
        candidate = score_loop_candidate(
            coords, edge_pairs, unique_edges, unique_vertices, face_normals,
            edge_faces, vertex_weights=vertex_weights,
            closed=(forward_closed or backward_closed))
        candidates.append(candidate)

    candidates.sort(key=lambda c: c.score)
    return candidates


def score_loop_candidate(coords, edge_pairs, edge_indices, vertex_indices,
                         face_normals, edge_faces, vertex_weights=None,
                         closed=False):
    """Score a loop by planarity, face-angle impact, and weight variation."""
    loop_coords = coords[list(vertex_indices)]
    scale = _candidate_scale(loop_coords)
    rms_dev, max_dev = _plane_deviation(loop_coords)
    normalized = rms_dev / scale if scale > 0.0 else 0.0
    mean_angle, max_angle = _face_angle_stats(edge_indices, face_normals, edge_faces)
    weight_variation = _weight_variation(vertex_indices, vertex_weights)

    # Initial cheap-risk score. Planarity dominates; face angle estimates
    # geometric impact; weight variation penalizes deformation-sensitive zones.
    score = normalized + 0.25 * (mean_angle / pi) + 0.50 * weight_variation

    return LoopCandidate(
        edge_indices=tuple(edge_indices),
        vertex_indices=tuple(vertex_indices),
        closed=closed,
        edge_count=len(edge_indices),
        length=sum(_edge_length(coords, edge_pairs[i]) for i in edge_indices),
        scale=scale,
        rms_plane_deviation=rms_dev,
        max_plane_deviation=max_dev,
        normalized_plane_deviation=normalized,
        mean_face_angle=mean_angle,
        max_face_angle=max_angle,
        weight_variation=weight_variation,
        score=score,
    )


def _build_vertex_edges(edges):
    adjacency = {}
    for edge_index, (a, b) in enumerate(edges):
        adjacency.setdefault(a, []).append((edge_index, b))
        adjacency.setdefault(b, []).append((edge_index, a))
    return adjacency


def _trace_loop_direction(coords, edges, edge_lookup, adjacency, start_a,
                          start_b, min_turn_cos):
    start_key = frozenset((start_a, start_b))
    start_edge_index = edge_lookup[start_key]
    edge_sequence = [start_edge_index]
    vertex_sequence = [start_a, start_b]
    visited_oriented = {(start_a, start_b)}
    prev_vertex = start_a
    current_vertex = start_b

    while True:
        next_step = _choose_next_edge(
            coords, adjacency, prev_vertex, current_vertex, min_turn_cos)
        if next_step is None:
            return edge_sequence, vertex_sequence, False

        next_edge_index, next_vertex = next_step
        oriented = (current_vertex, next_vertex)
        if oriented in visited_oriented:
            return edge_sequence, vertex_sequence, next_edge_index == start_edge_index
        if next_edge_index == start_edge_index:
            return edge_sequence, vertex_sequence, True

        visited_oriented.add(oriented)
        edge_sequence.append(next_edge_index)
        vertex_sequence.append(next_vertex)
        prev_vertex, current_vertex = current_vertex, next_vertex


def _choose_next_edge(coords, adjacency, prev_vertex, current_vertex, min_turn_cos):
    incident = adjacency.get(current_vertex, ())
    if len(incident) < 2 or len(incident) > 4:
        return None

    incoming = coords[current_vertex] - coords[prev_vertex]
    incoming_norm = np.linalg.norm(incoming)
    if incoming_norm <= 1e-12:
        return None
    incoming = incoming / incoming_norm

    best = None
    best_dot = -1.0
    for edge_index, other_vertex in incident:
        if other_vertex == prev_vertex:
            continue
        outgoing = coords[other_vertex] - coords[current_vertex]
        outgoing_norm = np.linalg.norm(outgoing)
        if outgoing_norm <= 1e-12:
            continue
        outgoing = outgoing / outgoing_norm
        dot = float(np.dot(incoming, outgoing))
        if dot > best_dot:
            best_dot = dot
            best = (edge_index, other_vertex)

    if best is None or best_dot < min_turn_cos:
        return None
    return best


def _build_face_data(coords, edges, faces):
    face_normals = []
    edge_faces = {i: [] for i in range(len(edges))}
    edge_lookup = {frozenset(edge): i for i, edge in enumerate(edges)}

    for face_index, face in enumerate(faces):
        normal = _face_normal(coords, face)
        face_normals.append(normal)
        face_vertices = list(face)
        for i, a in enumerate(face_vertices):
            b = face_vertices[(i + 1) % len(face_vertices)]
            edge_index = edge_lookup.get(frozenset((a, b)))
            if edge_index is not None:
                edge_faces[edge_index].append(face_index)
    return face_normals, edge_faces


def _face_normal(coords, face):
    if len(face) < 3:
        return np.zeros(3, dtype=np.float64)
    origin = coords[face[0]]
    normal = np.zeros(3, dtype=np.float64)
    for i in range(1, len(face) - 1):
        normal += np.cross(coords[face[i]] - origin, coords[face[i + 1]] - origin)
    norm = np.linalg.norm(normal)
    return normal / norm if norm > 1e-12 else normal


def _plane_deviation(points):
    if len(points) <= 3:
        return 0.0, 0.0
    centroid = points.mean(axis=0)
    centered = points - centroid
    covariance = centered.T @ centered / len(points)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    normal = eigenvectors[:, int(np.argmin(eigenvalues))]
    distances = np.abs(centered @ normal)
    return float(np.sqrt(np.mean(distances * distances))), float(np.max(distances))


def _candidate_scale(points):
    if len(points) == 0:
        return 0.0
    extents = points.max(axis=0) - points.min(axis=0)
    return max(float(np.linalg.norm(extents)), 1e-12)


def _face_angle_stats(edge_indices, face_normals, edge_faces):
    angles = []
    for edge_index in edge_indices:
        faces = edge_faces.get(edge_index, ())
        if len(faces) != 2:
            continue
        a = face_normals[faces[0]]
        b = face_normals[faces[1]]
        if np.linalg.norm(a) <= 1e-12 or np.linalg.norm(b) <= 1e-12:
            continue
        dot = float(np.clip(np.dot(a, b), -1.0, 1.0))
        angles.append(acos(dot))
    if not angles:
        return 0.0, 0.0
    return float(sum(angles) / len(angles)), float(max(angles))


def _weight_variation(vertex_indices, vertex_weights):
    if not vertex_weights:
        return 0.0

    group_names = set()
    for vertex_index in vertex_indices:
        group_names.update(vertex_weights.get(vertex_index, {}).keys())
    if not group_names:
        return 0.0

    ranges = []
    for group_name in group_names:
        values = [vertex_weights.get(vertex_index, {}).get(group_name, 0.0)
                  for vertex_index in vertex_indices]
        ranges.append(max(values) - min(values))
    return float(max(ranges)) if ranges else 0.0


def _edge_length(coords, edge):
    a, b = edge
    return float(np.linalg.norm(coords[a] - coords[b]))
