"""UV-independent, rest-mesh cheek mask and reversible base-color tint.

The cheek-mask and color-tint approach is extracted from zeldaRender's
zelda_preset/blush.py and adapted to ordinary Principled materials.
"""
import math

import bpy
from mathutils import Vector

from .common import active_output, math_node, node, surface_input_node_from_socket

PREFIX = 'BT · Blush '
ATTRIBUTE = 'bt_blush_cheeks_v1'


def prepare(obj, material_indices, settings):
    if obj.type != 'MESH' or obj.library or obj.data.library:
        return False
    if settings.blush_amount <= 0:
        return False

    if isinstance(material_indices, int):
        material_indices = {material_indices}
    else:
        material_indices = set(material_indices)
    vertices = {vertex for polygon in obj.data.polygons
                if polygon.material_index in material_indices for vertex in polygon.vertices}
    if not vertices:
        return False

    directions = {
        'NEG_Y': (0, -1, 0), 'POS_Y': (0, 1, 0),
        'NEG_Z': (0, 0, -1), 'POS_Z': (0, 0, 1),
        'NEG_X': (-1, 0, 0), 'POS_X': (1, 0, 0),
    }
    front = Vector(directions[settings.blush_front])
    up = Vector((0, 0, 1)) if abs(front.z) < .5 else Vector((0, 1, 0))
    right = up.cross(front).normalized()
    xs = [obj.data.vertices[index].co.dot(right) for index in vertices]
    zs = [obj.data.vertices[index].co.dot(up) for index in vertices]
    xmin, xmax = min(xs), max(xs)
    zmin, zmax = min(zs), max(zs)
    width = max(xmax - xmin, 1e-6)
    height = max(zmax - zmin, 1e-6)
    center = (xmin + xmax) * .5

    values = [0.0] * len(obj.data.vertices)
    for index in vertices:
        vertex = obj.data.vertices[index]
        x = (vertex.co.dot(right) - center) / width
        z = (vertex.co.dot(up) - zmin) / height
        dx = (abs(x) - settings.blush_spacing) / settings.blush_width
        dz = (z - settings.blush_height) / settings.blush_radius
        smooth = math.exp(-1.5 * (dx * dx + dz * dz))
        bridge = .12 * math.exp(-2 * ((x / .18) ** 2 +
                                      ((z - settings.blush_height) / settings.blush_radius) ** 2))
        facing = max(0, vertex.normal.dot(front)) ** .35
        values[index] = max(smooth, bridge) * facing

    attribute = obj.data.attributes.get(ATTRIBUTE)
    if attribute is None:
        attribute = obj.data.attributes.new(ATTRIBUTE, 'FLOAT', 'POINT')
    attribute.data.foreach_set('value', values)
    obj.data.update()
    return True


def disconnect(material):
    tree = material.node_tree
    if not tree:
        return
    mix = tree.nodes.get(PREFIX + 'Tint')
    if mix:
        source = mix.inputs[1]
        targets = [link.to_socket for link in list(mix.outputs[0].links)]
        for target in targets:
            if source.is_linked:
                tree.links.new(source.links[0].from_socket, target)
            else:
                for link in list(target.links):
                    tree.links.remove(link)
                target.default_value = source.default_value
    for value in list(tree.nodes):
        if value.name.startswith(PREFIX):
            tree.nodes.remove(value)
    material['bt_blush_active'] = False


def configure(material, settings):
    tree = material.node_tree
    if not tree:
        return False
    disconnect(material)
    if settings.blush_amount <= 0:
        return False

    output = active_output(tree)
    if not output or not output.inputs['Surface'].is_linked:
        return False
    surface = surface_input_node_from_socket(output.inputs['Surface'].links[0].from_socket)
    if not surface or not surface.inputs.get('Base Color'):
        return False

    base = surface.inputs['Base Color']
    mix = node(tree, 'ShaderNodeMixRGB', PREFIX + 'Tint',
               surface.location.x - 230, surface.location.y + 350)
    mix.blend_type = 'MULTIPLY'
    if base.is_linked:
        tree.links.new(base.links[0].from_socket, mix.inputs[1])
    else:
        mix.inputs[1].default_value = base.default_value
    mix.inputs[2].default_value = settings.blush_color

    if settings.blush_mask:
        uv = node(tree, 'ShaderNodeUVMap', PREFIX + 'UV', mix.location.x - 600, mix.location.y)
        uv.uv_map = settings.blush_uv
        mask = node(tree, 'ShaderNodeTexImage', PREFIX + 'Mask', mix.location.x - 450, mix.location.y)
        mask.image = settings.blush_mask
        tree.links.new(uv.outputs[0], mask.inputs['Vector'])
        source = mask.outputs['Color']
    else:
        mask = node(tree, 'ShaderNodeAttribute', PREFIX + 'Cheek mask',
                    mix.location.x - 450, mix.location.y)
        mask.attribute_name = ATTRIBUTE
        source = mask.outputs['Fac']

    factor = math_node(tree, PREFIX + 'Strength', 'MULTIPLY', source,
                       -settings.blush_amount, mix.location.x - 350, mix.location.y - 200)
    attenuation = math_node(tree, PREFIX + 'Smooth saturation', 'EXPONENT', factor,
                            None, mix.location.x - 170, mix.location.y - 200)
    factor = math_node(tree, PREFIX + 'Diffused tint', 'SUBTRACT', 1, attenuation,
                       mix.location.x, mix.location.y - 200)
    factor = math_node(tree, PREFIX + 'Preserve skin translucency', 'MULTIPLY', factor, .8,
                       mix.location.x + 150, mix.location.y - 200)
    tree.links.new(factor, mix.inputs[0])
    tree.links.new(mix.outputs[0], base)
    material['bt_blush_active'] = True
    return True


def cleanup_mesh_attribute(obj):
    if obj.type != 'MESH' or obj.library or obj.data.library:
        return
    still_used = any(
        other.type == 'MESH' and other.data == obj.data and
        any(slot.material and slot.material.get('bt_blush_active') for slot in other.material_slots)
        for other in bpy.data.objects
    )
    attribute = obj.data.attributes.get(ATTRIBUTE)
    if attribute and not still_used:
        obj.data.attributes.remove(attribute)
