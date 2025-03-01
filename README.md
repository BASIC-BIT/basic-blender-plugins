# Shape Key Manager

A Blender addon for managing, transferring, and manipulating shape keys (blend shapes) across meshes.

## Features

### Basic Operations
- **Copy Shape Keys**: Copy all shape key values from the active object
- **Cut Shape Keys**: Copy all shape key values and set them to zero
- **Paste Shape Keys**: Apply copied shape key values to the active object
- **Save to File**: Save shape key values to a JSON file for backup or sharing
- **Load from File**: Load shape key values from a JSON file

### Advanced Operations
- **Transfer Shape Keys via Surface Deform**: Transfer shape keys between meshes with different topologies using Blender's Surface Deform modifier
- **Smart Shape Key Filtering**: Automatically skip shape keys that don't meaningfully affect the target mesh

## Requirements
- Blender 4.3 or higher

## Installation

1. Download the `blender_copy_paste_shape_keys.py` file
2. Open Blender
3. Go to Edit > Preferences > Add-ons
4. Click "Install..." and select the downloaded file
5. Enable the addon by checking the box next to "Mesh: Shape Key Manager"

## Usage

### Basic Operations

The addon adds a new panel in the 3D View sidebar (press `N` to open) under the "Shape Keys" tab.

#### Copying and Pasting Shape Key Values

1. Select an object with shape keys
2. Click "Copy Shape Key Values" to store the current values
3. Select a different object that has the same shape key names
4. Click "Paste Shape Key Values" to apply the copied values

#### Cutting Shape Key Values

1. Select an object with shape keys
2. Click "Cut Shape Key Values" to copy the current values and set them to zero

#### Saving and Loading Shape Key Values

1. Click "Save Shape Keys to File" to export values to a JSON file
2. Click "Load Shape Keys from File" to import values from a previously saved file

### Advanced Operations

#### Transferring Shape Keys Between Different Meshes

This feature allows you to transfer shape keys from one mesh to another, even if they have completely different topologies:

1. Select the source mesh with shape keys you want to transfer
2. While holding Shift, select the target mesh (making it the active object with yellow outline)
3. Click "Transfer Shape Keys (Surface Deform)" in the Advanced Operations section
4. Configure the options:
   - **Shape Key Strength**: Adjusts the intensity of the transferred shape keys (default: 1.0)
   - **Clear Existing Shape Keys**: Remove existing shape keys on target before transfer
   - **Skip Non-Effective Shape Keys**: Only create shape keys that actually deform the target mesh
   - **Deformation Threshold**: Minimum vertex displacement (in Blender units) required to keep a shape key
5. Click "OK" to begin the transfer process

The addon will:
- Add a Surface Deform modifier to the target mesh
- Bind it to the source mesh
- For each shape key on the source:
  - Activate one shape key at maximum value
  - Measure how much the target mesh actually deforms
  - Skip shape keys that don't produce significant deformation (if enabled)
  - Create a corresponding shape key on the target for those that do have an effect
  - Name it to match the source shape key
- Clean up by removing the modifier when finished

## Tips and Troubleshooting

- **Intelligent Shape Key Filtering**: When transferring shape keys from a full body to clothing, enable "Skip Non-Effective Shape Keys" to automatically filter out irrelevant shape keys (e.g., leg shape keys won't affect a shirt).
- **Adjusting Threshold**: If too many shape keys are being skipped, try lowering the deformation threshold. If unnecessary shape keys are being created, increase the threshold.
- **Shape Key Transfer**: The source mesh should completely envelop the target mesh for best results.
- **Surface Deform Error**: If binding fails, try:
  - Moving the meshes closer together
  - Reducing mesh complexity
  - Ensuring meshes don't have non-manifold geometry
- **Performance**: For meshes with many vertices, the transfer process may take some time.
- **Undo Support**: All operations that modify mesh data support undo (Ctrl+Z).

## Notes on Shape Key Transfer

The Surface Deform transfer method works best when:
- The source mesh has clean topology
- The meshes are in similar poses
- The target mesh is fully contained within the source mesh's volume

## Version History

- 1.0: Initial release
  - Basic copy, cut, paste, save, and load functionality
  - Shape key transfer via Surface Deform
  - Smart filtering of non-effective shape keys during transfer

## License

This addon is free to use and modify.

## Credits

Created by AI Assistant 