"""Immutable baseline closure and native envelope reach on factory data."""
from pathlib import Path
import importlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import bpy
from mathutils import Matrix, Vector

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('boundary_fixture', ROOT/'scripts/verify_clothing_session_regressions.py')
fixture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
session, baseline = fixture.session, fixture.baseline
PACKAGE=fixture.fixture.PACKAGE
assert bpy.app.background


def counts():
    return tuple(len(getattr(bpy.data, name)) for name in ('objects','meshes','armatures','shape_keys','scenes','actions'))


def baseline_integrity():
    body, rig, pairs, mapping, settings=fixture.setup('ImmutableBaseline')
    rig['capture_value']=.2
    candidate=pairs[0]['candidate']
    candidate.data.shape_keys.key_blocks['Fit'].data[0].co.z+=.05
    curve=candidate.data.shape_keys.driver_add('key_blocks["Fit"].value')
    curve.driver.type='AVERAGE'
    variable=curve.driver.variables.new();variable.type='SINGLE_PROP'
    variable.targets[0].id=rig;variable.targets[0].data_path='["capture_value"]'
    record=baseline.capture_baseline(bpy.context,body,rig,[candidate])
    pairs[0]['reference']=bpy.data.objects[record['pairs'][0]['reference']]
    reference=pairs[0]['reference']
    scene=next(s for s in reference.users_scene if s.get('_basic_clothing_kind')=='BASELINE')
    frozen_rig=reference.modifiers[0].object
    sources=list(dict.fromkeys([body,rig,pairs[0]['candidate'],*scene.objects]))
    def run():
        before,allocations=session.fingerprint_inputs(sources),counts()
        worker=session.ValidationSession(bpy.context,body,rig,pairs,mapping,settings)
        worker.cancel()
        assert session.fingerprint_inputs(sources)==before and counts()==allocations
    run()
    def reject_edit(name,write,restore):
        write()
        modified, allocations=session.fingerprint_inputs(sources),counts()
        accepted=scene.get('_basic_clothing_baseline_state')
        fixture.fixture.reject(run,'modified retained baseline')
        assert session.fingerprint_inputs(sources)==modified and counts()==allocations,name
        assert scene.get('_basic_clothing_baseline_state')==accepted,name
        restore()
        run()
    point=reference.data.shape_keys.key_blocks['Basis'].data[0].co.copy()
    reject_edit('rest_mesh',lambda:setattr(reference.data.shape_keys.key_blocks['Basis'].data[0],'co',point+Vector((.01,0,0))),
                lambda:setattr(reference.data.shape_keys.key_blocks['Basis'].data[0],'co',point))
    group=reference.vertex_groups['hips'];weight=group.weight(0)
    reject_edit('weight',lambda:group.add([0],.4,'REPLACE'),lambda:group.add([0],weight,'REPLACE'))
    key=reference.data.shape_keys.key_blocks['Fit'];point=key.data[0].co.copy()
    reject_edit('shape',lambda:setattr(key.data[0],'co',point+Vector((0,0,.01))),lambda:setattr(key.data[0],'co',point))
    reject_edit('driver_dependency',lambda:frozen_rig.__setitem__('capture_value',.9),
                lambda:frozen_rig.__setitem__('capture_value',.2))
    # A copied driver dependency is part of the immutable closure too.
    reference.name='Renamed frozen garment';frozen_rig.name='Renamed frozen rig';frozen_rig.data.name='Renamed frozen rig data'
    reference.active_shape_key_index=1;reference.data.polygons[0].select=True
    run()
    body_hash=reference['_basic_clothing_baseline_body']
    del reference['_basic_clothing_baseline_body']
    altered,allocations=session.fingerprint_inputs(sources),counts()
    fixture.fixture.reject(run,'recapture')
    assert session.fingerprint_inputs(sources)==altered and counts()==allocations
    reference['_basic_clothing_baseline_body']=body_hash
    owner=reference['_basic_clothing_owner'];del reference['_basic_clothing_owner']
    altered,allocations=session.fingerprint_inputs(sources),counts()
    fixture.fixture.reject(run,'recapture')
    assert session.fingerprint_inputs(sources)==altered and counts()==allocations
    reference['_basic_clothing_owner']=owner
    source_scene=bpy.context.scene
    scene.collection.objects.unlink(reference);source_scene.collection.objects.link(reference)
    altered,allocations=session.fingerprint_inputs(sources),counts()
    fixture.fixture.reject(run,'recapture')
    assert session.fingerprint_inputs(sources)==altered and counts()==allocations
    source_scene.collection.objects.unlink(reference);scene.collection.objects.link(reference)
    run()
    scene['fixture_boundary_sources']={'body':body,'rig':rig,'reference':reference,'candidate':pairs[0]['candidate']}
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'immutable-baseline.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        command=[bpy.app.binary_path,'--background','--factory-startup',str(path),'--python-exit-code','9',
                 '--python',str(Path(__file__)),'--','--reopen',scene.name]
        if '--installed-extension' in sys.argv:command.append('--installed-extension')
        result=subprocess.run(command,capture_output=True,text=True)
        assert result.returncode==0 and 'BASELINE_FRESH_REOPEN_OK' in result.stdout,result.stdout+result.stderr
    accepted=scene['_basic_clothing_baseline_state']
    del scene['_basic_clothing_baseline_state']
    fixture.fixture.reject(run,'recapture')
    preserved=session.fingerprint_inputs(sources)
    record=baseline.capture_baseline(bpy.context,body,rig,[reference])
    assert session.fingerprint_inputs(sources)==preserved
    fresh=bpy.data.objects[record['pairs'][0]['reference']]
    worker=session.ValidationSession(bpy.context,body,rig,[dict(reference=fresh,candidate=pairs[0]['candidate'],confirmed=True)],mapping,settings)
    worker.cancel()
    assert '_basic_clothing_baseline_state' not in scene,'read stamped missing baseline state'
    scene['_basic_clothing_baseline_state']=accepted
    print('IMMUTABLE_BASELINE_CLOSURE_OK edits=4 rename_reopen=1 legacy_recapture=1')


