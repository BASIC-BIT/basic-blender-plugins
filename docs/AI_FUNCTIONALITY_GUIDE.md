# BASICs Shape Key Manager - AI Functionality Guide

This document explains the key functionality and logic flow of the BASICs Shape Key Manager addon to help AI tools understand how it works.

## Core Concepts

### Shape Keys in Blender
- Shape keys (also known as blend shapes or morph targets) define alternative vertex positions for a mesh
- The base mesh is the "Basis" shape key, and all other shape keys store deviations from it
- Each shape key has a "value" from 0.0 to 1.0 controlling how much of the deformation is applied
- Shape keys are stored in a mesh's `data.shape_keys.key_blocks` collection

### Vertex Groups in Blender
- Vertex groups are named collections of vertices with weights (0.0 to 1.0)
- Used for controlling armature deformation, modifiers, and other effects
- Stored in the object's `vertex_groups` collection

### Armatures in Blender
- Armatures are skeletal structures used to deform meshes
- Composed of bones organized in parent-child hierarchies
- Used for character animation, rigging, and deformation
- Each bone can influence mesh vertices through vertex groups

## Functionality Groups

### 1. Basic Shape Key Operations

**Copy/Cut/Paste Workflow**:
1. User selects an object with shape keys
2. Uses Copy or Cut to store shape key values in the global `copied_shape_keys` dictionary
3. Selects a different object and uses Paste to apply those values to matching shape keys

**Save/Load Workflow**:
1. User saves shape key values to a JSON file using the Save operator
2. Later loads these values using the Load operator, which restores the shape key state

### 2. Shape Key Mirroring

**Single Mirror Workflow**:
1. User selects a shape key with L/R designation (e.g., "SmileL")
2. The mirror operator detects the side using `detect_shape_key_side()`
3. Creates opposite-side shape key (e.g., "SmileR") using the mirror functions:
   - `build_mirror_vertex_mapping()` → Groups vertices by their X position (left/right/center)
   - `create_vertex_mirror_mapping()` → Creates detailed vertex mapping using Octree for efficiency
   - `mirror_shape_key()` → Creates and populates the new shape key

**Mirror All Missing Workflow**:
1. Similar to single mirror, but processes all shape keys
2. For ambiguous names (no clear L/R designation):
   - Analyzes both L→R and R→L mappings
   - Chooses mapping that produces more significant deformation

### 3. Mesh Mirroring

**Force Mirror Mesh Workflow**:
1. User selects an object (can be in Edit or Object mode)
2. The Force Mirror operator performs the following steps:
   - Determines which vertices are on left/right/center using `build_mirror_vertex_mapping()`
   - Creates vertex mappings using `create_vertex_mirror_mapping()` with Octree
   - In Edit mode: Only affects mirrors of selected vertices
   - In Object mode: Processes all vertices
   - Optionally creates a vertex group for failed vertices
   - Applies precise mirroring transformations

**Key Features**:
- Configurable tolerance for vertex matching
- Fault tolerance mode that continues even if some vertices fail
- Option to select mirrored vertices after operation
- Special handling for center vertices
- Direction control (L→R or R→L)

### 4. Shape Key Transfer

**Transfer Workflow**:
1. User selects source object (with shape keys) and target object
2. Transfer operator:
   - Applies Surface Deform modifier to target, binding it to source
   - For each shape key in source:
     - Activates it on source one at a time
     - Captures deformed vertex positions on target
     - Creates new shape key on target using those positions
   - Optionally filters out shape keys with minimal effect using `calculate_deformation_amount()`

### 5. Edit Mode Operations

**Remove Selected Vertices Workflow**:
1. User enters Edit Mode and selects vertices
2. The operator resets those vertex positions to match the Basis shape key
3. This effectively removes the influence of shape keys on those vertices

### 6. Vertex Group Operations

**Combine Groups Workflow**:
1. User selects object with vertex groups
2. Combine operator:
   - Filters groups based on lock status (locked/unlocked)
   - Accumulates weights from all selected groups for each vertex
   - Creates new vertex group with combined weights
   - Optionally normalizes weights to stay within 0.0-1.0 range

**Remove Empty Groups Workflow**:
1. User selects mesh object(s) or an armature
2. If a mesh is selected: processes that mesh
3. If an armature is selected: processes all mesh children
4. For each mesh, the operator:
   - Examines all vertex groups
   - Identifies groups with no vertices or zero weights
   - Removes these empty groups
   - Reports how many empty groups were removed from how many objects
5. This helps clean up rigs by removing unused vertex groups that can accumulate during rigging

### 7. Armature Operations

**Delete Other Bones Workflow**:
1. User selects an armature object and enters Edit Mode
2. User selects one or more bones to preserve
3. The Delete Other Bones operator:
   - Collects the selected bones to preserve
   - Identifies and preserves all parent bones up the chain to maintain hierarchy
   - Optionally preserves all child bones of selected bones (enabled by default)
   - Deletes all other bones in the armature
4. This is particularly useful for:
   - Extracting specific parts of a character (like hair) with their bone structure
   - Simplifying complex rigs by removing unnecessary bones
   - Creating focused sub-rigs for specific animations or components

