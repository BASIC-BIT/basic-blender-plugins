# BASICs Shape Key Manager - AI Codebase Map

This document provides a structural overview of the BASICs Shape Key Manager addon for Blender, designed to help AI tools understand the codebase organization.

## Directory Structure

```
BASICs_shape_key_manager/
├── README.md                    # General addon documentation
├── __init__.py                  # Main addon entry point, with bl_info
├── core/                        # Core functionality
│   ├── __init__.py              # Exports core components
│   ├── mirror_utils.py          # Common mirroring utility functions
│   ├── octree.py                # Octree implementation for spatial searching
│   ├── polyloop_reduction.py    # bpy-free edge-loop tracing + scoring
│   ├── polyloop_dissolve.py     # bpy-free loop dissolve + iterate-to-target
│   ├── shape_key_remap.py       # bpy-free shape-key remap across destructive rebuilds
│   └── vertex_group_utils.py    # bpy-free vertex group snapshot/protection helpers
├── operators/                   # Blender operators
│   ├── __init__.py              # Registers all operators
│   ├── basic_ops.py             # Basic shape key operations (copy/cut/paste)
│   ├── edit_ops.py              # Edit mode operations
│   ├── mirror_ops.py            # Shape key mirroring functions
│   ├── mesh_mirror_ops.py       # Mesh mirroring functions
│   ├── polyloop_ops.py          # Polyloop preview/dissolve/reduce operator glue
│   ├── smooth_ops.py            # Heuristic blendshape smoothing
│   ├── transfer_ops.py          # Shape key transfer between objects
│   ├── armature_ops.py          # Armature editing operations
│   └── vertex_group_ops.py      # Vertex group operations
├── ui/                          # User interface components
│   ├── __init__.py              # Registers UI elements
│   └── panels.py                # Main panel definition
└── utils/                       # Utility functions
    ├── __init__.py              # Exports utility functions
    └── properties.py            # Property definitions and registration
```

## Repository Structure (Outside the addon)

```
/
├── BASICs_shape_key_manager/    # Addon directory (as above)
├── scripts/                     # Packaging and installation scripts
│   ├── package_addon.py         # Python script for packaging and installing
│   ├── package_addon.bat        # Windows batch script interface
│   ├── package_addon.sh         # Shell script interface for macOS/Linux
│   └── PACKAGING_README.md      # Documentation for packaging tools
├── .github/                     # GitHub specific configuration
│   └── workflows/               # GitHub Actions workflows
│       ├── build-package.yml    # Auto-build workflow for commits and PRs
│       └── release.yml          # Manual release workflow
├── docs/                        # Documentation directory
│   ├── AI_CODEBASE_MAP.md       # This document
│   ├── AI_FUNCTIONALITY_GUIDE.md # Detailed functionality guide
│   ├── AI_RELATIONSHIP_MAP.md   # Component relationship mapping
│   └── prompt_plans/            # Implementation plans
│       └── force_mirror_mesh_implementation_plan.md # Plan for mesh mirroring feature
└── README.md                    # Main repository documentation
```

## File Contents

### __init__.py (Main)
- **Purpose**: Main entry point for the addon
- **Key Components**:
  - `bl_info`: Addon metadata (version, name, etc.)
  - `copied_shape_keys`: Global dictionary to store copied shape keys
  - `register()`: Registers all addon components
  - `unregister()`: Unregisters all addon components

### core/octree.py
- **Purpose**: Implements an Octree data structure for efficient 3D point searching
- **Key Classes**:
  - `OctreeNode`: Represents a node in the octree
  - `Octree`: Wrapper class for easy octree usage
- **Main Functions**:
  - `find_nearest()`: Find nearest point in 3D space

### core/mirror_utils.py
- **Purpose**: Common utility functions for mirroring operations
- **Main Functions**:
  - `detect_shape_key_side()`: Detects if a name has L/R designation
  - `generate_mirrored_name()`: Creates appropriate name for mirrored objects
  - `build_mirror_vertex_mapping()`: Maps vertices to left/right/center
  - `create_vertex_mirror_mapping()`: Creates detailed vertex mapping with octree

### operators/basic_ops.py
- **Purpose**: Basic shape key manipulation operators
- **Key Classes**:
  - `SHAPEKEY_OT_copy`: Copies shape key values
  - `SHAPEKEY_OT_cut`: Cuts (copies and zeros) shape key values
  - `SHAPEKEY_OT_paste`: Pastes shape key values
  - `SHAPEKEY_OT_save`: Saves shape key values to a JSON file
  - `SHAPEKEY_OT_load`: Loads shape key values from a JSON file

### operators/mirror_ops.py
- **Purpose**: Shape key mirroring functionality
- **Key Classes**:
  - `SHAPEKEY_OT_mirror`: Mirrors a single shape key
  - `SHAPEKEY_OT_mirror_all_missing`: Mirrors all shape keys missing counterparts
- **Helper Functions**:
  - `mirror_shape_key()`: Performs the actual mirroring operation

### operators/mesh_mirror_ops.py
- **Purpose**: Mesh mirroring functionality
- **Key Classes**:
  - `MESH_OT_force_mirror`: Forces symmetry in mesh by mirroring vertices
- **Helper Functions**:
  - `get_selected_vertices()`: Gets selected vertices in edit mode
  - `find_mirrors_of_selected()`: Maps selected vertices to their mirrors
  - `apply_mirror_transformation()`: Applies mirroring to vertices
  - `handle_center_vertices()`: Special handling for vertices near the center
  - `create_failed_vertex_group()`: Creates vertex group for vertices that couldn't be mirrored

