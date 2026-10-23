"""One main-thread timer session shared by native UI and synchronous callers."""
from copy import deepcopy
from itertools import combinations
import json
import uuid
import bpy
from ...core.clothing_checks import classify_pair
from ...core.clothing_motion import trajectory_key
from ...core.clothing_policy import (apply_policy, actionable_analysis, validate_policy,
                                     regional_plausibility, evidence_hash)
from .geometry import snapshot_mesh, analyze_pair, analyze_self, body_self_crossings, body_self_contacts
from .regions import capture_regions
from .inputs import (main_thread, preflight, owned_copies, remove_scene,
                     fingerprint_inputs, logical_id, data_blocks)
from .rig import IKMotionRig, resolve_mapping
from .identities import resolve_bindings, retain_bindings
from .sampling import prepare, refinements, coverage
from .reporting import compact_finding, weight_report, summarize, persist
from .shapes import effective_shapes, requested_mismatches


class ValidationSession:
    """Own all mutations. step returns True when terminal, including failures."""
    def __init__(self, context, body, rig, pairs, mapping, settings):
        main_thread()
        self.context, self.scene, self.motion = context, None, None
        self.closed, self.retained, self.current = False, False, None
        self.settings, self.queue, self.expected = prepare(settings)
        rows, self.sources = preflight(body, rig, pairs)
        mapping = resolve_mapping(rig, mapping)
        self.fingerprints = fingerprint_inputs(self.sources)
        self.scale = context.scene.unit_settings.scale_length
        self.depth, self.measurements, self.stable = 0, [], {}
        self.neutral_crossings = {}
        self.owner = uuid.uuid4().hex
        self.report = {'id': self.owner, 'status': 'RUNNING', 'blender': bpy.app.version_string,
                       'fingerprint_format': 'BASIC-CLOTHING-BINARY-1',
                       'regression_face_encoding': 'OBJECT_ID_TO_SOURCE_FACE_LIST',
                       'approximation': 'Synthetic constrained IK; not VRChat emulation or continuous collision proof',
                       'inputs': self.fingerprints, 'mapping': mapping, 'unit_scale': self.scale,
                       'settings': deepcopy(self.settings), 'cases': [], 'poses': [], 'results': [],
                       'weights': {}, 'errors': [], 'exclusions': [], 'omissions': [
                           'Runtime physics and runtime parity are not evaluated',
                           'Self containment is not evaluated; SELF scope is nonadjacent triangle crossings'],
                       'objects': {}, 'coverage': {}}
        try:
            self.scene = bpy.data.scenes.new('BASIC Clothing Review ' + self.owner[:8])
            self.scene['_basic_clothing_owner'], self.scene['_basic_clothing_kind'] = self.owner, 'JOB'
            self.scene.unit_settings.scale_length = self.scale
            self.copies = owned_copies(self.scene, self.sources, self.owner)
            self.body, self.rig = self.copies[body], self.copies[rig]
            for clone in self.copies.values():
                clone['_basic_clothing_role'] = 'DEPENDENCY'
                if clone.type == 'ARMATURE' and clone != self.rig:
                    clone.hide_set(True, view_layer=self.scene.view_layers[0])
            body_id, _ = resolve_bindings(body, pairs)
            self.body['_basic_clothing_id'] = body_id
            self.report['bindings'] = retain_bindings(self.scene, body, body_id, rows)
            self.body['_basic_clothing_role'] = 'BODY'
            self.rig['_basic_clothing_role'] = 'RIG'
            self.rig.data.pose_position = 'POSE'
            for key in ('bend_directions', 'accessory_bones'):
                if key in self.settings:
                    self.rig['basic_clothing_' + key] = json.dumps(self.settings[key], allow_nan=False)
            self.pairs = []
            for ref, candidate, identity in rows:
                before, after = self.copies[ref], self.copies[candidate]
                if before == after:
                    raise ValueError('capture an independent baseline before comparing')
                for copy, role in [(before, 'REFERENCE'), (after, 'CANDIDATE')]:
                    copy['_basic_clothing_id'], copy['_basic_clothing_role'] = identity, role
                self.pairs.append((before, after, identity))
                self.report['weights'][identity] = weight_report(ref, candidate, rig)
            for source, clone in self.copies.items():
                if clone.parent and clone.parent.type == 'ARMATURE':
                    world = clone.matrix_world.copy()
                    clone.parent = self.rig
                    clone.matrix_world = world
                if clone.get('_basic_clothing_role') == 'DEPENDENCY':
                    clone.hide_set(True, view_layer=self.scene.view_layers[0])
                self.report['objects'][clone.name] = {'source': source.name_full,
                    'id': logical_id(clone), 'role': clone.get('_basic_clothing_role', 'DEPENDENCY')}
                if clone.type == 'MESH':
                    for mod in clone.modifiers:
                        mod.object = self.rig
            for block in data_blocks(list(self.copies.values())):
                if block.animation_data:
                    for curve in block.animation_data.drivers:
                        for variable in curve.driver.variables:
                            for target in variable.targets:
                                if isinstance(target.id, bpy.types.Object) and target.id.type == 'ARMATURE':
                                    target.id = self.rig
            self.shape_current = {o: {k.name: k.value for k in o.data.shape_keys.key_blocks}
                                  for o in self.scene.objects if o.type == 'MESH' and o.data.shape_keys}
            for obj, values in self.shape_current.items():
                self.report['objects'][obj.name]['shape_current'] = values
            selected_keys = {}
            for shape in self.settings['shape_cases']:
                for identity, keys in shape['values'].items():
                    selected_keys.setdefault(identity, set()).update(keys)
            self.report['untested_shape_keys'] = {obj.name: [name for name in values
                    if name != obj.data.shape_keys.reference_key.name and name not in selected_keys.get(logical_id(obj), set())]
                    for obj, values in self.shape_current.items()}
            self.report['unselected_motion_families'] = sorted(
                {'neutral', 'reach', 'arm', 'shoulder', 'torso', 'lower_body', 'coordination', 'accessory'} - set(self.settings['families']))
            self.report['unselected_profiles'] = sorted({'HEAD_HANDS', 'FULL_BODY'} - set(self.settings['profiles']))
            self._capture_templates()
            self.regions = capture_regions([self.body, *[o for p in self.pairs for o in p[:2]]],
                                          self.settings.setdefault('region_definitions', {}))
            validate_policy(self.regions, self.settings.setdefault('contact_allowances', []))
            self.report['settings'] = deepcopy(self.settings)
            self.report['regions'] = deepcopy(self.regions)
            self.report['settings_hash'] = evidence_hash(self.settings)
            self.motion = IKMotionRig(self.rig, mapping, self.scene, self.scale)
            self.report['calibration'] = {'axes': {k: list(v) for k, v in self.motion.calibration['axes'].items()},
                                          'height_blender_units': self.motion.calibration['height'],
                                          'bend_directions': {k: list(v) for k, v in self.motion.calibration['poles'].items()}}
            self.jobs = [('BODY', self.body, a, self.body, b, identity)
                         for a, b, identity in self.pairs]
            self.jobs.extend(('GARMENT', a[0], b[0], a[1], b[1], None)
                             for a, b in combinations(self.pairs, 2))
            self.jobs.extend(('SELF', a, a, b, b, identity) for a, b, identity in self.pairs)
            self._update_coverage([])
        except Exception:
            self.close()
            raise

    def _capture_templates(self):
        with self.context.temp_override(scene=self.scene, view_layer=self.scene.view_layers[0]):
            self.scene.view_layers[0].update()
            graph = self.context.evaluated_depsgraph_get()
            for obj in [self.body, *[p[0] for p in self.pairs]]:
                snapshot = snapshot_mesh(obj, graph, unit_scale=self.scale)
                self.stable[obj] = {key: snapshot[key] for key in
                    ('id', 'topology', 'triangles', 'polygons', '_probe_layout') if key in snapshot}
            for reference, candidate, _ in self.pairs:
                self.stable[candidate] = self.stable[reference]

    def _snapshots(self, objects=None):
        with self.context.temp_override(scene=self.scene, view_layer=self.scene.view_layers[0]):
            self.scene.view_layers[0].update()
            graph = self.context.evaluated_depsgraph_get()
            snapshots = {}
            for obj in dict.fromkeys(objects or [self.body, *[o for p in self.pairs for o in p[:2]]]):
                snapshots[obj] = snapshot_mesh(obj, graph, self.stable[obj], self.scale)
            return snapshots

    def _begin_case(self, case):
        values = case['shape_values']
        known = {logical_id(o) for o in self.shape_current}
        if any(identity not in known for identity in values):
            raise ValueError('shape case names an unknown logical object ID')
        for obj, captured in self.shape_current.items():
            requested = values.get(logical_id(obj), {})
            if any(name not in captured for name in requested):
                raise ValueError('shape case names a missing key')
            for key in obj.data.shape_keys.key_blocks:
                key.value = requested.get(key.name, captured[key.name])
        solved = self.motion.apply(case)
        snapshots = self._snapshots()
        effective = effective_shapes(self.context, self.scene, self.scene.objects)
        mismatches = requested_mismatches(self.scene.objects, values, effective)
        if mismatches:
            self.report['unsupported_shape_values'] = mismatches
            self.report['rejected_case'] = deepcopy(case)
            raise ValueError('requested shape values differ from effective evaluated values: ' +
                             json.dumps(mismatches, allow_nan=False))
        solved['effective_shape_values'] = effective
        crossings = body_self_crossings(snapshots[self.body])
        shape = case['shape_case']
        plain_neutral = case['motion'] == 'neutral' and not any(key in case for key in
            ('controls', 'target_offsets_m', 'accessory_bones', 'accessory_axis', 'phase', 'sequence'))
        if shape not in self.neutral_crossings and plain_neutral:
            self.neutral_crossings[shape] = crossings
        elif shape not in self.neutral_crossings:
            # Establish neutral explicitly even when a replay starts elsewhere.
            neutral = dict(profile=case['profile'], motion='neutral', t=0.,
                           shape_case=shape, shape_values=deepcopy(values))
            self.motion.apply(neutral)
            self.neutral_crossings[shape] = body_self_crossings(self._snapshots([self.body])[self.body])
            self.motion.apply(case)
        solved['body_self_crossings_new'] = [list(p) for p in sorted(crossings - self.neutral_crossings[shape])]
        solved['body_self_crossings_baseline'] = [list(p) for p in sorted(self.neutral_crossings[shape])]
        solved['body_self_crossing_screen'] = 'NEW_CROSSINGS' if solved['body_self_crossings_new'] else 'NO_NEW_CROSSINGS'
        solved['regional_body_plausibility'] = regional_plausibility(
            self.regions.get(logical_id(self.body), {}), sorted(crossings),
            sorted(self.neutral_crossings[shape]), sorted(body_self_contacts(snapshots[self.body])))
        index = len(self.report['poses'])
        self.report['poses'].append(solved)
        self.current = {'case': case, 'pose': index, 'snapshots': snapshots, 'job': 0,
                        'collision': False, 'clearance_m': None, 'displacement_m': 0.}
        # Bounded representative probes guide search only, never collision certification.
        self.current['probes'] = [point for snapshot in snapshots.values()
                                 for point in snapshot['points'][::max(1, len(snapshot['points']) // 16)][:16]]

    def _pair(self):
        current = self.current
        kind, ra, rb, ca, cb, primary = self.jobs[current['job']]
        snapshots = current['snapshots']
        options = {k: self.settings[k] for k in ('contact_m', 'clearance_m', 'sample_limit')}
        if kind == 'SELF':
            reference = analyze_self(snapshots[ra], self.settings['contact_m'])
            candidate = analyze_self(snapshots[ca], self.settings['contact_m'])
        else:
            reference = analyze_pair(snapshots[ra], snapshots[rb], primary_id=primary, **options)
            candidate = analyze_pair(snapshots[ca], snapshots[cb], primary_id=primary, **options)
        reference, candidate = [apply_policy(analysis, self.regions, self.settings['contact_allowances'])
                                for analysis in (reference, candidate)]
        finding = classify_pair(reference, candidate, self.settings['worsening_m'])
        actionable = classify_pair(actionable_analysis(reference), actionable_analysis(candidate),
                                   self.settings['worsening_m'])
        finding['actionable'] = {key: value for key, value in actionable.items()
                                 if key not in {'reference', 'candidate'}}
        result = compact_finding(finding)
        result.update(case_id=current['case']['id'], pose_index=current['pose'], kind=kind,
                      pose_valid=self.report['poses'][current['pose']]['valid'],
                      plausibility=self.report['poses'][current['pose']]['plausibility'])
        self.report['results'].append(result)
        current['collision'] |= candidate['absolute_fit'] == 'CLIPPING'
        gap = candidate['clearance_m']
        if gap is not None:
            previous = current['clearance_m']
            current['clearance_m'] = gap if previous is None else min(previous, gap)
        current['job'] += 1

    def _update_coverage(self, truncated):
        self.report['coverage'] = coverage(self.report['cases'], self.expected, truncated, self.settings)
        if ('replay_coverage' in self.settings and self.report['status'] == 'COMPLETED' and
                len(self.report['cases']) == len(self.settings.get('cases', []))):
            original = self.settings['replay_coverage']
            self.report['coverage']['truncated_intervals'] = deepcopy(original.get('truncated_intervals', []))
            self.report['coverage']['status'] = original['status']
            self.report['coverage']['replayed_saved_cases'] = True
        summarize(self.report)

    def _finish(self):
        self.report['status'] = 'COMPLETED'
        self._update_coverage(self.truncated)
        self.scene.use_fake_user = True
        self.scene['_basic_clothing_kind'] = 'REVIEW'
        persist(self.report, self.scene)
        self.retained = True
        self.close()

    def step(self):
        main_thread()
        if self.report['status'] != 'RUNNING':
            return True
        try:
            if self.current is None and (fingerprint_inputs(self.sources) != self.fingerprints or
                    self.context.scene.unit_settings.scale_length != self.scale):
                self.report['status'] = 'STALE'
                self.report['errors'].append('Source inputs changed during evaluation')
                self.close()
                return True
            if self.current is not None:
                self._pair()
                if self.current['job'] == len(self.jobs):
                    measurement = {k: self.current[k] for k in ('case', 'collision', 'clearance_m', 'displacement_m')}
                    measurement['probes'] = self.current['probes']
                    for earlier in self.measurements:
                        if trajectory_key(earlier['case']) == trajectory_key(measurement['case']):
                            displacement = max((sum((a[i] - b[i]) ** 2 for i in range(3)) ** .5
                                                for a, b in zip(earlier['probes'], measurement['probes'])), default=0.)
                            measurement['displacement_m'] = max(measurement['displacement_m'], displacement)
                    if measurement['clearance_m'] is None:
                        measurement.pop('clearance_m')
                    self.measurements.append(measurement)
                    self.report['cases'].append(self.current['case'])
                    self.current = None
                    self._update_coverage([])
                return False
            if self.queue:
                self._begin_case(self.queue.pop(0))
                return False
            pending = [] if 'cases' in self.settings else refinements(self.measurements, self.depth, self.settings)
            remaining = self.settings['budget'] - len(self.report['cases'])
            if pending and remaining:
                self.queue = pending[:remaining]
                self.depth += 1
                self.truncated = pending[remaining:]
                return False
            # A depth bound is declared, but unresolved intervals still need disclosure.
            unresolved = [] if 'cases' in self.settings else refinements(self.measurements, 0, self.settings)
            self.truncated = getattr(self, 'truncated', []) + unresolved
            self._finish()
            return True
        except Exception as exc:
            self.report['status'] = 'ERROR'
            self.report['errors'].append(f'{type(exc).__name__}: {exc}')
            self.close()
            return True

    def cancel(self):
        if self.report['status'] == 'RUNNING':
            self.report['status'] = 'CANCELLED'
        self.close()

    def close(self):
        if self.closed:
            return
        if hasattr(self, 'report') and self.report['status'] == 'RUNNING':
            self.report['status'] = 'CANCELLED'
        try:
            if self.motion:
                self.motion.close()
        finally:
            if self.scene and not self.retained:
                remove_scene(self.scene, self.owner)
                self.scene = None
            self.closed = True
            if hasattr(self, 'report'):
                self._update_coverage(getattr(self, 'truncated', []))
            self.current, self.stable = None, {}


def run_validation(context, body, rig, pairs, mapping, settings, progress=None, cancelled=None):
    session = ValidationSession(context, body, rig, pairs, mapping, settings)
    try:
        while session.report['status'] == 'RUNNING':
            if cancelled and cancelled():
                session.cancel()
                break
            session.step()
            if progress:
                progress(deepcopy(session.report['summary']))
        return deepcopy(session.report)
    finally:
        session.close()


__all__ = ['ValidationSession', 'run_validation', 'fingerprint_inputs']
