"""Dependency-free tests for explicit clothing-weight refits."""

import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / 'BASICs_shape_key_manager/core/weight_refit.py'
SPEC = importlib.util.spec_from_file_location('weight_refit', PATH)
refit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refit)


class WeightRefitTests(unittest.TestCase):
    def test_preserves_each_bow_share_and_replaces_differently_named_limbs(self):
        result = refit.refit_vertex_weights(
            {'Arm_L': 0.8, 'Bow1': 0.6, 'Bow2': 0.6, 'Mask': 0.7},
            {'Left arm': 0.2, 'Chest': 0.8},
            {'Arm_L', 'Bow1', 'Bow2'}, {'Bow1', 'Bow2'})
        self.assertEqual(set(result), {'Bow1', 'Bow2', 'Left arm', 'Chest', 'Mask'})
        for name, expected in {'Bow1': 0.3, 'Bow2': 0.3, 'Left arm': 0.08,
                               'Chest': 0.32, 'Mask': 0.7}.items():
            self.assertAlmostEqual(result[name], expected)

    def test_no_preservation_replaces_all_anatomical_weights(self):
        self.assertEqual(refit.refit_vertex_weights(
            {'Arm_L': 1}, {'Left arm': 2}, {'Arm_L'}, set()), {'Left arm': 1})

    def test_preserved_name_on_body_is_not_overwritten(self):
        self.assertEqual(refit.refit_vertex_weights(
            {'Bow': 0.5, 'Chest': 0.5}, {'Bow': 0.9, 'Chest': 0.1},
            {'Bow', 'Chest'}, {'Bow'}), {'Bow': 0.5, 'Chest': 0.5})

    def test_fully_protected_vertex_needs_no_mapping(self):
        self.assertEqual(refit.refit_vertex_weights(
            {'Bow': 0.8}, {}, {'Bow'}, {'Bow'}), {'Bow': 1})

    def test_unweighted_vertex_can_receive_body_weights(self):
        self.assertEqual(refit.refit_vertex_weights(
            {'Mask': 0}, {'Chest': 0.2}, set(), set()), {'Mask': 0, 'Chest': 1})

    def test_missing_mapping_fails_instead_of_retaining_old_weights(self):
        with self.assertRaisesRegex(ValueError, 'body weights'):
            refit.refit_vertex_weights({'Arm_L': 1}, {}, {'Arm_L'}, set())

    def test_non_deforming_groups_cannot_be_physics_selection(self):
        with self.assertRaisesRegex(ValueError, 'deform'):
            refit.refit_vertex_weights({'Mask': 1}, {'Chest': 1}, set(), {'Mask'})

    def test_influence_cap_keeps_physics_and_largest_body_weights(self):
        result = refit.refit_vertex_weights(
            {'Bow': 0.4, 'Arm_L': 0.6}, {'Left arm': 0.3, 'Chest': 0.7},
            {'Bow', 'Arm_L'}, {'Bow'}, max_influences=2)
        self.assertEqual(result, {'Bow': 0.4, 'Chest': 0.6})

    def test_impossible_cap_refuses_to_erase_body_or_physics(self):
        for original, names, cap in [({'Bow': 0.5, 'Arm': 0.5}, {'Bow'}, 1),
                                      ({'Bow': 0.5, 'Bow2': 0.5}, {'Bow', 'Bow2'}, 1)]:
            with self.assertRaisesRegex(ValueError, 'influence'):
                refit.refit_vertex_weights(original, {'Chest': 1}, set(original),
                                          names, max_influences=cap)

    def test_zero_assignments_do_not_use_influence_slots(self):
        self.assertEqual(refit.refit_vertex_weights(
            {'Bow': 0, 'Arm': 1}, {'Chest': 1, 'Spine': 0}, {'Bow', 'Arm'},
            {'Bow'}, max_influences=1), {'Chest': 1})

    def test_nonfinite_and_negative_weights_are_rejected(self):
        for bad in [float('nan'), float('inf'), -0.1]:
            with self.assertRaisesRegex(ValueError, 'weight'):
                refit.refit_vertex_weights({'Arm': bad}, {'Chest': 1}, {'Arm'}, set())
            with self.assertRaisesRegex(ValueError, 'weight'):
                refit.refit_vertex_weights({'Arm': 1}, {'Chest': bad}, {'Arm'}, set())

    def test_invalid_influence_limit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'influence'):
            refit.refit_vertex_weights({}, {'Chest': 1}, set(), set(), max_influences=0)


if __name__ == '__main__':
    unittest.main()
