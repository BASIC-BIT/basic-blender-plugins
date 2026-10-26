"""Guard destructive mesh rebuilds against unsupported data loss."""

def _destructive_rebuild_blockers(obj):
    """Inventory data the ``clear_geometry()``/``from_pydata`` rebuild cannot
    preserve, split by severity.

    Returns ``(hard_blockers, lossy_layers)`` lists of human-readable strings:

    - ``hard_blockers``: shape-key configurations the rebuild genuinely
      cannot restore. Ordinary (relative) shape keys are now PRESERVED: they
      are captured before the rebuild, remapped through the same vertex
      mapping as the base mesh (``core/shape_key_remap.py``), and recreated
      afterwards. What still refuses outright:

      * absolute (non-relative) shape keys -- ``shape_key_add`` reassigns
        key frame timing, so the animation ordering cannot be rebuilt
        faithfully;
      * animation data (drivers/keyframes) on the shape-key datablock --
        the rebuild recreates the Key datablock, which would sever them.

    - ``lossy_layers``: UV maps, color attributes, and per-face material
      assignments. These are discarded by the rebuild; the operators only
      proceed when the user explicitly opts in via ``allow_attribute_loss``.
    """
    mesh = obj.data

    hard_blockers = []
    shape_keys = mesh.shape_keys
    if shape_keys is not None and len(shape_keys.key_blocks) > 0:
        if not shape_keys.use_relative:
            hard_blockers.append(
                "absolute (non-relative) shape keys: the rebuild cannot "
                "restore their frame timing")
        if getattr(shape_keys, "animation_data", None) is not None:
            hard_blockers.append(
                "animation data (drivers/keyframes) on the shape keys: the "
                "rebuild would sever them")

    lossy_layers = []
    if len(mesh.uv_layers) > 0:
        lossy_layers.append(f"{len(mesh.uv_layers)} UV map(s)")
    if len(mesh.color_attributes) > 0:
        lossy_layers.append(
            f"{len(mesh.color_attributes)} color attribute(s)")
    if len(mesh.materials) > 1:
        lossy_layers.append(
            f"per-face assignments across {len(mesh.materials)} material slots")
    return hard_blockers, lossy_layers


def _refuse_unpreservable_data(operator, obj, allow_attribute_loss):
    """Shared guard for the destructive operators. Reports and returns True
    when the rebuild must not run on this mesh."""
    hard_blockers, lossy_layers = _destructive_rebuild_blockers(obj)
    if hard_blockers:
        operator.report(
            {'ERROR'},
            "Cannot rebuild mesh with " + "; ".join(hard_blockers)
            + ". Remove the unsupported configuration first (relative shape "
              "keys without drivers are preserved automatically).")
        return True
    if lossy_layers and not allow_attribute_loss:
        operator.report(
            {'ERROR'},
            "Rebuild would discard " + ", ".join(lossy_layers)
            + ". Enable 'Allow Attribute Loss' to proceed anyway.")
        return True
    return False
