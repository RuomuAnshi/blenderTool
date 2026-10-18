"""Small shader-node helpers shared by the extracted effects."""


def node(tree, kind, name, x=0, y=0):
    value = tree.nodes.new(kind)
    value.name = value.label = name
    value.location = (x, y)
    return value


def math_node(tree, name, operation, a=None, b=None, x=0, y=0):
    value = node(tree, 'ShaderNodeMath', name, x, y)
    value.operation = operation
    for index, source in enumerate((a, b)):
        if source is None:
            continue
        if isinstance(source, (float, int)):
            value.inputs[index].default_value = source
        else:
            tree.links.new(source, value.inputs[index])
    return value.outputs[0]


def active_output(tree):
    return next((value for value in tree.nodes
                 if value.type == 'OUTPUT_MATERIAL' and value.is_active_output), None)


def principled_from_socket(socket, seen=None):
    """Find the Principled node feeding a shader socket, including wrappers."""
    if socket is None:
        return None
    seen = seen or set()
    value = socket.node
    pointer = value.as_pointer()
    if pointer in seen:
        return None
    seen.add(pointer)
    if value.type == 'BSDF_PRINCIPLED':
        return value
    for input_socket in value.inputs:
        if input_socket.type != 'SHADER':
            continue
        for link in input_socket.links:
            found = principled_from_socket(link.from_socket, seen)
            if found:
                return found
    return None


def surface_input_node_from_socket(socket, seen=None):
    """Find a Principled node or a shader group exposing a Base Color input."""
    if socket is None:
        return None
    seen = seen or set()
    value = socket.node
    pointer = value.as_pointer()
    if pointer in seen:
        return None
    seen.add(pointer)
    if value.type == 'BSDF_PRINCIPLED':
        return value
    if value.type == 'GROUP' and value.inputs.get('Base Color'):
        return value
    for input_socket in value.inputs:
        if input_socket.type != 'SHADER':
            continue
        for link in input_socket.links:
            found = surface_input_node_from_socket(link.from_socket, seen)
            if found:
                return found
    return None
