# Clothing pose checks

Use **3D View > BASIC > Developer > Clothing Pose Checks** to compare an outfit
before and after editing. The check uses copied native Blender data and synthetic
constrained IK. It does not reproduce VRChat IK or simulate PhysBones.

## Capture, edit and compare

1. Work in Object mode. Choose the body and rig in the panel. Select the clothing
   meshes, then choose **Capture selected outfit baseline**. Blender retains a
   separate baseline scene with independent mesh, shape-key, rig and action data.
2. Edit the original working clothing with normal Blender tools. The validator
   does not change geometry, weights, locks, animation or the ordinary refit tools.
3. Check every Before/After row. For independently prepared meshes, choose **Add
   external pair**, select both objects, and explicitly confirm the pairing.
   Pair topology, including polygon ordering, must match.
   Distinct captured objects must use independent Mesh, Armature and shape-key
   data. Linked users outside the captured input closure do not prevent a check.
   If captured objects share data, make their mesh/armature data single-user in
   Blender before capture.
4. Choose **Suggest mapping**, inspect every bone search field, and confirm the
   map. Suggestions alone do not authorize a run. Direct limb chains are required.
   Map `left_shoulder` and `right_shoulder` to the corresponding clavicles for
   shoulder sweeps. Each must parent its upper arm and descend from the chest.
   Legacy rigs can leave these blank, but shoulder cases then report invalid
   coverage instead of pretending that their clavicles were tested.
5. For collinear limbs, enter bend directions as armature-space vectors, for
   example `{"left_arm":[0,1,0],"right_arm":[0,1,0],"left_leg":[0,1,0],"right_leg":[0,1,0]}`.
   The correct direction depends on your rig. These values affect only copies.
6. Use **Preview neutral / reach / bend calibration** before a long run. Inspect
   the retained poses and residuals. **Return to source view** restores the source
   scene, selection and active object.
7. Choose tracking profiles and motion families. Both profiles are selected by
   default. Accessory flex is separate and requires explicit bone names in the
   Accessory bones JSON list. Secondary body jiggle bones are permitted. This is
   controlled local flex, not a claim about realistic physics behavior.
8. The current shape combination is always included. To add an endpoint, select
   a non-Basis key and choose **Add active shape endpoint**. Edit its value. Give
   multiple rows the same combination name to test them together. Body and garment
   keys have separate object-ID namespaces, even when their names match.
9. Run the checks. The native UI advances one copied pose or object-pair job per
   timer event. Cancel or Escape removes unfinished generated data. Source edits
   are detected between poses and stop the run as stale.

Unpin shape keys on the body and every reference/candidate mesh before baseline
capture or validation. Pinned keys override Blender geometry independently of
numeric key values, so capture and validation reject them without changing source
state. `CURRENT` uses the captured numeric blend, including supported drivers
evaluated for each pose. It does not test pinned-key display geometry. Changing
the pin or active shape key invalidates a running job or saved preview.

The default total budget is 512 evaluated pose/shape cases. Sampling reserves
coverage across selected profiles, shape states, motion families and heldout
cases. Additional shape variants consume that same budget. Reports identify
omitted cases and coverage strata. Refinement subdivides intervals near clipping, low clearance or
representative geometry displacement. Its finite depth and truncated intervals
are recorded. It does not prove collision freedom between samples.
The configured clearance warning threshold also selects near-clearance intervals
for refinement. An interval exactly at the threshold does not trigger that warning.

## Read the report and preview a correction

Retained reports carry a hash of their complete JSON payload. Preview, replay,
removal and export reject an edited or unhashed report. Rerun validation after
changing inputs instead of editing the retained report Text.
The result panel checks that same hash before displaying any report findings.
Unchanged redraws reuse one read-only display summary keyed by the exact Text
contents. Preview, replay, removal and export still read and validate the full
report each time.

The report separates regression, absolute fit and coverage. New, existing,
resolved and worsened regions use stable object pairs and source polygon IDs.
Every garment is checked against the body, every other selected garment and
itself. Self checks omit adjacent triangles that share vertices.
Weight audits separately record normalization, missing bones, four-influence
violations and changes to locked deform groups. Audits never repair weights.
Protected deform shares use the union of baseline and candidate locks. Unlocking
or removing a previously locked group cannot bypass the baseline comparison;
lock-state changes are listed separately and keep the audit invalid.
Declare utility masks explicitly in **Utility groups JSON**, for example
`{"captured-garment-id":["Mask","Pin"]}`. Use IDs from baseline/report bindings
and exact group names. Declared existing non-bone groups are excluded from the
deform audit and listed in `excluded_utility_groups`; undeclared unknown names
still report missing bones. Rig-bone names and nonexistent groups cannot be
declared as utilities. Declarations are captured in settings and retained on replay.

