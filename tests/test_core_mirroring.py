"""Keep master mirror naming, vertex pairing and spatial search stable."""
import importlib.util
from pathlib import Path
import sys
import types
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / 'BASICs_shape_key_manager' / 'core'
# These helpers import Vector for Blender, but their tuple search never uses it.
sys.modules.setdefault('mathutils', SimpleNamespace(Vector=tuple))
package = types.ModuleType('mirror_core')
package.__path__ = [str(ROOT)]
sys.modules['mirror_core'] = package


def load(name):
    spec = importlib.util.spec_from_file_location('mirror_core.' + name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


octree = load('octree')
package.Octree = octree.Octree
mirror = load('mirror_utils')

# Naming retains separators, full words and existing-key collision suffixes.
for source, target in [
        ('SmileL', 'SmileR'), ('SmileR', 'SmileL'),
        ('Smile_L', 'Smile_R'), ('Smile.R', 'Smile.L'),
        ('Smile-L', 'Smile-R'), ('SmileLeft', 'SmileRight'),
        ('SmileRight', 'SmileLeft'), ('Smile_Left', 'Smile_Right'),
        ('Smile.Left', 'Smile.Right'), ('Smile-Left', 'Smile-Right'),
        ('Smile_Right', 'Smile_Left'), ('Smile.Right', 'Smile.Left'),
        ('Smile-Right', 'Smile-Left'), ('Smile', 'Smile_Mirror')]:
    info = mirror.detect_shape_key_side(source)
    assert mirror.generate_mirrored_name(source, info, None) == target, source
    existing = {target, target + '_Mirror', target + '_Mirror_1'}
    assert mirror.generate_mirrored_name(source, info, existing) == target + '_Mirror_2'

# Both Blender mesh and shape-key coordinate collections use the same pairing.
points = [(-1, 0, 0), (1, 0, 0), (0, 0, 1), (-2, 0, 0), (3, 0, 0)]
vertices = [SimpleNamespace(co=SimpleNamespace(x=x, y=y, z=z)) for x, y, z in points]
for data in (SimpleNamespace(vertices=vertices), SimpleNamespace(data=vertices)):
    left, right, center = mirror.build_mirror_vertex_mapping(data)
    assert (left, right, center) == ([0, 3], [1, 4], [2])
    sources, targets, mapping, reverse = mirror.create_vertex_mirror_mapping(
        data, 'L', left, right, center)
    assert (sources, targets, mapping, reverse) == ([0, 3], [1, 4], {2: 2, 0: 1}, {1: 0})
    assert mirror.create_vertex_mirror_mapping(data, 'R', left, right, center)[2:] == (
        {2: 2, 1: 0}, {0: 1})

# Exact hits, bounded misses, empty insertion and subdivision preserve indices.
tree = octree.Octree()
assert tree.find_nearest((0, 0, 0)) == (float('inf'), None)
tree.insert((1, 2, 3), 17)
assert tree.find_nearest((1, 2, 3)) == (0, 17)
assert tree.find_nearest((10, 0, 0), max_dist=.1) == (float('inf'), None)
points = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
tree = octree.Octree(points, list(range(10, 18)), max_points_per_node=1)
assert not tree.root.is_leaf
children = tree.root.children
assert len(children) == 8
tree.root.subdivide()
assert tree.root.children is children
for i, point in enumerate(points):
    assert tree.find_nearest(point) == (0, i + 10)
assert tree.find_nearest((10, 0, 0), max_dist=.1) == (float('inf'), None)
distance, index = tree.find_nearest((10, 0, 0))
assert abs(distance - 83 ** .5) < 1e-12 and index in range(14, 18)
tree.insert((.2, .3, .4), 99)
assert tree.find_nearest((.2, .3, .4)) == (0, 99)
assert octree.Octree([(2, 0, 0)]).find_nearest((2, 0, 0)) == (0, 0)
node = octree.OctreeNode((0, 0, 0), 1, max_points=1, max_depth=0)
node.insert((0, 0, 0), 1)
node.insert((.5, .5, .5), 2)
assert node.is_leaf and node.find_nearest((.5, .5, .5)) == (0, 2)
print('Master mirror and spatial search regression tests passed')
