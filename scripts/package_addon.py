#!/usr/bin/env python3
import os
import zipfile
import shutil
import argparse
import platform
import sys
from pathlib import Path
import subprocess

def get_blender_addons_path(blender_version):
    """Get the path to Blender's addons directory based on the OS and version."""
    system = platform.system()
    addon_path = None
    
    if system == "Windows":
        # Windows: %APPDATA%\Blender Foundation\Blender\[version]\scripts\addons
        appdata = os.environ.get("APPDATA")
        if appdata:
            addon_path = Path(appdata) / "Blender Foundation" / "Blender" / blender_version / "scripts" / "addons"
    
    elif system == "Darwin":  # macOS
        # macOS: /Users/[user]/Library/Application Support/Blender/[version]/scripts/addons
        user_home = Path.home()
        addon_path = user_home / "Library" / "Application Support" / "Blender" / blender_version / "scripts" / "addons"
    
    elif system == "Linux":
        # Linux: ~/.config/blender/[version]/scripts/addons
        user_home = Path.home()
        addon_path = user_home / ".config" / "blender" / blender_version / "scripts" / "addons"
    
    return addon_path

def create_zip(source_dir, output_file):
    """Create a zip file from a directory."""
    print(f"Creating zip file: {output_file}")
    
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Walk through the directory
        for root, _, files in os.walk(source_dir):
            for file in files:
                # Calculate path for file in zip
                file_path = os.path.join(root, file)
                
                # Calculate the relative path (we don't want the full path in the zip)
                rel_path = os.path.relpath(file_path, os.path.dirname(source_dir))
                
                # Add file to zip
                zipf.write(file_path, rel_path)
                print(f"Added: {rel_path}")
    
    return output_file

def install_to_blender(zip_file, blender_version, blender_executable=None):
    """Install the addon to Blender."""
    addon_dir = get_blender_addons_path(blender_version)
    
    if not addon_dir:
        print(f"Could not determine Blender addons directory for version {blender_version}")
        return False
    
    if not addon_dir.exists():
        print(f"Creating Blender addons directory: {addon_dir}")
        addon_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Installing addon to: {addon_dir}")
    
    # Extract zip file to the addons directory
    with zipfile.ZipFile(zip_file, 'r') as zip_ref:
        zip_ref.extractall(addon_dir)
    
    print("Addon installed successfully!")
    
    # Try to enable the addon automatically if blender_executable is provided
    if blender_executable:
        try:
            # Create a temporary Python script to enable the addon
            temp_script = "temp_enable_addon.py"
            with open(temp_script, 'w') as f:
                f.write("""
import bpy
# Enable the addon
bpy.ops.preferences.addon_enable(module="BASICs_shape_key_manager")
# Save user preferences
bpy.ops.wm.save_userpref()
""")
            
            # Run Blender with the script
            subprocess.run([blender_executable, "--background", "--python", temp_script])
            
            # Clean up the temporary script
            os.remove(temp_script)
            print("Addon enabled in Blender preferences")
            
        except Exception as e:
            print(f"Could not automatically enable the addon: {e}")
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Package and install BASICs Shape Key Manager addon')
    parser.add_argument('--install', action='store_true', help='Install the addon to Blender')
    parser.add_argument('--blender-version', type=str, help='Blender version (e.g., 4.3)')
    parser.add_argument('--blender-exe', type=str, help='Path to Blender executable (optional, for auto-enabling)')
    
    args = parser.parse_args()
    
    # Get the directory of this script
    script_dir = Path(__file__).parent.parent.resolve()
    
    # Source directory (the addon)
    source_dir = script_dir / "BASICs_shape_key_manager"
    
    # Output zip file
    output_file = script_dir / "BASICs_shape_key_manager.zip"
    
    # Check if source directory exists
    if not source_dir.exists():
        print(f"Error: Source directory not found: {source_dir}")
        return 1
    
    # Create the zip file
    zip_file = create_zip(source_dir, output_file)
    print(f"Zip file created: {output_file}")
    
    # Install to Blender if requested
    if args.install:
        if not args.blender_version:
            print("Error: Blender version is required for installation (use --blender-version)")
            return 1
        
        success = install_to_blender(zip_file, args.blender_version, args.blender_exe)
        if not success:
            print("Installation failed")
            return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 