"""Evaluated, world-meter snapshots and object-pair clothing diagnostics.

Snapshots own plain coordinates/topology and a BVH. No evaluated mesh survives
to_mesh_clear. Captured triangulation is reused after exact topology checks.
"""
import math
import numpy as np

from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .geometry_queries import crossing, inside, probe_layout, samples, self_pairs, volume_support


def _positive(value, name, zero=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (value == 0 and not zero)):
        raise ValueError(f'{name} must be finite and {"nonnegative" if zero else "positive"}')


def _closed(faces):
    edges = {}
    for face in faces:
        for a, b in zip(face, face[1:] + face[:1]):
            edges.setdefault(tuple(sorted((a, b))), []).append((a, b))
    return bool(edges) and all(len(v) == 2 and v[0] == v[1][::-1] for v in edges.values())


def snapshot_mesh(obj, depsgraph, stable=None, unit_scale=1.0, *, scalar=False):
    """Capture triangles once; stable must be the earlier snapshot of this topology.

    Sessions set _basic_clothing_id on owned copies. Uncaptured objects receive a
    session UID without writing to source objects. Serialize that ID at capture.
    """
    _positive(unit_scale, 'unit_scale')
    if obj.type != 'MESH':
        raise ValueError('snapshot requires a mesh')
    if any(m.type != 'ARMATURE' for m in obj.modifiers if m.show_viewport):
        raise ValueError('unsupported modifier, only Armature is supported')
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        loops = np.empty(len(mesh.loops), dtype=np.int32)
        starts = np.empty(len(mesh.polygons), dtype=np.int32)
        sizes = np.empty(len(mesh.polygons), dtype=np.int32)
        mesh.loops.foreach_get('vertex_index', loops)
        mesh.polygons.foreach_get('loop_start', starts)
        mesh.polygons.foreach_get('loop_total', sizes)
        faces = [tuple(map(int, loops[start:start + size])) for start, size in zip(starts, sizes)]
        if scalar:
            faces = [tuple(p.vertices) for p in mesh.polygons]
        topology = {'vertex_count': len(mesh.vertices), 'faces': [list(f) for f in faces]}
        if stable is not None and stable['topology'] != topology:
            raise ValueError('evaluated topology changed, including source face ordering')
        if stable is None:
            mesh.calc_loop_triangles()
            indices = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
            owners = np.empty(len(mesh.loop_triangles), dtype=np.int32)
            mesh.loop_triangles.foreach_get('vertices', indices)
            mesh.loop_triangles.foreach_get('polygon_index', owners)
            triangles = [tuple(map(int, row)) for row in indices.reshape(-1, 3)]
            polygons = owners.tolist()
            if scalar:
                triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
                polygons = [t.polygon_index for t in mesh.loop_triangles]
        else:
            triangles = [tuple(t) for t in stable['triangles']]
            polygons = list(stable['polygons'])
        if not triangles:
            raise ValueError('snapshot requires triangle geometry')
        if scalar:
            points = [tuple((evaluated.matrix_world @ v.co) * unit_scale) for v in mesh.vertices]
        else:
            coordinates = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
            mesh.vertices.foreach_get('co', coordinates)
            matrix = np.asarray(evaluated.matrix_world, dtype=np.float64)
            points = (coordinates.reshape(-1, 3).astype(np.float64) @ matrix[:3, :3].T
                      + matrix[:3, 3]) * unit_scale
            points = [tuple(point) for point in points.tolist()]
    finally:
        evaluated.to_mesh_clear()
    if any(not math.isfinite(value) for point in points for value in point):
        raise ValueError('geometry contains nonfinite coordinates')
    object_id = str(obj.get('_basic_clothing_id', f'session:{obj.session_uid}'))
    if stable is not None:
        object_id = stable['id']
    layout = stable.get('_probe_layout') if stable is not None else None
    return {'id': object_id, 'points': points, 'triangles': triangles,
            'polygons': polygons, 'topology': topology, 'closed': _closed(faces),
            'bounds': [[min(p[i] for p in points) for i in range(3)],
                       [max(p[i] for p in points) for i in range(3)]],
            'bvh': BVHTree.FromPolygons(points, triangles, all_triangles=True),
            '_probe_layout': layout if layout is not None else probe_layout(triangles, polygons)}


def body_self_crossings(snapshot):
    """Return nonadjacent intersecting source polygon pairs for plausibility checks."""
    return {tuple(sorted((snapshot['polygons'][i], snapshot['polygons'][j])))
            for i, j in self_pairs(snapshot)}


def body_self_contacts(snapshot):
    return {tuple(sorted((snapshot['polygons'][i], snapshot['polygons'][j])))
            for i, j in self_pairs(snapshot, contacts=True)}


def analyze_self(snapshot, contact_m=0.0001):
    """Nonadjacent garment intersections with one real owner and explicit SELF kind."""
    _positive(contact_m, 'contact_m', zero=True)
    pairs = sorted(pair for pair in self_pairs(snapshot, contacts=True)
                   if crossing(snapshot, pair[0], snapshot, pair[1], contact_m))
    polygons = sorted({tuple(sorted((snapshot['polygons'][i], snapshot['polygons'][j])))
                       for i, j in pairs})
    identity = snapshot['id']
    faces = sorted({face for pair in polygons for face in pair})
    return {'pair': [identity, identity], 'kind': 'SELF', 'primary_id': identity,
            'scope': 'NONADJACENT_TRIANGLE_CROSSINGS',
            'crossing_faces': {identity: faces}, 'contained_faces': {identity: []},
            'depths_m': {}, 'triangle_pairs': [list(pair) for pair in pairs],
            'polygon_pairs': [list(pair) for pair in polygons],
            'contact_triangle_pairs': [], 'contact_polygon_pairs': [],
            'contained_polygon_pairs': [], 'containment': {identity: 'NOT_APPLICABLE'},
            'clearance_m': None, 'sampling_complete': True,
            'absolute_fit': 'CLIPPING' if pairs else 'CLEAR',
            'ambiguous': [], 'omissions': ['Self containment is not evaluated']}


