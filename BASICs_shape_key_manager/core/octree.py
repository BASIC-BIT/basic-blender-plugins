import numpy as np
from mathutils import Vector

# Octree implementation for efficient 3D point search
class OctreeNode:
    """Node for Octree spatial partitioning structure"""
    def __init__(self, center, size, max_points=10, depth=0, max_depth=10):
        self.center = center  # Center of this node's cube
        self.size = size      # Half-width of the cube
        self.max_points = max_points  # Max points before subdivision
        self.max_depth = max_depth    # Maximum tree depth
        self.depth = depth    # Current depth
        self.points = []      # Points contained in this node
        self.vertex_indices = []  # Vertex indices for these points
        self.children = None  # Octants (will be list of 8 nodes if subdivided)
        self.is_leaf = True   # Whether this is a leaf node
    
    def get_octant_index(self, point):
        """Determine which octant the point belongs in"""
        # Return an index 0-7 for the correct octant
        index = 0
        if point[0] >= self.center[0]: index |= 4
        if point[1] >= self.center[1]: index |= 2
        if point[2] >= self.center[2]: index |= 1
        return index
    
    def subdivide(self):
        """Split this node into 8 child octants"""
        if not self.is_leaf:
            return
            
        # Create 8 child nodes
        self.is_leaf = False
        self.children = []
        new_size = self.size / 2
        
        # Create child nodes for all 8 octants
        for x_dir in [-1, 1]:
            for y_dir in [-1, 1]:
                for z_dir in [-1, 1]:
                    new_center = [
                        self.center[0] + x_dir * new_size,
                        self.center[1] + y_dir * new_size,
                        self.center[2] + z_dir * new_size
                    ]
                    self.children.append(OctreeNode(
                        new_center, new_size,
                        self.max_points, self.depth + 1, self.max_depth
                    ))
        
        # Re-insert points into children
        points = self.points
        vertex_indices = self.vertex_indices
        self.points = []
        self.vertex_indices = []
        
        # Insert existing points into child nodes
        for i, point in enumerate(points):
            self._insert_point_in_children(point, vertex_indices[i])
    
    def _insert_point_in_children(self, point, vertex_idx):
        """Insert point into the appropriate child node"""
        octant = self.get_octant_index(point)
        self.children[octant].insert(point, vertex_idx)
    
    def insert(self, point, vertex_idx):
        """Insert a point and its vertex index into the octree"""
        # If leaf node and not full, just add it
        if self.is_leaf:
            self.points.append(point)
            self.vertex_indices.append(vertex_idx)
            
            # Check if we need to subdivide
            if len(self.points) > self.max_points and self.depth < self.max_depth:
                self.subdivide()
                
            return True
        
        # If not a leaf, pass to appropriate child
        self._insert_point_in_children(point, vertex_idx)
        return True
    
    def find_nearest(self, query_point, max_dist=float('inf')):
        """Find the nearest point to query_point within max_dist"""
        if self.is_leaf:
            best_dist = float('inf')
            best_idx = None
            
            # Check all points in this leaf
            for i, point in enumerate(self.points):
                dist = sum((query_point[j] - point[j])**2 for j in range(3))
                if dist < best_dist and dist <= max_dist**2:
                    best_dist = dist
                    best_idx = i
            
            if best_idx is not None:
                return (best_dist**0.5, self.vertex_indices[best_idx])
            return (float('inf'), None)
        
        # Find best child to descend into
        octant = self.get_octant_index(query_point)
        best_dist, best_idx = self.children[octant].find_nearest(query_point, max_dist)
        
        # Check if we need to look in other octants
        if best_dist < max_dist:
            max_dist = best_dist
        
        # Check if we might need to search other octants
        if max_dist > self.size:
            # Check other children
            for i, child in enumerate(self.children):
                if i != octant:
                    # Calculate min possible distance to this octant
                    min_dist_to_octant = 0
                    for j in range(3):
                        diff = abs(query_point[j] - child.center[j]) - child.size
                        if diff > 0:
                            min_dist_to_octant += diff**2
                    
                    min_dist_to_octant = min_dist_to_octant**0.5
                    
                    # If this octant could contain closer points, search it
                    if min_dist_to_octant < max_dist:
                        dist, idx = child.find_nearest(query_point, max_dist)
                        if dist < best_dist:
                            best_dist = dist
                            best_idx = idx
                            max_dist = best_dist
        
        return (best_dist, best_idx)
        
class Octree:
    """Wrapper for OctreeNode that makes usage simpler"""
    def __init__(self, points=None, vertex_indices=None, max_points_per_node=10):
        if points:
            # Find the bounding box
            min_coords = [float('inf'), float('inf'), float('inf')]
            max_coords = [float('-inf'), float('-inf'), float('-inf')]
            
            for point in points:
                for i in range(3):
                    min_coords[i] = min(min_coords[i], point[i])
                    max_coords[i] = max(max_coords[i], point[i])
            
            # Calculate center and size
            center = [(min_coords[i] + max_coords[i])/2 for i in range(3)]
            size = max(max_coords[i] - min_coords[i] for i in range(3)) / 2
            
            # Add a small buffer to ensure all points fit
            size *= 1.01
            
            # Create the root node
            self.root = OctreeNode(center, size, max_points_per_node)
            
            # Insert all points
            for i, point in enumerate(points):
                vertex_idx = vertex_indices[i] if vertex_indices else i
                self.root.insert(point, vertex_idx)
        else:
            # Create an empty octree
            self.root = None
    
    def insert(self, point, vertex_idx):
        """Insert a point and its vertex index into the octree"""
        if not self.root:
            # Initialize with this first point
            self.root = OctreeNode([point[0], point[1], point[2]], 1.0)
        self.root.insert(point, vertex_idx)
    
    def find_nearest(self, query_point, max_dist=float('inf')):
        """Find the nearest point to query_point within max_dist
           Returns (distance, vertex_index) or (inf, None) if not found
        """
        if not self.root:
            return (float('inf'), None)
        return self.root.find_nearest(query_point, max_dist) 