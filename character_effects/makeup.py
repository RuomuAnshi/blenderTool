"""Reversible eye shadow and lipstick on the existing face base color."""
from collections import Counter, defaultdict
import bpy
from mathutils import Vector
from .common import active_output, math_node, node, surface_input_node_from_socket

PREFIX = 'BT · Makeup '
COORDS = 'bt_makeup_face_coords_v1'


def face_frame(obj, indices, settings):
    vertices = {v for p in obj.data.polygons if p.material_index in indices for v in p.vertices}
    if not vertices:
        raise ValueError('脸部材质没有对应的网格面')
    front = Vector({'NEG_Y': (0,-1,0), 'POS_Y': (0,1,0), 'NEG_Z': (0,0,-1),
                    'POS_Z': (0,0,1), 'NEG_X': (-1,0,0), 'POS_X': (1,0,0)}[settings.blush_front])
    up = Vector((0,0,1)) if abs(front.z) < .5 else Vector((0,1,0))
    right = up.cross(front).normalized()
    xs = [obj.data.vertices[v].co.dot(right) for v in vertices]
    zs = [obj.data.vertices[v].co.dot(up) for v in vertices]
    center = (min(xs)+max(xs))*.5
    width, bottom, height = max(max(xs)-min(xs),1e-6), min(zs), max(max(zs)-min(zs),1e-6)
    return vertices, front, up, right, center, width, bottom, height


def fit(obj, indices, settings):
    """Use front face openings when available; retain adjustable proportion defaults."""
    verts, front, up, right, center, width, bottom, height = face_frame(obj, indices, settings)
    settings.makeup_eye_spacing = .21
    settings.makeup_eye_height = .63
    settings.makeup_eye_width = .14
    settings.makeup_eye_radius = .06
    settings.makeup_lip_height = .26
    settings.makeup_lip_width = .10
    settings.makeup_lip_radius = .025
    edges = Counter(tuple(sorted(e)) for p in obj.data.polygons if p.material_index in indices for e in p.edge_keys)
    adj = defaultdict(set)
    for (a,b), count in edges.items():
        if count == 1:
            adj[a].add(b); adj[b].add(a)
    seen, openings = set(), []
    for v in adj:
        if v in seen:
            continue
        seen.add(v); stack, group = [v], []
        while stack:
            a = stack.pop(); group.append(a)
            for b in adj[a]-seen:
                seen.add(b); stack.append(b)
        if len(group) < 6:
            continue
        x = [(obj.data.vertices[i].co.dot(right)-center)/width for i in group]
        z = [(obj.data.vertices[i].co.dot(up)-bottom)/height for i in group]
        xmin,xmax,zmin,zmax = min(x),max(x),min(z),max(z)
        # Ignore the outer face/neck boundary and very small holes.
        if .025 < xmax-xmin < .45 and .005 < zmax-zmin < .28:
            openings.append(((xmin+xmax)*.5,(zmin+zmax)*.5,xmax-xmin,zmax-zmin,zmax))
    eyes = [o for o in openings if .08 < abs(o[0]) < .38 and .40 < o[1] < .85]
    pairs = [(a,b) for a in eyes for b in eyes if a[0]<0<b[0] and abs(a[1]-b[1])<.06 and abs(a[0]+b[0])<.08]
    if pairs:
        a,b = max(pairs,key=lambda pair: pair[0][2]+pair[1][2])
        settings.makeup_eye_spacing = (abs(a[0])+abs(b[0]))*.5
        settings.makeup_eye_height = (a[4]+b[4])*.5+.018
        settings.makeup_eye_width = min(.25,(a[2]+b[2])*.29)
    mouths = [o for o in openings if abs(o[0])<.06 and .10<o[1]<.45]
    if mouths:
        m = max(mouths,key=lambda o:o[2])
        settings.makeup_lip_height = m[1]
        settings.makeup_lip_width = min(.22,m[2]*.60)
        settings.makeup_lip_radius = min(.09,max(.018,m[3]*.65+.008))
    obj.data['bt_makeup_fitted'] = True


def prepare(obj, indices, settings):
    if obj.library or obj.data.library:
        raise ValueError('链接网格不可编辑，请先创建本地副本')
    verts, front, up, right, center, width, bottom, height = face_frame(obj, indices, settings)
    values = [0.0] * (len(obj.data.vertices)*3)
    for i in verts:
        v = obj.data.vertices[i]
        values[i*3:i*3+3] = ((v.co.dot(right)-center)/width,
                             (v.co.dot(up)-bottom)/height,
                             max(0,v.normal.dot(front))**.4)
    attribute = obj.data.attributes.get(COORDS)
    if attribute is None:
        attribute = obj.data.attributes.new(COORDS, 'FLOAT_VECTOR', 'POINT')
    attribute.data.foreach_set('vector',values)
    obj.data.update()


