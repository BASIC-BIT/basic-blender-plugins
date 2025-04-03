#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import codecs
import re

def clean_content(content):
    """Clean the content by removing null bytes and fixing common encoding issues."""
    # Remove null bytes
    content = content.replace('\0', '')
    
    # Replace common problematic characters
    replacements = {
        '\ufffd': '',  # Remove replacement characters (U+FFFD)
        '\u2018': "'",  # Smart single quote
        '\u2019': "'",  # Smart single quote
        '\u201c': '"',  # Smart double quote
        '\u201d': '"',  # Smart double quote
        '\u2013': '-',  # En dash
        '\u2014': '--',  # Em dash
        '\u2026': '...',  # Ellipsis
        '\u00a0': ' ',  # Non-breaking space
        '\u00ad': '',  # Soft hyphen
        '\u00ae': '(R)',  # Registered trademark
        '\u00b0': 'deg',  # Degree sign
        '\u00b1': '+/-',  # Plus-minus sign
        '\u00b2': '^2',  # Superscript two
        '\u00b3': '^3',  # Superscript three
        '\u00b4': "'",  # Acute accent
        '\u00b5': 'u',  # Micro sign
        '\u00b6': 'P',  # Pilcrow sign
        '\u00b7': '*',  # Middle dot
        '\u00b8': '',  # Spacing cedilla
        '\u00b9': '^1',  # Superscript one
        '\u00ba': 'o',  # Masculine ordinal indicator
        '\u00bb': '>>',  # Right-pointing double angle quotation mark
        '\u00bc': '1/4',  # Vulgar fraction one quarter
        '\u00bd': '1/2',  # Vulgar fraction one half
        '\u00be': '3/4',  # Vulgar fraction three quarters
        '\u00bf': '?',  # Inverted question mark
        '\u00c0': 'A',  # Latin capital letter A with grave
        '\u00c1': 'A',  # Latin capital letter A with acute
        '\u00c2': 'A',  # Latin capital letter A with circumflex
        '\u00c3': 'A',  # Latin capital letter A with tilde
        '\u00c4': 'A',  # Latin capital letter A with diaeresis
        '\u00c5': 'A',  # Latin capital letter A with ring above
        '\u00c6': 'AE',  # Latin capital letter AE
        '\u00c7': 'C',  # Latin capital letter C with cedilla
        '\u00c8': 'E',  # Latin capital letter E with grave
        '\u00c9': 'E',  # Latin capital letter E with acute
        '\u00ca': 'E',  # Latin capital letter E with circumflex
        '\u00cb': 'E',  # Latin capital letter E with diaeresis
        '\u00cc': 'I',  # Latin capital letter I with grave
        '\u00cd': 'I',  # Latin capital letter I with acute
        '\u00ce': 'I',  # Latin capital letter I with circumflex
        '\u00cf': 'I',  # Latin capital letter I with diaeresis
        '\u00d0': 'D',  # Latin capital letter ETH
        '\u00d1': 'N',  # Latin capital letter N with tilde
        '\u00d2': 'O',  # Latin capital letter O with grave
        '\u00d3': 'O',  # Latin capital letter O with acute
        '\u00d4': 'O',  # Latin capital letter O with circumflex
        '\u00d5': 'O',  # Latin capital letter O with tilde
        '\u00d6': 'O',  # Latin capital letter O with diaeresis
        '\u00d7': 'x',  # Multiplication sign
        '\u00d8': 'O',  # Latin capital letter O with stroke
        '\u00d9': 'U',  # Latin capital letter U with grave
        '\u00da': 'U',  # Latin capital letter U with acute
        '\u00db': 'U',  # Latin capital letter U with circumflex
        '\u00dc': 'U',  # Latin capital letter U with diaeresis
        '\u00dd': 'Y',  # Latin capital letter Y with acute
        '\u00de': 'Th',  # Latin capital letter THORN
        '\u00df': 'ss',  # Latin small letter sharp s
        '\u00e0': 'a',  # Latin small letter a with grave
        '\u00e1': 'a',  # Latin small letter a with acute
        '\u00e2': 'a',  # Latin small letter a with circumflex
        '\u00e3': 'a',  # Latin small letter a with tilde
        '\u00e4': 'a',  # Latin small letter a with diaeresis
        '\u00e5': 'a',  # Latin small letter a with ring above
        '\u00e6': 'ae',  # Latin small letter ae
        '\u00e7': 'c',  # Latin small letter c with cedilla
        '\u00e8': 'e',  # Latin small letter e with grave
        '\u00e9': 'e',  # Latin small letter e with acute
        '\u00ea': 'e',  # Latin small letter e with circumflex
        '\u00eb': 'e',  # Latin small letter e with diaeresis
        '\u00ec': 'i',  # Latin small letter i with grave
        '\u00ed': 'i',  # Latin small letter i with acute
        '\u00ee': 'i',  # Latin small letter i with circumflex
        '\u00ef': 'i',  # Latin small letter i with diaeresis
        '\u00f0': 'd',  # Latin small letter eth
        '\u00f1': 'n',  # Latin small letter n with tilde
        '\u00f2': 'o',  # Latin small letter o with grave
        '\u00f3': 'o',  # Latin small letter o with acute
        '\u00f4': 'o',  # Latin small letter o with circumflex
        '\u00f5': 'o',  # Latin small letter o with tilde
        '\u00f6': 'o',  # Latin small letter o with diaeresis
        '\u00f7': '/',  # Division sign
        '\u00f8': 'o',  # Latin small letter o with stroke
        '\u00f9': 'u',  # Latin small letter u with grave
        '\u00fa': 'u',  # Latin small letter u with acute
        '\u00fb': 'u',  # Latin small letter u with circumflex
        '\u00fc': 'u',  # Latin small letter u with diaeresis
        '\u00fd': 'y',  # Latin small letter y with acute
        '\u00fe': 'th',  # Latin small letter thorn
        '\u00ff': 'y',  # Latin small letter y with diaeresis
    }
    
    # Track what was replaced
    replaced_chars = set()
    
    for old, new in replacements.items():
        if old in content:
            content = content.replace(old, new)
            replaced_chars.add(old)
    
    # Remove any remaining non-printable characters except newlines and tabs
    content = ''.join(char for char in content if char.isprintable() or char in '\n\t')
    
    return content, replaced_chars

