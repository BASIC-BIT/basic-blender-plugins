"""bpy-stubbed tests for the polyloop operator glue's shape-key handling.

The operator layer is deliberately thin, but the shape-key snapshot/rebuild
glue and the rebuild guards carry real decisions, so they get coverage here
with a stub ``bpy`` module and mock Blender data -- no Blender required::

    python tests/test_polyloop_ops_shape_keys.py

Covers:

* ``_destructive_rebuild_blockers`` / ``_refuse_unpreservable_data``:
  relative shape keys are no longer refused; absolute keys and shape-key
  animation data still hard-block; UV/color/material loss still gates on
  ``allow_attribute_loss``.
* ``_collect_shape_key_state``: faithful snapshot of key blocks + mesh-level
  settings into the bpy-free representation the core remaps.
* ``_apply_shape_key_state``: order, coordinates, relative-key links, and
  slider-range-before-value restore semantics (values must not be clamped by
  default slider ranges).
"""

import importlib.util
import os
import sys
import types


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(REPO_ROOT, "BASICs_shape_key_manager")
CORE_DIR = os.path.join(ADDON_DIR, "core")
OPS_DIR = os.path.join(ADDON_DIR, "operators")


# --------------------------------------------------------------------------- #
# Stub bpy so operators/polyloop_ops.py imports outside Blender.
# --------------------------------------------------------------------------- #

def _property_stub(**_kwargs):
    return None


bpy_stub = types.ModuleType("bpy")
bpy_props = types.ModuleType("bpy.props")
bpy_props.BoolProperty = _property_stub
bpy_props.FloatProperty = _property_stub
bpy_props.IntProperty = _property_stub
bpy_types = types.ModuleType("bpy.types")


class _StubOperator:
    def __init__(self):
        self.reports = []

    def report(self, level, message):
        self.reports.append((tuple(level), message))


bpy_types.Operator = _StubOperator
bpy_stub.props = bpy_props
bpy_stub.types = bpy_types
bpy_stub.ops = types.ModuleType("bpy.ops")
sys.modules["bpy"] = bpy_stub
sys.modules["bpy.props"] = bpy_props
sys.modules["bpy.types"] = bpy_types


# --------------------------------------------------------------------------- #
# Load the addon modules as a package so relative imports resolve.
# --------------------------------------------------------------------------- #

