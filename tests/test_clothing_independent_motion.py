"""Independent control coverage, replay identities and finite-budget omissions."""
import importlib.util
from itertools import combinations, product
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('motion', ROOT / 'BASICs_shape_key_manager/core/clothing_motion.py')
motion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(motion)
spec = importlib.util.spec_from_file_location('fixture.operators.clothing_checks.sampling',
                                            ROOT / 'BASICs_shape_key_manager/operators/clothing_checks/sampling.py')
sampling = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'fixture.core.clothing_motion': motion}):
    spec.loader.exec_module(sampling)


class IndependentMotionTests(unittest.TestCase):
    def cases(self, budget=100000, shapes=None):
        return motion.seed_cases(motion.PROFILES, shapes, budget=budget, steps=3)

    def test_sided_controls_override_only_the_named_joint_and_change_identity(self):
        base = self.cases()[0]
        controlled = dict(base, controls={'left_forearm': {'bend': 75}})
        case = motion.interpolate_case(controlled, 1)
        commands = motion.motion_commands(case)['rotations']
        self.assertIn({'bone': 'left_forearm', 'axis': 'bend', 'degrees': 75.}, commands)
        self.assertFalse(any(r['bone'] == 'right_forearm' for r in commands))
        self.assertNotEqual(case['id'], motion.interpolate_case(base, 1)['id'])
        self.assertEqual(case, motion.interpolate_case(case, 1))

    def test_invalid_controls_fail_at_the_case_boundary(self):
        base = self.cases()[0]
        for controls in ([], {'upper_arm': {'bone': 20}}, {'left_foot': {'unknown': 5}},
                         {'left_hand': {'right': float('nan')}}, {'left_shin': {'bend': True}},
                         {'left_upper_arm': {'elevation': 181}}):
            with self.subTest(controls=controls), self.assertRaises(ValueError):
                motion.interpolate_case(dict(base, controls=controls), .5)

    def test_equal_control_mappings_have_equal_native_command_order(self):
        base = self.cases()[0]
        a = dict(base, controls={'left_upper_arm': {'up': -20, 'bone': 30}})
        b = dict(base, controls={'left_upper_arm': {'bone': 30, 'up': -20}})
        self.assertEqual(motion.interpolate_case(a, 1)['id'], motion.interpolate_case(b, 1)['id'])
        self.assertEqual(motion.motion_commands(dict(a, t=1)), motion.motion_commands(dict(b, t=1)))

    def test_pairwise_values_are_independently_enumerated_for_each_arm(self):
        factors = [('upper_arm', 'elevation', (35, 140)), ('shoulder', 'forward', (0, 15)),
                   ('shoulder', 'up', (0, -15)), ('upper_arm', 'bone', (-35, 35)),
                   ('forearm', 'bend', (20, 90)), ('forearm', 'bone', (-45, 45))]
        cases = self.cases()
        for side in ('left', 'right'):
            own = [c for c in cases if c.get('coverage_kind') == 'PAIRWISE'
                   and c['profile'] == 'FULL_BODY' and c['t'] == 1
                   and side + '_upper_arm' in c['controls']]
            self.assertTrue(own, side)
            for (a, aa, av), (b, ba, bv) in combinations(factors, 2):
                observed = {(c['controls'][side + '_' + a][aa],
                             c['controls'][side + '_' + b][ba]) for c in own}
                self.assertEqual(observed, set(product(av, bv)), (side, a, aa, b, ba))

    def test_targeted_triples_are_bounded_around_a_failure_seed(self):
        failure = dict(self.cases()[0], controls={'left_upper_arm': {'elevation': 125, 'bone': 10},
                                                 'left_shoulder': {'up': -12}})
        cases = motion.targeted_cases(failure, budget=8, radius=5)
        observed = {(c['controls']['left_upper_arm']['elevation'],
                     c['controls']['left_upper_arm']['bone'],
                     c['controls']['left_shoulder']['up']) for c in cases}
        self.assertEqual(observed, set(product((120., 130.), (5., 15.), (-17., -7.))))
        self.assertEqual(cases, motion.targeted_cases(failure, budget=8, radius=5))

    def test_heldout_controls_and_trajectories_cannot_join_training_refinement(self):
        base = self.cases()[0]
        a = motion.interpolate_case(dict(base, controls={'left_forearm': {'bend': 20}}), 0)
        b = motion.interpolate_case(dict(base, controls={'left_forearm': {'bend': 80}}), 1)
        held = motion.interpolate_case(dict(a, partition='HELDOUT'), 1)
        self.assertEqual(motion.refinement_candidates([
            {'case': a, 'clearance_m': 0}, {'case': b, 'clearance_m': 0},
            {'case': held, 'clearance_m': 0}], 10), [])
        self.assertEqual(len({motion.trajectory_key(c) for c in (a, b, held)}), 3)
        changed_shape = motion.interpolate_case(dict(a, shape_values={'body': {'Fit': .5}}), 0)
        self.assertNotEqual(motion.trajectory_key(a), motion.trajectory_key(changed_shape))

    def test_collision_refinement_adds_targeted_triples_but_never_trains_on_holdouts(self):
        base = dict(self.cases()[0], controls={'left_upper_arm': {'elevation': 125, 'bone': 10},
                                               'left_shoulder': {'up': -12}}, t=1)
        measurements = [{'case': base, 'collision': True}]
        refined = motion.refinement_candidates(measurements, 8)
        self.assertEqual(len(refined), 8)
        self.assertTrue(all(c['coverage_kind'] == 'TARGETED_TRIPLE' for c in refined))
        self.assertEqual(motion.refinement_candidates([
            {'case': dict(base, partition='HELDOUT'), 'collision': True}], 8), [])

    def test_seed_control_values_are_distinct_between_training_and_holdouts(self):
        cases = [c for c in self.cases() if c.get('controls')]
        def values(case):
            return tuple((bone, tuple(sorted(axes.items()))) for bone, axes in sorted(case['controls'].items()))
        training = {values(c) for c in cases if c['partition'] == 'TRAINING'}
        heldout = {values(c) for c in cases if c['partition'] == 'HELDOUT'}
        self.assertTrue(training and heldout)
        self.assertFalse(training & heldout)

    def test_heldout_native_commands_do_not_repeat_training_at_three_or_five_steps(self):
        def signature(case):
            command = motion.motion_commands(case)
            return (tuple(sorted((r['bone'], r['axis'], round(r['degrees'], 8))
                                 for r in command['rotations'])),
                    tuple(round(v, 8) for v in command['pelvis_height_fractions']),
                    tuple(sorted(command['contacts'].items())), round(command['accessory_degrees'], 8))
        for steps in (3, 5):
            cases = motion.seed_cases(motion.PROFILES, budget=100000, steps=steps)
            training = {}
            for case in cases:
                if case['partition'] == 'TRAINING':
                    key = (case['profile'], case['motion'], case['shape_case'])
                    training.setdefault(key, set()).add(signature(case))
            repeated = [case['id'] for case in cases if case['partition'] == 'HELDOUT'
                        and case['motion'] != 'neutral' and signature(case) in
                        training[(case['profile'], case['motion'], case['shape_case'])]]
            self.assertEqual(repeated, [], (steps, repeated))
            self.assertFalse(any(c['partition'] == 'HELDOUT' and c['motion'] == 'neutral' for c in cases),
                             'constant neutral baselines must not count as independent heldouts')

    def test_session_sampling_preserves_reserved_strata_and_targeted_refinements(self):
        shapes = [{'id': 'current', 'values': {}}, {'id': 'heels', 'values': {'body': {'Lift': 1}}}]
        settings, cases, expected = sampling.prepare({'profiles': ['HEAD_HANDS', 'FULL_BODY'],
            'shape_cases': shapes, 'budget': 64, 'families': ['shoulder', 'coordination']})
        strata = {(c['profile'], c['shape_case'], c['family'], c['partition']) for c in cases}
        self.assertEqual(strata, set(product(motion.PROFILES, ('current', 'heels'),
                                            ('shoulder', 'coordination'), ('TRAINING', 'HELDOUT'))))
        self.assertEqual(sampling.coverage(cases, expected, [], settings)['uncovered_strata'], [])
        failure = motion.interpolate_case(dict(cases[0], controls={
            'left_upper_arm': {'elevation': 125, 'bone': 10}, 'left_shoulder': {'up': -12}}), 1)
        targeted = sampling.refinements([{'case': failure, 'collision': True}], 0, settings)
        self.assertEqual(len(targeted), 8)
        self.assertEqual(sampling.refinements([{'case': failure}], settings['refinement_depth'], settings), [])
        replay_settings, replay, _ = sampling.prepare(dict(settings, cases=[failure]))
        self.assertEqual(replay[0]['controls'], failure['controls'])
        self.assertEqual(replay[0]['id'], failure['id'])
        self.assertEqual(replay_settings['shape_cases'], shapes)

    def test_seed_budget_prioritizes_real_independent_values_and_temporal_phases(self):
        cases = self.cases(budget=512)
        for side in ('left', 'right'):
            controlled = [c for c in cases if side + '_upper_arm' in c.get('controls', {})
                          and c['partition'] == 'TRAINING' and c['t'] == 1]
            self.assertTrue(controlled, side)
        for phase in ('dance_loop', 'rapid_turn', 'stop', 'settle'):
            self.assertTrue(any(c['motion'] == phase for c in cases), phase)

    def test_budget_reserves_profiles_shapes_families_and_holdouts(self):
        shapes = [{'id': 'current', 'values': {}},
                  {'id': 'heels', 'values': {'body': {'Heels': 1}, 'socks': {'High': 1}}}]
        cases = self.cases(budget=64, shapes=shapes)
        for profile, shape, family, partition in product(motion.PROFILES, ('current', 'heels'),
                                                        {v[0] for v in motion.MOTIONS.values()},
                                                        ('TRAINING', 'HELDOUT')):
            if family == 'neutral' and partition == 'HELDOUT':
                continue
            self.assertTrue(any(c['profile'] == profile and c['shape_case'] == shape
                                and c['family'] == family and c['partition'] == partition
                                for c in cases), (profile, shape, family, partition))
        small = self.cases(budget=1, shapes=shapes)
        summary = motion.coverage_summary(small, motion.PROFILES, shapes, steps=3)
        self.assertTrue(summary['uncovered_strata'])
        expected = {(p, s, f, h) for p, s, f, h in product(motion.PROFILES, ('current', 'heels'),
                    {v[0] for v in motion.MOTIONS.values()}, ('TRAINING', 'HELDOUT'))
                    if f != 'neutral' or h != 'HELDOUT'}
        expected -= {(c['profile'], c['shape_case'], c['family'], c['partition']) for c in small}
        actual = {(s['profile'], s['shape_case'], s['family'], s['partition'])
                  for s in summary['uncovered_strata']}
        self.assertEqual(actual, expected)

    def test_asymmetric_lower_body_and_temporal_catalog_reach_commands(self):
        cases = self.cases()
        names = {c['motion'] for c in cases}
        for name in ('overhead_across_left', 'overhead_across_right', 'behind_back_left',
                     'behind_back_right', 'opposite_hip_left', 'opposite_hip_right',
                     'crouch_reach', 'seated_twist', 'kneel', 'crossed_legs', 'heel_roll', 'toe_roll',
                     'dance_loop', 'rapid_turn', 'stop', 'settle'):
            self.assertIn(name, names)
        for name in ('dance_loop', 'rapid_turn', 'stop', 'settle'):
            commands = [motion.motion_commands(c) for c in cases
                        if c['motion'] == name and c['partition'] == 'TRAINING']
            self.assertTrue(all(c['metadata']['temporal_phase'] == name for c in commands))
            self.assertNotEqual(commands[0]['rotations'], commands[-1]['rotations'])
        heel = next(c for c in cases if c['motion'] == 'heel_roll' and c['t'] == 1)
        command = motion.motion_commands(heel)
        self.assertTrue(any(r['bone'].endswith('foot') and r['degrees'] for r in command['rotations']))
        self.assertEqual(command['metadata']['contact_pivot_coverage'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