### operators/transfer_ops.py
- **Purpose**: Transfer shape keys between objects
- **Key Classes**:
  - `SHAPEKEY_OT_transfer_with_surface_deform`: Transfers shape keys using Blender's Surface Deform modifier
- **Main Functions**:
  - `calculate_deformation_amount()`: Calculates mesh deformation metrics
- **Safety**: Protected vertex groups (outfit-only/locked/keep-prefix, see `core/vertex_group_utils.py`) are snapshotted before the pre-bind vertex group clear and restored on EVERY exit path via `try`/`finally` (bind failure, unhandled errors mid-transfer, and normal completion)

### core/shape_key_remap.py
- **Purpose**: bpy-free shape-key remap math for destructive mesh rebuilds (stage-4 shape-key-aware reduction; see `docs/molt_design.md` section 2.6)
- **Key Classes**:
  - `ShapeKeyRemapError`: raised on inconsistent inputs (coordinate-count mismatch, empty/out-of-range source lists)
- **Main Functions**:
  - `remap_shape_keys()`: carries every shape key's absolute per-vertex coordinates through a vertex mapping; singleton sources copy exactly (survivors), multi-source entries average (merges, preserving relative-key deltas by linearity)
  - `sources_from_vertex_remap()`: builds the survivor (singleton) source lists from the dissolve's `{old: new}` index remap
- **Tested by**: `tests/test_shape_key_remap.py` (bpy-free; identity/removal/merge/relative-chain/validation cases)

### operators/polyloop_ops.py
- **Purpose**: Thin Blender glue for the tested polyloop core (no topology math here)
- **Key Classes**:
  - `MESH_OT_preview_polyloop_reduction`: Selects best-scoring loop candidates (non-destructive)
  - `MESH_OT_dissolve_polyloop_candidate`: Dissolves the single safest loop (destructive rebuild)
  - `MESH_OT_reduce_polyloop_to_target`: Iteratively dissolves loops to a target face count (destructive rebuild)
- **Helper Functions**:
  - `_mesh_to_tuples()` / `_write_tuples_to_mesh()`: bpy <-> tuple-mesh mirror; weights AND shape keys are ALWAYS collected, threaded through the core dissolve, and reapplied/recreated after the rebuild
  - `_collect_shape_key_state()` / `_apply_shape_key_state()`: snapshot key blocks (absolute coordinates + metadata + mesh-level state) into the bpy-free representation and recreate them on the rebuilt mesh (original order, relative-key links by name, slider ranges restored before values)
  - `_destructive_rebuild_blockers()` / `_refuse_unpreservable_data()`: guard the `clear_geometry()`/`from_pydata` rebuild — relative shape keys are now preserved (not refused); hard-refuse remains only for absolute (non-relative) shape keys and animation data (drivers/keyframes) on the shape-key datablock; UV maps, color attributes, and multi-material face assignments block unless the user enables the `allow_attribute_loss` toggle
- **Tested by**: `tests/test_polyloop_ops_shape_keys.py` (bpy-stubbed harness for the guards and shape-key snapshot/rebuild glue)

### operators/edit_ops.py
- **Purpose**: Edit mode operations for shape keys
- **Key Classes**:
  - `SHAPEKEY_OT_remove_selected_vertices`: Removes selected vertices from shape keys

### operators/armature_ops.py
- **Purpose**: Armature editing operations
- **Key Classes**:
  - `ARMATURE_OT_delete_other_bones`: Deletes all bones except selected ones and their hierarchy
  - `ARMATURE_OT_check_fix_modifiers`: Ensures all meshes parented to an armature have exactly one correctly configured armature modifier
- **Helper Functions**:
  - `add_children_recursive()`: Recursively collects child bones to preserve
  - `_get_child_meshes()`: Gets all mesh objects parented to an armature
  - `_check_and_fix_modifiers()`: Checks and fixes armature modifiers on a mesh

### operators/vertex_group_ops.py
- **Purpose**: Vertex group operations
- **Key Classes**:
  - `VERTEXGROUP_OT_combine_groups`: Combines multiple vertex groups
  - `VERTEXGROUP_OT_remove_empty`: Removes empty vertex groups from meshes
- **Helper Functions**:
  - `_remove_empty_groups()`: Identifies and removes vertex groups with no weights

### ui/panels.py
- **Purpose**: Defines the addon's user interface
- **Key Classes**:
  - `SHAPEKEY_PT_manager`: Main panel in the 3D view sidebar

### utils/properties.py
- **Purpose**: Property definitions and registration
- **Key Functions**:
  - `register_properties()`: Registers addon properties
  - `unregister_properties()`: Unregisters addon properties

## Key Relationships
- The main `__init__.py` imports and registers all components
- `operators/__init__.py` collects and registers all operators
- `ui/panels.py` references operator IDs (bl_idname) to create UI buttons
- `mirror_ops.py` and `mesh_mirror_ops.py` use the common functions from `core/mirror_utils.py`
- Both mirroring modules use the Octree from `core/octree.py` for efficient vertex mapping

## Global Data
- `copied_shape_keys`: Dictionary in main `__init__.py` that stores copied shape key data

## Packaging Scripts (Outside the addon)
- `scripts/package_addon.py`: Python script for packaging and installing
- `scripts/package_addon.bat`: Windows batch script interface
- `scripts/package_addon.sh`: Shell script interface for macOS/Linux
- `scripts/PACKAGING_README.md`: Documentation for the packaging tools