"""Absolute findings remain visible when coverage cannot certify a clean fit."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'BASICs_shape_key_manager'
spec = importlib.util.spec_from_file_location('checks', ROOT / 'core/clothing_checks.py')
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
spec = importlib.util.spec_from_file_location('policy', ROOT / 'core/clothing_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
spec = importlib.util.spec_from_file_location(
    'fixture.operators.clothing_checks.reporting',
    ROOT / 'operators/clothing_checks/reporting.py')
reporting = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'bpy': ModuleType('bpy'), 'fixture.core.clothing_checks': checks}):
    spec.loader.exec_module(reporting)
spec = importlib.util.spec_from_file_location('fingerprints', ROOT / 'operators/clothing_checks/fingerprints.py')
fingerprints = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'bpy': ModuleType('bpy')}):
    spec.loader.exec_module(fingerprints)


def result(clipping):
    candidate = {'pair': ['body', 'shirt'], 'primary_id': 'shirt',
                 'crossing_faces': {'shirt': [2] if clipping else []},
                 'containment': {'shirt': 'UNKNOWN'},
                 'absolute_fit': 'CLIPPING' if clipping else 'INDETERMINATE'}
    return {'candidate': candidate, 'new': [], 'existing': [], 'worsened': [],
            'regression': 'NO_DETECTED_REGRESSION'}


class ClothingReportingTests(unittest.TestCase):
    def test_bone_deformation_state_excludes_creator_display_metadata(self):
        def prop(name, kind='FLOAT', readonly=False, array=False):
            return SimpleNamespace(identifier=name, type=kind, is_readonly=readonly, is_array=array)
        bone = SimpleNamespace(name='Arm', parent=SimpleNamespace(name='Chest'),
                               matrix_local=[[1., 0.], [0., 1.]], length=1., use_connect=False,
                               inherit_scale='FULL', use_relative_parent=False, envelope_weight=1.,
                               bbone_scalein=[1., 1., 1.], bbone_custom_handle_start=None,
                               bbone_custom_handle_end=None, show_wire=False, select=False,
                               collections=[object()], children=[object()], bbone_x=.1, bbone_z=.1)
        bone.bl_rna = SimpleNamespace(properties=[prop('inherit_scale', 'ENUM'),
            prop('use_relative_parent', 'BOOLEAN'), prop('envelope_weight'),
            prop('bbone_scalein', array=True), prop('show_wire', 'BOOLEAN'), prop('select', 'BOOLEAN'),
            prop('collections', 'COLLECTION', True), prop('children', 'COLLECTION', True),
            prop('bbone_x'), prop('bbone_z')])
        data = SimpleNamespace(bones=[bone])
        initial = fingerprints.bone_deformation_state(data)
        bone.show_wire, bone.select, bone.collections = True, True, []
        bone.bbone_x, bone.bbone_z = .5, .6
        self.assertEqual(fingerprints.bone_deformation_state(data), initial)
        for field, value in [('parent', None), ('use_connect', True), ('use_relative_parent', True),
                             ('inherit_scale', 'NONE'), ('envelope_weight', .5),
                             ('bbone_scalein', [1.1, 1., 1.]),
                             ('bbone_custom_handle_start', SimpleNamespace(name='Handle'))]:
            previous = getattr(bone, field)
            setattr(bone, field, value)
            self.assertNotEqual(fingerprints.bone_deformation_state(data), initial, field)
            setattr(bone, field, previous)

    def test_report_integrity_detects_edits_and_ignores_its_previous_hash(self):
        report = {'id': 'fixture', 'settings': {'clearance_m': .001}}
        with self.assertRaises(ValueError):
            reporting.validate_report(report)
        report['report_hash'] = reporting.report_digest(report)
        self.assertIs(reporting.validate_report(report), report)
        self.assertEqual(reporting.report_digest(dict(report, report_hash='old')), report['report_hash'])
        report['settings']['clearance_m'] = .1
        with self.assertRaises(ValueError):
            reporting.validate_report(report)
        with self.assertRaises(ValueError):
            reporting.validate_report([])

    def test_legacy_action_keyframe_edits_change_the_public_source_fingerprint(self):
        class Block(SimpleNamespace):
            def items(self):
                return {}.items()
        key = SimpleNamespace(co=[1., 0.], handle_left=[.5, 0.], handle_right=[1.5, 0.],
                              interpolation='BEZIER')
        curve = SimpleNamespace(data_path='location', array_index=0, extrapolation='CONSTANT',
                                keyframe_points=[key], modifiers=[], bl_rna=SimpleNamespace(properties=[]),
                                group=SimpleNamespace(name='Legacy group', mute=False))
        # Blender 4.3 actions expose fcurves without layered-action attributes.
        action = SimpleNamespace(name='Legacy', fcurves=[curve])
        matrix = [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]
        obj = Block(type='EMPTY', name_full='LegacySource', data=Block(), parent=None,
                    parent_type='OBJECT', parent_bone='', matrix_world=matrix, matrix_parent_inverse=matrix,
                    modifiers=[], constraints=[], animation_data=SimpleNamespace(action=action, drivers=[]))
        with patch.object(fingerprints, 'evaluate_sources'):
            before = fingerprints.fingerprint(obj)
            action.name = 'Creator renamed legacy Action'
            curve.group.name = 'Creator renamed legacy group'
            self.assertEqual(fingerprints.fingerprint(obj), before)
            curve.group.mute = True
            self.assertNotEqual(fingerprints.fingerprint(obj), before)
            curve.group.mute = False
            key.co[1] = .5
            self.assertNotEqual(fingerprints.fingerprint(obj), before)
            key.co[1] = 0.
            curve.modifiers.append(SimpleNamespace(type='GENERATOR', bl_rna=SimpleNamespace(properties=[])))
            self.assertNotEqual(fingerprints.fingerprint(obj), before)

    def test_legacy_action_curves_work_without_layers_or_slots(self):
        curve = SimpleNamespace(data_path='location', array_index=0)
        for action in (SimpleNamespace(fcurves=[curve]),
                       SimpleNamespace(fcurves=[curve], layers=[], slots=[])):
            self.assertEqual(fingerprints.action_curves(action), [curve])

    def test_available_layer_influence_and_mix_mode_are_semantic(self):
        class Block(SimpleNamespace):
            def items(self):
                return {}.items()
        curve = SimpleNamespace(data_path='location', array_index=0, extrapolation='CONSTANT',
                                keyframe_points=[], modifiers=[], bl_rna=SimpleNamespace(properties=[]))
        layer = SimpleNamespace(name='Layer', influence=1., mix_mode='REPLACE',
            strips=[SimpleNamespace(channelbag=lambda slot: SimpleNamespace(fcurves=[curve]))])
        action = SimpleNamespace(name='Experimental layered', layers=[layer],
                                 slots=[SimpleNamespace(target_id_type='OBJECT')])
        matrix = [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]
        obj = Block(type='EMPTY', name_full='LayerSource', data=Block(), parent=None,
                    parent_type='OBJECT', parent_bone='', matrix_world=matrix, matrix_parent_inverse=matrix,
                    modifiers=[], constraints=[], animation_data=SimpleNamespace(action=action, drivers=[]))
        with patch.object(fingerprints, 'evaluate_sources'):
            before = fingerprints.fingerprint(obj)
            layer.name = 'Creator renamed layer'
            self.assertEqual(fingerprints.fingerprint(obj), before)
            for field, value in [('influence', .25), ('mix_mode', 'ADD')]:
                previous = getattr(layer, field)
                setattr(layer, field, value)
                self.assertNotEqual(fingerprints.fingerprint(obj), before, field)
                setattr(layer, field, previous)

    def test_layered_action_curves_preserve_all_channelbags(self):
        first, second = object(), object()
        strip = SimpleNamespace(channelbag=lambda slot: SimpleNamespace(fcurves=[first, second]) if slot == 1 else None)
        action = SimpleNamespace(layers=[SimpleNamespace(strips=[strip])], slots=[0, 1])
        self.assertEqual(fingerprints.action_curves(action), [first, second])

    def test_compact_findings_preserve_complete_faces_and_reconstruct_actionable_results(self):
        identity = 'shirt-' + 'a' * 64
        faces = list(range(2000))
        analysis = {'pair': ['body', identity], 'primary_id': identity,
                    'crossing_faces': {identity: faces}, 'contained_faces': {},
                    'containment': {identity: 'UNKNOWN'}, 'absolute_fit': 'CLIPPING',
                    'polygon_pairs': [[0, face] for face in faces]}
        analysis = policy.apply_policy(analysis, {}, [])
        finding = checks.classify_pair(analysis, analysis)
        actionable = checks.classify_pair(policy.actionable_analysis(analysis), policy.actionable_analysis(analysis))
        finding['actionable'] = {key: value for key, value in actionable.items()
                                 if key not in {'reference', 'candidate'}}
        compact = reporting.compact_finding(finding)
        self.assertFalse('candidate_absolute' in compact, 'derived absolute faces were duplicated')
        self.assertEqual(compact['existing'], {identity: faces})
        self.assertEqual(compact['candidate']['crossing_faces'][identity], faces)
        self.assertEqual(compact['candidate']['policy']['actionable_crossing_faces'][identity], faces)
        reconstructed = checks.classify_pair(policy.actionable_analysis(compact['reference']),
                                             policy.actionable_analysis(compact['candidate']))
        self.assertEqual(compact['actionable']['absolute_fit'], reconstructed['absolute_fit'])
        self.assertEqual(compact['actionable']['regression'], reconstructed['regression'])
        self.assertEqual(compact['actionable']['existing_count'], len(reconstructed['existing']))
        self.assertEqual(compact['actionable']['evidence_hash'], policy.evidence_hash(finding['actionable']))
        rebuilt = {key: value for key, value in reconstructed.items() if key not in {'reference', 'candidate'}}
        self.assertEqual(compact['actionable']['evidence_hash'], policy.evidence_hash(rebuilt))
        self.assertFalse('candidate_absolute' in compact['actionable'], 'derived actionable faces were duplicated')
        self.assertLess(len(json.dumps(compact)), len(json.dumps(finding)) / 5)
        self.assertEqual(finding['existing'][1999], {'object_id': identity, 'face': 1999})

    def test_summary_counts_grouped_and_legacy_regression_faces(self):
        grouped, legacy = result(True), result(True)
        grouped.update(new={'shirt': [1, 2]}, existing={'body': [3], 'shirt': [4, 5]})
        legacy.update(new=[{'object_id': 'shirt', 'face': 6}])
        report = {'results': [grouped, legacy], 'poses': [{'valid': True}],
                  'cases': [1], 'coverage': {}, 'status': 'COMPLETED'}
        reporting.summarize(report)
        self.assertEqual(report['summary']['new_faces'], 3)
        self.assertEqual(report['summary']['existing_faces'], 3)

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

    def test_allowed_crossings_preserve_unknown_actionable_containment(self):
        finding = result(True)
        finding['candidate']['policy'] = {'allowed_count': 1, 'actionable_count': 0}
        finding['actionable'] = {'absolute_fit': 'INDETERMINATE'}
        report = {'results': [finding], 'poses': [{'valid': True}],
                  'cases': [1], 'coverage': {}, 'status': 'COMPLETED'}
        reporting.summarize(report)
        self.assertEqual(report['summary']['absolute_fit'], 'CLIPPING')
        self.assertEqual(report['summary']['unknown'], 0)
        self.assertEqual(report['summary']['actionable_fit'], 'INDETERMINATE')
        self.assertEqual(report['summary']['actionable_unknown'], 1)

    def test_actionable_clipping_survives_other_actionable_uncertainty(self):
        findings = [result(True), result(True)]
        for finding, status in zip(findings, ('INDETERMINATE', 'CLIPPING')):
            finding['candidate']['policy'] = {'allowed_count': 0, 'actionable_count': 1}
            finding['actionable'] = {'absolute_fit': status}
        report = {'results': findings, 'poses': [{'valid': True}],
                  'cases': [1], 'coverage': {}, 'status': 'COMPLETED'}
        reporting.summarize(report)
        self.assertEqual(report['summary']['actionable_fit'], 'CLIPPING')
        self.assertEqual(report['summary']['actionable_unknown'], 1)


if __name__ == '__main__':
    unittest.main()
