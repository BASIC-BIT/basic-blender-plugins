# BASICs Shape Key Manager - AI Codebase Map

This document provides a structural overview of the BASICs Shape Key Manager addon for Blender, designed to help AI tools understand the codebase organization.

## Directory Structure

```
BASICs_shape_key_manager/
├── README.md                    # General addon documentation
├── __init__.py                  # Main addon entry point, with bl_info
├── core/                        # Core functionality
│   ├── __init__.py              # Exports core components
│   └── octree.py                # Octree implementation for spatial searching
├── operators/                   # Blender operators
│   ├── __init__.py              # Registers all operators
│   ├── basic_ops.py             # Basic shape key operations (copy/cut/paste)
│   ├── edit_ops.py              # Edit mode operations
│   ├── mirror_ops.py            # Shape key mirroring functions
│   ├── transfer_ops.py          # Shape key transfer between objects
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
│   └── AI_RELATIONSHIP_MAP.md   # Component relationship mapping
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
  - `detect_shape_key_side()`: Detects if a shape key is for left or right side
  - `generate_mirrored_name()`: Generates appropriate name for mirrored shape key
  - `build_mirror_vertex_mapping()`: Creates mapping between vertices for mirroring
  - `create_vertex_mirror_mapping()`: Detailed vertex mapping with octree
  - `mirror_shape_key()`: Performs the actual mirroring operation

### operators/transfer_ops.py
- **Purpose**: Transfer shape keys between objects
- **Key Classes**:
  - `SHAPEKEY_OT_transfer_with_surface_deform`: Transfers shape keys using Blender's Surface Deform modifier
- **Main Functions**:
  - `calculate_deformation_amount()`: Calculates mesh deformation metrics

### operators/edit_ops.py
- **Purpose**: Edit mode operations for shape keys
- **Key Classes**:
  - `SHAPEKEY_OT_remove_selected_vertices`: Removes selected vertices from shape keys

### operators/vertex_group_ops.py
- **Purpose**: Vertex group operations
- **Key Classes**:
  - `VERTEXGROUP_OT_combine_groups`: Combines multiple vertex groups

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
- `mirror_ops.py` uses the Octree from `core/octree.py` for efficient vertex mapping

## Global Data
- `copied_shape_keys`: Dictionary in main `__init__.py` that stores copied shape key data

## Packaging Scripts (Outside the addon)
- `scripts/package_addon.py`: Python script for packaging and installing
- `scripts/package_addon.bat`: Windows batch script interface
- `scripts/package_addon.sh`: Shell script interface for macOS/Linux
- `scripts/PACKAGING_README.md`: Documentation for the packaging tools 