def _load(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_pkg = types.ModuleType("skm_pkg")
_pkg.__path__ = [ADDON_DIR]
sys.modules["skm_pkg"] = _pkg
_core_pkg = types.ModuleType("skm_pkg.core")
_core_pkg.__path__ = [CORE_DIR]
sys.modules["skm_pkg.core"] = _core_pkg
_ops_pkg = types.ModuleType("skm_pkg.operators")
_ops_pkg.__path__ = [OPS_DIR]
sys.modules["skm_pkg.operators"] = _ops_pkg

_load("skm_pkg.core.polyloop_reduction",
      os.path.join(CORE_DIR, "polyloop_reduction.py"))
_load("skm_pkg.core.shape_key_remap",
      os.path.join(CORE_DIR, "shape_key_remap.py"))
_load("skm_pkg.core.polyloop_dissolve",
      os.path.join(CORE_DIR, "polyloop_dissolve.py"))
ops = _load("skm_pkg.operators.polyloop_ops",
            os.path.join(OPS_DIR, "polyloop_ops.py"))


# --------------------------------------------------------------------------- #
# Mock Blender data.
# --------------------------------------------------------------------------- #

class FakeShapeKeyPoint:
    def __init__(self, co):
        self.co = tuple(co)


class FakeKeyBlockData:
    """Mimics ``key_block.data``: indexable points plus ``foreach_set``."""

    def __init__(self, count):
        self.points = [FakeShapeKeyPoint((0.0, 0.0, 0.0)) for _ in range(count)]

    def __iter__(self):
        return iter(self.points)

    def __len__(self):
        return len(self.points)

    def foreach_set(self, attribute, flat_values):
        assert attribute == "co"
        assert len(flat_values) == 3 * len(self.points), (
            f"foreach_set got {len(flat_values)} floats for "
            f"{len(self.points)} points")
        for i, point in enumerate(self.points):
            point.co = tuple(flat_values[3 * i:3 * i + 3])


class FakeKeyBlock:
    def __init__(self, name, vertex_count):
        self.name = name
        self.data = FakeKeyBlockData(vertex_count)
        self._value = 0.0
        self.slider_min = 0.0
        self.slider_max = 1.0
        self.mute = False
        self.interpolation = 'KEY_LINEAR'
        self.vertex_group = ''
        self.relative_key = None

    # Blender clamps ``value`` into [slider_min, slider_max]; emulating that
    # makes the tests prove the glue restores slider ranges BEFORE values.
    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = min(max(new_value, self.slider_min), self.slider_max)


class FakeShapeKeys:
    def __init__(self, use_relative=True, animation_data=None):
        self.key_blocks = []
        self.use_relative = use_relative
        self.eval_time = 0.0
        self.animation_data = animation_data


class FakeMesh:
    def __init__(self, shape_keys=None, uv_layers=(), color_attributes=(),
                 materials=()):
        self.shape_keys = shape_keys
        self.uv_layers = list(uv_layers)
        self.color_attributes = list(color_attributes)
        self.materials = list(materials)


class FakeObject:
    def __init__(self, mesh, vertex_count=0):
        self.data = mesh
        self.vertex_groups = []
        self.active_shape_key_index = 0
        self.show_only_shape_key = False
        self._vertex_count = vertex_count

    def shape_key_add(self, name, from_mix=False):
        assert from_mix is False
        if self.data.shape_keys is None:
            self.data.shape_keys = FakeShapeKeys()
        block = FakeKeyBlock(name, self._vertex_count)
        self.data.shape_keys.key_blocks.append(block)
        return block


def make_object_with_keys(use_relative=True, animation_data=None):
    shape_keys = FakeShapeKeys(use_relative=use_relative,
                               animation_data=animation_data)
    obj = FakeObject(FakeMesh(shape_keys=shape_keys), vertex_count=3)
    basis = FakeKeyBlock("Basis", 3)
    basis.data.foreach_set("co", [0, 0, 0, 1, 0, 0, 2, 0, 0])
    smile = FakeKeyBlock("Smile", 3)
    smile.data.foreach_set("co", [0, 1, 0, 1, 1, 0, 2, 1, 0])
    smile.relative_key = basis
    smile._value = 0.4
    smile.slider_min = -1.0
    smile.slider_max = 2.0
    smile.vertex_group = "Head"
    smile.mute = True
    smile.interpolation = 'KEY_CARDINAL'
    shape_keys.key_blocks.extend([basis, smile])
    obj.active_shape_key_index = 1
    obj.show_only_shape_key = True
    return obj


# --------------------------------------------------------------------------- #
# Guard behaviour.
# --------------------------------------------------------------------------- #

def test_relative_shape_keys_are_no_longer_hard_blockers():
    obj = make_object_with_keys()
    hard, lossy = ops._destructive_rebuild_blockers(obj)
    assert hard == []
    assert lossy == []
    operator = _StubOperator()
    assert ops._refuse_unpreservable_data(operator, obj, False) is False
    assert operator.reports == []


def test_absolute_shape_keys_still_refuse():
    obj = make_object_with_keys(use_relative=False)
    hard, _lossy = ops._destructive_rebuild_blockers(obj)
    assert len(hard) == 1 and "absolute" in hard[0]
    operator = _StubOperator()
    assert ops._refuse_unpreservable_data(operator, obj, True) is True
    assert operator.reports and operator.reports[0][0] == ('ERROR',)


def test_shape_key_animation_data_still_refuses():
    obj = make_object_with_keys(animation_data=object())
    hard, _lossy = ops._destructive_rebuild_blockers(obj)
    assert len(hard) == 1 and "animation" in hard[0]
    operator = _StubOperator()
    assert ops._refuse_unpreservable_data(operator, obj, True) is True


def test_lossy_layers_still_gate_on_allow_attribute_loss():
    obj = make_object_with_keys()
    obj.data.uv_layers = ["UVMap"]
    operator = _StubOperator()
    assert ops._refuse_unpreservable_data(operator, obj, False) is True
    assert "Allow Attribute Loss" in operator.reports[0][1]
    operator = _StubOperator()
    assert ops._refuse_unpreservable_data(operator, obj, True) is False


def test_mesh_without_shape_keys_has_no_blockers():
    obj = FakeObject(FakeMesh())
    assert ops._destructive_rebuild_blockers(obj) == ([], [])


# --------------------------------------------------------------------------- #
# Snapshot (collect) behaviour.
# --------------------------------------------------------------------------- #

def test_collect_shape_key_state_snapshots_everything():
    obj = make_object_with_keys()
    state = ops._collect_shape_key_state(obj)
    assert state["use_relative"] is True
    assert state["active_index"] == 1
    assert state["show_only_shape_key"] is True
    keys = state["keys"]
    assert [k["name"] for k in keys] == ["Basis", "Smile"]
    assert keys[0]["coordinates"] == [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    assert keys[1]["coordinates"] == [(0, 1, 0), (1, 1, 0), (2, 1, 0)]
    assert keys[0]["relative_key"] is None
    assert keys[1]["relative_key"] == "Basis"
    assert keys[1]["value"] == 0.4
    assert keys[1]["slider_min"] == -1.0
    assert keys[1]["slider_max"] == 2.0
    assert keys[1]["mute"] is True
    assert keys[1]["interpolation"] == 'KEY_CARDINAL'
    assert keys[1]["vertex_group"] == "Head"


def test_collect_shape_key_state_none_without_keys():
    assert ops._collect_shape_key_state(FakeObject(FakeMesh())) is None
    assert ops._collect_shape_key_state(
        FakeObject(FakeMesh(shape_keys=FakeShapeKeys()))) is None


# --------------------------------------------------------------------------- #
# Rebuild (apply) behaviour.
# --------------------------------------------------------------------------- #

def test_apply_shape_key_state_round_trips_through_remap():
    source = make_object_with_keys()
    state = ops._collect_shape_key_state(source)

    # Simulate the core's remap: vertex 1 was dissolved, 0 and 2 survive.
    remapped = []
    for key in state["keys"]:
        new_key = dict(key)
        new_key["coordinates"] = [key["coordinates"][0], key["coordinates"][2]]
        remapped.append(new_key)

    target = FakeObject(FakeMesh(), vertex_count=2)
    ops._apply_shape_key_state(target, state, remapped)

    blocks = target.data.shape_keys.key_blocks
    assert [b.name for b in blocks] == ["Basis", "Smile"]
    assert [p.co for p in blocks[0].data] == [(0, 0, 0), (2, 0, 0)]
    assert [p.co for p in blocks[1].data] == [(0, 1, 0), (2, 1, 0)]
    # Relative-key link restored as an object reference.
    assert blocks[1].relative_key is blocks[0]
    # Value 0.4 with slider range [-1, 2]: survives only because the glue
    # sets slider ranges before values (default range would clamp fine here,
    # so also check a value outside the default range below).
    assert blocks[1].value == 0.4
    assert blocks[1].slider_min == -1.0
    assert blocks[1].slider_max == 2.0
    assert blocks[1].mute is True
    assert blocks[1].interpolation == 'KEY_CARDINAL'
    assert blocks[1].vertex_group == "Head"
    assert target.data.shape_keys.use_relative is True
    assert target.active_shape_key_index == 1
    assert target.show_only_shape_key is True


def test_apply_sets_slider_range_before_value():
    # A value ABOVE the default slider_max (1.0) must survive the rebuild.
    source = make_object_with_keys()
    source.data.shape_keys.key_blocks[1]._value = 1.8
    state = ops._collect_shape_key_state(source)
    target = FakeObject(FakeMesh(), vertex_count=3)
    ops._apply_shape_key_state(target, state, state["keys"])
    assert target.data.shape_keys.key_blocks[1].value == 1.8


def test_apply_clamps_active_index_when_keys_shrink():
    source = make_object_with_keys()
    source.active_shape_key_index = 5    # stale/out-of-range index
    state = ops._collect_shape_key_state(source)
    target = FakeObject(FakeMesh(), vertex_count=3)
    ops._apply_shape_key_state(target, state, state["keys"])
    assert target.active_shape_key_index == 1


def main():
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    if failures:
        print(f"{failures} test(s) failed")
        sys.exit(1)
    print("All tests passed")


if __name__ == "__main__":
    main()
