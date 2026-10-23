# BASICs Shape Key Manager Architecture

This file is generated from `architecture.json`. Run `python scripts/verify_repository.py --write-architecture` after editing the map.

Read the matching row before changing code. Core modules are Blender-free; operators adapt Blender state to core APIs; UI only exposes properties and commands.

| Area | Reach here when | Source | Tests | Design docs |
|---|---|---|---|---|
| Clothing pose checks | Changing immutable baseline capture, paired collision diagnostics, synthetic IK, validation jobs or review scenes | `BASICs_shape_key_manager/core/clothing_checks.py`<br>`BASICs_shape_key_manager/core/clothing_motion.py`<br>`BASICs_shape_key_manager/operators/clothing_checks`<br>`BASICs_shape_key_manager/ui/clothing_checks_panel.py`<br>`BASICs_shape_key_manager/utils/clothing_checks_properties.py`<br>`BASICs_shape_key_manager/core/clothing_policy.py` | `tests/test_clothing_checks.py`<br>`tests/test_clothing_motion.py`<br>`tests/test_clothing_reporting.py`<br>`scripts/verify_clothing_geometry_blender.py`<br>`scripts/verify_clothing_ik_blender.py`<br>`scripts/verify_clothing_shoulders_blender.py`<br>`scripts/verify_clothing_checks_blender.py`<br>`scripts/verify_clothing_session_regressions.py`<br>`scripts/verify_clothing_inactive_sources.py`<br>`scripts/verify_clothing_inputs_blender.py`<br>`scripts/verify_clothing_review_state.py`<br>`scripts/clothing_session_reopen.py`<br>`scripts/clothing_export_fixture.py`<br>`scripts/verify_clothing_export_blender.py`<br>`tests/test_clothing_policy.py`<br>`scripts/verify_clothing_policy_blender.py`<br>`tests/test_clothing_independent_motion.py` | `docs/clothing_pose_checks.md` |
| Addon registration and UI | Changing registration, sidebar layout, or persistent scene properties | `BASICs_shape_key_manager/__init__.py`<br>`BASICs_shape_key_manager/operators/__init__.py`<br>`BASICs_shape_key_manager/ui`<br>`BASICs_shape_key_manager/utils` | - | `README.md` |
| Shape-key mirror and spatial matching | Changing side naming, mirrored vertex matching or nearest-point lookup | `BASICs_shape_key_manager/core/mirror_utils.py`<br>`BASICs_shape_key_manager/core/octree.py` | `tests/test_core_mirroring.py` | `docs/AI_FUNCTIONALITY_GUIDE.md` |
| Polyloop reduction | Changing existing loop scoring, dissolve or reduction | `BASICs_shape_key_manager/core/polyloop_reduction.py`<br>`BASICs_shape_key_manager/core/polyloop_dissolve.py`<br>`BASICs_shape_key_manager/core/polyloop_models.py`<br>`BASICs_shape_key_manager/operators/polyloop_ops.py`<br>`BASICs_shape_key_manager/operators/polyloop_guards.py` | `tests/test_polyloop_reduction.py`<br>`tests/test_polyloop_dissolve.py`<br>`tests/test_polyloop_ops_shape_keys.py` | `docs/molt_design.md` |
| Armature maintenance | Changing bone cleanup, weight rollup or modifier repair | `BASICs_shape_key_manager/operators/armature_ops.py`<br>`BASICs_shape_key_manager/operators/armature_modifiers.py` | - | `docs/AI_FUNCTIONALITY_GUIDE.md` |
| Vertex groups and explicit clothing refit | Changing protected transfer, group cleanup, rigid anchors, painting, or blending | `BASICs_shape_key_manager/core/vertex_group_utils.py`<br>`BASICs_shape_key_manager/core/weight_refit.py`<br>`BASICs_shape_key_manager/operators/weights`<br>`BASICs_shape_key_manager/operators/vertex_group_ops.py` | `tests/test_vertex_group_utils_mock.py`<br>`tests/test_weight_refit.py`<br>`scripts/verify_weight_refit_blender.py` | `docs/AI_FUNCTIONALITY_GUIDE.md`<br>`docs/weight_refit.md` |
| Repository quality and Blender CI | Changing test discovery, coverage gates, package verification, or installed-extension smoke checks | `scripts/run_coverage.py`<br>`scripts/run_blender_checks.py`<br>`.github/workflows/blender-integration.yml` | `tests/tooling`<br>`scripts/verify_blender_factory_import.py`<br>`scripts/verify_blender_registration.py` | `docs/testing.md` |

## Dependency Rules

- `core/` must not import `bpy`, `operators`, or `ui`.
- `operators/` owns Blender data conversion and may depend on `core/`.
- `ui/` owns layout only; mesh algorithms belong in `core/`.
- Scripts and tests should consume public package APIs instead of private helpers.
- Maintained text files have a hard 500-line maximum.
