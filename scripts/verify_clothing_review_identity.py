"""Action semantics and retained scene/object identity, factory fixtures only."""
from pathlib import Path
import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('identity_fixture',ROOT/'scripts/verify_clothing_review_state.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
session,preview=fixture.session,fixture.preview
PACKAGE=fixture.PACKAGE
fingerprints=importlib.import_module(PACKAGE+'.operators.clothing_checks.fingerprints')
reporting=importlib.import_module(PACKAGE+'.operators.clothing_checks.reporting')
assert bpy.app.background


def action_identity():
    body,rig,pairs,mapping,settings=fixture.fixture.setup('ActionIdentity')
    body.keyframe_insert(data_path='location',frame=1)
    action=body.animation_data.action
    objects=[body,rig,pairs[0]['reference'],pairs[0]['candidate']]
    ids=fixture.identities.capture_source_ids(objects)
    before=fingerprints.fingerprint_inputs(objects,ids)
    action.name='Creator renamed active Action'
    assert fingerprints.fingerprint_inputs(objects,ids)==before,'active Action display name changed source hash'
    curve=fingerprints.action_curves(action)[0];value=curve.keyframe_points[0].co.y
    curve.keyframe_points[0].co.y=value+.2
    assert fingerprints.fingerprint_inputs(objects,ids)!=before,'meaningful active Action edit was ignored'
    curve.keyframe_points[0].co.y=value
    extra=action.slots.new(id_type='OBJECT',name='Additional slot')
    bag=action.layers[0].strips[0].channelbag(extra,ensure=True)
    bag.fcurves.new('location',index=0).keyframe_points.insert(1,.4)
    before=fingerprints.fingerprint_inputs(objects,ids);slot=body.animation_data.action_slot
    body.animation_data.action_slot=extra
    assert fingerprints.fingerprint_inputs(objects,ids)!=before,'Action slot assignment was ignored'
    body.animation_data.action_slot=slot
    different=action.copy();fingerprints.action_curves(different)[0].keyframe_points[0].co.y+=.3
    body.animation_data.action=different
    assert fingerprints.fingerprint_inputs(objects,ids)!=before,'different Action assignment was ignored'
    body.animation_data.action=action;body.animation_data.action_slot=slot
    record=fixture.fixture.baseline.capture_baseline(bpy.context,body,rig,[pairs[0]['candidate']])
    pairs[0]['reference']=bpy.data.objects[record['pairs'][0]['reference']]
    frozen=bpy.data.objects[record['body']]
    retained=frozen['basic_clothing_action'];old=fingerprints.fingerprint_inputs([frozen])
    retained.name='Creator renamed retained inactive Action'
    assert fingerprints.fingerprint_inputs([frozen])==old,'retained inactive Action display name changed hash'
    worker=session.ValidationSession(bpy.context,body,rig,pairs,mapping,settings);worker.cancel()
    key=fingerprints.action_curves(retained)[0].keyframe_points[0];value=key.co.y;key.co.y=value+.1
    fixture.fixture.fixture.reject(lambda:session.ValidationSession(bpy.context,body,rig,pairs,mapping,settings),'modified retained baseline')
    key.co.y=value
    print('ACTION_DISPLAY_IDENTITY_OK active=1 retained=1 curves_stale=1 slots_stale=1')


def action_group_settings():
    body,rig,pairs,mapping,settings=fixture.fixture.setup('ActionGroupSettings')
    body.keyframe_insert(data_path='location',frame=1,group='Authored group')
    action=body.animation_data.action;group=fingerprints.action_curves(action)[0].group
    before=fingerprints.fingerprint_inputs([body]);group.name='Renamed group';group.select=False
    assert fingerprints.fingerprint_inputs([body])==before,'group display labels changed source hash'
    group.mute=True
    assert fingerprints.fingerprint_inputs([body])!=before,'Action group mute omitted from source hash'
    group.mute=False
    print('ACTION_GROUP_SETTINGS_OK active_mute=1 display_rename=1')


def retained_action_group_settings():
    body,rig,pairs,mapping,settings=fixture.fixture.setup('RetainedActionGroupSettings')
    body.keyframe_insert(data_path='location',frame=1,group='Retained group')
    record=fixture.fixture.baseline.capture_baseline(bpy.context,body,rig,[pairs[0]['candidate']])
    reference=bpy.data.objects[record['pairs'][0]['reference']]
    pairs[0]['reference']=reference;scene=bpy.data.scenes[record['scene']]
    frozen=bpy.data.objects[record['body']]
    retained=frozen['basic_clothing_action'];group=fingerprints.action_curves(retained)[0].group
    before=fingerprints.fingerprint_inputs(list(scene.objects));group.name='Renamed frozen group'
    assert fingerprints.fingerprint_inputs(list(scene.objects))==before
    worker=session.ValidationSession(bpy.context,body,rig,pairs,mapping,settings);worker.cancel()
    scene['fixture_action_group_sources']={'body':body,'rig':rig,'reference':reference,
                                          'candidate':pairs[0]['candidate'],'frozen':frozen}
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'retained-group.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path))
        command=[bpy.app.binary_path,'--background','--factory-startup',str(path),'--python-exit-code','9',
                 '--python',str(Path(__file__)),'--','--reopen-action-group',scene.name]
        if '--installed-extension' in sys.argv:command.append('--installed-extension')
        result=subprocess.run(command,capture_output=True,text=True)
        assert result.returncode==0 and 'RETAINED_ACTION_GROUP_REOPEN_OK' in result.stdout,result.stdout+result.stderr
    _reject_retained_group_edit(scene,body,rig,pairs,mapping,settings,group)
    print('RETAINED_ACTION_GROUP_SETTINGS_OK inactive_mute=1 display_rename=1 fresh_reopen=1 prewrite=1')


def _reject_retained_group_edit(scene,body,rig,pairs,mapping,settings,group):
    working=[body,rig,pairs[0]['candidate']]
    before=fingerprints.fingerprint_inputs(working);accepted=scene['_basic_clothing_baseline_state']
    group.mute=True
    altered=fingerprints.fingerprint_inputs(list(scene.objects));allocations=fixture.allocations()
    fixture.fixture.fixture.reject(lambda:session.ValidationSession(bpy.context,body,rig,pairs,mapping,settings),
                                   'modified retained baseline')
    assert fixture.allocations()==allocations and scene['_basic_clothing_baseline_state']==accepted
    assert fingerprints.fingerprint_inputs(working)==before
    assert fingerprints.fingerprint_inputs(list(scene.objects))==altered


def source_scale():
    previous=bpy.context.scene;bpy.context.window.scene=bpy.data.scenes.new('Captured source scale fixture')
    report,sources,before=fixture.make_report()
    source=bpy.context.scene;review=bpy.data.scenes[report['review_scene']]
    accepted=review['_basic_clothing_review_state'];owned=fingerprints.fingerprint_inputs(list(review.objects))
    source.unit_settings.scale_length=.01
    try:fixture.fixture.fixture.reject(lambda:preview.preview_failure(bpy.context,report),'source scene scale')
    finally:source.unit_settings.scale_length=report['unit_scale']
    assert fingerprints.fingerprint_inputs(list(review.objects))==owned and review['_basic_clothing_review_state']==accepted
    other=bpy.data.scenes.new('Different preview context');other.unit_settings.scale_length=.1
    source.name='Renamed original source Scene';bpy.context.window.scene=other
    preview.preview_failure(bpy.context,report);preview.clear_preview(bpy.context)
    assert bpy.context.scene==other,'preview guessed context instead of captured source Scene'
    source_binding=review.get('_basic_clothing_source_scene')
    del review['_basic_clothing_source_scene']
    altered=fingerprints.fingerprint_inputs(list(review.objects));accepted=review['_basic_clothing_review_state']
    fixture.fixture.fixture.reject(lambda:preview.preview_failure(bpy.context,report),'source scene')
    assert fingerprints.fingerprint_inputs(list(review.objects))==altered and review['_basic_clothing_review_state']==accepted
    review['_basic_clothing_source_scene']=source_binding
    bpy.context.window.scene=source
    assert session.fingerprint_inputs(sources)==before
    bpy.context.window.scene=other
    bpy.data.scenes.remove(source)
    altered=fingerprints.fingerprint_inputs(list(review.objects));accepted=review['_basic_clothing_review_state']
    fixture.fixture.fixture.reject(lambda:preview.preview_failure(bpy.context,report),'source scene')
    assert fingerprints.fingerprint_inputs(list(review.objects))==altered and review['_basic_clothing_review_state']==accepted
    bpy.context.window.scene=previous
    print('SOURCE_SCENE_SCALE_IDENTITY_OK changed_rejected=1 other_context=1 missing_rejected=1 deleted_rejected=1')


def renamed_report():
    body,rig,pairs,mapping,settings=fixture.fixture.setup('RenamedReview',captured=True)
    body.keyframe_insert(data_path='location',frame=1)
    # Recapture after authoring the Action, then capture another garment independently.
    a=pairs[0]['candidate'];b=fixture.fixture.fixture.mesh('SecondGarment',rig,.05)
    pairs=[]
    for garment in (a,b):
        record=fixture.fixture.baseline.capture_baseline(bpy.context,body,rig,[garment])
        pairs.append(dict(reference=bpy.data.objects[record['pairs'][0]['reference']],candidate=garment,confirmed=True))
    for key in a.data.shape_keys.key_blocks:
        for point,delta in zip(key.data,(-.04,.04,.04)):point.co.z+=delta
    values={session.logical_id(pairs[0]['reference']):{'Fit':.8},
            session.logical_id(pairs[1]['reference']):{'Fit':.6},session.logical_id(body):{'Fit':.7}}
    base=settings['cases'][0]
    settings.update(cases=[base,fixture.fixture.fixture.ik_fixture.motion.interpolate_case(
        dict(base,shape_case='combined',shape_values=values),.75)],budget=2,
        shape_cases=[{'id':'current','values':{}},{'id':'combined','values':values}])
    sources=[body,rig,*[o for pair in pairs for o in (pair['reference'],pair['candidate'])]]
    before=session.fingerprint_inputs(sources)
    report=session.run_validation(bpy.context,body,rig,pairs,mapping,settings)
    assert report['status']=='COMPLETED',report['errors']
    assert any(any(result['candidate']['crossing_faces'].values()) for result in report['results']),'fixture needs real face findings'
    return report,sources,before


def review_rename():
    report,sources,before=renamed_report()
    scene=bpy.data.scenes[report['review_scene']]
    for index,obj in enumerate(scene.objects):
        obj.name='Renamed retained object '+str(index);obj.data.name='Renamed retained data '+str(index)
        if isinstance(obj.get('basic_clothing_action'),bpy.types.Action):
            obj['basic_clothing_action'].name='Renamed inactive Action '+str(index)
    sources[0].animation_data.action.name='Renamed active source Action'
    for index,result in enumerate(report['results']):
        for side in ('REFERENCE','CANDIDATE'):
            preview.preview_failure(bpy.context,report,index,side)
            actual=fixture.identities.resolve_review_objects(scene,report)
            effective=importlib.import_module(PACKAGE+'.operators.clothing_checks.shapes').effective_shapes(bpy.context,scene,scene.objects)
            pose=report['poses'][result['pose_index']]
            analysis=result['reference' if side=='REFERENCE' else 'candidate']
            for obj,key in actual.items():
                if obj.type!='MESH':continue
                expected=set(analysis['crossing_faces'].get(report['objects'][key]['id'],[]))|set(analysis['contained_faces'].get(report['objects'][key]['id'],[]))
                assert {p.index for p in obj.data.polygons if p.select}==expected
                assert effective.get(obj.name,{})==pose['effective_shape_values'].get(key,{})
            preview.clear_preview(bpy.context)
    scene.name='Renamed retained review Scene'
    preview.preview_failure(bpy.context,report);preview.clear_preview(bpy.context)
    assert session.fingerprint_inputs(sources)==before
    scene['fixture_identity_report']=bpy.data.texts[report['text']]
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'renamed-review.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path))
        command=[bpy.app.binary_path,'--background','--factory-startup',str(path),'--python-exit-code','9','--python',str(Path(__file__)),'--','--reopen-review',scene.name]
        if '--installed-extension' in sys.argv:command.append('--installed-extension')
        result=subprocess.run(command,capture_output=True,text=True)
        assert result.returncode==0 and 'RENAMED_REVIEW_REOPEN_OK' in result.stdout,result.stdout+result.stderr
    bindings={key:{'object':row['object'],'key':row['key']} for key,row in scene['_basic_clothing_report_objects'].items()}
    del scene['_basic_clothing_report_objects']
    owned=fingerprints.fingerprint_inputs(list(scene.objects));accepted=scene['_basic_clothing_review_state']
    fixture.fixture.fixture.reject(lambda:preview.preview_failure(bpy.context,report),'object bindings')
    assert fingerprints.fingerprint_inputs(list(scene.objects))==owned and scene['_basic_clothing_review_state']==accepted
    scene['_basic_clothing_report_objects']=bindings
    for kind in ('swapped','aliased'):
        altered={key:dict(row) for key,row in bindings.items()};keys=list(altered)
        if kind=='swapped':
            altered[keys[0]]['object'],altered[keys[1]]['object']=altered[keys[1]]['object'],altered[keys[0]]['object']
        else:altered['extra']=dict(altered[keys[0]])
        scene['_basic_clothing_report_objects']=altered
        fixture.fixture.fixture.reject(lambda:preview.preview_failure(bpy.context,report),
            'modified retained review' if kind=='swapped' else 'object bindings')
        assert fingerprints.fingerprint_inputs(list(scene.objects))==owned and scene['_basic_clothing_review_state']==accepted
        scene['_basic_clothing_report_objects']=bindings
    print('REVIEW_BINDING_INTEGRITY_OK missing=1 swapped=1 aliased=1 prewrite_preservation=1')
    print('RETAINED_REVIEW_RENAME_OK both_sides=1 shapes=1 actual_faces=1 separate_captures=2 actions=1 scene=1 fresh_reopen=1')


def subset_dependencies():
    for kind in ('parent','key_driver'):
        body,rig,pairs,mapping,settings=fixture.fixture.setup('Subset'+kind)
        a=pairs[0]['candidate'];b=fixture.fixture.fixture.mesh('UnselectedDependency'+kind,rig,.07)
        if kind=='parent':a.parent=b
        else:
            curve=a.data.shape_keys.driver_add('key_blocks["Fit"].value');curve.driver.type='AVERAGE'
            variable=curve.driver.variables.new();variable.type='SINGLE_PROP'
            variable.targets[0].id_type='KEY';variable.targets[0].id=b.data.shape_keys
            variable.targets[0].data_path='key_blocks["Fit"].value'
        record=fixture.fixture.baseline.capture_baseline(bpy.context,body,rig,[a,b])
        reference=bpy.data.objects[record['pairs'][0]['reference']]
        a.parent=None
        if kind=='key_driver':a.data.shape_keys.driver_remove('key_blocks["Fit"].value')
        selected=[dict(reference=reference,candidate=a,confirmed=True)]
        source=[body,rig,a,*bpy.data.scenes[record['scene']].objects]
        before=session.fingerprint_inputs(source)
        worker=session.ValidationSession(bpy.context,body,rig,selected,mapping,settings)
        dependency=bpy.data.objects[record['pairs'][1]['reference']]
        assert dependency in worker.copies
        clone=worker.copies[dependency]
        assert clone.get('_basic_clothing_role')=='DEPENDENCY' and clone.hide_get(view_layer=worker.scene.view_layers[0])
        worker.cancel();assert session.fingerprint_inputs(source)==before
        if kind=='parent':a.parent=b
        else:
            curve=a.data.shape_keys.driver_add('key_blocks["Fit"].value');curve.driver.type='AVERAGE'
            variable=curve.driver.variables.new();variable.type='SINGLE_PROP';variable.targets[0].id_type='KEY'
            variable.targets[0].id=b.data.shape_keys;variable.targets[0].data_path='key_blocks["Fit"].value'
        altered=session.fingerprint_inputs(source+[b]);allocations=fixture.allocations()
        fixture.fixture.fixture.reject(lambda:session.ValidationSession(bpy.context,body,rig,selected,mapping,settings),'outside')
        assert session.fingerprint_inputs(source+[b])==altered and fixture.allocations()==allocations
        a.parent=None
        if kind=='key_driver':a.data.shape_keys.driver_remove('key_blocks["Fit"].value')
        scene=bpy.data.scenes[record['scene']]
        scene['fixture_subset_sources']={'body':body,'rig':rig,'reference':reference,'candidate':a}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'subset.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path))
            command=[bpy.app.binary_path,'--background','--factory-startup',str(path),'--python-exit-code','9','--python',str(Path(__file__)),'--','--reopen-subset',scene.name]
            if '--installed-extension' in sys.argv:command.append('--installed-extension')
            result=subprocess.run(command,capture_output=True,text=True)
            assert result.returncode==0 and 'SUBSET_REOPEN_OK' in result.stdout,result.stdout+result.stderr
    print('CAPTURED_SUBSET_DEPENDENCIES_OK parent=1 key_driver=1 fresh_reopen=1 hidden=1')


if __name__=='__main__':
    if '--reopen-action-group' in sys.argv:
        scene=bpy.data.scenes[sys.argv[sys.argv.index('--reopen-action-group')+1]]
        saved=scene['fixture_action_group_sources'];body,rig=saved['body'],saved['rig']
        pairs=[dict(reference=saved['reference'],candidate=saved['candidate'],confirmed=True)]
        mapping=fixture.fixture.fixture.ik_fixture.confirmed(rig)
        worker=session.ValidationSession(bpy.context,body,rig,pairs,mapping,{});worker.cancel()
        group=fingerprints.action_curves(saved['frozen']['basic_clothing_action'])[0].group
        _reject_retained_group_edit(scene,body,rig,pairs,mapping,{},group)
        print('RETAINED_ACTION_GROUP_REOPEN_OK')
    elif '--reopen-review' in sys.argv:
        scene=bpy.data.scenes[sys.argv[sys.argv.index('--reopen-review')+1]]
        report=reporting.parse_report(scene['fixture_identity_report'].as_string())
        preview.preview_failure(bpy.context,report);preview.clear_preview(bpy.context)
        source=scene['_basic_clothing_source_scene']
        owned=fingerprints.fingerprint_inputs(list(scene.objects));accepted=scene['_basic_clothing_review_state']
        source.unit_settings.scale_length*=2
        fixture.fixture.fixture.reject(lambda:preview.preview_failure(bpy.context,report),'source scene scale')
        assert fingerprints.fingerprint_inputs(list(scene.objects))==owned and scene['_basic_clothing_review_state']==accepted
        source.unit_settings.scale_length=report['unit_scale']
        body=next(obj for obj in fixture.identities.read_source_ids(scene) if obj.animation_data and obj.animation_data.action)
        fingerprints.action_curves(body.animation_data.action)[0].keyframe_points[0].co.y+=.2
        fixture.fixture.fixture.reject(lambda:preview.preview_failure(bpy.context,report),'stale preview')
        assert fingerprints.fingerprint_inputs(list(scene.objects))==owned and scene['_basic_clothing_review_state']==accepted
        print('RENAMED_REVIEW_REOPEN_OK')
    elif '--reopen-subset' in sys.argv:
        scene=bpy.data.scenes[sys.argv[sys.argv.index('--reopen-subset')+1]];saved=scene['fixture_subset_sources']
        mapping=fixture.fixture.fixture.ik_fixture.confirmed(saved['rig'])
        worker=session.ValidationSession(bpy.context,saved['body'],saved['rig'],[dict(reference=saved['reference'],candidate=saved['candidate'],confirmed=True)],mapping,{})
        worker.cancel();print('SUBSET_REOPEN_OK')
    else:
        cases={'action':action_identity,'action_groups':action_group_settings,
               'retained_groups':retained_action_group_settings,
               'scale':source_scale,'rename':review_rename,'subset':subset_dependencies}
        for name in ([sys.argv[sys.argv.index('--case')+1]] if '--case' in sys.argv else cases):cases[name]()
        print('CLOTHING_REVIEW_IDENTITY_OK')
