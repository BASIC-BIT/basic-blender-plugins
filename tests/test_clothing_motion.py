"""Deterministic budget and interval checks without Blender."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'BASICs_shape_key_manager/core/clothing_motion.py'


class MotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert PATH.exists(), 'motion sampler is not implemented'
        spec = importlib.util.spec_from_file_location('clothing_motion', PATH)
        cls.motion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.motion)

    def test_shapes_consume_equal_reserved_profile_budget(self):
        shapes = [{'id': 'current', 'values': {}}, {'id': 'Fit', 'values': {'Fit': 1}}]
        cases = self.motion.seed_cases(['FULL_BODY', 'HEAD_HANDS'], shapes, budget=19)
        self.assertEqual(cases, self.motion.seed_cases(['HEAD_HANDS', 'FULL_BODY'], shapes, budget=19))
        self.assertEqual(len(cases), 19)
        self.assertEqual(sum(c['profile'] == 'HEAD_HANDS' for c in cases), 10)
        self.assertEqual(len({c['id'] for c in cases}), len(cases))
        coverage = self.motion.coverage_summary(cases, ['HEAD_HANDS', 'FULL_BODY'], shapes, steps=5)
        self.assertEqual(coverage['status'], 'INCOMPLETE')
        self.assertTrue(coverage['uncovered_cases'])

    def test_seed_endpoints_and_profiles_have_truthful_assumptions(self):
        cases = self.motion.seed_cases(['HEAD_HANDS', 'FULL_BODY'])
        for profile in ('HEAD_HANDS', 'FULL_BODY'):
            own = [c for c in cases if c['profile'] == profile and c['partition'] == 'TRAINING']
            self.assertEqual({c['t'] for c in own}, {0, .25, .5, .75, 1})
            self.assertTrue(self.motion.profile_metadata(profile)['synthetic'])
        self.assertTrue(any(c['family'] == 'accessory' for c in cases))

    def test_interpolation_copies_and_validates(self):
        case = self.motion.seed_cases(['FULL_BODY'])[0]
        changed = self.motion.interpolate_case(case, .125)
        self.assertEqual(changed['t'], .125)
        self.assertNotEqual(case['id'], changed['id'])
        changed['shape_values']['Fit'] = 1
        self.assertNotIn('Fit', case['shape_values'])
        for bad in (-.1, 1.1, float('nan')):
            with self.assertRaises(ValueError):
                self.motion.interpolate_case(case, bad)

    def test_refines_only_related_intervals_with_change_or_small_clearance(self):
        base = self.motion.seed_cases(['HEAD_HANDS'])[0]
        a = self.motion.interpolate_case(base, 0)
        b = self.motion.interpolate_case(base, .5)
        c = self.motion.interpolate_case(base, 1)
        measurements = [{'case': a, 'clearance_m': .02, 'collision': False},
                        {'case': b, 'clearance_m': .0002, 'collision': True},
                        {'case': c, 'clearance_m': .02, 'collision': False}]
        refined = self.motion.refinement_candidates(measurements, 1)
        self.assertEqual([r['t'] for r in refined], [.25])
        self.assertEqual(refined, self.motion.refinement_candidates(list(reversed(measurements)), 1))
        self.assertEqual(self.motion.refinement_candidates(measurements, 0), [])

    def test_refinement_uses_the_configured_clearance_warning(self):
        base = self.motion.seed_cases(['HEAD_HANDS'])[0]
        samples = [{'case': self.motion.interpolate_case(base, t), 'clearance_m': .005, 'collision': False}
                   for t in (0., 1.)]
        self.assertEqual(self.motion.refinement_candidates(samples, 2), [])
        self.assertEqual([c['t'] for c in self.motion.refinement_candidates(samples, 2, clearance_m=.01)], [.5])
        self.assertEqual(self.motion.refinement_candidates(samples, 2, clearance_m=.005), [])
        self.assertEqual(self.motion.refinement_candidates(samples, 2, clearance_m=0.), [])
        for threshold in (-1., float('nan'), True):
            with self.assertRaises(ValueError):
                self.motion.refinement_candidates(samples, 2, clearance_m=threshold)

    def test_motion_commands_bounded_mirrored_and_coupled(self):
        for case in self.motion.seed_cases(['FULL_BODY']):
            command = self.motion.motion_commands(case)
            self.assertTrue(command['rotations'])
            self.assertIn('contacts', command)
            for rotation in command['rotations']:
                self.assertLessEqual(abs(rotation['degrees']), 150)
        reach = next(c for c in self.motion.seed_cases(['FULL_BODY'])
                     if c['motion'] == 'reach_forward' and c['t'] == 1)
        names = {r['bone'] for r in self.motion.motion_commands(reach)['rotations']}
        self.assertTrue({'left_upper_arm', 'right_upper_arm', 'chest'} <= names)

    def test_rejects_ambiguous_inputs(self):
        for kwargs in ({'profiles': []}, {'profiles': ['OTHER']},
                       {'profiles': ['FULL_BODY'], 'steps': 1},
                       {'profiles': ['FULL_BODY'], 'budget': -1},
                       {'profiles': ['FULL_BODY'], 'shape_cases': [{'id': 'x', 'values': {'A': float('inf')}}]}):
            with self.assertRaises(ValueError):
                self.motion.seed_cases(**kwargs)

    def test_overhead_is_upward_from_left_outstretched_arm(self):
        case = next(c for c in self.motion.seed_cases(['FULL_BODY'])
                    if c['motion'] == 'reach_overhead' and c['t'] == 1)
        left = next(r for r in self.motion.motion_commands(case)['rotations']
                    if r['bone'] == 'left_upper_arm')
        self.assertGreater(left['degrees'], 0)

    def test_shoulder_sweeps_cover_down_side_up_and_twist_independently(self):
        cases = self.motion.seed_cases(['FULL_BODY'], budget=10000, steps=9)
        sweeps = [c for c in cases if c['family'] == 'shoulder']
        self.assertGreaterEqual(len({c['motion'] for c in sweeps}), 6)
        def rotations(name, t):
            case = next(c for c in sweeps if c['motion'] == name and c['t'] == t)
            return self.motion.motion_commands(case)['rotations']
        start, end = rotations('arm_side_sweep', 0), rotations('arm_side_sweep', 1)
        self.assertEqual(next(r['degrees'] for r in start if r['bone'] == 'left_upper_arm'), 15)
        self.assertEqual(next(r['degrees'] for r in end if r['bone'] == 'left_upper_arm'), 150)
        self.assertTrue({'left_shoulder', 'right_shoulder'} <= {r['bone'] for r in end})
        a = rotations('arm_side_twist_in', .5)
        b = rotations('arm_side_twist_out', .5)
        self.assertNotEqual(a, b)
        self.assertTrue(any(r['axis'] == 'bone' and r['bone'] == 'left_upper_arm' for r in a))

    def test_lateral_and_overhead_paths_are_distinct(self):
        self.assertNotEqual(self.motion.MOTIONS['reach_lateral'][1][0],
                            self.motion.MOTIONS['reach_overhead'][1][0])

    def test_unilateral_lower_body_has_reviewable_right_mirrors(self):
        cases = self.motion.seed_cases(['FULL_BODY'])
        for name in ('step', 'lunge', 'knee_lift', 'ankle'):
            left = next(c for c in cases if c['motion'] == name and c['t'] == 1)
            right = next(c for c in cases if c['motion'] == name + '_right' and c['t'] == 1)
            a = self.motion.motion_commands(left)
            b = self.motion.motion_commands(right)
            self.assertEqual(a['contacts']['left_foot'], b['contacts']['right_foot'])

    def test_shapes_keep_object_namespaces_independent(self):
        shapes = [{'id': 'same-key', 'values': {'body-id': {'Fit': .25}, 'shirt-id': {'Fit': .75}}}]
        cases = self.motion.seed_cases(['HEAD_HANDS'], shapes, budget=1)
        self.assertEqual(cases[0]['shape_values'], shapes[0]['values'])
        changed = self.motion.interpolate_case(cases[0], .5)
        changed['shape_values']['body-id']['Fit'] = 1
        self.assertEqual(cases[0]['shape_values']['body-id']['Fit'], .25)
        with self.assertRaises(ValueError):
            self.motion.seed_cases(['HEAD_HANDS'], [{'id': 'bad', 'values': {'body-id': {'Fit': float('nan')}}}])

    def test_accessory_subsets_have_distinct_deterministic_case_ids(self):
        base = next(c for c in self.motion.seed_cases(['HEAD_HANDS']) if c['family'] == 'accessory')
        a = self.motion.interpolate_case(dict(base, accessory_bones=['A'], accessory_axis='X'), .5)
        b = self.motion.interpolate_case(dict(base, accessory_bones=['B'], accessory_axis='X'), .5)
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual(a, self.motion.interpolate_case(a, .5))
        with self.assertRaises(ValueError):
            self.motion.interpolate_case(dict(base, accessory_axis='bad'), .5)
        end = self.motion.interpolate_case(b, 1)
        self.assertEqual(self.motion.refinement_candidates([
            {'case': self.motion.interpolate_case(a, 0), 'clearance_m': 0},
            {'case': end, 'clearance_m': 0}], 10), [])
        normal = self.motion.seed_cases(['HEAD_HANDS'])[0]
        with self.assertRaises(ValueError):
            self.motion.interpolate_case(dict(normal, accessory_axis='Y'), .5)


if __name__ == '__main__':
    unittest.main()