def reopen():
    scene=bpy.data.scenes[sys.argv[sys.argv.index('--reopen')+1]]
    saved=scene['fixture_boundary_sources']
    pairs=[dict(reference=saved['reference'],candidate=saved['candidate'],confirmed=True)]
    mapping=fixture.fixture.ik_fixture.confirmed(saved['rig'])
    worker=session.ValidationSession(bpy.context,saved['body'],saved['rig'],pairs,mapping,{})
    worker.cancel()
    saved['reference'].data.shape_keys.key_blocks['Fit'].data[0].co.x+=.02
    before=session.fingerprint_inputs(list(scene.objects));allocations=counts()
    fixture.fixture.reject(lambda:session.ValidationSession(bpy.context,saved['body'],saved['rig'],pairs,mapping,{}),
                           'modified retained baseline')
    assert session.fingerprint_inputs(list(scene.objects))==before and counts()==allocations
    print('BASELINE_FRESH_REOPEN_OK')


def envelope_reach():
    for kind in ('outside','zero_radius','zero_weight','masked','shape_keys'):
        body,rig,pairs,mapping,settings=fixture.setup('Envelope'+kind)
        mod=body.modifiers[0];mod.use_vertex_groups=False;mod.use_bone_envelopes=True
        if kind!='shape_keys':body.shape_key_clear()
        if kind=='outside':body.location.x=100
        elif kind=='zero_radius':
            for bone in rig.data.bones:
                bone.head_radius=bone.tail_radius=bone.envelope_distance=0
        elif kind=='zero_weight':
            for bone in rig.data.bones:bone.envelope_weight=0
        elif kind=='masked':mod.vertex_group=body.vertex_groups.new(name='EmptyMask').name
        sources=[body,rig,pairs[0]['reference'],pairs[0]['candidate']]
        before,allocations=session.fingerprint_inputs(sources),counts()
        fixture.fixture.reject(lambda:session.ValidationSession(bpy.context,body,rig,pairs,mapping,settings),
                               'unsupported' if kind=='shape_keys' else 'body')
        assert session.fingerprint_inputs(sources)==before and counts()==allocations,kind
    for kind in ('native','transformed','offset_compensated','inverted_mask','weighted_shape','multiply'):
        body,rig,pairs,mapping,settings=fixture.setup('Reach'+kind)
        if kind!='weighted_shape':body.shape_key_clear()
        mod=body.modifiers[0]
        mod.use_vertex_groups=kind in {'weighted_shape','multiply'};mod.use_bone_envelopes=kind!='multiply'
        if kind=='multiply':
            for bone in rig.data.bones:bone.use_envelope_multiply=True
        if kind=='transformed':
            transform=Matrix.Translation((2,-3,1))@Matrix.Rotation(.4,4,'Z')@Matrix.Diagonal((1.4,.8,1.1,1))
            for obj in [rig,body,*[o for p in pairs for o in (p['reference'],p['candidate'])]]:obj.matrix_world=transform
        elif kind=='inverted_mask':
            mod.vertex_group=body.vertex_groups.new(name='EmptyMask').name;mod.invert_vertex_group=True
        elif kind=='offset_compensated':
            body.location.x=3
            for vertex in body.data.vertices:vertex.co.x-=3
        worker=session.ValidationSession(bpy.context,body,rig,pairs,mapping,settings)
        def positions():
            worker.scene.view_layers[0].update()
            evaluated=worker.body.evaluated_get(worker.scene.view_layers[0].depsgraph)
            return [evaluated.matrix_world@v.co for v in evaluated.data.vertices]
        initial=positions();worker.rig.pose.bones['hips'].location.x+=.1
        assert any((a-b).length>.001 for a,b in zip(initial,positions())),kind
        worker.cancel()
    print('NATIVE_ENVELOPE_REACH_OK rejected=5 moving=6 transformed=1 weighted_shapes=1')


