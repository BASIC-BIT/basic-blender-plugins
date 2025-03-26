# BASICs Shape Key Manager - Packaging Tools

This directory contains scripts to help you package and install the BASICs Shape Key Manager addon for Blender.

## Included Scripts

- `package_addon.py` - The main Python script that handles packaging and installation
- `package_addon.bat` - Windows batch script with a user-friendly menu
- `package_addon.sh` - Shell script for macOS and Linux with a user-friendly menu

## Requirements

- Python 3.6 or higher

## Usage

### On Windows

1. Double-click on `package_addon.bat` to run the menu-driven interface
2. Choose one of the options:
   - **Option 1**: Just create a ZIP file of the addon
   - **Option 2**: Create a ZIP file and install it to your Blender installation
   - **Option 3**: Exit

If you choose option 2, you will need to provide:
- The Blender version (e.g., "4.3")
- Optionally, the path to the Blender executable (to automatically enable the addon)

### On macOS/Linux

1. Open Terminal in this directory
2. Make the shell script executable if it's not already:
   ```
   chmod +x package_addon.sh
   ```
3. Run the script:
   ```
   ./package_addon.sh
   ```
4. The menu options are the same as in the Windows version

### Running the Python Script Directly

You can also run the Python script directly with command-line arguments:

```
# Just create the ZIP file
python package_addon.py

# Create ZIP and install to Blender
python package_addon.py --install --blender-version=4.3

# Create ZIP, install to Blender, and enable the addon
python package_addon.py --install --blender-version=4.3 --blender-exe="C:\Program Files\Blender Foundation\Blender 4.3\blender.exe"
```

## Installation Paths

The script will install the addon to the standard Blender addon directory for your platform:

- **Windows**: `%APPDATA%\Blender Foundation\Blender\[version]\scripts\addons`
- **macOS**: `/Users/[user]/Library/Application Support/Blender/[version]/scripts/addons`
- **Linux**: `~/.config/blender/[version]/scripts/addons`

## Troubleshooting

If you encounter any issues:

1. Make sure Python 3 is installed and in your PATH
2. Verify that you have the correct Blender version
3. Make sure you have write permissions to the Blender addons directory
4. For automatic addon enabling, ensure the Blender executable path is correct

If the addon doesn't appear in Blender after installation, try:
1. Restart Blender
2. In Blender, go to Edit > Preferences > Add-ons
3. Search for "BASICs Shape Key Manager"
4. Enable the addon manually 

## GitHub Actions Workflows

The project includes automated build and release processes using GitHub Actions:

### Automated Builds

The `build-package.yml` workflow automatically builds the addon package:
- Triggered on pushes to `master`/`main` and pull requests into `master`/`main`
- Packages the addon using the `package_addon.py` script
- Uploads the package as a GitHub Actions artifact
- Artifacts are available for 14 days

To access the artifacts:
1. Go to the Actions tab in your GitHub repository
2. Select the workflow run
3. Scroll down to the Artifacts section
4. Download the BASICs_shape_key_manager.zip file

### Release Process

The `release.yml` workflow creates official GitHub releases:
- Manually triggered through the GitHub UI
- Requires specifying a version number (e.g., 1.0.0)
- Option to mark as pre-release
- Creates a GitHub Release with appropriate tag (e.g., v1.0.0)
- Attaches the addon package to the release

To create a release:
1. Go to the Actions tab in your GitHub repository
2. Select the "Create Release" workflow
3. Click "Run workflow"
4. Enter the version number and select pre-release status
5. Click "Run workflow" to start the process

## Related Documentation

For more information about the project structure and functionality, refer to these documentation files:
- `docs/AI_CODEBASE_MAP.md` - Overview of the codebase structure
- `docs/AI_FUNCTIONALITY_GUIDE.md` - Detailed functionality explanation
- `docs/AI_RELATIONSHIP_MAP.md` - Component relationship documentation 