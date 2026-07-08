"""Tests for the bpy-free shape-key remap math (stage-4 shape-key-aware
reduction).

Runs without Blender, matching the sibling polyloop test pattern
(importlib-by-path, hand-verifiable synthetic data)::

    python tests/test_shape_key_remap.py
"""

import importlib.util
import os
import sys


MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "BASICs_shape_key_manager", "core", "shape_key_remap.py")

spec = importlib.util.spec_from_file_location("shape_key_remap", MODULE_PATH)
skr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skr)


def make_keys(n):
    """Basis plus two relative keys over ``n`` vertices with distinct,
    hand-checkable coordinates.

    * Basis: vertex i at (i, 0, 0).
    * "Smile": basis + (0, 1, 0) everywhere (relative to Basis).
    * "BigSmile": Smile + (0, 0, i) per vertex (relative to Smile) -- a
      relative-key CHAIN whose per-vertex delta varies.
    """
    basis = [(float(i), 0.0, 0.0) for i in range(n)]
    smile = [(float(i), 1.0, 0.0) for i in range(n)]
    big = [(float(i), 1.0, float(i)) for i in range(n)]
    return [
        {"name": "Basis", "coordinates": basis, "value": 0.0,
         "relative_key": None},
        {"name": "Smile", "coordinates": smile, "value": 0.3,
         "relative_key": "Basis"},
        {"name": "BigSmile", "coordinates": big, "value": 1.0,
         "relative_key": "Smile"},
    ]


def deltas(keys, name, relative_name):
    by_name = {k["name"]: k for k in keys}
    key = by_name[name]["coordinates"]
    rel = by_name[relative_name]["coordinates"]
    return [tuple(a - b for a, b in zip(k, r)) for k, r in zip(key, rel)]


# --------------------------------------------------------------------------- #
# Identity / survivor mapping.
# --------------------------------------------------------------------------- #

def test_identity_mapping_copies_coordinates_and_metadata():
    keys = make_keys(4)
    sources = [[0], [1], [2], [3]]
    out = skr.remap_shape_keys(keys, sources, source_vertex_count=4)
    assert [k["name"] for k in out] == ["Basis", "Smile", "BigSmile"]
    for before, after in zip(keys, out):
        assert after["coordinates"] == [tuple(c) for c in before["coordinates"]]
        assert after["value"] == before["value"]
        assert after["relative_key"] == before["relative_key"]
    # Input untouched (new dicts, new coordinate lists).
    assert out[0] is not keys[0]
    assert out[0]["coordinates"] is not keys[0]["coordinates"]


def test_removal_drops_deleted_vertices_and_keeps_survivor_order():
    keys = make_keys(5)
    # Vertices 1 and 3 removed; survivors keep ascending order (0, 2, 4),
    # exactly how the dissolve builds its remap.
    sources = [[0], [2], [4]]
    out = skr.remap_shape_keys(keys, sources, source_vertex_count=5)
    assert out[0]["coordinates"] == [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0),
                                     (4.0, 0.0, 0.0)]
    assert out[2]["coordinates"] == [(0.0, 1.0, 0.0), (2.0, 1.0, 2.0),
                                     (4.0, 1.0, 4.0)]
    assert all(len(k["coordinates"]) == 3 for k in out)


def test_relative_key_chain_deltas_survive_removal():
    keys = make_keys(6)
    sources = [[0], [3], [5]]
    out = skr.remap_shape_keys(keys, sources, source_vertex_count=6)
    # Smile-over-Basis delta is (0, 1, 0) at every surviving vertex.
    assert deltas(out, "Smile", "Basis") == [(0.0, 1.0, 0.0)] * 3
    # BigSmile-over-Smile delta carries each SOURCE vertex's (0, 0, i).
    assert deltas(out, "BigSmile", "Smile") == [
        (0.0, 0.0, 0.0), (0.0, 0.0, 3.0), (0.0, 0.0, 5.0)]


# --------------------------------------------------------------------------- #
# Merge (multi-source) mapping.
# --------------------------------------------------------------------------- #