def disconnect(material):
    tree = material.node_tree
    if not tree:
        return
    # Reverse stack order so each layer restores the previous color connection.
    for key in ('Lip', 'Eye'):
        mix = tree.nodes.get(PREFIX+key+' Tint')
        if mix:
            source = mix.inputs[1]
            for link in list(mix.outputs[0].links):
                target = link.to_socket
                if source.is_linked:
                    tree.links.new(source.links[0].from_socket,target)
                else:
                    tree.links.remove(link)
                    target.default_value = source.default_value
    for n in list(tree.nodes):
        if n.name.startswith(PREFIX):
            tree.nodes.remove(n)
    material['bt_makeup_active'] = False


def configure(material, settings):
    tree = material.node_tree
    if not tree:
        return False
    output = active_output(tree)
    if not output or not output.inputs['Surface'].is_linked:
        return False
    surface = surface_input_node_from_socket(output.inputs['Surface'].links[0].from_socket)
    if not surface or not surface.inputs.get('Base Color'):
        return False
    disconnect(material)
    attr = node(tree,'ShaderNodeAttribute',PREFIX+'Coordinates',surface.location.x-1300,surface.location.y+600)
    attr.attribute_name = COORDS
    split = node(tree,'ShaderNodeSeparateXYZ',PREFIX+'Face axes',attr.location.x+180,attr.location.y)
    tree.links.new(attr.outputs['Vector'],split.inputs[0])
    x,y,gate = split.outputs
    sequence = [0]
    def math(label,op,a,b=None):
        sequence[0]+=1
        return math_node(tree,PREFIX+label,op,a,b,attr.location.x+(sequence[0]%5)*180,attr.location.y-180-(sequence[0]//5)*160)
    def ellipse(key,cx,cy,rx,ry):
        dx = math(key+' x','DIVIDE',math(key+' cx','SUBTRACT',x,cx),rx)
        dy = math(key+' y','DIVIDE',math(key+' cy','SUBTRACT',y,cy),ry)
        dist = math(key+' ellipse','ADD',math(key+' xx','MULTIPLY',dx,dx),math(key+' yy','MULTIPLY',dy,dy))
        fade = node(tree,'ShaderNodeMapRange',PREFIX+key+' Feather',attr.location.x+500,attr.location.y-700)
        fade.interpolation_type='SMOOTHSTEP'
        fade.inputs['From Min'].default_value = 1-settings.makeup_softness
        fade.inputs['From Max'].default_value = 1
        fade.inputs['To Min'].default_value = 1
        fade.inputs['To Max'].default_value = 0
        tree.links.new(dist,fade.inputs['Value'])
        return fade.outputs[0]
    base = surface.inputs['Base Color']
    for key, enabled, amount, color, image in (
        ('Eye',settings.makeup_eye_enabled,settings.makeup_eye_amount,settings.makeup_eye_color,settings.makeup_eye_mask),
        ('Lip',settings.makeup_lip_enabled,settings.makeup_lip_amount,settings.makeup_lip_color,settings.makeup_lip_mask),
    ):
        if not enabled or amount <= 0:
            continue
        if image:
            uv=node(tree,'ShaderNodeUVMap',PREFIX+key+' UV',attr.location.x,attr.location.y-1100)
            uv.uv_map=settings.makeup_uv
            mask=node(tree,'ShaderNodeTexImage',PREFIX+key+' Mask',attr.location.x+180,attr.location.y-1100)
            mask.image=image
            tree.links.new(uv.outputs[0],mask.inputs['Vector'])
            coverage=mask.outputs['Color']
        elif key=='Eye':
            left=ellipse('Left eye',-settings.makeup_eye_spacing,settings.makeup_eye_height,settings.makeup_eye_width,settings.makeup_eye_radius)
            right=ellipse('Right eye',settings.makeup_eye_spacing,settings.makeup_eye_height,settings.makeup_eye_width,settings.makeup_eye_radius)
            coverage=math('Both eyes','MAXIMUM',left,right)
        else:
            coverage=ellipse('Lips',0,settings.makeup_lip_height,settings.makeup_lip_width,settings.makeup_lip_radius)
        coverage=math(key+' Front only','MULTIPLY',coverage,gate)
        coverage=math(key+' Strength','MULTIPLY',coverage,amount)
        mix=node(tree,'ShaderNodeMixRGB',PREFIX+key+' Tint',surface.location.x-250,surface.location.y+(420 if key=='Eye' else 180))
        mix.blend_type='MIX'
        mix.inputs[2].default_value=color
        if base.is_linked:
            tree.links.new(base.links[0].from_socket,mix.inputs[1])
        else:
            mix.inputs[1].default_value=base.default_value
        tree.links.new(coverage,mix.inputs[0])
        tree.links.new(mix.outputs[0],base)
    material['bt_makeup_active'] = True
    return True


def cleanup(obj):
    still_used = any(o.type=='MESH' and o.data==obj.data and any(s.material and s.material.get('bt_makeup_active') for s in o.material_slots) for o in bpy.data.objects)
    if not still_used:
        attr=obj.data.attributes.get(COORDS)
        if attr:
            obj.data.attributes.remove(attr)
