"""Shape-key remapping across destructive mesh rebuilds.

This is the stage-4 "shape-key aware reduction" core (see
``docs/molt_design.md``). Like every other module in ``core/`` it is
bpy-free: it operates on a dumb, serializable representation so the remap
math can be unit tested outside Blender.

Representation
--------------
A shape key is a ``dict`` with at least:

* ``"name"``        -- the key block name (``"Basis"``, ``"vrc.v_aa"``, ...).
* ``"coordinates"`` -- a list of ``(x, y, z)`` ABSOLUTE per-vertex positions,
  one per source vertex, exactly how Blender stores key block data
  (``key_block.data[i].co``). Not deltas.

Any other entries (``"value"``, ``"slider_min"``, ``"relative_key"``, ...)
are metadata the Blender glue layer cares about; this module passes them
through untouched. Key ORDER is preserved, which is what encodes the
Basis-first convention and the key list the user sees.

Mapping rule
------------
``vertex_sources`` names, for each NEW vertex, the OLD source vertices it
derives from. The remapped coordinate of a key at a new vertex is the
component-wise MEAN of that key's absolute coordinates over the source
vertices:

* **Identity / surviving vertices** (a single source -- the only case the
  polyloop dissolve produces today, since a loop dissolve deletes vertices
  but never moves or blends the survivors): the mean of one point is an
  exact copy, so every surviving vertex keeps its exact shape-key positions.
* **Merged vertices** (several sources): averaging absolute positions is
  consistent with how a merge would place the base-mesh vertex (the mean of
  the merged base positions), and by linearity it preserves relative-key
  deltas exactly: ``mean(key) - mean(relative_key) == mean(key -
  relative_key)``, so a chain of relative keys keeps the same net offsets
  after the remap.
* **Removed vertices** (appearing in no source list): their shape-key data
  drops out, the same way their base-mesh position does -- geometry that no
  longer exists cannot morph.
"""


class ShapeKeyRemapError(ValueError):
    """Raised when shape keys cannot be remapped onto the new vertices.

    The message names the inconsistency (a key whose coordinate count does
    not match the source mesh, an empty source list, an out-of-range source
    index) so callers can report a useful reason.
    """


def sources_from_vertex_remap(vertex_remap, new_vertex_count):
    """Build a ``vertex_sources`` list from an ``{old: new}`` index remap.

    This is the identity/survivor case: every new vertex derives from exactly
    one old vertex. Raises :class:`ShapeKeyRemapError` if the remap does not
    cover every new vertex exactly once.
    """
    sources = [None] * new_vertex_count
    for old_index, new_index in vertex_remap.items():
        if not 0 <= new_index < new_vertex_count:
            raise ShapeKeyRemapError(
                f"vertex remap maps old vertex {old_index} to new index "
                f"{new_index}, outside the new mesh's 0..{new_vertex_count - 1}")
        if sources[new_index] is not None:
            raise ShapeKeyRemapError(
                f"vertex remap maps two old vertices to new index {new_index}; "
                "build multi-source lists explicitly for merges")
        sources[new_index] = [old_index]
    missing = [i for i, s in enumerate(sources) if s is None]
    if missing:
        raise ShapeKeyRemapError(
            f"vertex remap covers no source for new vertices {missing[:8]}"
            + ("..." if len(missing) > 8 else ""))
    return sources


def remap_shape_keys(shape_keys, vertex_sources, source_vertex_count=None):
    """Carry every shape key through a vertex mapping.

    Parameters
    ----------
    shape_keys:
        Ordered list of shape-key dicts (see module docstring). May be empty.
    vertex_sources:
        One entry per NEW vertex: a non-empty list of OLD vertex indices the
        new vertex derives from. Singleton lists copy; longer lists average.
    source_vertex_count:
        Optional expected length of every key's ``coordinates``; when given,
        keys of any other length raise instead of silently misindexing.

    Returns
    -------
    A new list of shape-key dicts in the same order, each a shallow copy of
    the input dict with ``"coordinates"`` replaced by the remapped list (one
    tuple per new vertex). Metadata entries are shared, not copied.

    Raises
    ------
    ShapeKeyRemapError
        On empty source lists, out-of-range source indices, or coordinate
        lists whose length disagrees with ``source_vertex_count``.
    """
    for new_index, sources in enumerate(vertex_sources):
        if not sources:
            raise ShapeKeyRemapError(
                f"new vertex {new_index} has no source vertices")
        if any(s < 0 for s in sources):
            raise ShapeKeyRemapError(
                f"new vertex {new_index} references a negative source index")

    remapped = []
    for key in shape_keys:
        coordinates = key["coordinates"]
        if (source_vertex_count is not None
                and len(coordinates) != source_vertex_count):
            raise ShapeKeyRemapError(
                f"shape key '{key.get('name', '?')}' has "
                f"{len(coordinates)} coordinates but the source mesh has "
                f"{source_vertex_count} vertices")

        new_coordinates = []
        for new_index, sources in enumerate(vertex_sources):
            try:
                points = [coordinates[s] for s in sources]
            except IndexError:
                raise ShapeKeyRemapError(
                    f"new vertex {new_index} references a source vertex "
                    f"outside shape key '{key.get('name', '?')}' "
                    f"({len(coordinates)} coordinates)")
            if len(points) == 1:
                point = points[0]
                new_coordinates.append((point[0], point[1], point[2]))
            else:
                inv = 1.0 / len(points)
                new_coordinates.append((
                    sum(p[0] for p in points) * inv,
                    sum(p[1] for p in points) * inv,
                    sum(p[2] for p in points) * inv,
                ))

        new_key = dict(key)
        new_key["coordinates"] = new_coordinates
        remapped.append(new_key)
    return remapped
