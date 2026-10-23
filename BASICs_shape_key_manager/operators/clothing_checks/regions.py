"""Capture fixed semantic regions from native FACE attributes, never weights."""
from array import array


def capture_regions(objects, definitions):
    if not isinstance(definitions, dict):
        raise ValueError('region_definitions must map captured object IDs to named attributes')
    objects = list(objects)
    known = {str(obj['_basic_clothing_id']) for obj in objects}
    if any(identity not in known for identity in definitions):
        raise ValueError('region definition names an uncaptured object ID')
    result = {}
    for obj in objects:
        identity = str(obj['_basic_clothing_id'])
        named = {}
        if not isinstance(definitions.get(identity, {}), dict):
            raise ValueError('object region definitions must be dictionaries')
        for name, definition in definitions.get(identity, {}).items():
            if not isinstance(name, str) or not name or not isinstance(definition, dict):
                raise ValueError('region requires a name and attribute definition')
            attribute = obj.data.attributes.get(definition.get('attribute', ''))
            value = definition.get('value', 1)
            if (attribute is None or attribute.domain != 'FACE'
                    or attribute.data_type not in {'BOOLEAN', 'INT'}
                    or isinstance(value, bool) or not isinstance(value, int)
                    or attribute.data_type == 'BOOLEAN' and value not in (0, 1)):
                raise ValueError('region requires a BOOLEAN or INT FACE attribute and integer value')
            values = array('i', [0]) * len(attribute.data)
            attribute.data.foreach_get('value', values)
            if len(values) != len(obj.data.polygons):
                raise ValueError('region attribute does not match source polygon topology')
            named[name] = [face for face, actual in enumerate(values) if actual == value]
            if not named[name]:
                raise ValueError('requested FACE region is empty: ' + name)
        if identity in result and result[identity] != named:
            raise ValueError('reference and candidate fixed FACE regions differ')
        result[identity] = named
    return result
