"""Native authoring fields for explicit clothing validation inputs."""
import json
import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       IntProperty, PointerProperty, StringProperty)


def clear_pair_confirmation(self, _context):
    self.confirmed = False


def clear_mapping_confirmation(self, _context):
    self.id_data.clothing_checks.mapping_confirmed = False


def mapping_signature(options):
    return json.dumps([(row.canonical, row.bone) for row in options.mapping])


def capture_mapping_confirmation(self, _context):
    self.confirmed_rig = self.rig if self.mapping_confirmed else None
    self.confirmed_mapping = mapping_signature(self) if self.mapping_confirmed else ''


class BASIC_ClothingPair(bpy.types.PropertyGroup):
    reference: PointerProperty(name='Before', type=bpy.types.Object, poll=lambda _, o: o.type == 'MESH',
                               update=clear_pair_confirmation)
    candidate: PointerProperty(name='After', type=bpy.types.Object, poll=lambda _, o: o.type == 'MESH',
                               update=clear_pair_confirmation)
    confirmed: BoolProperty(name='Confirm pairing', default=False)


class BASIC_ClothingMapping(bpy.types.PropertyGroup):
    canonical: StringProperty(update=clear_mapping_confirmation)
    bone: StringProperty(name='Bone', update=clear_mapping_confirmation)


class BASIC_ClothingShape(bpy.types.PropertyGroup):
    case: StringProperty(name='Combination', default='Endpoint')
    object: PointerProperty(name='Mesh', type=bpy.types.Object, poll=lambda _, o: o.type == 'MESH')
    key: StringProperty(name='Shape key')
    value: FloatProperty(name='Value', default=1.)


class BASIC_ClothingSettings(bpy.types.PropertyGroup):
    body: PointerProperty(name='Body', type=bpy.types.Object, poll=lambda _, o: o.type == 'MESH')
    rig: PointerProperty(name='Rig', type=bpy.types.Object, poll=lambda _, o: o.type == 'ARMATURE',
                         update=clear_mapping_confirmation)
    pairs: CollectionProperty(type=BASIC_ClothingPair)
    mapping: CollectionProperty(type=BASIC_ClothingMapping)
    mapping_confirmed: BoolProperty(name='I confirm this humanoid mapping', default=False,
                                    update=capture_mapping_confirmation)
    confirmed_rig: PointerProperty(type=bpy.types.Object, options={'HIDDEN'})
    confirmed_mapping: StringProperty(options={'HIDDEN'})
    bend_directions: StringProperty(name='Bend directions JSON', default='{}',
        description='Explicit armature-space vectors for collinear left_arm, right_arm, left_leg, right_leg')
    accessory_bones: StringProperty(name='Accessory bones JSON', default='[]',
        description='Explicit bone names, including secondary jiggle bones. No physics is simulated')
    shapes: CollectionProperty(type=BASIC_ClothingShape)
    region_definitions: StringProperty(name='FACE regions JSON', default='{}',
        description='Captured object ID -> region name -> {attribute: FACE attribute name, value: integer}')
    contact_allowances: StringProperty(name='Contact allowances JSON', default='[]',
        description='Rules with kind CROSSING/CONTACT/CONTAINED and endpoints a/b {object_id, region}')
    utility_groups: StringProperty(name='Utility groups JSON', default='{}',
        description='Captured garment ID -> exact non-bone group names excluded from deform-weight audits')
    families: EnumProperty(name='Motion families', options={'ENUM_FLAG'}, items=[
        ('neutral', 'Neutral', ''), ('reach', 'Reach', ''), ('arm', 'Arm', ''),
        ('torso', 'Torso', ''), ('lower_body', 'Lower body', ''),
        ('coordination', 'Coordination', ''), ('accessory', 'Accessory flex', ''),
        ('shoulder', 'Shoulder and arm sweeps', 'Requires explicit clavicle mappings')],
        default={'neutral', 'reach', 'arm', 'shoulder', 'torso', 'lower_body', 'coordination'})
    head_hands: BoolProperty(name='Head and hands approximation', default=True)
    full_body: BoolProperty(name='Full body approximation', default=True)
    budget: IntProperty(name='Total evaluated case cap', default=512, min=1, max=100000)
    refinement_depth: IntProperty(name='Refinement depth', default=3, min=0, max=8)
    contact_m: FloatProperty(name='Contact band (meters)', default=.0001, min=0, precision=5)
    clearance_m: FloatProperty(name='Clearance warning (meters)', default=.001, min=0, precision=5)
    worsening_m: FloatProperty(name='Worsening (meters)', default=.0005, min=0, precision=5)
    sample_limit: IntProperty(name='Containment probes per object', default=512, min=1, max=100000)
    report_text: StringProperty(name='Report Text')
    result_index: IntProperty(name='Pair finding', min=0)
    preview_side: EnumProperty(name='View', items=[('REFERENCE', 'Before', ''), ('CANDIDATE', 'After', '')], default='CANDIDATE')
    replay: BoolProperty(name='Replay saved report cases', default=False)
    status: StringProperty(name='Progress', default='Idle', options={'SKIP_SAVE'})


classes = (BASIC_ClothingPair, BASIC_ClothingMapping, BASIC_ClothingShape, BASIC_ClothingSettings)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.clothing_checks = PointerProperty(type=BASIC_ClothingSettings)


def unregister():
    del bpy.types.Scene.clothing_checks
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
