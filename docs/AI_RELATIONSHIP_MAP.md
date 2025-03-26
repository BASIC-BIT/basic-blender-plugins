# BASICs Shape Key Manager - Component Relationship Map

This document maps the relationships between the various components of the BASICs Shape Key Manager addon, helping AI tools understand dependencies and interactions.

## Registration Chain

```
__init__.py (main)
├── utils/properties.py: register_properties()
├── operators/__init__.py: register()
│   ├── basic_ops.py: SHAPEKEY_OT_* classes
│   ├── mirror_ops.py: SHAPEKEY_OT_* classes
│   ├── transfer_ops.py: SHAPEKEY_OT_* classes
│   ├── edit_ops.py: SHAPEKEY_OT_* classes
│   └── vertex_group_ops.py: VERTEXGROUP_OT_* classes
└── ui/__init__.py: register()
    └── panels.py: SHAPEKEY_PT_manager class
```

## Module Dependencies

| Module | Depends On | Depended On By |
|--------|------------|---------------|
| __init__.py | core, operators, ui, utils | N/A (top level) |
| core/octree.py | numpy, mathutils | mirror_ops.py |
| operators/basic_ops.py | bpy, json, Global copied_shape_keys | operators/__init__.py |
| operators/mirror_ops.py | bpy, re, mathutils, core/octree.py | operators/__init__.py |
| operators/transfer_ops.py | bpy, numpy | operators/__init__.py |
| operators/edit_ops.py | bpy | operators/__init__.py |
| operators/vertex_group_ops.py | bpy | operators/__init__.py |
| ui/panels.py | bpy | ui/__init__.py |
| utils/properties.py | bpy | __init__.py |

## Data Flow Relationships

```
Global variable: copied_shape_keys
├── Used by: SHAPEKEY_OT_copy (write)
├── Used by: SHAPEKEY_OT_cut (write)
└── Used by: SHAPEKEY_OT_paste (read)

Scene properties (registered in utils/properties.py)
├── shapekey_transfer_strength: Used by SHAPEKEY_OT_transfer_with_surface_deform
├── shapekey_transfer_clear_existing: Used by SHAPEKEY_OT_transfer_with_surface_deform
├── shapekey_transfer_skip_minimal: Used by SHAPEKEY_OT_transfer_with_surface_deform
├── shapekey_transfer_threshold: Used by SHAPEKEY_OT_transfer_with_surface_deform
└── shapekey_mirror_tolerance: Used by SHAPEKEY_OT_mirror, SHAPEKEY_OT_mirror_all_missing

UI Panel (SHAPEKEY_PT_manager)
├── Displays: Operators via bl_idname (shapekey.*, vertexgroup.*)
└── Displays: Scene properties
```

## Object Relationships

```
Mesh Object
├── data.shape_keys.key_blocks: Accessed by all shape key operators
└── vertex_groups: Accessed by VERTEXGROUP_OT_combine_groups

Shape Keys
├── Basis shape key: Referenced by all shape key operators as the reference
└── Other shape keys: Manipulated by operators
```

## Function Call Relationships

**In mirror_ops.py:**
```
SHAPEKEY_OT_mirror.execute()
├── detect_shape_key_side()
├── generate_mirrored_name()
├── build_mirror_vertex_mapping()
├── create_vertex_mirror_mapping()
│   └── Uses Octree from core/octree.py
└── mirror_shape_key()
```

**In transfer_ops.py:**
```
SHAPEKEY_OT_transfer_with_surface_deform.execute()
├── Sets up Surface Deform modifier
├── Binds modifier
├── For each shape key:
│   ├── calculate_deformation_amount() (if skip_minimal_effect)
│   └── Creates new shape key on target
└── Restores original state
```

## Blender API Usage

| Module | Blender API Components Used |
|--------|----------------------------|
| basic_ops.py | bpy.types.Operator, shape_keys, key_blocks, report, window_manager.fileselect_add |
| mirror_ops.py | bpy.types.Operator, shape_keys, key_blocks, report, shape_key_add |
| transfer_ops.py | bpy.types.Operator, shape_keys, modifiers, ops.object.mode_set, view_layer.update, depsgraph |
| edit_ops.py | bpy.types.Operator, bpy.ops.object.mode_set, shape_keys, key_blocks |
| vertex_group_ops.py | bpy.types.Operator, vertex_groups, add, weight, report |
| panels.py | bpy.types.Panel, layout, box, column, row, prop, operator |
| properties.py | bpy.types.Scene, FloatProperty, BoolProperty |

## Cross-File Function Usage

| Function/Class | Defined In | Used In |
|----------------|-----------|---------|
| Octree | core/octree.py | operators/mirror_ops.py |
| copied_shape_keys | __init__.py | operators/basic_ops.py |
| register_properties | utils/properties.py | __init__.py |
| SHAPEKEY_OT_* classes | operators/*.py | ui/panels.py (via bl_idname) |
| VERTEXGROUP_OT_* classes | operators/vertex_group_ops.py | ui/panels.py (via bl_idname) |

## Property References in UI

| Scene Property | Defined In | Referenced In UI |
|----------------|-----------|-----------------|
| shapekey_mirror_tolerance | utils/properties.py | ui/panels.py |
| shapekey_transfer_* properties | utils/properties.py | ui/panels.py |

## CI/CD Relationships

The GitHub Actions workflows (in the `.github/workflows` directory) automate the build, packaging, and release processes:

1. `build-package.yml` workflow:
   - Triggered on pushes to `master`/`main` and pull requests into `master`/`main`
   - Uses the `scripts/package_addon.py` script to build the addon package
   - Uploads the package as a GitHub Actions artifact

2. `release.yml` workflow:
   - Manually triggered via GitHub UI with version number and pre-release status
   - Uses the same packaging script to build the addon package
   - Creates a GitHub Release with the addon package
   - Applies appropriate version tag and description

These workflows rely on the `scripts/package_addon.py` script, which follows the package creation process defined in the packaging tools documentation.

This relationship map should help AI tools understand how the various components of the addon interact with each other. 