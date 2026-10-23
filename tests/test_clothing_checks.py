"""Blender-free regression and weight-audit policy."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'BASICs_shape_key_manager/core/clothing_checks.py'
SPEC = importlib.util.spec_from_file_location('clothing_checks', PATH)
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)


def finding(pair=('body', 'shirt'), faces=(2,), depth=None, supported=True):
    return {'pair': list(pair), 'crossing_faces': {pair[1]: list(faces)},
            'contained_faces': {}, 'depths_m': {pair[1]: {'2': depth}} if depth else {},
            'triangle_pairs': [], 'containment': {key: 'SUPPORTED' if supported
                                                else 'UNKNOWN' for key in pair},
            'absolute_fit': 'CLIPPING' if faces else 'CLEAR'}


class ClothingChecksTests(unittest.TestCase):
    def test_self_pair_requires_explicit_kind_and_keeps_real_owner(self):
        report = finding(pair=('shirt', 'shirt'))
        with self.assertRaises(ValueError):
            checks.absolute_findings(report)
        report['kind'] = 'SELF'
        result = checks.classify_pair(report, report)
        self.assertEqual(result['pair'], ['shirt', 'shirt'])
        self.assertEqual(result['candidate_absolute']['crossing'], [{'object_id': 'shirt', 'face': 2}])

    def test_clean_self_scope_does_not_upgrade_open_body_containment(self):
        report = finding(pair=('shirt', 'shirt'), faces=(), supported=False)
        report.update(kind='SELF', scope='NONADJACENT_TRIANGLE_CROSSINGS',
                      containment={'shirt': 'NOT_APPLICABLE'}, sampling_complete=True)
        self.assertEqual(checks.classify_pair(report, report)['absolute_fit'], 'CLEAR')
        body_pair = finding(faces=(), supported=False)
        self.assertEqual(checks.classify_pair(body_pair, body_pair)['absolute_fit'], 'INDETERMINATE')
        report['scope'] = 'UNSUPPORTED'
        self.assertEqual(checks.classify_pair(report, report)['absolute_fit'], 'INDETERMINATE')

    def test_new_existing_resolved_face_identity(self):
        result = checks.classify_pair(finding(faces=(1, 2)), finding(faces=(2, 3)))
        self.assertEqual(result['new'], [{'object_id': 'shirt', 'face': 3}])
        self.assertEqual(result['existing'], [{'object_id': 'shirt', 'face': 2}])
        self.assertEqual(result['resolved'], [{'object_id': 'shirt', 'face': 1}])
        self.assertEqual(result['regression'], 'REGRESSION')

    def test_changed_partner_triangle_is_existing(self):
        before, after = finding(), finding()
        before['triangle_pairs'], after['triangle_pairs'] = [[0, 1]], [[8, 1]]
        result = checks.classify_pair(before, after)
        self.assertEqual(result['new'], [])
        self.assertEqual(result['regression'], 'NO_DETECTED_REGRESSION')

    def test_identical_clipping_is_still_an_absolute_finding(self):
        result = checks.classify_pair(finding(), finding())
        self.assertEqual(result['regression'], 'NO_DETECTED_REGRESSION')
        self.assertEqual(result['absolute_fit'], 'CLIPPING')
        self.assertEqual(result['candidate_absolute']['affected'],
                         [{'object_id': 'shirt', 'face': 2}])

    def test_absolute_clear_does_not_depend_on_reference_support(self):
        result = checks.classify_pair(finding(faces=(), supported=False), finding(faces=()))
        self.assertEqual(result['absolute_fit'], 'CLEAR')

    def test_absolute_containment_survives_unknown_reference(self):
        before, after = finding(faces=(), supported=False), finding(faces=())
        after['contained_faces'] = {'shirt': [2]}
        result = checks.classify_pair(before, after)
        self.assertEqual(result['regression'], 'INDETERMINATE')
        self.assertEqual(result['absolute_fit'], 'CLIPPING')
        self.assertEqual(result['candidate_absolute']['contained'],
                         [{'object_id': 'shirt', 'face': 2}])

    def test_absolute_summary_keeps_existing_faces_with_unknown_pairs(self):
        clipped = checks.classify_pair(finding(), finding())
        unknown = checks.classify_pair(finding(faces=(), supported=False),
                                       finding(faces=(), supported=False))
        result = checks.summarize_absolute([clipped, clipped, unknown])
        self.assertEqual(result['candidate_clipping_pairs'], 2)
        self.assertEqual(result['absolute_crossing_faces'], 2)
        self.assertEqual(result['absolute_contained_faces'], 0)
        self.assertEqual(result['absolute_unique_faces'], 1)
        self.assertEqual(result['absolute_faces'],
                         [{'pair': ['body', 'shirt'], 'object_id': 'shirt', 'face': 2}])

    def test_absolute_owner_and_unsupported_containment(self):
        report = finding()
        report['primary_id'] = 'shirt'
        report['contained_faces'] = {'body': [0]}
        result = checks.absolute_findings(report)
        self.assertEqual(result['contained'], [])
        report['contained_faces'] = {'shirt': [3]}
        report['containment']['shirt'] = 'UNKNOWN'
        self.assertEqual(checks.absolute_findings(report)['contained'], [])
        report['primary_id'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'primary'):
            checks.absolute_findings(report)

    def test_changed_body_face_partner_is_not_a_new_garment_region(self):
        before, after = finding(), finding()
        before['primary_id'] = after['primary_id'] = 'shirt'
        before['crossing_faces']['body'] = [1]
        after['crossing_faces']['body'] = [8]
        result = checks.classify_pair(before, after)
        self.assertEqual(result['new'], [])
        self.assertEqual(result['existing'], [{'object_id': 'shirt', 'face': 2}])

    def test_different_object_pair_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'pair'):
            checks.classify_pair(finding(), finding(pair=('pants', 'shirt')))

    def test_supported_depth_worsening_and_threshold(self):
        result = checks.classify_pair(finding(depth=.001), finding(depth=.002))
        self.assertEqual(result['worsened'][0]['face'], 2)
        self.assertAlmostEqual(result['worsened'][0]['delta_m'], .001)
        result = checks.classify_pair(finding(depth=.001), finding(depth=.0014))
        self.assertEqual(result['worsened'], [])

    def test_missing_sampled_depth_remains_unknown_for_existing_crossing(self):
        result = checks.classify_pair(finding(), finding())
        self.assertEqual(result['depth_status'], 'UNKNOWN')

    def test_containment_cannot_be_new_when_reference_volume_was_unknown(self):
        before, after = finding(faces=(), supported=False), finding(faces=())
        after['contained_faces'] = {'shirt': [2]}
        result = checks.classify_pair(before, after)
        self.assertEqual(result['new'], [])
        self.assertEqual(result['unclassified'], [{'object_id': 'shirt', 'face': 2}])
        self.assertEqual(result['regression'], 'INDETERMINATE')

    def test_boundary_rejects_malformed_reports(self):
        for key, value in [('pair', 'body'), ('pair', ['x', 'x']),
                           ('crossing_faces', {'other': [1]}),
                           ('crossing_faces', {'shirt': [-1]}),
                           ('depths_m', {'shirt': {'2': -1}})]:
            report = finding()
            report[key] = value
            with self.assertRaises(ValueError):
                checks.classify_pair(report, finding())
        bad = finding()
        bad['primary_id'] = 'body'
        with self.assertRaises(ValueError):
            checks.classify_pair(bad, finding())

    def test_boundary_rejects_invalid_audit_inputs(self):
        for rows, deform, locked, cap in [([{}], set(), set(), 0),
                                          ([{}], set(), {'unknown'}, 4),
                                          ([{'': 1}], set(), set(), 4),
                                          ([{'bone': '1'}], {'bone'}, set(), 4)]:
            with self.assertRaises(ValueError):
                checks.audit_weights(rows, deform, locked, cap=cap)
        result = checks.audit_weights([{}], {'lock'}, {'lock'}, baseline_rows=[{}])
        self.assertEqual(result['protected_changes'], [])

    def test_unknown_depth_and_open_mesh_cannot_pass_absolute(self):
        result = checks.classify_pair(finding(faces=(), supported=False),
                                     finding(faces=(), supported=False))
        self.assertEqual(result['depth_status'], 'UNKNOWN')
        self.assertEqual(result['absolute_fit'], 'INDETERMINATE')

    def test_primary_supported_depth_ignores_open_garment_volume(self):
        before, after = finding(depth=.001), finding(depth=.002)
        for report in (before, after):
            report['primary_id'] = 'shirt'
            report['containment']['body'] = 'UNKNOWN'
        result = checks.classify_pair(before, after)
        self.assertEqual(result['depth_status'], 'SUPPORTED')
        self.assertEqual(len(result['worsened']), 1)

    def test_containing_body_in_closed_outer_garment_is_not_primary_clipping(self):
        report = finding(faces=())
        report['primary_id'] = 'shirt'
        report['contained_faces'] = {'body': [0]}
        result = checks.classify_pair(report, report)
        self.assertEqual(result['absolute_fit'], 'CLEAR')

    def test_coverage_distinguishes_unknown_incomplete_and_complete(self):
        self.assertEqual(checks.coverage_status(1, 0, 0, 0)['coverage'], 'COMPLETE')
        for counts in [(1, 1, 0, 0), (1, 0, 1, 0), (0, 0, 0, 0)]:
            self.assertEqual(checks.coverage_status(*counts)['coverage'], 'INCOMPLETE')
        self.assertEqual(checks.coverage_status(1, 0, 0, 1)['absolute_fit'], 'INDETERMINATE')
        with self.assertRaises(ValueError):
            checks.coverage_status(-1, 0, 0, 0)

    def test_audit_cap_missing_normalization_and_protected_share(self):
        rows = [{'bone': .6, 'lock': .2, 'gone': .1}, {'bone': 1, 'mask': .4}]
        result = checks.audit_weights(rows, {'bone', 'lock'}, {'lock'},
                                      baseline_rows=[{'bone': .5, 'lock': .5}, {'bone': 1}], cap=1)
        self.assertEqual(result['cap_violations'], [0])
        self.assertEqual(result['unnormalized'], [0])
        self.assertEqual(result['missing_bones'], [{'vertex': 0, 'name': 'gone', 'weight': .1},
                                                  {'vertex': 1, 'name': 'mask', 'weight': .4}])
        self.assertEqual(result['protected_changes'][0]['vertex'], 0)
        self.assertEqual(rows[0]['lock'], .2)

    def test_audit_protected_share_uses_normalized_deform_total(self):
        result = checks.audit_weights([{'bone': 1, 'lock': 1}], {'bone', 'lock'}, {'lock'},
                                      baseline_rows=[{'bone': .5, 'lock': .5}])
        self.assertEqual(result['protected_changes'], [])

    def test_invalid_weights_and_configuration_are_rejected(self):
        for value in [-1, float('inf'), float('nan')]:
            with self.assertRaises(ValueError):
                checks.audit_weights([{'bone': value}], {'bone'}, set())
        with self.assertRaises(ValueError):
            checks.audit_weights([{}], set(), set(), baseline_rows=[])
        with self.assertRaises(ValueError):
            checks.classify_pair(finding(), finding(), worsening_m=-1)


if __name__ == '__main__':
    unittest.main()