**Check/Fix Armature Modifiers Workflow**:
1. User selects an armature
2. The Check/Fix Armature Modifiers operator:
   - Identifies all mesh objects parented to the armature
   - For each mesh:
     - Checks if it has exactly one armature modifier pointing to the correct armature
     - If not, removes all existing armature modifiers
     - Adds a new armature modifier configured correctly
     - Ensures the modifier is at the top of the modifier stack for best results
3. This ensures all meshes deform properly with the armature
4. Useful when:
   - Importing models with incorrect modifier setups
   - After joining or separating meshes that may have duplicate or missing modifiers
   - For batch fixing multiple character meshes at once

## Logic Diagram

```
User Input → UI Panel (panels.py) → Operator (operators/*.py) → Core Functions (core/*.py) → Blender API → 3D View Update
```

## Registration Flow

1. `__init__.py` → `register()`
2. `utils/properties.py` → `register_properties()` (registers custom scene properties)
3. `operators/__init__.py` → `register()` (registers all operator classes)
4. `ui/__init__.py` → `register()` (registers all panel classes)

## Data Flow Examples

### Shape Key Mirroring Data Flow:
```
User selects shape key → Clicks Mirror → SHAPEKEY_OT_mirror.execute() → 
detect_shape_key_side() → build_mirror_vertex_mapping() → 
create_vertex_mirror_mapping() (uses Octree) → 
mirror_shape_key() → Creates new shape key → Updates UI
```

### Mesh Mirroring Data Flow:
```
User selects mesh → Clicks Force Mirror → MESH_OT_force_mirror.execute() →
[If in Edit mode] get_selected_vertices() →
build_mirror_vertex_mapping() → create_vertex_mirror_mapping() (uses Octree) →
apply_mirror_transformation() → [If option enabled] create_failed_vertex_group() →
Updates mesh vertices → Updates UI
```

### Shape Key Transfer Data Flow:
```
User selects objects → Clicks Transfer → SHAPEKEY_OT_transfer_with_surface_deform.execute() → 
Adds Surface Deform modifier → Binds to source → 
For each shape key: Activate on source → Capture deformation on target → 
Create shape key on target → Updates UI
```

### Armature Bone Deletion Data Flow:
```
User selects armature → Enters Edit Mode → Selects bones → 
Clicks Delete Other Bones → ARMATURE_OT_delete_other_bones.execute() →
Collects selected bones → Traces parent hierarchy → 
Recursively adds children (if option enabled) → 
Identifies bones to preserve → Deletes other bones → Updates UI
```

### Armature Modifier Check/Fix Data Flow:
```
User selects armature → Clicks Check/Fix Armature Modifiers → 
ARMATURE_OT_check_fix_modifiers.execute() →
_get_child_meshes() → For each mesh: _check_and_fix_modifiers() →
[If needed] Remove existing modifiers → Add new modifier → 
Move modifier to top of stack → Updates UI
```

### Remove Empty Vertex Groups Data Flow:
```
User selects mesh or armature → Clicks Remove Empty Vertex Groups → 
VERTEXGROUP_OT_remove_empty.execute() →
[If armature selected] Collect child meshes → 
For each mesh: _remove_empty_groups() →
Check each vertex group for vertices with weight > 0 →
Remove empty groups → Updates UI
```

## Common Utility Functions

The addon now uses shared utility functions in `core/mirror_utils.py` for both shape key and mesh mirroring operations:

1. **build_mirror_vertex_mapping()**: Groups vertices as left/right/center based on X coordinate
2. **create_vertex_mirror_mapping()**: Creates a detailed mapping between vertices using Octree
3. **detect_shape_key_side()**: Analyzes name to determine L/R designation
4. **generate_mirrored_name()**: Creates an appropriate name for the mirrored element

These shared functions allow consistent behavior between mesh and shape key mirroring operations.

## CI/CD Process

### Automated Build Process

The repository includes GitHub Actions workflows that automate the build and release processes:

1. **Continuous Integration (build-package.yml)**:
   - Triggered automatically on:
     - Pushes to `master`/`main` branch
     - Pull requests into `master`/`main` branch
   - Process flow:
     - Check out repository code
     - Set up Python environment
     - Run `scripts/package_addon.py` to create the addon package
     - Upload package as a GitHub Actions artifact (available for 14 days)

2. **Release Process (release.yml)**:
   - Manually triggered workflow with inputs:
     - Version number (e.g., 1.0.0)
     - Pre-release flag (true/false)
   - Process flow:
     - Check out repository code
     - Set up Python environment
     - Run `scripts/package_addon.py` to create the addon package
     - Create a GitHub Release with:
       - Version tag (e.g., v1.0.0)
       - Release name and date
       - Installation instructions
       - Attached addon package ZIP file

These workflows utilize the same packaging script (`scripts/package_addon.py`) that's available for local use, ensuring consistency between manual and automated builds.

## Error Handling Patterns

- Most operators use `self.report({'INFO'/'WARNING'/'ERROR'}, message)` to report status
- Many operations are wrapped in try/except blocks
- Operators return `{'FINISHED'}` on success or `{'CANCELLED'}` on error

## Performance Considerations

- Octree is used for efficient spatial searching during mirroring
- Shape key transfer can be slow for complex meshes
- The addon provides options to skip shape keys with minimal effect to improve performance