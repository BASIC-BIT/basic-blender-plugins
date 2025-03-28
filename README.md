# BASICs Shape Key Manager

A powerful Blender addon that makes working with shape keys easy and efficient.

![BASICs Shape Key Manager](https://via.placeholder.com/800x400?text=BASICs+Shape+Key+Manager)

## What Can It Do?

- **Copy, cut, and paste** shape key values between objects
- **Mirror** shape keys from one side to another (L to R or R to L)
- **Transfer** shape keys between completely different meshes
- **Remove** shape key influence from selected vertices
- **Combine** vertex groups into new ones
- **Save and load** shape keys to/from files
- **Extract armature parts** by preserving selected bones and their hierarchies
- **Check and fix armature modifiers** on all meshes parented to an armature
- **Remove empty vertex groups** from meshes to clean up your rigs

## Installation

### Quick Install
1. [Download the latest release](https://github.com/BASICBIT/blender-shape-keys/releases/latest)
2. In Blender: Edit > Preferences > Add-ons > Install...
3. Select the downloaded ZIP file
4. Enable the addon by checking the box

### Manual Install
1. Download or clone this repository
2. Navigate to the `scripts` folder
3. Run `package_addon.bat` (Windows) or `package_addon.sh` (macOS/Linux)
4. Choose option 2 to package and install to Blender

## How to Use

The addon adds a "BASIC" tab in the 3D View sidebar (press N to show/hide).

### Quickly Copy Shape Keys Between Objects

1. Select an object with shape keys
2. Click "Copy Shape Key Values"
3. Select another object
4. Click "Paste Shape Key Values"

### Mirroring Made Easy

1. Select an object with shape keys named with L/R convention (e.g., "SmileL")
2. Select the shape key you want to mirror
3. Click "Mirror Shape Key"
4. A new mirrored shape key is created (e.g., "SmileR")

### Transfer Between Different Meshes

1. Select the source mesh with shape keys
2. Hold Shift and select the target mesh (so it's active)
3. Adjust transfer settings in the panel
4. Click "Execute Transfer"

### Save Your Work

1. Click "Save Shape Keys to File"
2. Choose a location to save the JSON file
3. Later, use "Load Shape Keys from File" to restore them

### Extract Armature Parts

1. Select an armature object
2. Enter Edit Mode (Tab key)
3. Select the bone(s) you want to keep (like a hair bone)
4. In the BASIC tab, find the "Armature Operations" section
5. Click "Delete Other Bones"
6. This preserves the selected bones, their parent chains, and their children while removing all other bones

### Fix Armature Modifiers

1. Select an armature object
2. In the BASIC tab, find the "Armature Operations" section
3. Click "Check/Fix Armature Modifiers"
4. All meshes parented to the armature will be checked and fixed to ensure they have exactly one correctly configured armature modifier

### Remove Empty Vertex Groups

1. Select a mesh (or multiple meshes) to clean up its vertex groups
   OR
   Select an armature to clean up all its child meshes
2. In the BASIC tab, find the "Vertex Group Operations" section
3. Click "Remove Empty Vertex Groups"
4. All vertex groups with no assigned vertices (or zero weights) will be removed

## Requirements

- Blender 4.3 or higher
- Python 3.6+ (for packaging scripts)

## Tips for Best Results

- When transferring shape keys, ensure the source mesh completely surrounds the target
- For mirroring, use consistent naming conventions (SmileL/SmileR, Smile.L/Smile.R)
- Use "Skip Non-Effective Shape Keys" option to avoid creating unnecessary shape keys
- When extracting armature parts, select the highest bone in the chain you want to preserve
- Run the "Check/Fix Armature Modifiers" operation after importing or joining meshes to ensure proper deformation
- Use "Remove Empty Vertex Groups" periodically during rigging to keep your rig clean and efficient

## Need More?

Check out the documentation files in the `docs` folder for detailed information on each feature:
- `docs/AI_CODEBASE_MAP.md` - Overview of the codebase structure
- `docs/AI_FUNCTIONALITY_GUIDE.md` - Detailed functionality explanation
- `docs/AI_RELATIONSHIP_MAP.md` - Component relationship documentation

## Credits

Created by BASICBIT

## Random stuff to do

- Make the mirroring vertex functionality move the vertexes to the average center point instead of moving one to the other's mirrored position
- Fix release script
- Confirm functionality of mirroring code (both original blendshape mirroring and new vertex mirroring)