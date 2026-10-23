# Testing

The repository has two deliberately separate test layers.

## Fast Core Checks

`verify_repository.py` validates architecture, file-size policy and dependency
direction, then runs every plain-Python test. Install the development requirements
below before running the full tests:

```powershell
python scripts/verify_repository.py
```

For measured branch coverage, install the development dependencies and run:

```powershell
python -m pip install -r requirements-dev.txt
python scripts/run_coverage.py
```

Coverage is intentionally scoped to `BASICs_shape_key_manager/core`. Blender UI
and operator registration are tested in Blender rather than rewarded for large
mock implementations. The gates are:

- 77.5% across all core code, including visible legacy gaps.
- 86.5% across clothing validation and explicit clothing-refit math.

The active feature list in `scripts/run_coverage.py` names every promoted
clothing core module. The overall gate still includes all existing core code.
`coverage.xml` is uploaded by the package workflow.

## Blender 5.1 Integration

The integration runner creates an isolated Blender user profile, builds the
extension with Blender's extension command, installs and enables it, and runs:

- factory-startup import checks;
- normal-startup registration checks for the panel, properties, and
  representative mesh, armature, and vertex-group operators;
- evaluated clothing geometry, native IK, session replay and cancellation;
- fixed FACE regions, endpoint-pair contact allowances, raw/actionable evidence
  and nonadjacent garment self-collision;
- a vendor-free skinned/shape-keyed native and FBX roundtrip with four influences,
  protected weights, UV/material/bind/posed-point checks and corruption rejection;
- explicit clothing refits, protected influence shares, utility masks, shape
  keys, cancellation, unmapped vertices, and failed-commit rollback.

Run it locally with:

```powershell
python scripts/run_blender_checks.py `
  --blender D:\SteamLibrary\steamapps\common\Blender\blender.exe
```

`.github/workflows/blender-integration.yml` performs the same checks in CI with
the official Blender 5.1.2 Linux archive. The archive is cached and checked
against Blender's published SHA-256 file before execution. Build/package PRs
and releases both call this reusable workflow.

## Promotion and user installation

This branch preserves canonical master's existing tools and adds only clothing
validation, explicit refit and their quality checks. The development snapshot
also has unrelated Molt and armature features. Installing this smaller package
over that snapshot would remove those tools. Test this package with the isolated
runner; install the updated development tree into the existing user profile.
Factory and normal-startup checks from the isolated runner prove this package's
registration. A smoke check from the full development installation is separate
evidence and does not prove that this minimal package was installed there.
