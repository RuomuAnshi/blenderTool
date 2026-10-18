"""Restore material connections from shader-only water versions before 1.4."""

PREFIX = 'BT · Wet '


def disconnect(material):
    tree = material.node_tree
    if not tree:
        return
    tint = tree.nodes.get(PREFIX + 'Tint')
    if tint:
        source = tint.inputs[1]
        for target in [link.to_socket for link in list(tint.outputs[0].links)]:
            if source.is_linked:
                tree.links.new(source.links[0].from_socket, target)
            else:
                for link in list(target.links):
                    tree.links.remove(link)
                target.default_value = source.default_value
    wrapper = tree.nodes.get(PREFIX + 'Layer')
    if wrapper and wrapper.inputs['Dry Shader'].is_linked:
        source = wrapper.inputs['Dry Shader'].links[0].from_socket
        for link in list(wrapper.outputs[0].links):
            tree.links.new(source, link.to_socket)
    for value in list(tree.nodes):
        if value.name.startswith(PREFIX):
            tree.nodes.remove(value)
    material['bt_wet_active'] = False