Body and garment self-crossing screens use the same configured contact band in
meters. Body neutral baselines use that band too; shallow contact within it is
not promoted to a new body crossing.

Absolute findings include candidate crossings and supported containment even
when the same clipping exists in the baseline. Confirmed `CLIPPING` stays visible
when unrelated pairs or unsampled intervals are unknown. Counts distinguish
repeated face observations from unique pair/object/source-face regions. Preview
selects absolute findings, including existing clipping. A clean regression result
does not establish a clean fit.

Saved reports keep complete raw crossing/contained face lists and actionable
policy face maps. Regression categories `new`, `existing`, `resolved` and
`unclassified` group source face IDs by object ID. The report declares
`regression_face_encoding: OBJECT_ID_TO_SOURCE_FACE_LIST`; core classification
APIs still return per-face records. Actionable summaries retain statuses, category
counts and a hash of complete classification evidence. Their full classification
can be reconstructed from the reference/candidate analyses and policy face maps.
Derived absolute face records are omitted from each pair result. Regional body
evidence is stored once per pose, reached through each result's `pose_index`.

The shoulder family includes down-to-raised lateral sweeps with straight and
bent elbows, inward/outward upper-arm twist, torso lean/turn, shrug and shoulder
protraction. Clavicles move explicitly. Lateral reach and overhead reach now use
different paths. These are synthetic stress poses, not VRChat IK emulation.
Lateral and overhead targets use anatomical arm elevation relative to the torso,
not rotation from the source rest pose. Side sweeps cover 15 to 150 degrees from
arms-down on both T-pose and A-pose sources; torso lean/turn carries that frame.
The motion library is versioned; reports from the old library require a new run
instead of silently replaying changed trajectories under their old case names.

Independent cases vary sided shoulder, upper-arm twist, elbow and forearm
controls. Asymmetric reaches and combined crouch, seated, kneeling and crossed-leg
poses supplement the sweeps. Pairwise combinations and bounded triples near a
failure expose combinations missed by a single coupled trajectory. Heldout cases
stay separate from adaptive fitting cases. Dance, turn, stop and settle phases
in Blender are kinematic samples. They do not simulate secondary motion.

Heel/toe rotations preserve the authored foot orientation. These are ankle tests;
the rig has no sole landmarks for a physical heel/toe contact pivot.

## Fixed regions and intended contacts

Use named BOOLEAN or INT attributes on the mesh's FACE domain to mark a region.
Keep the same region memberships on the baseline and candidate. These regions
are independent of edited vertices and add no deform vertex groups. Missing,
wrong-domain and empty requested regions are rejected.

The panel's FACE regions JSON maps captured object IDs to named attributes:

```json
{"garment-id":{"underarm":{"attribute":"Underarm","value":1}}}
```

Object IDs come from the captured baseline/report bindings. A body region may be
declared in the same dictionary. The report keeps local body self-crossing and
contact warnings alongside global warnings, distinguishing neutral and new pairs.
An unrelated body contact does not remove regional crossing evidence. Regional
screening never upgrades unknown global containment or certifies anatomy.

Contact allowances name both endpoint regions and a finding kind:

```json
[{"kind":"CROSSING","a":{"object_id":"garment-id","region":"attachment"},
  "b":{"object_id":"wing-id","region":"mount"}}]
```

Declare both regions first. Allowed, actionable and raw findings remain separate.
An allowed attachment face can still collide with another disallowed partner.
Preview retains raw findings. Review allowances deliberately; they describe
accepted contact rather than a repaired mesh.

Open, ambiguous or sparsely probed volumes remain unknown. A confirmed crossing
can still be useful when containment or penetration depth is unknown. An invalid
solve, missing seed, unresolved interval, cancellation or stale input prevents
complete coverage. Body self-crossing warnings retain their garment findings but
do not count as normal-motion proof. A screened synthetic pose remains an
approximation even when no new body self-crossing is found.

Select a pair finding, choose Before or After, then preview. The retained native
review scene applies the saved armature-space bone matrices, restores that shape
case and selects affected source polygons. Wire display exposes selected faces.
The report stores one pose record per case, not duplicated geometry per finding.
Illustrative triangle pairs are capped at 32 per analysis, with full counts and
explicit truncation flags. Source polygon lists remain complete.

Use **Replay saved report cases** to rerun the identical saved pose set after a
correction. The original coverage omissions and truncated intervals remain
visible. Choose **Export clothing JSON report** to save the report. Save the
`.blend` to retain native baseline/review scenes and their fake-user Text reports.
Source edits invalidate old preview; rerun against the edited inputs to make new
review evidence. New runs preserve earlier reviews. **Remove this generated
review** explicitly removes only the selected report's owned native scene.

## Supported inputs and limits

