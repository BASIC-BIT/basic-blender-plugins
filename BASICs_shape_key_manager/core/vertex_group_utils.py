"""
Vertex group protection utilities shared by the transfer operators.

These helpers implement the snapshot/restore pattern that keeps
PhysBone/dynamics vertex groups (and any locked vertex group) intact
across destructive operations such as the Surface Deform shape key
transfer's vertex group clear and full weight transfers.

Protected group collection rules:
- Any vertex group with ``lock_weight`` set (Blender's weight lock) is
  protected. This reuses the addon's existing lock convention from
  the Combine Vertex Groups operator.
- Any vertex group whose name starts with one of the user-configured,
  case-insensitive prefixes (scene property
  ``weight_transfer_protected_prefixes``) is protected. These are
  typically dynamics chains the body armature does not own
  (PhysBones): Boob, Tail, Skirt, Ear, Hair, etc.
"""


def parse_protected_prefixes(prefix_string):
    """Parse a comma-separated prefix string into a tuple of lowercase prefixes."""
    if not prefix_string:
        return ()
    return tuple(p.strip().lower() for p in prefix_string.split(',') if p.strip())


def collect_protected_group_names(obj, respect_lock_weight=True, prefixes=()):
    """Return the set of vertex group names on obj that must never be modified."""
    protected = set()
    for vg in obj.vertex_groups:
        if respect_lock_weight and vg.lock_weight:
            protected.add(vg.name)
            continue
        name_lower = vg.name.lower()
        for prefix in prefixes:
            if name_lower.startswith(prefix):
                protected.add(vg.name)
                break
    return protected


def snapshot_vertex_groups(obj, group_names):
    """Snapshot per-vertex weights for the given vertex group names.

    Harvests weights in a single pass over mesh.vertices[*].groups instead
    of per-group VertexGroup.weight() calls (which raise RuntimeError for
    every vertex not in the group).

    Returns a list of {'name', 'lock_weight', 'weights': {vertex_index: weight}}
    entries, in the object's vertex group order.
    """
    entries_by_index = {}
    snapshot = []
    for vg in obj.vertex_groups:
        if vg.name in group_names:
            entry = {'name': vg.name, 'lock_weight': vg.lock_weight, 'weights': {}}
            entries_by_index[vg.index] = entry
            snapshot.append(entry)

    if entries_by_index:
        for v in obj.data.vertices:
            for g in v.groups:
                entry = entries_by_index.get(g.group)
                if entry is not None:
                    entry['weights'][v.index] = g.weight

    return snapshot


def restore_vertex_groups(obj, snapshot):
    """Recreate snapshotted vertex groups exactly (weights and lock flag).

    Any same-named group currently on the object is removed first, so
    whatever a transfer wrote into a protected name is discarded.
    Returns the number of groups restored.
    """
    for entry in snapshot:
        existing = obj.vertex_groups.get(entry['name'])
        if existing is not None:
            obj.vertex_groups.remove(existing)
        vg = obj.vertex_groups.new(name=entry['name'])
        # Batch adds by weight value so each distinct weight is one add() call
        buckets = {}
        for vertex_index, weight in entry['weights'].items():
            buckets.setdefault(weight, []).append(vertex_index)
        for weight, indices in buckets.items():
            vg.add(indices, weight, 'REPLACE')
        vg.lock_weight = entry['lock_weight']
    return len(snapshot)


def compute_snapshot_drift(obj, snapshot):
    """Max absolute per-vertex weight difference between obj's current
    groups and the snapshot.

    0.0 means the protected groups are bit-identical to the snapshot;
    float('inf') means a snapshotted group is missing entirely.
    """
    current = snapshot_vertex_groups(obj, {entry['name'] for entry in snapshot})
    current_by_name = {entry['name']: entry for entry in current}
    drift = 0.0
    for entry in snapshot:
        cur = current_by_name.get(entry['name'])
        if cur is None:
            return float('inf')
        for vertex_index in set(entry['weights']) | set(cur['weights']):
            diff = abs(entry['weights'].get(vertex_index, 0.0)
                       - cur['weights'].get(vertex_index, 0.0))
            if diff > drift:
                drift = diff
    return drift


def limit_vertex_influences(obj, protected_names, max_influences):
    """Prune the smallest unprotected weights so no vertex exceeds
    max_influences total influences.

    Protected groups are never pruned, even if a vertex is above the cap
    from protected entries alone. Returns the set of pruned vertex indices.
    """
    protected_indices = {vg.index for vg in obj.vertex_groups if vg.name in protected_names}
    removals_by_group = {}
    pruned_vertices = set()
    for v in obj.data.vertices:
        entries = [(g.group, g.weight) for g in v.groups]
        if len(entries) <= max_influences:
            continue
        protected_count = sum(1 for group_index, _ in entries if group_index in protected_indices)
        unprotected = [e for e in entries if e[0] not in protected_indices]
        keep = max(0, max_influences - protected_count)
        if len(unprotected) <= keep:
            continue
        unprotected.sort(key=lambda e: e[1], reverse=True)
        for group_index, _weight in unprotected[keep:]:
            removals_by_group.setdefault(group_index, []).append(v.index)
        pruned_vertices.add(v.index)
    groups_by_index = {vg.index: vg for vg in obj.vertex_groups}
    for group_index, vertex_indices in removals_by_group.items():
        groups_by_index[group_index].remove(vertex_indices)
    return pruned_vertices


def lock_aware_renormalize(obj, protected_names, extra_vertex_indices=frozenset()):
    """Scale unprotected weights so vertex totals reach 1.0 while protected
    weights stay exactly as-is (lock-aware normalize).

    Processes vertices that carry protected weights, plus any explicitly
    requested indices (e.g. vertices that just had influences pruned).
    Returns (rescaled_count, unfillable_count); unfillable vertices have
    weight budget left but no unprotected weights to scale up.
    """
    protected_indices = {vg.index for vg in obj.vertex_groups if vg.name in protected_names}
    rescaled = 0
    unfillable = 0
    for v in obj.data.vertices:
        protected_sum = 0.0
        unprotected_entries = []
        for g in v.groups:
            if g.group in protected_indices:
                protected_sum += g.weight
            else:
                unprotected_entries.append(g)
        if protected_sum <= 0.0 and v.index not in extra_vertex_indices:
            continue
        budget = max(0.0, 1.0 - protected_sum)
        unprotected_sum = sum(g.weight for g in unprotected_entries)
        if unprotected_sum <= 0.0:
            if budget > 0.0 and (protected_sum > 0.0 or unprotected_entries):
                unfillable += 1
            continue
        factor = budget / unprotected_sum
        if abs(factor - 1.0) <= 1e-9:
            continue
        for g in unprotected_entries:
            g.weight *= factor
        rescaled += 1
    return rescaled, unfillable
