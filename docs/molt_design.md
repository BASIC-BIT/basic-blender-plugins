# Molt — Smart Polyloop Reduction

> **Working name:** *Molt* — avatars shedding excess geometry the way an animal
> molts. The final name is BASIC's call; see the [Naming](#appendix-naming) appendix
> for the shortlist. The design reads the same under any name, so read "Molt"
> below as "the tool."

**Status:** shipped on `master` (PR #1 dissolve + iterate-to-target; PR #2 weight
preservation fix). Stages 1–3 of the [staged plan](#staged-plan) are implemented,
unit-tested (13 bpy-free tests, all green), and wired into the *BASICs Shape Key
Manager* Blender extension. Stages 4–5 are roadmap.

**Audience:** BASIC and future contributors; written so it can stand as a public
design note if Molt is ever released to the VRChat avatar-optimization community.

---

## TL;DR

Molt reduces the polygon count of avatar and clothing meshes by dissolving whole
edge loops that a human artist would judge "safe to remove," instead of collapsing
arbitrary edges the way a naive decimator does. It **traces** coherent edge loops,
**scores** each one for how much damage dissolving it would do (planarity, silhouette
impact, deformation-weight variation), **dissolves the single safest loop**, then
**re-traces and re-scores the changed mesh** and repeats until it hits a target face
count or runs out of loops it considers safe. The scoring/tracing/dissolving core is
pure Python + NumPy with **no `bpy` dependency**, so the entire judgment pipeline is
unit-tested outside Blender on hand-verifiable synthetic meshes. Weight preservation
is always on; boundary and non-manifold edges are refused.

---

## 1. The problem

VRChat avatars live and die by their polygon budget (the performance-rank system
punishes high triangle counts), but avatar meshes are not free-form scenery — they
are **rigged, morphed, and textured**, and their topology encodes all three:

- **Deformation.** Edge loops around elbows, knees, shoulders, hips, fingers, and
  chest/jiggle regions exist so the mesh bends cleanly when the skeleton moves.
  Removing the wrong loop makes a joint pinch, collapse, or candy-wrap.
- **Shape keys / blendshapes.** Visemes, expressions, and body morphs are per-vertex
  deltas. Delete a vertex that a morph moves and you silently break the morph.
- **UV seams and material boundaries.** Texture islands and material splits ride on
  specific edges. Dissolving across a seam smears or tears the texture.

Blender's built-in **Decimate** modifier (Collapse / Un-Subdivide / Planar) optimizes
a *geometric* error metric with no idea that any of the above matters. On an avatar it
reliably trashes deformation loops and morph-critical vertices to save triangles it
"thinks" are cheap. That is why experienced avatar creators don't trust one-click
decimation on a final mesh — instead they **alt-click edge loops by hand and dissolve
the ones they judge structurally unimportant**: a run of loops down a forearm, a band
of subdivision on a flat skirt panel. The reduction is loop-level because the *decision*
is loop-level. The loop is the unit at which "does this matter to how the avatar
deforms/morphs/textures?" has a clean answer.

That hand process is slow and doesn't scale to a whole wardrobe. **Molt automates the
judgment, not just the cut.** It is not a better error metric bolted onto collapse —
it keeps the artist's primitive (dissolve a coherent loop) and encodes the artist's
reasoning (which loops are safe) as a score, so the output is inspectable and the tool
degrades gracefully: when it isn't confident a loop is safe, it stops rather than
guessing.

Molt is **not** a Decimate replacement for arbitrary game props. It is a
topology-aware, avatar/clothing-shaped reducer that trades maximum compression for
"won't wreck the rig."

---

## 2. How it works

The pipeline is the classic simplification loop from Garland & Heckbert's Quadric
Error Metrics work (*assign an error to each candidate edit, apply the lowest-error
safe one, re-score, repeat*) — but the edit primitive is a **whole edge-loop dissolve**
instead of a single edge collapse, and the error function is **avatar-aware**.

```
   ┌──────────────────────────────────────────────────────────────┐
   │  trace coherent loops  →  score each  →  filter unsafe        │
   │        ↑                                     │                │
   │        │            dissolve the             ▼                │
   │        └──────  single safest loop  ◄──  pick best (lowest    │
   │   (re-trace & re-score the CHANGED mesh)      score)          │
   └──────────────────────────────────────────────────────────────┘
        stop when: target face count met · safest loop exceeds the
        quality floor · no loop passes the guardrails
```

### 2.1 Trace coherent loops
`polyloop_reduction.find_loop_candidates(vertices, edges, faces, vertex_weights=None,
min_edges=4, max_turn_degrees=75)` approximates Blender's alt-click loop selection in
pure Python. From each seed edge it walks forward and backward, at every vertex
choosing the outgoing edge that stays **most collinear** with the incoming edge
(`_choose_next_edge` maximizes the dot product of normalized incoming/outgoing
directions). It **stops** at branches, boundaries, non-manifold junctions (valence
outside the 2–4 band), or turns sharper than `max_turn_degrees`. Loops shorter than
`min_edges` are discarded, and a `seen` set dedups loops reached from different seeds.
This is a deliberate *conservative approximation* of Blender's selection, not a claim
of exact parity — good enough to nominate the loops a human would, cheap enough to
re-run every iteration, and (crucially) testable without Blender.

### 2.2 Score safety (lower = safer to dissolve)
`score_loop_candidate(...)` returns a frozen `LoopCandidate` dataclass. The score
combines three terms:

```
score = normalized_plane_deviation
      + 0.25 * (mean_face_angle / π)
      + 0.50 * weight_variation
```

- **Planarity (PCA).** Fit a best-fit plane to the loop's vertices via the eigen-
  decomposition of their covariance (`_plane_deviation`); take the RMS distance to
  that plane and **normalize by the loop's bounding-box diagonal** (`_candidate_scale`)
  so a small accessory and a large clothing panel are judged on the same scale. A loop
  that lies flat is cheap to remove; a loop that carries curvature is not.
- **Silhouette impact (face angle).** Mean dihedral angle between the two faces
  adjacent to each loop edge (`_face_angle_stats`). Low dihedral means dissolving the
  loop barely changes the visible outline.
- **Deformation sensitivity (weight variation).** Across every vertex group touched by
  the loop, the **maximum range** of any group's weight along the loop
  (`_weight_variation`). A loop sitting in a joint-transition zone — where, say,
  `UpperArm` fades into `Forearm` — has high weight variation and is penalized, so
  Molt prefers the flat mid-forearm loops over the elbow band **without any hardcoded
  body-part table**. It falls out of the weights the rigger already painted.

The constants (`0.25`, `0.50`) are **starting weights, not final truth** — they are
meant to be tuned against real avatar/clothing meshes.

### 2.3 Dissolve the safest loop
`polyloop_dissolve.dissolve_loop(vertices, edges, faces, loop_edge_indices,
vertex_weights=None)` performs the destructive edit on the same tuple-mesh
representation, mirroring `bmesh.ops.dissolve_edges` semantics in two steps:

1. **Merge faces across each loop edge.** A union-find over faces collapses a whole
   run of quads sharing loop edges into one merged polygon deterministically
   (`_merge_face_group` / `_merge_faces_across_edge` splice the two faces' arcs that
   avoid the shared edge).
2. **Dissolve the collinear loop vertices** left at valence-2 in the merged boundary
   (`_dissolve_interior_vertices`), so a dissolved quad-strip leaves **clean quads**
   behind rather than n-gons studded with redundant collinear vertices. Vertices at
   T-junctions or loop corners are kept so a hole is never opened.

It then rebuilds the edge list from the surviving faces, re-indexes vertices (dropping
orphans), and **remaps vertex-group weights onto the surviving vertices**. The result
is a `DissolveResult` carrying the new mesh plus counters (removed edges/vertices,
merged faces, before/after face counts) so callers and tests can assert on the edit
without re-deriving topology.

### 2.4 Recompute + re-score + iterate to target
`polyloop_dissolve.reduce_to_target(...)` is the outer loop. Each iteration it
**re-traces and re-scores the current mesh** (mandatory — every dissolve changes
adjacency, planarity, face angles, and weights), takes the lowest-scoring candidate,
and dissolves it; if that candidate hits a guardrail it walks down the sorted list
until one dissolves cleanly. It stops on the first of:

- `target_faces` reached,
- the safest remaining loop exceeds `max_score` (**the quality floor — never dissolve
  a risky loop just to hit a count**),
- an optional `max_plane_deviation_ratio` filter leaves no candidate,
- no loop passes the manifold guardrails, or `max_iterations` is hit.

It returns the reduced mesh, the number of dissolves applied, before/after face
counts, and a `stopped_reason` string.

### 2.5 Determinism and guardrails (always-on)
- **Deterministic.** Candidates come back in stable score order, so identical input
  always yields the identical reduction sequence — reproducible, reviewable, testable.
- **Boundary / non-manifold protection.** `dissolve_loop` refuses (`DissolveError`)
  any loop edge that touches fewer than two faces (would open a hole) or more than two
  (ambiguous non-manifold edit). The iterator skips such loops rather than aborting.
- **Weight preservation is always on, and is separate from weight scoring.** This is a
  deliberate decoupling (PR #2 / Greptile P1 fix): the operator *always* threads vertex
  weights through the dissolve and re-applies the remapped weights on rebuild, so a
  rigged mesh never loses deformation weights. The `include_weight_penalty` /
  `score_with_weights` toggle only controls whether weight variation influences the
  *ranking* — turning off weight-aware scoring must never destroy weights. (The earlier
  bug: unchecking the box made the operator pass `weights=None`, and the
  `clear_geometry` + `from_pydata` rebuild silently dropped every weight.)

---

## 3. Architecture

### 3.1 Pure-Python core vs. thin Blender glue
The design's load-bearing decision is a hard split between **judgment** and **Blender
plumbing**:

| Layer | Files | `bpy`? | Tested? |
|---|---|---|---|
| **Core (all topology math + scoring)** | `core/polyloop_reduction.py` (trace + score), `core/polyloop_dissolve.py` (dissolve + iterate) | **No** — pure Python + NumPy | **Yes** — 13 bpy-free tests |
| **Operator glue** | `operators/polyloop_ops.py` | Yes | No (deliberately) |

Everything operates on one dumb, serializable representation:

```
vertices       : list of (x, y, z) tuples
edges          : list of (a, b) vertex-index pairs
faces          : list of vertex-index tuples (any arity; quads in practice)
vertex_weights : optional {vertex_index: {group_name: weight}}
```

The Blender operators are intentionally **thin and untested**: they (1) read the active
mesh into those tuples (`_mesh_to_tuples` / `_collect_vertex_weights`), (2) call the
tested core, and (3) mirror the rebuilt tuple mesh back into Blender
(`_write_tuples_to_mesh` via `clear_geometry` + `from_pydata`, then re-apply remapped
weights). **No topology math lives in the operator layer** — a comment in the file says
so explicitly, and it's a maintenance rule, not just a description.

Three operators expose the three stages:

- `MESH_OT_preview_polyloop_reduction` — non-destructive: selects the best candidate
  loop(s) in Edit Mode so a human can eyeball them before anything is cut.
- `MESH_OT_dissolve_polyloop_candidate` — dissolves the single safest candidate.
- `MESH_OT_reduce_polyloop_to_target` — runs `reduce_to_target` to a face budget.

All three share props: `min_edges` (default 8), `max_turn_degrees` (75),
`max_plane_deviation_ratio` (0.005), `include_weight_penalty` (on), plus
`target_faces` / `max_score` / `max_iterations` on the reducer.

### 3.2 Why bpy-free is the whole game
`bpy` can only be imported inside a running Blender. If the scoring and dissolve logic
lived in the operator, testing it would mean launching headless Blender per run —
slow, flaky, and awkward in CI. By keeping the core pure, the entire judgment pipeline
runs under plain `python tests/test_polyloop_*.py` in milliseconds, and the only
untested code is the mechanical glue that has no decisions in it.

### 3.3 Testing philosophy: synthetic, hand-verifiable meshes
Tests build tiny meshes by hand — `make_strip_mesh` (a flat quad strip),
`make_grid(cols, rows, warp=...)` (a grid whose `warp(c, r)` can lift chosen columns
out of plane) — and assert on outcomes a human can verify by eye:

- planar loops score below warped ones;
- a joint-like weight gradient scores worse than a uniform one;
- dissolving the middle loop of a 2×2 grid yields exactly two clean quads, removing
  exactly three vertices;
- boundary and non-manifold loops raise `DissolveError`;
- `reduce_to_target` actually reaches the face count, stays all-quads-manifold, leaves
  no orphaned indices, prefers flat loops over a warped ridge, halts at the quality
  floor when the target is unreachable safely, is **byte-for-byte deterministic** across
  runs, and preserves weights even with scoring disabled.

Tests load the modules by file path with `importlib` (bypassing the package
`__init__`, which would drag in `bpy`), registering a stub `core` package so
`polyloop_dissolve`'s `from . import polyloop_reduction` resolves. This is the same
proven harness the repo already uses for `test_vertex_group_utils_mock.py`; **any new
core module should adopt it.**

---

## 4. Roadmap

Molt covers stages 1–3 of the original spec. The remaining stages deepen the
*judgment* and add a human-in-the-loop safety gate.

### Stage 4 — Deformation/morph/UV-aware scoring
Today's weight-variation term already catches joint zones implicitly. Stage 4 makes the
score understand the rest of what avatar topology encodes:

- **Bone-chain hot spots.** Read the mesh's armature and add extra penalty to loops in
  high-motion regions (elbows, knees, shoulders, hips, fingers, chest/jiggle). The
  sibling `armature-base-converter` addon already carries canonical Zinpia/ZinFit
  deformation-bone name tables (Boob/Butt/Thigh-Jiggle/Hips-Dips, etc.) that can seed a
  hot-spot list without inventing one.
- **Shape-key delta variation.** Penalize loops whose vertices carry large blendshape
  deltas, so morph- and viseme-critical geometry is not dissolved blindly.
- **UV-seam / material-boundary delimiters.** Treat UV islands and material splits as
  hard stops (mirroring Blender's dissolve *delimiters*), so a reduction never tears a
  texture island or merges across a material.
- **Bridge-pair scoring.** When the loops on both sides of a candidate are nearly
  parallel, planar, and weight-consistent, the middle loop is an even stronger dissolve
  candidate — the redundant-subdivision case.

Guardrail data for this already exists in the wider toolchain:
`vrc-creation-workflows/scripts/blender/mesh_topology_report.py` computes per-mesh
boundary/non-manifold edge counts, and `fbx_inventory_report.py` reports UV maps,
vertex groups, and shape keys — both headless bpy scripts Molt's operator layer can
lean on to gather stage-4 inputs.

### Stage 5 — Visual validation gate
Before automated reductions are trusted on a *final* avatar, require a before/after
visual check. `vrc-creation-workflows` already has the pieces: headless preview
renders (`render_mesh_preview.py`) and a VLM-based Unity screenshot verify harness
(`scripts/unity-verify/`). Molt would emit a candidate reduction, render before/after,
and gate acceptance on that review rather than trusting the score blindly on the last
mile.

### Near-term ergonomics
A `dry_run` report (CSV/JSON of the top candidates and their score breakdowns) so a
user can inspect *why* a loop ranked where it did before dissolving anything — cheap,
high-trust, and a natural extension of the existing preview operator.

### Intersection with Poiyomi atlasing
Molt is one of **two** avatar-optimization tracks in BASIC's tooling; the other is
**Poiyomi-aware material analysis + texture atlasing** (compatibility check → build
atlas → remap UV islands → replace material slots). The two intersect at **UVs**:

- Atlasing **rewrites** UVs (packing many islands into one texture); Molt must
  **respect** UV seams (stage 4). If both run, **atlas first, reduce second** so Molt
  scores against the final UV layout — or Molt must re-read UVs after any atlas pass.
- They share infrastructure: the same bpy-free-core + synthetic-test pattern, the same
  headless inventory scripts, and the same visual-validation harness. The atlas
  compatibility/UV-packer core is the natural next module to build in this repo using
  Molt's testing scaffold.

Net: Molt (topology) and the atlas tool (materials/UVs) are complementary halves of a
"poor → Good performance rank" pipeline, coupled through the UV layer.

---

## 5. Staged plan (status)

| Stage | Description | Status |
|---|---|---|
| 1 | Preview only: analyze, score, select best loop(s) in Edit Mode | ✅ shipped |
| 2 | Single-loop dissolve with Blender semantics + poly-delta report | ✅ shipped |
| 3 | Target-face-count mode: iterate safest-first, re-score each edit | ✅ shipped |
| 4 | Bone-chain / shape-key / UV-seam-aware scoring + bridge pairs | roadmap |
| 5 | Visual validation gate (before/after) on final meshes | roadmap |

---

## Appendix: Naming

*Molt* is the working name used throughout this document. **The final name is BASIC's
call.** Candidates on the table (doc reads fine under any):

| Name | Idea | Notes |
|---|---|---|
| **Molt** | Avatars shedding excess geometry like an animal molting | Evocative, memorable, on-theme; slightly indirect about what it does. |
| **Loopshed** | "Shed edge loops" | Literal about the mechanism; keeps the shedding metaphor. |
| **Loopwise** | Reduce loops *wisely* (the judgment angle) | Leans on the "smart/safe" differentiator; a touch cute. |
| **Occam** | Occam's razor — remove what isn't needed | Elegant, but overloaded as a software name and reads generic. |
| **Retopo-Lite** | "Retopology, but lighter/automatic" | Most self-explanatory to the target audience; risks under-selling (it's dissolve, not full retopo) and sounds like a stripped-down edition. |
| **Polyshear** | "Shear away polys" | Direct and toolish; "shear" has a specific geometric meaning that could mislead. |

Selection criteria worth weighing: discoverability to VRChat creators searching for a
polycount tool, non-collision with existing addons, and honesty about scope (loop
dissolve, not general decimation or full retopology).

---

## Reference: source map

| File | Role |
|---|---|
| `core/polyloop_reduction.py` | Loop tracer + safety scorer (`find_loop_candidates`, `score_loop_candidate`, `LoopCandidate`). bpy-free. |
| `core/polyloop_dissolve.py` | Destructive dissolve + iterate-to-target (`dissolve_loop`, `reduce_to_target`, `DissolveResult`, `DissolveError`). bpy-free. |
| `operators/polyloop_ops.py` | Blender operators (preview / dissolve-safest / reduce-to-target) + tuple-mesh glue. Thin, untested. |
| `tests/test_polyloop_reduction.py` | Scorer tests (synthetic strips). |
| `tests/test_polyloop_dissolve.py` | Dissolve + reducer tests (synthetic grids). |
| `docs/smart_polyloop_reduction_plan.md` | Original implementation plan (superseded in scope by this design doc). |

### References
- Garland & Heckbert, *Surface Simplification Using Quadric Error Metrics*, SIGGRAPH 1997.
- Garland & Heckbert, *Simplifying Surfaces with Color and Texture using Quadric Error Metrics*, IEEE Visualization 1998.
- Blender Decimate modifier (Planar mode + delimiters); `bmesh.ops.dissolve_edges`; `mesh.loop_multi_select`.
