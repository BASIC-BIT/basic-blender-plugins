# Refit clothing weights

Use **Refit Clothing Weights** after sculpting clothing to match a body. It
replaces anatomical weights while retaining chosen clothing dynamics.

## Workflow

1. Save an incremental working copy. Use independent mesh data for clothing.
2. Fit both meshes in their rig rest poses. Each needs one Armature modifier.
3. In the clothing's vertex-group list, lock every bone group whose influence
   should survive. The BASIC panel also shows Blender's native group list.
4. Select the body, then the clothing last so clothing is active.
5. Open **BASIC > Vertex Group Operations > Refit Clothing Weights**.
6. Review the body, clothing, and exact locked bone-group list, then apply.
7. Ensure the final deforming rig contains the body bones and preserved
   clothing chains. Check chain parents and rest orientations, then test poses.

The result uses body bone names. Original unpreserved anatomical groups are
removed even when their names differ from the body's. The action does not
rename or migrate bones, switch rigs, or modify mesh shape keys or geometry.

## Preservation means influence share

For each vertex, the action divides each locked bone's original weight by
the original total over actual deform-bone groups. Those individual fractions
are reserved; transferred body weights fill the remainder. For example, a bow
weight of 0.6 and arm weight of 0.8 reserve 0.6 / 1.4 for the bow.

Stored numbers may change during normalization, while the chosen bone's
proportional contribution stays the same. Non-deforming masks and utility
groups remain unchanged and do not consume the bone-weight budget.

Only locked bone groups are preserved. Missing source names and legacy
prefixes never add hidden preservation choices. Combine Vertex Groups is not
needed. Influence limiting is off by default; impossible limits are refused.

## Failure and compatibility

Transfer runs on a temporary copy and commits only validated weights. Missing
body mappings, cancellation, incompatible utility names, posed rigs, shared
mesh data, or impossible limits leave the clothing unchanged. A failed commit
restores the original group snapshot. The operation is undoable.

The existing **Robust Weight Transfer (Protected Groups)** remains available
through Blender operator search and its original Python identifier.
Shape-key transfer retains its existing raw-weight preservation rules.

## Checks

Run `python tests/test_weight_refit.py` for Blender-free math cases. Run
`scripts/verify_weight_refit_blender.py` in Blender with factory startup for
transfer, masks, shape keys, cancellation, unmapped vertices and rollback.
It is included in `scripts/run_blender_checks.py`.
