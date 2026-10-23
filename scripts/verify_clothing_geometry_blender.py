"""Factory Blender fixtures for evaluated clothing geometry. No user scene access."""
import importlib
from itertools import combinations
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
if '--installed-extension' not in sys.argv:
    sys.path.insert(0, str(ROOT))
PACKAGE = ('bl_ext.user_default.basics_shape_key_manager' if '--installed-extension' in sys.argv
           else 'BASICs_shape_key_manager')
geometry = importlib.import_module(PACKAGE + '.operators.clothing_checks.geometry')
queries = importlib.import_module(PACKAGE + '.operators.clothing_checks.geometry_queries')


def mesh(name, vertices, faces):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj['_basic_clothing_id'] = name
    return obj


def snapshot(obj, stable=None):
    bpy.context.view_layer.update()
    return geometry.snapshot_mesh(obj, bpy.context.evaluated_depsgraph_get(), stable)


def cube(name, scale=1, offset=0, reverse=False):
    points = [(x * scale + offset, y * scale, z * scale)
              for x, y, z in [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                              (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    if reverse:
        faces = [tuple(reversed(face)) for face in faces]
    return mesh(name, points, faces)


def test_outside_vertices_crossing_and_contact():
    a = snapshot(mesh('crossA', [(-2, -1, 0), (2, -1, 0), (0, 2, 0)], [(0, 1, 2)]))
    b = snapshot(mesh('crossB', [(0, -2, -1), (0, -2, 1), (0, 2, 0)], [(0, 1, 2)]))
    result = geometry.analyze_pair(a, b)
    assert result['crossing_faces'] == {'crossA': [0], 'crossB': [0]}, result
    assert result['containment']['crossA'] == 'UNKNOWN', result
    flat = snapshot(mesh('contact', [(-2, -1, 0), (2, -1, 0), (0, 2, 0)], [(0, 1, 2)]))
    result = geometry.analyze_pair(a, flat)
    assert not any(result['crossing_faces'].values()), result
    assert result['absolute_fit'] == 'INDETERMINATE', result


def test_body_and_garment_self_crossings_share_contact_band():
    for depth in (1e-5, 1e-3):
        obj = mesh('contact-band-' + str(depth),
                   [(-1, -1, 0), (1, -1, 0), (0, 1, 0),
                    (0, -.5, -depth), (0, -.5, depth), (0, .5, 0)],
                   [(0, 1, 2), (3, 4, 5)])
        native = snapshot(obj)
        expected_default = {(0, 1)} if depth > .0001 else set()
        assert geometry.body_self_crossings(native) == expected_default, 'body/garment default contact bands differ'
        for tolerance in (0., 1e-6, 1e-4):
            expected = {(0, 1)} if depth > tolerance else set()
            actual = geometry.body_self_crossings(native, contact_m=tolerance)
            assert actual == expected, (depth, tolerance, actual)
            garment = geometry.analyze_self(native, contact_m=tolerance)
            assert {tuple(pair) for pair in garment['polygon_pairs']} == expected
    for tolerance in (-1., float('nan'), True):
        try:
            geometry.body_self_crossings(native, contact_m=tolerance)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid body contact band accepted')


def test_buried_reversed_open_and_density():
    outer, inner = snapshot(cube('outer')), snapshot(cube('inner', .2))
    result = geometry.analyze_pair(outer, inner)
    assert not any(result['crossing_faces'].values()), result
    assert result['contained_faces']['inner'] == list(range(6)), result
    assert result['absolute_fit'] == 'CLIPPING', result
    assert min(result['depths_m']['inner'].values()) > .7, result
    reversed_result = geometry.analyze_pair(snapshot(cube('reversed', reverse=True)), inner)
    assert reversed_result['contained_faces']['inner'] == list(range(6)), reversed_result
    open_obj = cube('open')
    vertices = [tuple(v.co) for v in open_obj.data.vertices]
    open_faces = [tuple(p.vertices) for p in open_obj.data.polygons][:-1]
    open_body = snapshot(mesh('open-body', vertices, open_faces))
    result = geometry.analyze_pair(open_body, inner, sample_limit=3)
    assert result['containment']['inner'] == 'UNKNOWN', result
    assert result['absolute_fit'] == 'INDETERMINATE', result
    assert result['samples']['inner']['tested'] == 3, result
    assert result['samples']['inner']['density'] < 1, result


def test_fixed_quad_triangles_and_reordered_topology():
    obj = mesh('quad', [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [(0, 1, 2, 3)])
    before = snapshot(obj)
    obj.data.vertices[1].co.z = 2
    after = snapshot(obj, before)
    assert before['triangles'] == after['triangles']
    assert before['points'] != after['points']
    assert before['bvh'].find_nearest((0, 0, 0))[0] is not None
    obj.data.clear_geometry()
    obj.data.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 3, 2, 1)])
    try:
        snapshot(obj, before)
    except ValueError as exc:
        assert 'topology' in str(exc)
    else:
        raise AssertionError('changed source face ordering was accepted')


def test_self_intersection_and_bad_orientation():
    a = cube('selfA')
    b = cube('selfB', offset=.7)
    for vertex in b.data.vertices:
        vertex.co.y += .4
        vertex.co.z += .3
    points = [tuple(v.co) for v in a.data.vertices] + [tuple(v.co) for v in b.data.vertices]
    faces = [tuple(p.vertices) for p in a.data.polygons]
    faces += [tuple(v + 8 for v in p.vertices) for p in b.data.polygons]
    crossed = snapshot(mesh('self-crossed', points, faces))
    assert geometry.body_self_crossings(crossed)
    result = geometry.analyze_pair(crossed, snapshot(cube('buried', .1)))
    assert result['containment']['buried'] == 'UNKNOWN', result
    body = cube('bad-orientation')
    bad_faces = [tuple(p.vertices) for p in body.data.polygons]
    bad_faces[0] = tuple(reversed(bad_faces[0]))
    bad = snapshot(mesh('mixed', [tuple(v.co) for v in body.data.vertices], bad_faces))
    assert not bad['closed']


def test_near_edge_ray_ambiguity():
    # First deterministic ray exits exactly through the cube's top/right edge.
    point = (0, 1 - .3713906763541037, 0)
    tiny = snapshot(mesh('edge-probe', [point, (point[0] + 1e-7, point[1], 0),
                                      (point[0], point[1] + 1e-7, 0)], [(0, 1, 2)]))
    result = geometry.analyze_pair(snapshot(cube('edge-box')), tiny)
    assert result['containment']['edge-probe'] == 'AMBIGUOUS', result


def test_primary_fit_and_bounded_sampling():
    body, outer = snapshot(cube('small-body', .2)), snapshot(cube('outer-shirt'))
    result = geometry.analyze_pair(body, outer, primary_id=outer['id'])
    assert result['absolute_fit'] == 'CLEAR', result
    result = geometry.analyze_pair(body, outer, primary_id=outer['id'], sample_limit=1)
    assert result['absolute_fit'] == 'INDETERMINATE', result
    assert not result['sampling_complete'], result
    outside = snapshot(mesh('open-shirt', [(2, 0, 0), (2, .1, 0), (2, 0, .1)], [(0, 1, 2)]))
    result = geometry.analyze_pair(snapshot(cube('closed-body')), outside,
                                   primary_id=outside['id'])
    assert result['absolute_fit'] == 'CLEAR', result
    assert result['containment']['open-shirt'] == 'SUPPORTED', result


def test_thin_shell_cavity_never_becomes_interior():
    for thickness in (.00002, .0000002, .01):
        outer, inner = cube('shell-outer'), cube('shell-inner', 1 - thickness, reverse=True)
        points = [tuple(v.co) for v in outer.data.vertices] + [tuple(v.co) for v in inner.data.vertices]
        faces = [tuple(p.vertices) for p in outer.data.polygons]
        faces += [tuple(v + 8 for v in p.vertices) for p in inner.data.polygons]
        shell = snapshot(mesh('hollow-shell', points, faces))
        probe = snapshot(mesh('cavity-probe', [(-.05, -.05, 0), (.05, -.05, 0), (0, .05, 0)],
                              [(0, 1, 2)]))
        result = geometry.analyze_pair(shell, probe, primary_id='cavity-probe')
        assert not result['contained_faces']['cavity-probe'], result
        assert not result['depths_m']['cavity-probe'], result
        assert result['absolute_fit'] != 'CLIPPING', result
        if thickness == .01:
            assert result['containment']['cavity-probe'] == 'SUPPORTED', result
            assert result['absolute_fit'] == 'CLEAR', result


def grid_snapshot(name, n=92):
    points = [(i * .001, j * .001, 0) for j in range(n) for i in range(n)]
    faces = []
    for j in range(n - 1):
        for i in range(n - 1):
            k = j * n + i
            faces.extend([(k, k + 1, k + n), (k + 1, k + n + 1, k + n)])
    return snapshot(mesh(name, points, faces))


def test_bounded_cached_probes_and_volume_validation():
    large = grid_snapshot('bounded-grid')
    with patch.object(queries, 'Vector', wraps=queries.Vector) as vectors:
        probes, count = queries.samples(large, 512)
        assert len(probes) == 512 and count['available'] > 40000, count
        assert vectors.call_count <= 2048, vectors.call_count
        initial_count = vectors.call_count
        for _ in range(9):
            repeated, repeated_count = queries.samples(large, 512)
            assert repeated is probes and repeated_count == count
        assert vectors.call_count == initial_count
    body = snapshot(cube('cached-volume'))
    with patch.object(queries, 'self_pairs', wraps=queries.self_pairs) as checked:
        for _ in range(9):
            assert queries.volume_support(body)
        assert checked.call_count == 1, checked.call_count


def test_topology_reused_without_stale_pose_points():
    obj = cube('moving-probes')
    before = snapshot(obj)
    old_probes, _ = queries.samples(before, 32)
    assert queries.volume_support(before)
    obj.location.x = 3
    after = snapshot(obj, before)
    new_probes, _ = queries.samples(after, 32)
    assert after['_probe_layout'] is before['_probe_layout']
    assert old_probes is not new_probes
    assert abs(new_probes[0][0].x - old_probes[0][0].x - 3) < 1e-6
    with patch.object(queries, 'self_pairs', wraps=queries.self_pairs) as checked:
        assert queries.volume_support(after)
        assert checked.call_count == 1


def benchmark_nine_piece_probes():
    pieces = [grid_snapshot('benchmark-grid-' + str(i)) for i in range(9)]
    started = time.perf_counter()
    for piece in pieces:
        for _ in range(9):
            queries.samples(piece, 512)
    elapsed = time.perf_counter() - started
    assert elapsed < 1, elapsed
    print('NINE_PIECE_PROBES_SECONDS', elapsed)


def benchmark_outfit(manifest_path):
    """Read a saved checkpoint in this background process; never save changes."""
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    bpy.ops.wm.open_mainfile(filepath=manifest['file'])
    scene = bpy.data.scenes[manifest['scene']]
    body = scene.objects[manifest['body']]
    pairs = [(scene.objects[p['reference']], scene.objects[p['candidate']])
             for p in manifest['pairs']]
    objects = [body, *[obj for pair in pairs for obj in pair]]
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        scene.view_layers[0].update()
        graph = bpy.context.evaluated_depsgraph_get()
        start = time.perf_counter()
        templates = {obj: geometry.snapshot_mesh(obj, graph, unit_scale=scene.unit_settings.scale_length)
                     for obj in objects}
        capture_seconds = time.perf_counter() - start
        start = time.perf_counter()
        snapshots = {obj: geometry.snapshot_mesh(obj, graph, templates[obj],
                                                scene.unit_settings.scale_length)
                     for obj in objects}
        pose_snapshot_seconds = time.perf_counter() - start
    start = time.perf_counter()
    for value in snapshots.values():
        for _ in range(9):
            queries.samples(value, 512)
    probe_seconds = time.perf_counter() - start
    jobs = []
    for side in (0, 1):
        garments = [snapshots[p[side]] for p in pairs]
        jobs.extend((snapshots[body], garment, garment['id']) for garment in garments)
        jobs.extend((a, b, None) for a, b in combinations(garments, 2))
    start = time.perf_counter()
    statuses = {}
    for a, b, primary in jobs:
        result = geometry.analyze_pair(a, b, primary_id=primary)
        statuses[result['absolute_fit']] = statuses.get(result['absolute_fit'], 0) + 1
    pair_seconds = time.perf_counter() - start
    result = {'objects': len(objects), 'garments_per_side': len(pairs), 'pair_checks': len(jobs),
              'vertices_per_side': sum(len(snapshots[p[0]]['points']) for p in pairs),
              'cold_snapshot_seconds': capture_seconds,
              'pose_snapshot_seconds': pose_snapshot_seconds,
              'probe_construction_and_9x_reuse_seconds': probe_seconds,
              'pair_queries_seconds': pair_seconds,
              'paired_geometry_case_seconds': pose_snapshot_seconds + probe_seconds + pair_seconds,
              'statuses': statuses,
              'scope': 'Saved current pose, geometry only; no IK, source hashing or live scene writes'}
    print('ACTUAL_OUTFIT_GEOMETRY_BENCHMARK', json.dumps(result, sort_keys=True))


for test in (test_outside_vertices_crossing_and_contact, test_body_and_garment_self_crossings_share_contact_band,
             test_buried_reversed_open_and_density,
             test_fixed_quad_triangles_and_reordered_topology,
             test_self_intersection_and_bad_orientation, test_near_edge_ray_ambiguity,
             test_primary_fit_and_bounded_sampling, test_thin_shell_cavity_never_becomes_interior,
             test_bounded_cached_probes_and_volume_validation,
             test_topology_reused_without_stale_pose_points, benchmark_nine_piece_probes):
    test()
    print('PASS', test.__name__)
print('CLOTHING_GEOMETRY_OK')
if '--benchmark-manifest' in sys.argv:
    benchmark_outfit(sys.argv[sys.argv.index('--benchmark-manifest') + 1])