def envelope_weight_semantics():
    inputs=importlib.import_module(PACKAGE+'.operators.clothing_checks.inputs')
    errors=[]
    for weighted in (True,False):
        for weight in (0,.5,1,2):
            for distance in (.25,.4):
                body,rig,pairs,mapping,settings=fixture.setup('EnvelopeWeight')
                body.shape_key_clear()
                for bone in rig.data.bones:
                    bone.use_deform=bone.name=='hips';bone.use_envelope_multiply=True
                    bone.head_radius=bone.tail_radius=.1;bone.envelope_distance=.2;bone.envelope_weight=weight
                for vertex in body.data.vertices:vertex.co=(distance,0,1.05)
                mod=body.modifiers[0];mod.use_vertex_groups=weighted;mod.use_bone_envelopes=not weighted
                mask=body.vertex_groups.new(name='ReachMask');mask.add([0,1,2],.5,'REPLACE');mod.vertex_group=mask.name
                transform=Matrix.Translation((2,-3,1))@Matrix.Rotation(.4,4,'Z')@Matrix.Diagonal((1.4,.8,1.1,1))
                for obj in [rig,body,*[o for p in pairs for o in (p['reference'],p['candidate'])]]:obj.matrix_world=transform
                sources=[body,rig,pairs[0]['reference'],pairs[0]['candidate']]
                inputs.evaluate_sources(sources)
                before,allocations=session.fingerprint_inputs(sources),counts()
                def position():
                    bpy.context.view_layer.update()
                    return body.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices[0].co.copy()
                initial=position();rig.pose.bones['hips'].location.x=.1
                moved=(position()-initial).length>.001
                rig.pose.bones['hips'].location.x=0;inputs.evaluate_sources(sources)
                expected=distance<.3 and (weighted or weight>0)
                assert moved==expected,('native oracle',weighted,weight,distance,moved)
                try:inputs.preflight(body,rig,pairs);accepted=True
                except ValueError as error:
                    assert 'body' in str(error),str(error)
                    accepted=False
                assert session.fingerprint_inputs(sources)==before and counts()==allocations
                print('ENVELOPE_NATIVE_PARITY',weighted,weight,distance,'moved='+str(moved),'accepted='+str(accepted))
                if accepted!=moved:errors.append((weighted,weight,distance,moved,accepted))
    assert not errors,errors
    print('ENVELOPE_WEIGHT_NATIVE_PARITY_OK cases=16 transformed_masked=16')