def analyze_pair(a, b, contact_m=0.0001, clearance_m=0.001, sample_limit=512,
                 *, primary_id=None):
    """Report confirmed crossings and sampled clearance/containment.

    containment[id] describes samples of that object inside the other object.
    UNKNOWN means the other surface cannot support volume classification.
    AMBIGUOUS means a valid volume had at least one uncertain parity/contact.
    primary_id limits fit/regression ownership to that garment for body checks.
    None compares both garment owners. Raw measurements retain both directions.
    """
    _positive(contact_m, 'contact_m', zero=True)
    _positive(clearance_m, 'clearance_m', zero=True)
    if isinstance(sample_limit, bool) or not isinstance(sample_limit, int) or sample_limit < 1:
        raise ValueError('sample_limit must be a positive integer')
    if not a['id'] or not b['id'] or a['id'] == b['id']:
        raise ValueError('pair requires distinct stable object IDs')
    if primary_id is not None and primary_id not in (a['id'], b['id']):
        raise ValueError('primary_id must belong to pair')
    if a['id'] > b['id']:
        a, b = b, a
    ids = [a['id'], b['id']]
    crossed, contained, depths = ({i: set() for i in ids}, {i: set() for i in ids},
                                  {i: {} for i in ids})
    triangle_pairs, contacts, ambiguity, contained_pairs = [], [], [], set()
    separated = any(a['bounds'][1][i] < b['bounds'][0][i]
                    or b['bounds'][1][i] < a['bounds'][0][i] for i in range(3))
    overlaps = [] if separated else a['bvh'].overlap(b['bvh'])
    for ia, ib in sorted(set(overlaps)):
        if crossing(a, ia, b, ib, contact_m):
            triangle_pairs.append([ia, ib])
            crossed[a['id']].add(a['polygons'][ia])
            crossed[b['id']].add(b['polygons'][ib])
        else:
            contacts.append([ia, ib])
    if contacts:
        ambiguity.append('surface contact or crossing within contact tolerance')
    support = {s['id']: volume_support(s) for s in (a, b)}
    containment, sample_counts = {}, {}
    clearance = 0.0 if overlaps else None
    for source, target in ((a, b), (b, a)):
        sid = source['id']
        probes, sample_counts[sid] = samples(source, sample_limit)
        state = 'SUPPORTED' if support[target['id']] else 'UNKNOWN'
        if state == 'UNKNOWN':
            ambiguity.append(f'{sid}: opposing surface is open, inconsistently oriented or self-intersecting')
        for point, faces in probes:
            nearest = target['bvh'].find_nearest(point)
            if nearest[0] is None:
                state = 'AMBIGUOUS' if state != 'UNKNOWN' else state
                continue
            distance = nearest[3]
            clearance = distance if clearance is None else min(clearance, distance)
            if not support[target['id']]:
                continue
            interior = False if separated else inside(point, target, contact_m)
            if interior is None:
                state = 'AMBIGUOUS'
            elif interior:
                contained[sid].update(faces)
                for face in faces:
                    partner = target['polygons'][nearest[2]]
                    pair = (face, partner) if sid == ids[0] else (partner, face)
                    contained_pairs.add((sid, *pair))
                for face in faces:
                    key = str(face)
                    depths[sid][key] = max(depths[sid].get(key, 0), distance)
        containment[sid] = state
        if state == 'AMBIGUOUS':
            ambiguity.append(f'{sid}: grazing, contact, near-edge or disagreeing parity rays')
    owners = [primary_id] if primary_id else ids
    clipping = any(crossed[i] or contained[i] for i in owners)
    sampling_complete = all(sample_counts[i]['tested'] == sample_counts[i]['available'] for i in owners)
    if not sampling_complete:
        ambiguity.append('probe budget omitted possible containment regions')
    absolute = ('CLIPPING' if clipping else 'CLEAR' if all(
        containment[i] == 'SUPPORTED' for i in owners) and not contacts and sampling_complete
        else 'INDETERMINATE')
    return {'pair': ids, 'primary_id': primary_id,
            'kind': 'PAIR',
            'polygon_pairs': [list(pair) for pair in sorted({(a['polygons'][i], b['polygons'][j])
                                                           for i, j in triangle_pairs})],
            'contact_polygon_pairs': [list(pair) for pair in sorted({(a['polygons'][i], b['polygons'][j])
                                                                   for i, j in contacts})],
            'contained_polygon_pairs': [{'source_id': sid, 'faces': [fa, fb]}
                                        for sid, fa, fb in sorted(contained_pairs)],
            'crossing_faces': {i: sorted(v) for i, v in crossed.items()},
            'contained_faces': {i: sorted(v) for i, v in contained.items()},
            'depths_m': depths, 'triangle_pairs': triangle_pairs, 'contact_triangle_pairs': contacts,
            'clearance_m': clearance,
            'clearance_warning': clearance is not None and clearance < clearance_m,
            'containment': containment, 'ambiguous': ambiguity, 'samples': sample_counts,
            'sampling_complete': sampling_complete,
            'absolute_fit': absolute, 'contact_m': contact_m, 'clearance_threshold_m': clearance_m}
