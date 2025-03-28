"""
Mirror utility functions for both shape key and mesh mirroring operations.
These functions provide common functionality for vertex classification and mapping.
"""

import re
from mathutils import Vector
from . import Octree

def detect_shape_key_side(key_name):
    """Detect if a shape key name has L/R designation and return pattern info"""
    # Store information about the match for better name creation
    pattern_info = {
        'base_name': None,
        'from_side': None,
        'to_side': None,
        'separator': None   # Will store separator like '_', '.', '-' or '' (empty for direct suffix)
    }
    
    # Regular expression patterns for different naming conventions
    left_patterns = [
        (r'([a-zA-Z0-9]+)L$', ''),               # Direct suffix, e.g., "SmileL"
        (r'([a-zA-Z0-9]+)[._-]L$', None),        # With separator (will be extracted)
        (r'([a-zA-Z0-9]+)Left$', ''),            # Direct suffix, e.g., "SmileLeft"
        (r'([a-zA-Z0-9]+)[._-]Left$', None)      # With separator
    ]
    
    right_patterns = [
        (r'([a-zA-Z0-9]+)R$', ''),               # Direct suffix, e.g., "SmileR"
        (r'([a-zA-Z0-9]+)[._-]R$', None),        # With separator (will be extracted)
        (r'([a-zA-Z0-9]+)Right$', ''),           # Direct suffix, e.g., "SmileRight"
        (r'([a-zA-Z0-9]+)[._-]Right$', None)     # With separator
    ]
    
    # Check if it's a left-side shape key
    for pattern, sep in left_patterns:
        match = re.match(pattern, key_name)
        if match:
            pattern_info['base_name'] = match.group(1)
            pattern_info['from_side'] = 'L'
            pattern_info['to_side'] = 'R'
            
            # If separator needs to be extracted
            if sep is None:
                # Find which separator was used
                if '_L' in key_name:
                    pattern_info['separator'] = '_'
                elif '.L' in key_name:
                    pattern_info['separator'] = '.'
                elif '-L' in key_name:
                    pattern_info['separator'] = '-'
                # For names like "Smile_Left"
                elif '_Left' in key_name:
                    pattern_info['separator'] = '_'
                elif '.Left' in key_name:
                    pattern_info['separator'] = '.'
                elif '-Left' in key_name:
                    pattern_info['separator'] = '-'
            else:
                pattern_info['separator'] = sep
            
            break
            
    # If not found, check if it's a right-side shape key
    if not pattern_info['base_name']:
        for pattern, sep in right_patterns:
            match = re.match(pattern, key_name)
            if match:
                pattern_info['base_name'] = match.group(1)
                pattern_info['from_side'] = 'R'
                pattern_info['to_side'] = 'L'
                
                # If separator needs to be extracted
                if sep is None:
                    # Find which separator was used
                    if '_R' in key_name:
                        pattern_info['separator'] = '_'
                    elif '.R' in key_name:
                        pattern_info['separator'] = '.'
                    elif '-R' in key_name:
                        pattern_info['separator'] = '-'
                    # For names like "Smile_Right"
                    elif '_Right' in key_name:
                        pattern_info['separator'] = '_'
                    elif '.Right' in key_name:
                        pattern_info['separator'] = '.'
                    elif '-Right' in key_name:
                        pattern_info['separator'] = '-'
                else:
                    pattern_info['separator'] = sep
                
                break
            
    return pattern_info

def build_mirror_vertex_mapping(mesh_or_basis_key):
    """Build a mapping between vertices on opposite sides of the mesh or shape key
    
    Parameters:
        mesh_or_basis_key: Either a mesh or a shape key to classify vertices from
    
    Returns:
        Tuple of (left_vertices, right_vertices, center_vertices)
    """
    # Group vertices by their X sign (left/right of the center)
    left_vertices = []  # X < 0
    right_vertices = []  # X > 0
    center_vertices = []  # X ≈ 0
    
    # Small threshold for center vertices
    center_threshold = 0.0001
    
    # Determine if we're working with a mesh or shape key
    # Shape keys have a .data attribute with vertex data
    is_shape_key = hasattr(mesh_or_basis_key, 'data')
    
    # Sorting vertices based on X coordinate sign
    vertex_count = len(mesh_or_basis_key.data if is_shape_key else mesh_or_basis_key.vertices)
    
    for i in range(vertex_count):
        if is_shape_key:
            x_coord = mesh_or_basis_key.data[i].co.x
        else:
            x_coord = mesh_or_basis_key.vertices[i].co.x
            
        if abs(x_coord) < center_threshold:
            center_vertices.append(i)
        elif x_coord < 0:
            left_vertices.append(i)
        else:
            right_vertices.append(i)
    
    return left_vertices, right_vertices, center_vertices

