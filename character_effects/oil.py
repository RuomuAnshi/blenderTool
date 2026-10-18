"""Independent smooth oil highlights, retaining the original skin shader."""
import bpy

from .common import active_output, math_node, node, surface_input_node_from_socket

GROUP_NAME = 'BT · Oil Skin v1'
PREFIX = 'BT · Oil '


def ensure_group():
    group = bpy.data.node_groups.get(GROUP_NAME)
    if group and group.get('bt_oil_version') == 1:
        return group
    group = bpy.data.node_groups.new(GROUP_NAME, 'ShaderNodeTree')
    group['bt_oil_version'] = 1
    for name, kind, value in (
        ('Dry Shader', 'NodeSocketShader', None), ('Normal', 'NodeSocketVector', (0, 0, 1)),
        ('Alpha', 'NodeSocketFloat', 1), ('UV', 'NodeSocketVector', (0, 0, 0)),
        ('Mask', 'NodeSocketFloat', 1), ('Amount', 'NodeSocketFloat', .85),
        ('Gloss', 'NodeSocketFloat', 1), ('Roughness', 'NodeSocketFloat', .18),
    ):
        socket = group.interface.new_socket(name=name, in_out='INPUT', socket_type=kind)
        if value is not None:
            socket.default_value = value
    group.interface.new_socket(name='Shader', in_out='OUTPUT', socket_type='NodeSocketShader')
    inputs = node(group, 'NodeGroupInput', 'Oil inputs', -1000, 0)
    output = node(group, 'NodeGroupOutput', 'Oil skin', 1200, 0)
    noise = node(group, 'ShaderNodeTexNoise', 'Soft oil coverage', -800, 400)
    noise.inputs['Scale'].default_value = 6
    noise.inputs['Detail'].default_value = 2
    group.links.new(inputs.outputs['UV'], noise.inputs['Vector'])
    profile = node(group, 'ShaderNodeMapRange', 'Continuous oil film', -600, 400)
    profile.clamp = True
    profile.interpolation_type = 'SMOOTHSTEP'
    for name, value in (('From Min', .25), ('From Max', .75), ('To Min', .55), ('To Max', 1)):
        profile.inputs[name].default_value = value
    group.links.new(noise.outputs['Fac'], profile.inputs['Value'])
    coverage = math_node(group, 'Oil reflection weight', 'MULTIPLY', profile.outputs[0], .22, -400, 400)
    for index, source in enumerate((inputs.outputs['Amount'], inputs.outputs['Mask'],
                                    inputs.outputs['Alpha'], inputs.outputs['Gloss'])):
        coverage = math_node(group, f'Oil gate {index}', 'MULTIPLY', coverage,
                             source, -200 + index * 160, 400)
    coverage = math_node(group, 'Bound oil energy', 'MINIMUM', coverage, .6, 500, 400)
    reflection = node(group, 'ShaderNodeBsdfGlossy', 'Smooth oil highlights', 400, -200)
    reflection.inputs['Color'].default_value = (1, 1, 1, 1)
    group.links.new(inputs.outputs['Roughness'], reflection.inputs['Roughness'])
    group.links.new(inputs.outputs['Normal'], reflection.inputs['Normal'])
    added = node(group, 'ShaderNodeAddShader', 'Keep skin beneath oil', 650, -100)
    group.links.new(inputs.outputs['Dry Shader'], added.inputs[0])
    group.links.new(reflection.outputs[0], added.inputs[1])
    result = node(group, 'ShaderNodeMixShader', 'Controlled oil overlay', 950, 0)
    group.links.new(coverage, result.inputs[0])
    group.links.new(inputs.outputs['Dry Shader'], result.inputs[1])
    group.links.new(added.outputs[0], result.inputs[2])
    group.links.new(result.outputs[0], output.inputs[0])
    return group


def disconnect(material):
    tree = material.node_tree
    if not tree:
        return
    wrapper = tree.nodes.get(PREFIX + 'Layer')
    if wrapper and wrapper.inputs['Dry Shader'].is_linked:
        source = wrapper.inputs['Dry Shader'].links[0].from_socket
        for link in list(wrapper.outputs[0].links):
            tree.links.new(source, link.to_socket)
    for value in list(tree.nodes):
        if value.name.startswith(PREFIX):
            tree.nodes.remove(value)
    material['bt_oil_active'] = False


def configure(material, settings):
    tree = material.node_tree
    if not tree:
        return False
    disconnect(material)
    if settings.oil_amount <= 0:
        return False
    output = active_output(tree)
    if not output or not output.inputs['Surface'].is_linked:
        return False
    source = output.inputs['Surface'].links[0].from_socket
    surface = surface_input_node_from_socket(source)
    wrapper = node(tree, 'ShaderNodeGroup', PREFIX + 'Layer',
                   output.location.x - 180, output.location.y - 500)
    wrapper.node_tree = ensure_group()
    tree.links.new(source, wrapper.inputs['Dry Shader'])
    if surface:
        for name in ('Normal', 'Alpha'):
            socket = surface.inputs.get(name)
            if socket and socket.is_linked:
                tree.links.new(socket.links[0].from_socket, wrapper.inputs[name])
            elif socket and name == 'Alpha':
                wrapper.inputs[name].default_value = socket.default_value
    if not wrapper.inputs['Normal'].is_linked:
        geometry = node(tree, 'ShaderNodeNewGeometry', PREFIX + 'Normal',
                        wrapper.location.x - 450, wrapper.location.y - 300)
        tree.links.new(geometry.outputs['Normal'], wrapper.inputs['Normal'])
    uv = node(tree, 'ShaderNodeUVMap', PREFIX + 'UV', wrapper.location.x - 450, wrapper.location.y)
    uv.uv_map = settings.oil_uv
    tree.links.new(uv.outputs[0], wrapper.inputs['UV'])
    for name, value in (('Amount', settings.oil_amount), ('Gloss', settings.oil_gloss),
                        ('Roughness', settings.oil_roughness)):
        wrapper.inputs[name].default_value = value
    if settings.oil_mask:
        mask = node(tree, 'ShaderNodeTexImage', PREFIX + 'Mask',
                    wrapper.location.x - 250, wrapper.location.y - 300)
        mask.image = settings.oil_mask
        tree.links.new(uv.outputs[0], mask.inputs['Vector'])
        tree.links.new(mask.outputs['Color'], wrapper.inputs['Mask'])
    tree.links.new(wrapper.outputs[0], output.inputs['Surface'])
    material['bt_oil_active'] = True
    return True
