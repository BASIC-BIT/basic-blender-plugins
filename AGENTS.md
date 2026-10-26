# BASICs Shape Key Manager Agent Guide

Before editing this repository, read `ARCHITECTURE.md` and follow the row for
the feature being changed. Update `architecture.json` when ownership or paths
move, then regenerate the map with:

```powershell
python scripts/verify_repository.py --write-architecture --structure-only
```

Run `python scripts/verify_repository.py` before packaging or installing the
addon. Maintained text files have a hard 500-line maximum; files at 450 lines
should be split before adding substantial behavior. Split by responsibility,
never into numbered `part1`/`part2` modules.

Install `requirements-dev.txt` and run `python scripts/run_coverage.py` when
changing Blender-free core behavior. Preserve both coverage gates; add focused
regression cases instead of lowering them.

Keep reusable mesh, topology, armature-selection, and weight math under
`BASICs_shape_key_manager/core/` without importing `bpy`. Blender data access
and operators belong under `operators/`; panel layout belongs under `ui/`.

For BASIC plugin feature work, finish with the Blender 5.1 installer and both
factory-startup and real-user-preferences smoke checks documented in
`D:\bench\vrc-creation-workflows\skills\basic\references\basic-blender-plugin.md`.
The equivalent isolated integration command is documented in `docs/testing.md`
and is mandatory in CI.
