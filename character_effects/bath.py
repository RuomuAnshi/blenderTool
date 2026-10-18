"""Packed texture bath overlay adapted from 沐浴露节点 by 瑞鵆."""
from pathlib import Path
import bpy
from .common import active_output, node, math_node, surface_input_node_from_socket

GROUP_NAME = 'BT · Bath Reference v1'
PREFIX = 'BT · Bath '


def ensure_group():
    group = next((g for g in bpy.data.node_groups if g.get('bt_bath_resource') == 1), None)
    if group:
        return group
    path = str(Path(__file__).parent / 'assets' / 'bath.blend')
    with bpy.data.libraries.load(path, link=False) as (source, target):
        target.node_groups = [GROUP_NAME]
    return target.node_groups[0]


def disconnect(material):
    tree = material.node_tree
    if not tree:
        return
    wrapper = tree.nodes.get(PREFIX + 'Blend')
    if wrapper and wrapper.inputs[1].is_linked:
        source = wrapper.inputs[1].links[0].from_socket
        for link in list(wrapper.outputs[0].links):
            tree.links.new(source, link.to_socket)
    for value in list(tree.nodes):
        if value.name.startswith(PREFIX):
            tree.nodes.remove(value)
    material['bt_bath_active'] = False


def configure(material, settings, face=False):
    tree = material.node_tree
    if not tree:
        return False
    disconnect(material)
    if settings.bath_amount <= 0:
        return False
    output = active_output(tree)
    if not output or not output.inputs['Surface'].is_linked:
        return False
    source = output.inputs['Surface'].links[0].from_socket
    surface = surface_input_node_from_socket(source)
    x, y = output.location
    overlay = node(tree, 'ShaderNodeGroup', PREFIX + 'Layer', x-460, y-360)
    overlay.node_tree = ensure_group()
    tree.links.new(source, overlay.inputs['皮肤'])
    for key, value in (
        ('沐浴露密度', settings.bath_density), ('沐浴露位置', settings.bath_location),
        ('糙度', max(.15, settings.bath_roughness) if face else settings.bath_roughness),
        ('高光', settings.bath_specular), ('透明度', settings.bath_opacity),
        ('法线强度', settings.bath_normal * (.4 if face else 1)),
    ):
        overlay.inputs[key].default_value = value
    blend = node(tree, 'ShaderNodeMixShader', PREFIX + 'Blend', x-180, y)
    tree.links.new(source, blend.inputs[1])
    tree.links.new(overlay.outputs[0], blend.inputs[2])
    gate = settings.bath_amount
    if surface:
        alpha = surface.inputs.get('Alpha')
        if alpha:
            a = alpha.links[0].from_socket if alpha.is_linked else alpha.default_value
            gate = math_node(tree, PREFIX+'Alpha gate', 'MULTIPLY', a, gate, x-700, y-400)
    if settings.bath_mask:
        uv = node(tree, 'ShaderNodeUVMap', PREFIX+'Mask UV', x-1100, y-700)
        uv.uv_map = settings.bath_uv
        mask = node(tree, 'ShaderNodeTexImage', PREFIX+'Mask', x-900, y-700)
        mask.image = settings.bath_mask
        tree.links.new(uv.outputs[0], mask.inputs['Vector'])
        gate = math_node(tree, PREFIX+'Mask gate', 'MULTIPLY', gate, mask.outputs['Color'], x-600, y-700)
    if face:
        facing = node(tree, 'ShaderNodeFresnel', PREFIX+'Face edge', x-900, y-1000)
        fade = node(tree, 'ShaderNodeMapRange', PREFIX+'Soft edge', x-700, y-1000)
        fade.interpolation_type = 'SMOOTHSTEP'
        facing.inputs['IOR'].default_value = 1.45
        fade.inputs['From Min'].default_value = .10
        fade.inputs['From Max'].default_value = .42
        fade.inputs['To Min'].default_value = 1
        fade.inputs['To Max'].default_value = 0
        tree.links.new(facing.outputs[0], fade.inputs['Value'])
        gate = math_node(tree, PREFIX+'Face gate', 'MULTIPLY', gate, fade.outputs[0], x-420, y-900)
    if isinstance(gate, (float, int)):
        blend.inputs[0].default_value = gate
    else:
        tree.links.new(gate, blend.inputs[0])
    tree.links.new(blend.outputs[0], output.inputs['Surface'])
    material['bt_bath_active'] = True
    return True