Version one supports relative shape keys and Armature modifiers. It rejects
other modifiers, simulations, source constraints, NLA, segmented B-Bones,
scripted drivers, rig drivers and unresolved or external driver targets.
Simple non-scripted SINGLE_PROP/TRANSFORMS drivers with known internal targets
are copied and retargeted. Parent dependencies must stay inside the captured
closure. Compatible captured reference rigs are accepted, then both sides use
one shared copied evaluation rig. Changes to a captured baseline body require a
separate capture rather than silently changing its comparison reference.

Captured rig compatibility compares world/rest matrices, bone hierarchy and
connection, inheritance, envelopes, B-Bone deformation settings and named handles,
and the armature's Pose/Rest evaluation mode. Changing these requires recapturing
the baseline. Rig labels, ownership, current pose bases and creator display,
selection or collection changes (including B-Bone display widths) remain allowed.

Editing either Before/After mesh clears that pair's confirmation. Changing the
selected rig or a mapping field clears mapping confirmation; its saved signature
also detects collection edits. Confirm the current inputs again before running.
Saved-case replay uses retained settings before reading any unused live shape or
JSON fields, while still requiring the current rig/mapping and pairs.

With refinement enabled, one quarter of the case cap is reserved for adaptive
search. The default cap starts with 384 of 738 stratified seeds and leaves 128
slots for refinement. Omitted seeds, missing strata and unresolved intervals
remain visible. Depth zero uses the full seed cap; exact replay keeps its cases.

Fingerprint format `BASIC-CLOTHING-BINARY-2` uses captured input identities and
native source pointers retained only on owned scenes. Rig/object labels and
armature-data names can change without making unchanged geometry stale. Source
properties are never changed to create identities. Previous-format baselines
require a new capture, and previous-format reports require a new validation run.
To preserve pre-edit geometry, choose the old baseline's frozen body and rig,
select its frozen garments, and capture a new independent baseline. This route
copies the frozen inputs and preserves the previous scene and evidence. Compare
against that new capture or use the original pre-edit source if still available.
If the original working body and rig remain the intended comparison inputs,
keep those selected and capture the frozen garments into a new baseline instead.

Explicit shape endpoints are checked against their effective evaluated values
after native drivers and clamping. An unrealized value stops the run with the
object, role, key, requested value and actual value in the report. CURRENT may use
pose-dependent drivers; every pose records their effective values. Source hashes
include authored key data, driver definitions and inputs. They exclude the
driver outputs that Blender computes from those inputs.

Each pair shares one reference triangle template captured before any test pose.
Owned scene metadata retains native source-object bindings and logical IDs.
These bindings preserve external pair/body shape namespaces after native reopen
without adding properties to source objects. Internal dependency meshes and rigs
stay hidden in both preview modes.

Before comparing, copying or fingerprinting sources, the validator materializes
their owning native view-layer graphs. This includes inactive reference scenes
after reopening a file. It preserves the window, selection and frame values and
keeps exact rig compatibility checks.

Defaults are 0.0001 meters for contact, 0.001 meters for clearance warnings and
0.0005 meters for worsened sampled depth. They are editable fitting choices.
Unsigned clearance and sampled depth are approximations. Unity skinning, shader
displacement, runtime physics and client parity are outside Blender's checks.
The separate workflow Unity capture tool tests imported/evaluated meshes and
records temporal evidence; it does not establish VRChat parity. The report lists omitted families, profiles, shape
keys and unevaluated cases.

## Synchronous API

Import `operators.clothing_checks.session` and use
`ValidationSession(context, body, rig, pairs, mapping, settings)`. `step()` returns
True when terminal. `cancel()` and `close()` are idempotent. A completed session
retains its owned review; an unfinished session removes only its own data.

`run_validation(context, body, rig, pairs, mapping, settings, progress=None,
cancelled=None)` drives that same session. Pairs are dictionaries containing
native `reference`, `candidate` objects and a `confirmed` flag. Mapping is a
complete canonical-name to bone-name dictionary. Settings contain the thresholds,
`budget`, `profiles`, `families`, `steps`, `refinement_depth`, `sample_limit`,
`bend_directions`, `accessory_bones`, optional `shape_cases`, `region_definitions`
and `contact_allowances`.

A shape case is `{"id":"name","values":{"logical-object-ID":{"key":1.0}}}`.
`capture_baseline(context, body, rig, clothing)` returns saved scene/object names,
pair identities and fingerprints. It does not add custom properties to sources.
Pass a saved report's `cases` as settings `cases` for exact pose replay. Pass its
`settings.motion_library_version` too; mismatched or missing versions are rejected.
Pass its `coverage` as `replay_coverage` to retain its previous coverage gaps. Newly
authored explicit cases also require the current `core.clothing_motion.LIBRARY_VERSION`.
Per-case
accessory subsets and local axes use `accessory_bones` and `accessory_axis`.