def posed_body_influence():
    motion=fixture.fixture.ik_fixture.motion
    for profile in ('HEAD_HANDS','FULL_BODY'):
        for angled in (False,True):
            for group_name in ('Independent','IndependentEnvelope','MappedPelvis','Follower'):
                body,rig,pairs,mapping,settings=fixture.setup('PosedBody')
                bpy.context.view_layer.objects.active=rig;rig.select_set(True)
                bpy.ops.object.mode_set(mode='EDIT')
                for name,parent in (('Independent',None),('Follower','chest')):
                    bone=rig.data.edit_bones.new(name);bone.head=(0,0,1.4);bone.tail=(0,0,1.5)
                    bone.parent=rig.data.edit_bones[parent] if parent else None
                if angled:
                    for side,sign in (('left',1),('right',-1)):
                        root=rig.data.edit_bones[side+'_upper_arm'].head.copy()
                        rotation=Matrix.Rotation(.78539816339*sign,3,'Y')
                        for part in ('upper_arm','forearm','hand'):
                            bone=rig.data.edit_bones[side+'_'+part]
                            bone.head=root+rotation@(bone.head-root);bone.tail=root+rotation@(bone.tail-root)
                bpy.ops.object.mode_set(mode='OBJECT');rig.select_set(False)
                rig.data.bones['hips'].name='MappedPelvis';mapping['hips']='MappedPelvis'
                body.shape_key_clear();body.vertex_groups.clear()
                body.vertex_groups.new(name='Independent' if group_name=='IndependentEnvelope' else group_name).add([0,1,2],1,'REPLACE')
                # A real independent VG must suppress otherwise reachable mapped envelopes.
                body.modifiers[0].use_bone_envelopes=True
                if group_name=='IndependentEnvelope':
                    body.modifiers[0].use_vertex_groups=False
                    for bone in rig.data.bones:
                        bone.use_deform=bone.name=='Independent';bone.envelope_distance=10
                mask=body.vertex_groups.new(name='BodyMask');mask.add([0,1,2],.5,'REPLACE')
                body.modifiers[0].vertex_group=mask.name
                transform=Matrix.Translation((2,-3,1))@Matrix.Rotation(.4,4,'Z')@Matrix.Diagonal((1.4,.8,1.1,1))
                sources=[rig,body,*[o for p in pairs for o in (p['reference'],p['candidate'])]]
                for obj in sources:obj.matrix_world=transform
                inputs=importlib.import_module(PACKAGE+'.operators.clothing_checks.inputs');inputs.evaluate_sources(sources)
                case=next(c for c in motion.seed_cases([profile]) if c['motion']=='torso_bend' and c['t']==1)
                def positions():
                    bpy.context.view_layer.update()
                    return [v.co.copy() for v in body.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
                initial=positions()
                with fixture.fixture.ik_fixture.native.IKMotionRig(rig,mapping,bpy.context.scene) as control:
                    control.apply(case);moved=any((a-b).length>.001 for a,b in zip(initial,positions()))
                assert moved==(not group_name.startswith('Independent')),(profile,angled,group_name,moved)
                inputs.evaluate_sources(sources)
                if group_name.startswith('Independent'):
                    record=baseline.capture_baseline(bpy.context,body,rig,[pairs[0]['candidate']])
                    assert bpy.data.scenes.get(record['scene']),'generic baseline capture requires no mapping'
                before,allocations=session.fingerprint_inputs(sources),counts()
                settings.update(cases=[case],profiles=[profile])
                if not moved:
                    fixture.fixture.reject(lambda:session.ValidationSession(bpy.context,body,rig,pairs,mapping,settings),'posed mapping')
                else:
                    worker=session.ValidationSession(bpy.context,body,rig,pairs,mapping,settings)
                    assert any('coplanar' in omission for omission in worker.report['omissions'])
                    worker.cancel()
                assert session.fingerprint_inputs(sources)==before and counts()==allocations
    print('POSED_BODY_INFLUENCE_OK rejected=8 moving=8 profiles=2 rests=2 transformed_masked=16')


if __name__=='__main__':
    if '--reopen' in sys.argv:reopen()
    else:
        cases={'baseline':baseline_integrity,'envelope':envelope_reach,'envelope_weights':envelope_weight_semantics,
               'posed_body':posed_body_influence}
        for name in ([sys.argv[sys.argv.index('--case')+1]] if '--case' in sys.argv else cases):cases[name]()
        print('CLOTHING_BASELINE_BOUNDARIES_OK')
