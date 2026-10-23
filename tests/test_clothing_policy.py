"""Endpoint-specific allowances preserve every disallowed partner."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'BASICs_shape_key_manager/core/clothing_policy.py'
SPEC = importlib.util.spec_from_file_location('clothing_policy', PATH)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class ClothingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.regions = {'shirt': {'hem': [0]}, 'body': {'waist': [1]}}
        self.allow = [{'kind': 'CROSSING', 'a': {'object_id': 'shirt', 'region': 'hem'},
                       'b': {'object_id': 'body', 'region': 'waist'}}]
        self.report = {'pair': ['body', 'shirt'], 'primary_id': 'shirt',
                       'polygon_pairs': [[1, 0], [2, 0]], 'triangle_pairs': [[4, 7], [5, 7]],
                       'crossing_faces': {'body': [1, 2], 'shirt': [0]},
                       'contained_faces': {}, 'contact_polygon_pairs': []}

    def test_allowed_face_keeps_disallowed_partner(self):
        result = policy.apply_policy(self.report, self.regions, self.allow)
        self.assertEqual(result['policy']['allowed_count'], 1)
        self.assertEqual(result['policy']['actionable_count'], 1)
        self.assertEqual(result['policy']['actionable_crossing_faces']['shirt'], [0])
        self.assertEqual(result['crossing_faces'], self.report['crossing_faces'])

    def test_wrong_pair_or_kind_is_not_allowed(self):
        self.allow[0]['kind'] = 'CONTACT'
        self.assertEqual(policy.apply_policy(self.report, self.regions, self.allow)
                         ['policy']['actionable_count'], 2)
        self.allow[0]['b']['object_id'] = 'other'
        with self.assertRaises(ValueError):
            policy.validate_policy(self.regions, self.allow)

    def test_missing_region_and_bad_face_rejected(self):
        self.allow[0]['a']['region'] = 'missing'
        with self.assertRaises(ValueError):
            policy.validate_policy(self.regions, self.allow)
        with self.assertRaises(ValueError):
            policy.validate_policy({'shirt': {'hem': [-1]}}, [])
        with self.assertRaises(ValueError):
            policy.validate_policy({'shirt': {'hem': []}}, [])

    def test_regional_body_eligibility_keeps_global_warning(self):
        result = policy.regional_plausibility({'shoulder': [1, 2], 'thigh': [8]}, [[8, 9]])
        self.assertEqual(result['shoulder']['status'], 'NO_LOCAL_CROSSINGS')
        self.assertEqual(result['thigh']['status'], 'LOCAL_CROSSINGS')
        self.assertEqual(result['shoulder']['global_crossing_count'], 1)
        self.assertEqual(result['shoulder']['containment'], 'UNCHANGED')

    def test_local_contacts_warn_and_baseline_is_not_reported_as_new(self):
        result = policy.regional_plausibility({'shoulder': [1], 'thigh': [8]},
                                              [[8, 9]], [[8, 9]], [[1, 3], [8, 9]])
        self.assertEqual(result['shoulder']['status'], 'LOCAL_CONTACTS')
        self.assertEqual(result['thigh']['new_crossing_pairs'], [])
        self.assertEqual(result['thigh']['baseline_crossing_pairs'], [[8, 9]])

    def test_self_kind_and_no_allowance_retains_full_evidence(self):
        report = dict(self.report, pair=['shirt', 'shirt'], kind='SELF',
                      polygon_pairs=[[0, 4]], crossing_faces={'shirt': [0, 4]})
        result = policy.apply_policy(report, self.regions, [])
        self.assertEqual(result['policy']['actionable_crossing_faces'], {'shirt': [0, 4]})

    def test_allowances_are_symmetric_but_never_hide_a_later_partner(self):
        self.allow[0]['a'], self.allow[0]['b'] = self.allow[0]['b'], self.allow[0]['a']
        report = dict(self.report, polygon_pairs=[[1, 0]] * 40 + [[2, 0]])
        result = policy.apply_policy(report, self.regions, self.allow)['policy']
        self.assertEqual(result['allowed_count'], 40)
        self.assertEqual(result['actionable_count'], 1)
        self.assertEqual(result['actionable_crossing_faces']['shirt'], [0])

    def test_hash_covers_untruncated_partner_evidence_and_settings(self):
        first = policy.apply_policy(self.report, self.regions, self.allow)
        changed = dict(self.report, polygon_pairs=self.report['polygon_pairs'] + [[9, 0]])
        second = policy.apply_policy(changed, self.regions, self.allow)
        self.assertNotEqual(first['policy']['raw_evidence_hash'], second['policy']['raw_evidence_hash'])
        self.assertNotEqual(policy.evidence_hash(self.allow), policy.evidence_hash([]))

    def test_containment_requires_its_own_explicit_kind(self):
        report = dict(self.report, polygon_pairs=[],
                      contained_polygon_pairs=[{'faces': [1, 0], 'source_id': 'shirt'}])
        self.assertEqual(policy.apply_policy(report, self.regions, self.allow)
                         ['policy']['actionable_count'], 1)
        self.allow[0]['kind'] = 'CONTAINED'
        self.assertEqual(policy.apply_policy(report, self.regions, self.allow)
                         ['policy']['allowed_count'], 1)

    def test_containment_only_marks_source_not_nearest_opposing_boundary(self):
        for source_id, expected, absolute in [('body', {'body': [7], 'shirt': []}, 'CLEAR'),
                                              ('shirt', {'body': [], 'shirt': [12]}, 'CLIPPING')]:
            with self.subTest(source_id=source_id):
                raw = dict(self.report, polygon_pairs=[], crossing_faces={'body': [], 'shirt': []},
                           contained_faces=expected, absolute_fit=absolute,
                           contained_polygon_pairs=[{'faces': [7, 12], 'source_id': source_id}])
                result = policy.apply_policy(raw, self.regions, [])
                self.assertEqual(result['policy']['actionable_contained_faces'], expected)
                self.assertEqual(policy.actionable_analysis(result)['absolute_fit'], absolute)

    def test_containment_allowance_still_matches_both_source_and_boundary_regions(self):
        raw = dict(self.report, polygon_pairs=[], contained_faces={'body': [1], 'shirt': []},
                   contained_polygon_pairs=[{'faces': [1, 0], 'source_id': 'body'},
                                            {'faces': [2, 0], 'source_id': 'body'}])
        self.allow[0]['kind'] = 'CONTAINED'
        result = policy.apply_policy(raw, self.regions, self.allow)
        self.assertEqual(result['policy']['allowed_count'], 1)
        self.assertEqual(result['policy']['actionable_contained_faces'], {'body': [2], 'shirt': []})
        raw['contained_polygon_pairs'][0]['source_id'] = 'outside_pair'
        with self.assertRaises(ValueError):
            policy.apply_policy(raw, self.regions, self.allow)

    def test_policy_boundary_rejects_malformed_inputs_and_rules(self):
        for regions, allowances in [(None, []), ({}, None), ({'': {}}, []),
                                     ({'shirt': []}, []), ({}, [{}]), ({}, ['CROSSING'])]:
            with self.subTest(regions=regions, allowances=allowances), self.assertRaises(ValueError):
                policy.validate_policy(regions, allowances)

    def test_actionable_view_keeps_raw_clipping_and_does_not_certify_allowed_contact(self):
        raw = dict(self.report, absolute_fit='CLIPPING')
        analyzed = policy.apply_policy(raw, self.regions, self.allow)
        actionable = policy.actionable_analysis(analyzed)
        self.assertEqual(actionable['absolute_fit'], 'CLIPPING')
        self.assertEqual(actionable['crossing_faces']['body'], [2])
        all_allowed = policy.apply_policy(dict(raw, polygon_pairs=[[1, 0]]), self.regions, self.allow)
        self.assertEqual(policy.actionable_analysis(all_allowed)['absolute_fit'], 'INDETERMINATE')
        self.assertEqual(all_allowed['absolute_fit'], 'CLIPPING')
        clear = policy.apply_policy(dict(raw, absolute_fit='CLEAR', primary_id=None, polygon_pairs=[]),
                                    self.regions, [])
        self.assertEqual(policy.actionable_analysis(clear)['absolute_fit'], 'CLEAR')


if __name__ == '__main__':
    unittest.main()
