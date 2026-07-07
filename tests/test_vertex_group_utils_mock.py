"""Mock-based tests for the protected vertex group rules.

Runs without Blender: vertex_group_utils.py is pure Python, so it is
loaded directly from its file path (bypassing the package __init__,
which pulls in bpy-dependent modules).

    python tests/test_vertex_group_utils_mock.py
"""

import importlib.util
import os
import sys

MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "BASICs_shape_key_manager", "core", "vertex_group_utils.py")

spec = importlib.util.spec_from_file_location("vertex_group_utils", MODULE_PATH)
vgu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vgu)


class MockVertexGroup:
    def __init__(self, name, lock_weight=False):
        self.name = name
        self.lock_weight = lock_weight


class MockObject:
    def __init__(self, group_names, locked=()):
        self.vertex_groups = [
            MockVertexGroup(n, lock_weight=(n in locked)) for n in group_names]


def test_parse_prefix_list():
    assert vgu.parse_prefix_list("") == ()
    assert vgu.parse_prefix_list(None) == ()
    assert vgu.parse_prefix_list("Boob, Breast") == ("boob", "breast")
    assert vgu.parse_prefix_list("Tail,,  ,Skirt,") == ("tail", "skirt")


def test_primary_rule_outfit_only_groups_protected():
    # Outfit has its own dynamics chains (feathers, bows, straps) the
    # body does not: those are protected automatically, no configuration.
    target = MockObject(["Hips", "Spine", "Feather_01", "Bow.L", "Strap_root"])
    source_names = {"Hips", "Spine", "Chest", "Head"}
    protected = vgu.collect_protected_group_names(
        target, source_group_names=source_names)
    assert protected == {"Feather_01", "Bow.L", "Strap_root"}


def test_groups_on_both_meshes_not_protected_by_default():
    # Names that exist on the source ARE the transfer set: not protected.
    target = MockObject(["Hips", "Boob_L", "Boob_R"])
    source_names = {"Hips", "Boob_L", "Boob_R"}
    protected = vgu.collect_protected_group_names(
        target, source_group_names=source_names)
    assert protected == set()


def test_secondary_rule_lock_weight():
    target = MockObject(["Hips", "Spine"], locked={"Spine"})
    source_names = {"Hips", "Spine"}
    assert vgu.collect_protected_group_names(
        target, source_group_names=source_names) == {"Spine"}
    # And the lock rule can be disabled.
    assert vgu.collect_protected_group_names(
        target, source_group_names=source_names,
        respect_lock_weight=False) == set()


def test_override_rule_keep_existing_prefixes():
    # The override protects groups even though they exist on both meshes
    # (outfit has hand-tuned jiggle weights the user wants kept).
    target = MockObject(["Hips", "Boob_L", "Boob_R", "Breast_root"])
    source_names = {"Hips", "Boob_L", "Boob_R", "Breast_root"}
    protected = vgu.collect_protected_group_names(
        target, source_group_names=source_names,
        keep_existing_prefixes=("boob", "breast"))
    assert protected == {"Boob_L", "Boob_R", "Breast_root"}


def test_override_is_case_insensitive_prefix_match():
    target = MockObject(["BOOB_L", "boobie", "Rebooboo"])
    protected = vgu.collect_protected_group_names(
        target, source_group_names={"BOOB_L", "boobie", "Rebooboo"},
        keep_existing_prefixes=("boob",))
    assert protected == {"BOOB_L", "boobie"}  # prefix, not substring


def test_no_source_set_skips_primary_rule():
    # source_group_names=None: only lock + prefix rules apply.
    target = MockObject(["Hips", "Feather_01"], locked={"Hips"})
    protected = vgu.collect_protected_group_names(
        target, source_group_names=None)
    assert protected == {"Hips"}


def test_all_rules_union():
    target = MockObject(
        ["Hips", "Spine", "Feather_01", "Boob_L"], locked={"Spine"})
    source_names = {"Hips", "Spine", "Boob_L"}
    protected = vgu.collect_protected_group_names(
        target, source_group_names=source_names,
        keep_existing_prefixes=("boob",))
    assert protected == {"Feather_01", "Spine", "Boob_L"}


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