def create_vertex_mirror_mapping(object_data, from_side, left_vertices, right_vertices, center_vertices, tolerance=0.001):
    """Create a detailed mapping between source and target vertices for mirroring
    
    Parameters:
        object_data: Either a mesh or shape key to get vertex coordinates from
        from_side: 'L' for mirroring left to right, 'R' for right to left
        left_vertices: List of vertex indices on the left side
        right_vertices: List of vertex indices on the right side
        center_vertices: List of vertex indices near the center
        tolerance: Maximum distance allowed between mirrored vertices
    
    Returns:
        Tuple of (source_vertices, target_vertices, mirror_map, reverse_map)
    """
    # Build the mirror mapping
    mirror_map = {}
    
    # Center vertices mirror to themselves
    for i in center_vertices:
        mirror_map[i] = i
    
    # Find matches between left and right vertices
    source_vertices = left_vertices if from_side == 'L' else right_vertices
    target_vertices = right_vertices if from_side == 'L' else left_vertices
    
    # Create an octree with the target vertices for efficient searching
    octree = Octree()
    
    # Determine if we're working with a mesh or shape key
    is_shape_key = hasattr(object_data, 'data')
    
    # Populate the octree with target vertices
    for tgt_idx in target_vertices:
        if is_shape_key:
            tgt_co = object_data.data[tgt_idx].co
        else:
            tgt_co = object_data.vertices[tgt_idx].co
            
        search_point = (tgt_co.x, tgt_co.y, tgt_co.z)
        octree.insert(search_point, tgt_idx)
        
    # For each source vertex, find the best match in the octree
    for src_idx in source_vertices:
        if is_shape_key:
            src_co = object_data.data[src_idx].co
        else:
            src_co = object_data.vertices[src_idx].co
        
        # Create a query point with the mirrored X coordinate
        query_point = (-src_co.x, src_co.y, src_co.z)
        
        # Find the nearest vertex in the octree within the tolerance distance
        distance, best_match_idx = octree.find_nearest(query_point, max_dist=tolerance)
        
        # If we found a match, add it to the mapping
        if best_match_idx is not None:
            mirror_map[src_idx] = best_match_idx
    
    # Create a reverse mapping for efficient lookup: target_idx -> source_idx
    reverse_map = {}
    for src_idx, tgt_idx in mirror_map.items():
        if src_idx != tgt_idx:  # Only include actual mappings (skip self-mapping for center vertices)
            reverse_map[tgt_idx] = src_idx
            
    return source_vertices, target_vertices, mirror_map, reverse_map

def generate_mirrored_name(shape_key_name, pattern_info, shape_keys):
    """Generate a mirrored name for a shape key based on pattern info"""
    # If we couldn't determine the side, use _Mirror suffix
    if not pattern_info['base_name']:
        new_key_name = f"{shape_key_name}_Mirror"
    else:
        # Create the new name using the pattern information
        base_name = pattern_info['base_name']
        to_side = pattern_info['to_side']
        separator = pattern_info['separator']
        
        # Handle special cases for "Left" and "Right"
        if to_side == 'L' and 'Right' in shape_key_name:
            if separator:
                new_key_name = base_name + separator + 'Left'
            else:
                new_key_name = base_name + 'Left'
        elif to_side == 'R' and 'Left' in shape_key_name:
            if separator:
                new_key_name = base_name + separator + 'Right'
            else:
                new_key_name = base_name + 'Right'
        else:
            # Standard L/R naming
            if separator:
                new_key_name = base_name + separator + to_side
            else:
                new_key_name = base_name + to_side
    
    # Check if the shape key with the new name already exists
    if shape_keys and new_key_name in shape_keys:
        new_key_name = f"{new_key_name}_Mirror"
        # Check again with the modified name
        if new_key_name in shape_keys:
            i = 1
            while f"{new_key_name}_{i}" in shape_keys:
                i += 1
            new_key_name = f"{new_key_name}_{i}"
    
    return new_key_name 