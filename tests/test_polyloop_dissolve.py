"""Tests for destructive edge-loop dissolve + iterate-to-target reduction.

Runs without Blender, matching the sibling ``test_polyloop_reduction.py``
pattern (importlib-by-path, synthetic tuple meshes, plain python)::

    python tests/test_polyloop_dissolve.py

``polyloop_dissolve`` does ``from . import polyloop_reduction``, so we register
a minimal fake ``core`` package before loading it, then load the dissolve
module as ``core.polyloop_dissolve``. No Blender, no NumPy trickery beyond what
the scorer already needs.
"""

import importlib.util
import os
import sys
import types


CORE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "BASICs_shape_key_manager", "core")


def _load(module_name, filename):
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(CORE_DIR, filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Load the scorer, then a stub ``core`` package so the dissolve module's
# ``from . import polyloop_reduction`` resolves to it.
reduction = _load("polyloop_reduction", "polyloop_reduction.py")
_core_pkg = types.ModuleType("core")
_core_pkg.__path__ = [CORE_DIR]
sys.modules["core"] = _core_pkg
sys.modules["core.polyloop_reduction"] = reduction
dissolve = _load("core.polyloop_dissolve", "polyloop_dissolve.py")


# --------------------------------------------------------------------------- #
# Synthetic mesh builders (hand-verifiable).
# --------------------------------------------------------------------------- #

def make_grid(cols, rows, warp=None):
    """A ``cols`` x ``rows`` grid of quads.

    Vertices sit at integer ``(col, row, 0)``; ``warp`` may override z as
    ``warp(col, row) -> float`` to make some loops non-planar.
    """
    def z(c, r):
        return 0.0 if warp is None else float(warp(c, r))

    vertices = []
    for r in range(rows + 1):
        for c in range(cols + 1):
            vertices.append((float(c), float(r), z(c, r)))

    def vindex(c, r):
        return r * (cols + 1) + c

    faces = []
    for r in range(rows):
        for c in range(cols):
            faces.append((vindex(c, r), vindex(c + 1, r),
                          vindex(c + 1, r + 1), vindex(c, r + 1)))
    edges = list(dissolve._edges_from_faces(faces))
    return vertices, edges, faces, vindex


def edge_indices_for(edges, keys):
    keyset = {dissolve._edge_key(a, b) for (a, b) in keys}
    return [i for i, e in enumerate(edges) if dissolve._edge_key(*e) in keyset]


def is_all_quads_manifold(faces, edges):
    if any(len(f) != 4 for f in faces):
        return False
    edge_faces = dissolve._build_edge_faces(edges, faces)
    return all(len(f) <= 2 for f in edge_faces.values())


# --------------------------------------------------------------------------- #
# Tests.
# --------------------------------------------------------------------------- #

def test_dissolve_middle_loop_of_2x2_grid_leaves_clean_quads():
    # 2x2 grid; dissolve the middle vertical loop (column c=1).
    vertices, edges, faces, V = make_grid(2, 2)
    loop = edge_indices_for(edges, [(V(1, 0), V(1, 1)), (V(1, 1), V(1, 2))])
    result = dissolve.dissolve_loop(vertices, edges, faces, loop)

    assert result.faces_before == 4
    assert result.faces_after == 2            # two columns merged into one
    assert result.merged_faces == 2
    assert result.removed_vertices == 3       # verts 1, 4, 7 dissolved
    assert len(result.vertices) == 6          # outer ring only
    # The surviving verts are exactly the x in {0, 2} columns.
    xs = sorted({round(v[0], 6) for v in result.vertices})
    assert xs == [0.0, 2.0]
    assert all(len(f) == 4 for f in result.faces)


def test_dissolve_removes_expected_edge_and_vertex_counts():
    vertices, edges, faces, V = make_grid(3, 1)  # a 3x1 strip, 3 quads
    # Dissolve the interior vertical loop at column c=1 (single edge here, but
    # min_edges filtering is a tracer concern, not a dissolve concern).
    loop = edge_indices_for(edges, [(V(1, 0), V(1, 1))])
    before_faces = len(faces)
    result = dissolve.dissolve_loop(vertices, edges, faces, loop)
    assert result.faces_after == before_faces - 1
    assert result.merged_faces == 1
    assert is_all_quads_manifold(result.faces, result.edges)


def test_dissolve_refuses_boundary_edge():
    # A lone quad: every edge is a boundary edge, so nothing can dissolve.
    vertices = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    faces = [(0, 1, 2, 3)]
    try:
        dissolve.dissolve_loop(vertices, edges, faces, [0])
    except dissolve.DissolveError:
        return
    raise AssertionError("expected DissolveError on a boundary loop edge")


def test_dissolve_refuses_non_manifold_edge():
    # Three quads fanning around one shared edge (0,1) -> non-manifold.
    vertices = [(0, 0, 0), (0, 1, 0),
                (1, 0, 0), (1, 1, 0),
                (-1, 0, 0), (-1, 1, 0),
                (0, 0, 1), (0, 1, 1)]
    faces = [(0, 1, 3, 2), (0, 1, 5, 4), (0, 1, 7, 6)]
    edges = list(dissolve._edges_from_faces(faces))
    loop = edge_indices_for(edges, [(0, 1)])
    try:
        dissolve.dissolve_loop(vertices, edges, faces, loop)
    except dissolve.DissolveError:
        return
    raise AssertionError("expected DissolveError on a non-manifold loop edge")


def test_dissolve_remaps_vertex_weights():
    vertices, edges, faces, V = make_grid(2, 2)
    # Give every vertex a distinct weight so we can prove the remap is faithful.
    weights = {i: {"G": float(i)} for i in range(len(vertices))}
    loop = edge_indices_for(edges, [(V(1, 0), V(1, 1)), (V(1, 1), V(1, 2))])
    result = dissolve.dissolve_loop(
        vertices, edges, faces, loop, vertex_weights=weights)

    # Weights only for surviving verts, and every survivor keeps its value.
    assert set(result.vertex_weights) == set(range(len(result.vertices)))
    # Original vertex 0 (weight 0.0) survives and remaps to new index 0.
    assert result.vertex_weights[0]["G"] == 0.0
    # The dissolved verts (1, 4, 7) contributed no stray weight keys.
    assert len(result.vertex_weights) == len(result.vertices)


def test_reduce_to_target_reaches_face_count():
    vertices, edges, faces, _ = make_grid(5, 3)  # 15 quads
    out = dissolve.reduce_to_target(
        vertices, edges, faces, target_faces=6, min_edges=3)
    assert out["faces_after"] <= 6
    assert out["stopped_reason"] == "target_reached"
    assert out["iterations"] >= 1
    assert is_all_quads_manifold(out["faces"], out["edges"])
    # No orphaned indices.
    assert max(max(f) for f in out["faces"]) < len(out["vertices"])


def test_reduce_stops_at_quality_floor_before_target():
    # A grid warped so that loops are non-planar: a tiny target with a strict
    # max_score should stop early on the quality floor, not chew to the target.
    def warp(c, r):
        return 0.4 if (c % 2 == 1) else 0.0  # zig-zag ridges => warped loops

    vertices, edges, faces, _ = make_grid(6, 4, warp=warp)
    out = dissolve.reduce_to_target(
        vertices, edges, faces, target_faces=2, max_score=1e-6, min_edges=3)
    # Impossible-to-reach target under a strict floor -> stops on the floor
    # (or on no dissolvable candidate), never claims target_reached.
    assert out["faces_after"] > 2
    assert out["stopped_reason"] in ("quality_floor", "no_candidates",
                                     "no_dissolvable_candidate")


def test_reduce_prefers_planar_loops_over_warped_ones():
    # One warped ridge column; the flat loops should be dissolved first, so a
    # single-dissolve run leaves the warped ridge intact.
    def warp(c, r):
        return 0.5 if c == 3 else 0.0

    vertices, edges, faces, V = make_grid(6, 2, warp=warp)
    # Vertices on the warped ridge column c=3.
    ridge_verts = {V(3, r) for r in range(3)}

    out = dissolve.reduce_to_target(
        vertices, edges, faces, target_faces=len(faces) - 1, min_edges=3)
    assert out["iterations"] == 1
    # The ridge should still be present: at least one surviving vertex must be
    # lifted in z (the warp), proving a flat loop was chosen over the ridge.
    assert any(abs(v[2]) > 0.4 for v in out["vertices"])
    # And the ridge column vertices should not all have been dissolved.
    survivor_z = [v[2] for v in out["vertices"]]
    assert max(survivor_z) >= 0.5


def test_reduce_is_deterministic():
    a = dissolve.reduce_to_target(
        *make_grid(6, 4)[:3], target_faces=8, min_edges=3)
    b = dissolve.reduce_to_target(
        *make_grid(6, 4)[:3], target_faces=8, min_edges=3)
    assert a["faces"] == b["faces"]
    assert a["iterations"] == b["iterations"]
    assert a["stopped_reason"] == b["stopped_reason"]


def test_reduce_no_op_when_target_already_met():
    vertices, edges, faces, _ = make_grid(3, 2)  # 6 faces
    out = dissolve.reduce_to_target(
        vertices, edges, faces, target_faces=6, min_edges=3)
    assert out["iterations"] == 0
    assert out["faces_after"] == 6
    assert out["stopped_reason"] == "target_reached"


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