def fix_file_encoding(file_path):
    """Fix a file's encoding to UTF-8 without BOM."""
    try:
        # Try to read the file with different encodings
        encodings = ['utf-8', 'utf-8-sig', 'ascii', 'iso-8859-1', 'cp1252', 'latin1']
        content = None
        
        for encoding in encodings:
            try:
                with codecs.open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            print(f"Error: Could not read {file_path} with any supported encoding")
            return False
        
        # Clean the content
        content, replaced_chars = clean_content(content)
        
        # Write back as UTF-8 without BOM
        with codecs.open(file_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(content)
        
        if replaced_chars:
            print(f"Fixed encoding for: {file_path}")
            char_codes = []
            for c in replaced_chars:
                if c:  # Only add non-empty characters
                    char_codes.append(f'U+{ord(c):04x}')
            if char_codes:  # Only print if we have valid codes
                print(f"  Replaced characters: {', '.join(char_codes)}")
        else:
            print(f"No encoding issues found in: {file_path}")
            
        return True
        
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")
        return False

def validate_python_file(file_path):
    """Validate a Python file for common issues."""
    try:
        with codecs.open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Check for null bytes
        if '\0' in content:
            print(f"Warning: Found null bytes in {file_path}")
            return False
            
        # Check for common encoding issues
        if '\ufffd' in content:  # Check for replacement character (U+FFFD)
            print(f"Warning: Found replacement character in {file_path}")
            return False
            
        # Check for other problematic characters
        problematic_chars = re.findall(r'[^\x00-\x7F]', content)
        if problematic_chars:
            char_codes = []
            for c in problematic_chars:
                if c:  # Only add non-empty characters
                    char_codes.append(f'U+{ord(c):04x}')
            if char_codes:  # Only print if we have valid codes
                print(f"Warning: Found problematic characters in {file_path}: {', '.join(char_codes)}")
            return False
            
        return True
        
    except Exception as e:
        print(f"Error validating {file_path}: {str(e)}")
        return False

def process_directory(directory):
    """Process all Python files in a directory and its subdirectories."""
    success = True
    files_processed = 0
    files_failed = 0
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                if fix_file_encoding(file_path):
                    if validate_python_file(file_path):
                        files_processed += 1
                    else:
                        files_failed += 1
                        success = False
                else:
                    files_failed += 1
                    success = False
    
    return success, files_processed, files_failed

def main():
    # Get the directory of this script
    script_dir = Path(__file__).parent.parent.resolve()
    
    # Process the addon directory
    addon_dir = script_dir / "BASICs_shape_key_manager"
    
    if not addon_dir.exists():
        print(f"Error: Addon directory not found: {addon_dir}")
        return 1
    
    print("Starting encoding fix process...")
    success, processed, failed = process_directory(addon_dir)
    
    print("\nResults:")
    print(f"Files processed successfully: {processed}")
    print(f"Files failed: {failed}")
    
    if not success:
        print("\nSome files had issues. Please check the warnings above.")
        return 1
    
    print("\nAll files processed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 