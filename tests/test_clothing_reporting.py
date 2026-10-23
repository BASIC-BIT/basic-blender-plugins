"""Absolute findings remain visible when coverage cannot certify a clean fit."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'BASICs_shape_key_manager'
spec = importlib.util.spec_from_file_location('checks', ROOT / 'core/clothing_checks.py')
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
spec = importlib.util.spec_from_file_location(
    'fixture.operators.clothing_checks.reporting',
    ROOT / 'operators/clothing_checks/reporting.py')
reporting = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'bpy': ModuleType('bpy'), 'fixture.core.clothing_checks': checks}):
    spec.loader.exec_module(reporting)


def result(clipping):
    candidate = {'pair': ['body', 'shirt'], 'primary_id': 'shirt',
                 'crossing_faces': {'shirt': [2] if clipping else []},
                 'containment': {'shirt': 'UNKNOWN'},
                 'absolute_fit': 'CLIPPING' if clipping else 'INDETERMINATE'}
    return {'candidate': candidate, 'new': [], 'existing': [], 'worsened': [],
            'regression': 'NO_DETECTED_REGRESSION'}


class ClothingReportingTests(unittest.TestCase):
    def test_compaction_retains_faces_counts_and_hashes_complete_evidence(self):
        analysis = {'triangle_pairs': [[i, 0] for i in range(60)],
                    'polygon_pairs': [[i, 0] for i in range(60)],
                    'crossing_faces': {'shirt': list(range(60))}}
        compact = reporting.compact_analysis(analysis)
        self.assertEqual(compact['triangle_pairs_count'], 60)
        self.assertTrue(compact['polygon_pairs_truncated'])
        self.assertEqual(compact['crossing_faces']['shirt'], list(range(60)))
        self.assertEqual(len(compact['triangle_pairs']), 32)
        changed = dict(analysis, triangle_pairs=analysis['triangle_pairs'] + [[100, 0]])
        self.assertNotEqual(compact['evidence_hash'], reporting.compact_analysis(changed)['evidence_hash'])

    def test_positive_evidence_survives_unknown_and_incomplete_coverage(self):
        report = {'results': [result(True), result(False)], 'poses': [{'valid': False}],
                  'cases': [1], 'coverage': {}, 'status': 'RUNNING'}
        reporting.summarize(report)
        self.assertEqual(report['summary']['absolute_fit'], 'CLIPPING')
        self.assertEqual(report['summary']['coverage'], 'INCOMPLETE')
        self.assertEqual(report['summary']['unknown'], 1)
        self.assertEqual(report['summary']['absolute_unique_faces'], 1)

    def test_unknown_without_positive_evidence_stays_indeterminate(self):
        report = {'results': [result(False)], 'poses': [{'valid': True}],
                  'cases': [1], 'coverage': {}, 'status': 'COMPLETED'}
        reporting.summarize(report)
        self.assertEqual(report['summary']['absolute_fit'], 'INDETERMINATE')
        self.assertEqual(report['summary']['absolute_faces'], [])


if __name__ == '__main__':
    unittest.main()
