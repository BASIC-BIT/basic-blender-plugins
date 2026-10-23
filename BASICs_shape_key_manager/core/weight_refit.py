"""Explicit clothing refits, independent of Blender and legacy raw snapshots."""

import math


def refit_vertex_weights(original, transferred, original_deform_names,
                         preserved_names, max_influences=None):
    """Keep chosen normalized bone shares and fill the remainder from the body.

    Utility groups survive verbatim, outside both normalization and the cap.
    An empty body mapping is valid only for a fully preserved vertex.
    """
    if not preserved_names <= original_deform_names:
        raise ValueError('Preserved groups must be original deform-bone groups')
    if max_influences is not None and max_influences < 1:
        raise ValueError('The influence limit must be positive')
    if any(not math.isfinite(w) or w < 0
           for row in (original, transferred) for w in row.values()):
        raise ValueError('Invalid negative or nonfinite weight')

    total = sum(w for name, w in original.items() if name in original_deform_names)
    preserved = {name: weight / total for name, weight in original.items()
                 if name in preserved_names and weight > 0} if total else {}
    remaining = max(0.0, 1.0 - sum(preserved.values()))
    body = {name: weight for name, weight in transferred.items()
            if name not in preserved_names and weight > 0}
    if max_influences is not None:
        slots = max_influences - len(preserved)
        if slots < 0 or (remaining > 1e-12 and slots < 1):
            raise ValueError('The influence limit cannot keep physics and body influence')
        body = dict(sorted(body.items(), key=lambda item: (-item[1], item[0]))[:slots])
    body_total = sum(body.values())
    if remaining > 1e-12 and body_total <= 0:
        raise ValueError('No usable transferred body weights for the remaining budget')

    result = {name: weight for name, weight in original.items()
              if name not in original_deform_names}
    result.update(preserved)
    if remaining > 1e-12:
        result.update({name: remaining * weight / body_total
                       for name, weight in body.items()})
    return result