def test_merge_averages_absolute_coordinates():
    keys = make_keys(4)
    # New vertex 0 merges old 0+2; new vertex 1 is old 3 untouched.
    sources = [[0, 2], [3]]
    out = skr.remap_shape_keys(keys, sources, source_vertex_count=4)
    assert out[0]["coordinates"][0] == (1.0, 0.0, 0.0)     # mean of x=0, x=2
    assert out[1]["coordinates"][0] == (1.0, 1.0, 0.0)     # Smile mean
    assert out[2]["coordinates"][0] == (1.0, 1.0, 1.0)     # BigSmile mean of z=0,2


def test_merge_preserves_relative_deltas_by_linearity():
    keys = make_keys(8)
    sources = [[0, 1, 2], [3], [4, 7]]
    out = skr.remap_shape_keys(keys, sources, source_vertex_count=8)
    # mean(key) - mean(rel) == mean(key - rel): the uniform (0,1,0) Smile
    # delta survives any merge...
    assert deltas(out, "Smile", "Basis") == [(0.0, 1.0, 0.0)] * 3
    # ...and the varying BigSmile delta becomes the mean of its sources.
    assert deltas(out, "BigSmile", "Smile") == [
        (0.0, 0.0, 1.0),    # mean of z deltas 0, 1, 2
        (0.0, 0.0, 3.0),
        (0.0, 0.0, 5.5),    # mean of z deltas 4, 7
    ]


# --------------------------------------------------------------------------- #
# sources_from_vertex_remap (the dissolve's survivor map).
# --------------------------------------------------------------------------- #

def test_sources_from_vertex_remap_builds_singletons():
    remap = {0: 0, 2: 1, 4: 2}
    assert skr.sources_from_vertex_remap(remap, 3) == [[0], [2], [4]]


def test_sources_from_vertex_remap_rejects_gaps_and_collisions():
    try:
        skr.sources_from_vertex_remap({0: 0, 2: 2}, 3)   # new index 1 uncovered
    except skr.ShapeKeyRemapError:
        pass
    else:
        raise AssertionError("expected ShapeKeyRemapError on uncovered index")
    try:
        skr.sources_from_vertex_remap({0: 0, 1: 0}, 1)   # two olds -> one new
    except skr.ShapeKeyRemapError:
        pass
    else:
        raise AssertionError("expected ShapeKeyRemapError on collision")
    try:
        skr.sources_from_vertex_remap({0: 5}, 3)         # out of range
    except skr.ShapeKeyRemapError:
        pass
    else:
        raise AssertionError("expected ShapeKeyRemapError on out-of-range")


# --------------------------------------------------------------------------- #
# Validation.
# --------------------------------------------------------------------------- #

def test_rejects_empty_source_list():
    try:
        skr.remap_shape_keys(make_keys(3), [[0], []], source_vertex_count=3)
    except skr.ShapeKeyRemapError:
        return
    raise AssertionError("expected ShapeKeyRemapError on empty sources")


def test_rejects_mismatched_coordinate_count():
    keys = make_keys(3)
    keys[1]["coordinates"] = keys[1]["coordinates"][:2]   # corrupt one key
    try:
        skr.remap_shape_keys(keys, [[0], [1]], source_vertex_count=3)
    except skr.ShapeKeyRemapError:
        return
    raise AssertionError("expected ShapeKeyRemapError on length mismatch")


def test_rejects_out_of_range_and_negative_source_indices():
    keys = make_keys(3)
    try:
        skr.remap_shape_keys(keys, [[0], [7]], source_vertex_count=None)
    except skr.ShapeKeyRemapError:
        pass
    else:
        raise AssertionError("expected ShapeKeyRemapError on out-of-range")
    try:
        skr.remap_shape_keys(keys, [[0], [-1]])
    except skr.ShapeKeyRemapError:
        pass
    else:
        raise AssertionError("expected ShapeKeyRemapError on negative index")


def test_empty_key_list_is_a_no_op():
    assert skr.remap_shape_keys([], [[0], [1]]) == []


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
