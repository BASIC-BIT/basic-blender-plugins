"""Tests for smart poly loop candidate scoring.

Runs without Blender:

    python tests/test_polyloop_reduction.py
"""

import importlib.util
import os
import sys


MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "BASICs_shape_key_manager", "core", "polyloop_reduction.py")

spec = importlib.util.spec_from_file_location("polyloop_reduction", MODULE_PATH)
polyloop = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = polyloop
spec.loader.exec_module(polyloop)


def make_strip_mesh(length=5):
    vertices = []
    for y in (0.0, 1.0):
        for x in range(length):
            vertices.append((float(x), y, 0.0))

    edges = []
    for y_offset in (0, length):
        for x in range(length - 1):
            edges.append((y_offset + x, y_offset + x + 1))
    for x in range(length):
        edges.append((x, length + x))

    faces = []
    for x in range(length - 1):
        faces.append((x, x + 1, length + x + 1, length + x))
    return vertices, edges, faces


def score_square(points, vertex_weights=None):
    edge_pairs = ((0, 1), (1, 2), (2, 3), (3, 0))
    face_normals, edge_faces = polyloop._build_face_data(points, edge_pairs, ())
    return polyloop.score_loop_candidate(
        polyloop.np.asarray(points, dtype=polyloop.np.float64),
        edge_pairs,
        (0, 1, 2, 3),
        (0, 1, 2, 3),
        face_normals,
        edge_faces,
        vertex_weights=vertex_weights,
        closed=True)


def test_find_loop_candidates_on_quad_strip():
    vertices, edges, faces = make_strip_mesh(length=6)
    candidates = polyloop.find_loop_candidates(vertices, edges, faces, min_edges=4)
    assert candidates
    assert candidates[0].edge_count >= 4
    assert candidates[0].normalized_plane_deviation == 0.0


def test_planar_loop_has_lower_deviation_than_warped_loop():
    planar = score_square(((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)))
    warped = score_square(((0, 0, 0), (1, 0, 0.2), (1, 1, 0), (0, 1, -0.1)))
    assert planar.normalized_plane_deviation == 0.0
    assert warped.normalized_plane_deviation > planar.normalized_plane_deviation


def test_weight_variation_penalizes_joint_like_loops():
    stable_weights = {
        0: {"Forearm": 0.5}, 1: {"Forearm": 0.5},
        2: {"Forearm": 0.5}, 3: {"Forearm": 0.5},
    }
    changing_weights = {
        0: {"UpperArm": 1.0}, 1: {"UpperArm": 0.7, "Forearm": 0.3},
        2: {"UpperArm": 0.3, "Forearm": 0.7}, 3: {"Forearm": 1.0},
    }
    stable = score_square(
        ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)), stable_weights)
    changing = score_square(
        ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)), changing_weights)
    assert stable.weight_variation == 0.0
    assert changing.weight_variation > stable.weight_variation
    assert changing.score > stable.score


def main():
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    if failures:
        print(f"{failures} test(s) failed")
        sys.exit(1)
    print("All tests passed")


if __name__ == "__main__":
    main()
