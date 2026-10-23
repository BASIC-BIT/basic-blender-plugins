"""Native BVH queries and conservative containment for owned geometry snapshots."""
from mathutils import Vector


RAY_DIRECTIONS = tuple(Vector(v).normalized() for v in (
    (1, .3713906763541037, .529173), (.23719, 1, .41937), (.61317, .21739, 1)))


def crossing(a, ia, b, ib, tolerance):
    """BVH overlap is necessary; strict plane straddling excludes contact."""
    ta = [Vector(a['points'][v]) for v in a['triangles'][ia]]
    tb = [Vector(b['points'][v]) for v in b['triangles'][ib]]
    for source, other in ((ta, tb), (tb, ta)):
        normal = (source[1] - source[0]).cross(source[2] - source[0])
        if normal.length < 1e-15:
            return False
        normal.normalize()
        distances = [(p - source[0]).dot(normal) for p in other]
        if min(distances) >= -tolerance or max(distances) <= tolerance:
            return False
    return True


def self_pairs(snapshot, contacts=False, contact_m=1e-8):
    """Exclude shared vertices, including a quad's own captured diagonal."""
    result = set()
    for i, j in snapshot['bvh'].overlap(snapshot['bvh']):
        if i >= j or set(snapshot['triangles'][i]) & set(snapshot['triangles'][j]):
            continue
        if contacts or crossing(snapshot, i, snapshot, j, contact_m):
            result.add((i, j))
    return result


def volume_support(snapshot):
    if '_volume_support' not in snapshot:
        snapshot['_volume_support'] = _volume_support(snapshot)
    return snapshot['_volume_support']


def _volume_support(snapshot):
    if not snapshot['closed']:
        return False
    if self_pairs(snapshot, contacts=True):
        return False
    volume = 0
    for triangle in snapshot['triangles']:
        a, b, c = (Vector(snapshot['points'][v]) for v in triangle)
        if (b - a).cross(c - a).length < 1e-15:
            return False
        volume += a.dot(b.cross(c)) / 6
    return abs(volume) > 1e-15


def probe_layout(triangles, polygons):
    """Immutable topology recipes, shared across poses without any positions."""
    vertices, edges, centroids = {}, {}, []
    for index, triangle in enumerate(triangles):
        face = polygons[index]
        for v in triangle:
            vertices.setdefault(v, set()).add(face)
        for va, vb in zip(triangle, triangle[1:] + triangle[:1]):
            edges.setdefault(tuple(sorted((va, vb))), set()).add(face)
        centroids.append((tuple(triangle), (face,)))
    groups = (tuple(((v,), tuple(sorted(faces))) for v, faces in sorted(vertices.items())),
              tuple((edge, tuple(sorted(faces))) for edge, faces in sorted(edges.items())),
              tuple(centroids))
    return {'groups': groups, 'available': sum(map(len, groups))}


def _descriptor(groups, index):
    """Invert the interleaved rank without materializing all probe coordinates."""
    lengths = tuple(map(len, groups))
    low, high = 0, max(lengths)
    while low + 1 < high:
        middle = (low + high) // 2
        if sum(min(middle, length) for length in lengths) <= index:
            low = middle
        else:
            high = middle
    remainder = index - sum(min(low, length) for length in lengths)
    return [group for group in groups if len(group) > low][remainder][low]


def samples(snapshot, limit):
    """Evaluate at most limit recipes once per immutable evaluated snapshot."""
    cache = snapshot.setdefault('_probe_cache', {})
    if limit in cache:
        return cache[limit]
    if '_probe_layout' not in snapshot:
        snapshot['_probe_layout'] = probe_layout(snapshot['triangles'], snapshot['polygons'])
    layout, points = snapshot['_probe_layout'], snapshot['points']
    available = layout['available']
    count = min(available, limit)
    selected = []
    for i in range(count):
        indices, faces = _descriptor(layout['groups'], i * available // count)
        point = sum((Vector(points[v]) for v in indices), Vector()) / len(indices)
        selected.append((point, faces))
    cache[limit] = selected, {'tested': count, 'available': available,
                             'density': count / available if available else 0}
    return cache[limit]


def _edge_distance(point, a, b):
    edge = b - a
    if edge.length_squared == 0:
        return (point - a).length
    t = max(0, min(1, (point - a).dot(edge) / edge.length_squared))
    return (point - (a + edge * t)).length


def inside(point, target, tolerance):
    """Three parity rays must agree; any grazing/near-edge event is unknown."""
    # Ray progress follows float32 precision, not the fitting contact band.
    magnitude = max(abs(value) for bound in target['bounds'] for value in bound)
    progress = max(1e-8, magnitude * 2 ** -21)
    epsilon = max(progress, tolerance)
    nearest = target['bvh'].find_nearest(point)
    if nearest[0] is None or nearest[3] <= epsilon:
        return None
    parity = []
    for direction in RAY_DIRECTIONS:
        origin, hits = point.copy(), 0
        for _ in range(len(target['triangles']) + 1):
            location, normal, index, _distance = target['bvh'].ray_cast(origin, direction)
            if location is None:
                break
            tri = [Vector(target['points'][v]) for v in target['triangles'][index]]
            near_edge = min(_edge_distance(location, a, b)
                            for a, b in zip(tri, tri[1:] + tri[:1])) <= epsilon
            if near_edge or abs(normal.dot(direction)) < 1e-6:
                return None
            hits += 1
            origin = location + direction * progress
            nearest = target['bvh'].find_nearest(origin)
            # A nearer different boundary may have been skipped by numerical progress.
            if nearest[2] != index and nearest[3] <= progress * 2:
                return None
        else:
            return None
        parity.append(hits % 2)
    return bool(parity[0]) if len(set(parity)) == 1 else None
