"""Result and error types for polyloop dissolve."""
from dataclasses import dataclass

@dataclass(frozen=True)
class DissolveResult:
    """Outcome of dissolving a single loop.

    ``vertices``/``edges``/``faces``/``vertex_weights`` are the new mesh. The
    counters describe the edit so an operator (or a test) can assert on it
    without re-deriving topology.
    """

    vertices: list
    edges: list
    faces: list
    vertex_weights: dict
    removed_edges: int
    removed_vertices: int
    merged_faces: int
    faces_before: int
    faces_after: int
    shape_keys: list = None


class DissolveError(ValueError):
    """Raised when a loop cannot be safely dissolved.

    The message names the guardrail that fired (boundary edge, non-manifold
    edge, or a loop that would delete a face outright) so callers can report a
    useful reason instead of silently skipping.
    """
