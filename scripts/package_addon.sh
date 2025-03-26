#!/bin/bash

echo "BASICs Shape Key Manager - Packaging Tool"
echo "========================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH."
    echo "Please install Python from https://www.python.org/downloads/"
    exit 1
fi

# Make this script executable if it's not already
if [ ! -x "$0" ]; then
    chmod +x "$0"
fi

show_menu() {
    clear
    echo "What would you like to do?"
    echo ""
    echo "1) Just package the addon to ZIP"
    echo "2) Package and install to Blender"
    echo "3) Exit"
    echo ""
    read -p "Enter your choice (1-3): " choice
    
    case $choice in
        1)
            python3 package_addon.py
            echo ""
            echo "Done. Press Enter to return to the menu..."
            read
            show_menu
            ;;
        2)
            echo ""
            read -p "Enter Blender version (e.g., 4.3): " blender_version
            echo ""
            read -p "Enter path to Blender executable (optional, leave empty to skip): " blender_exe
            
            if [ -z "$blender_exe" ]; then
                python3 package_addon.py --install --blender-version="$blender_version"
            else
                python3 package_addon.py --install --blender-version="$blender_version" --blender-exe="$blender_exe"
            fi
            
            echo ""
            echo "Done. Press Enter to return to the menu..."
            read
            show_menu
            ;;
        3)
            exit 0
            ;;
        *)
            echo "Invalid choice. Press Enter to try again..."
            read
            show_menu
            ;;
    esac
}

show_menu 