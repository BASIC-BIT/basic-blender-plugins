# Force Mirror Mesh Implementation Plan

## Overview
This feature will implement a mesh mirroring operation that forces vertices to be perfectly mirrored even when they're slightly misaligned. It will use the existing octree implementation to find corresponding vertices across the X-axis and ensure precise mirroring.

## Core Components

1. **New Operator Class**: `MESH_OT_force_mirror`
   - Main tolerance parameter for vertex matching
   - Center tolerance parameter for near-center vertices
   - Fault tolerance mode toggle
   - Option to create vertex group for failed vertices
   - Option to select mirrored vertices upon completion

2. **Key Operation Logic**:
   - In Edit mode: Find and adjust mirrors of selected vertices (not the selected vertices themselves)
   - In Object mode: Process all vertices (or optionally limit to specific vertex groups)

3. **Advanced Settings**:
   - Option to move near-center vertices exactly to X=0
   - Configurable threshold for what's considered "center"

## Implementation Structure

```python
class MESH_OT_force_mirror(Operator):
    bl_idname = "mesh.force_mirror"
    bl_label = "Force Mirror Mesh"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Main parameters
    mirror_tolerance: FloatProperty(...)
    fault_tolerant: BoolProperty(...)
    create_failed_group: BoolProperty(...)
    select_mirrored: BoolProperty(...)
    
    # Advanced parameters
    center_tolerance: FloatProperty(...)
    move_to_center: BoolProperty(...)
```

## UI Organization

To address usability concerns with many options:
- Display only the most critical options by default
- Add an "Advanced Settings" collapsible section for less common options
- Provide clear tooltips for all parameters

## Function Flow

1. Classify vertices (left/right/center based on X coordinate)
2. If in Edit mode, identify selected vertices
3. Build mirror mapping using octree for efficient vertex pairing
4. Apply precise mirroring transformations to the appropriate vertices
5. Handle failed vertices (create vertex group if requested)
6. Update selection if requested

## Implementation Notes

- Will reuse significant portions of the existing octree and mirror mapping code
- Vertex group for failed vertices will be named "Mirror_Failed_Vertices"
- Statistical reporting will include total vertices processed and success/failure counts
- Should preserve vertex selection after operation
- In Edit mode, will affect mirrors of selected vertices, not the selected vertices themselves

## Detailed Implementation Plan

### File Changes Required

1. **New File**: `BASICs_shape_key_manager/operators/mesh_mirror_ops.py`
   - Will contain the new `MESH_OT_force_mirror` operator
   - Will share utility functions with `mirror_ops.py` or duplicate relevant functions

2. **Update**: `BASICs_shape_key_manager/operators/__init__.py`
   - Import and register the new operator class
   - Add to the `classes` tuple for registration

3. **Update**: `BASICs_shape_key_manager/ui/panels.py`
   - Add new section in UI for mesh operations or extend existing vertex group operations section
   - Add UI controls for the new operator

4. **Update**: `BASICs_shape_key_manager/utils/properties.py`
   - Add global settings for mesh mirror tolerance if needed
   - Potentially add separate settings from the shape key mirror tolerance

### Code Reuse

1. **From `mirror_ops.py`**:
   - `build_mirror_vertex_mapping()` - Reuse to classify vertices as left/right/center
   - `create_vertex_mirror_mapping()` - Adapt to create the detailed vertex mappings

2. **From `core/octree.py`**:
   - Use the existing `Octree` class for efficient spatial searching

3. **From `vertex_group_ops.py`**:
   - Similar patterns for creating and managing vertex groups

### New Functionality

1. **Vertex Selection Handling**:
   ```python
   # Pseudocode for vertex selection handling
   def get_selected_vertices(mesh):
       """Get indices of selected vertices in edit mode"""
       selected_verts = []
       for v in mesh.vertices:
           if v.select:
               selected_verts.append(v.index)
       return selected_verts
   
   def find_mirrors_of_selected(selected_verts, reverse_map):
       """Find the mirror vertices of selected vertices"""
       mirror_verts = []
       for v_idx in selected_verts:
           mirror_idx = reverse_map.get(v_idx)
           if mirror_idx is not None:
               mirror_verts.append(mirror_idx)
       return mirror_verts
   ```

2. **Apply Mirror Transformation**:
   ```python
   # Pseudocode for applying mirror transformation
   def apply_mirror_transformation(mesh, mirror_map):
       """Apply precise mirroring to vertices based on mapping"""
       for src_idx, tgt_idx in mirror_map.items():
           src_co = mesh.vertices[src_idx].co
           # Mirror coordinates (flip X)
           mirrored_co = (-src_co.x, src_co.y, src_co.z)
           # Apply to target vertex
           mesh.vertices[tgt_idx].co.x = mirrored_co[0]
           mesh.vertices[tgt_idx].co.y = mirrored_co[1]
           mesh.vertices[tgt_idx].co.z = mirrored_co[2]
   ```

3. **Center Vertex Handling**:
   ```python
   # Pseudocode for handling center vertices
   def handle_center_vertices(mesh, center_vertices, move_to_center):
       """Process vertices near the center line"""
       if move_to_center:
           for v_idx in center_vertices:
               # Force vertex exactly to center (X=0)
               mesh.vertices[v_idx].co.x = 0.0
   ```

4. **Failed Vertex Group Creation**:
   ```python
   # Pseudocode for creating failed vertex group
   def create_failed_vertex_group(obj, failed_vertices):
       """Create a vertex group containing vertices that couldn't be mirrored"""
       group_name = "Mirror_Failed_Vertices"
       # Remove existing group if it exists
       if group_name in obj.vertex_groups:
           vg = obj.vertex_groups[group_name]
           obj.vertex_groups.remove(vg)
       
       # Create new group
       vg = obj.vertex_groups.new(name=group_name)
       for v_idx in failed_vertices:
           vg.add([v_idx], 1.0, 'REPLACE')
   ```

### Integration with Blender UI

The new operator will be added to the BASIC panel in the 3D View sidebar:

```python
# Add to panels.py
# In an appropriate section of the SHAPEKEY_PT_manager.draw method

# Mesh Operations section
box = layout.box()
box.label(text="Mesh Operations")

col = box.column(align=True)
row = col.row()
row.operator("mesh.force_mirror")

# Additional UI for advanced settings
if context.scene.get("mesh_mirror_show_advanced", False):
    col.prop(context.scene, "mesh_mirror_show_advanced", toggle=True, text="Hide Advanced")
    
    # Show advanced options
    row = col.row()
    row.prop(context.scene, "mesh_mirror_center_tolerance")
    row = col.row()
    row.prop(context.scene, "mesh_mirror_move_center_vertices")
else:
    col.prop(context.scene, "mesh_mirror_show_advanced", toggle=True, text="Show Advanced")
```

### Testing Strategy

1. **Basic Functionality**:
   - Test on symmetrical meshes with slight deviations
   - Verify vertices are correctly mirrored

2. **Edit Mode Selection**:
   - Test with various vertex selections
   - Verify only mirrors of selected vertices are affected

3. **Center Vertex Handling**:
   - Test with vertices near the center
   - Verify they're handled correctly based on settings

4. **Error Handling**:
   - Test with non-mirrored meshes to verify fault tolerance works
   - Test failed vertex group creation

5. **UI Integration**:
   - Verify all parameters are accessible in UI
   - Test advanced settings toggle

### Performance Considerations

- For large meshes, building the octree could be time-consuming
- Consider limiting processing to selected vertices and their mirrors
- Potentially add a progress indicator for large operations 