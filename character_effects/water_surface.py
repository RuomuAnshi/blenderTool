"""Closed, skin-conforming liquid trails with transferred armature weights."""
import bisect
import math
import random
from array import array

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def remove(obj):
    count = 0
    for child in list(obj.children):
        if not child.get('bt_water_surface'):
            continue
        mesh = child.data
        materials = list(mesh.materials)
        bpy.data.objects.remove(child, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        for material in materials:
            if material and material.get('bt_water_surface') and material.users == 0:
                bpy.data.materials.remove(material)
        count += 1
    return count


def _barycentric(point, a, b, c):
    u, v, w = b - a, c - a, point - a
    uu, uv, vv = u.dot(u), u.dot(v), v.dot(v)
    denominator = uu * vv - uv * uv
    if abs(denominator) < 1e-20:
        return (1.0, 0.0, 0.0)
    y = (vv * w.dot(u) - uv * w.dot(v)) / denominator
    z = (uu * w.dot(v) - uv * w.dot(u)) / denominator
    weights = [max(0.0, 1 - y - z), max(0.0, y), max(0.0, z)]
    total = sum(weights)
    return tuple(value / total for value in weights)


def _material(settings, thickness, face=False):
    material = bpy.data.materials.new('水渍 · 脸部薄液面' if face else '水渍 · 透明液体')
    material['bt_water_surface'] = True
    material.use_nodes = True
    tree = material.node_tree
    shader = next(n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED')
    shader.inputs['Base Color'].default_value = (.98, .995, 1, 1)
    roughness = max(settings.wet_roughness, .16) if face else settings.wet_roughness
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['IOR'].default_value = 1.333
    shader.inputs['Transmission Weight'].default_value = 1
    if shader.inputs.get('Thin Wall'):
        shader.inputs['Thin Wall'].default_value = False
    output = next(n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL')
    transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
    transparent.label = 'Toon-compatible clear transmission'
    lens = tree.nodes.new('ShaderNodeMixShader')
    lens.label = 'Controlled refraction'
    lens.inputs[0].default_value = settings.wet_refraction * (.25 if face else 1)
    tree.links.new(transparent.outputs[0], lens.inputs[1])
    tree.links.new(shader.outputs[0], lens.inputs[2])
    reflection = tree.nodes.new('ShaderNodeBsdfGlossy')
    reflection.inputs['Color'].default_value = (.4, .4, .4, 1) if face else (1, 1, 1, 1)
    reflection.inputs['Roughness'].default_value = roughness
    fresnel = tree.nodes.new('ShaderNodeFresnel')
    fresnel.inputs['IOR'].default_value = 1.333
    surface = tree.nodes.new('ShaderNodeMixShader')
    surface.label = 'Curved liquid boundary'
    added = tree.nodes.new('ShaderNodeAddShader')
    added.label = 'Preserve skin through unlit liquid edges'
    tree.links.new(lens.outputs[0], added.inputs[0])
    tree.links.new(reflection.outputs[0], added.inputs[1])
    tree.links.new(fresnel.outputs[0], surface.inputs[0])
    tree.links.new(lens.outputs[0], surface.inputs[1])
    tree.links.new(added.outputs[0], surface.inputs[2])
    if face:
        # Fade the whole liquid surface at grazing angles, including refraction.
        # Face-on water remains visible; silhouettes cannot accumulate bright rims.
        fade = tree.nodes.new('ShaderNodeMapRange')
        fade.label = 'Protect face silhouette'
        fade.clamp = True
        fade.interpolation_type = 'SMOOTHSTEP'
        for name, value in (('From Min', .10), ('From Max', .42), ('To Min', 1), ('To Max', 0)):
            fade.inputs[name].default_value = value
        tree.links.new(fresnel.outputs[0], fade.inputs['Value'])
        protected = tree.nodes.new('ShaderNodeMixShader')
        tree.links.new(fade.outputs[0], protected.inputs[0])
        tree.links.new(transparent.outputs[0], protected.inputs[1])
        tree.links.new(surface.outputs[0], protected.inputs[2])
        tree.links.new(protected.outputs[0], output.inputs['Surface'])
    else:
        tree.links.new(surface.outputs[0], output.inputs['Surface'])
    for attr in ('use_raytrace_refraction', 'use_screen_refraction', 'use_transparent_shadow'):
        if hasattr(material, attr):
            setattr(material, attr, True)
    if hasattr(material, 'refraction_depth'):
        material.refraction_depth = thickness
    if hasattr(material, 'thickness_mode'):
        choices = material.bl_rna.properties['thickness_mode'].enum_items
        slab = next((item.identifier for item in choices if item.identifier == 'SLAB'), None)
        if slab:
            material.thickness_mode = slab
    return material


def generate(obj, material_indices, settings):
    """Trace gravity along the rest skin, then give each trail a convex volume."""
    mesh = obj.data
    mesh.calc_loop_triangles()
    triangles = [triangle for triangle in mesh.loop_triangles
                 if mesh.polygons[triangle.polygon_index].material_index in material_indices]
    if not triangles or settings.wet_amount <= 0:
        remove(obj)
        return None
    coords = [vertex.co.copy() for vertex in mesh.vertices]
    normals = [vertex.normal.copy() for vertex in mesh.vertices]
    indices = [tuple(triangle.vertices) for triangle in triangles]
    face_slots = set()
    for i in material_indices:
        material = obj.material_slots[i].material
        name = str(material.get('zd_original_name', material.name)).casefold()
        if material == settings.blush_material or material.get('bt_effect_role') == 'FACE' or any(
            word in name for word in ('face', 'cheek', 'facial', '脸', '面部', '顔', 'かお')
        ):
            face_slots.add(i)
    face_triangles = [mesh.polygons[t.polygon_index].material_index in face_slots for t in triangles]
    face_front = Vector({
        'NEG_Y': (0, -1, 0), 'POS_Y': (0, 1, 0), 'NEG_X': (-1, 0, 0),
        'POS_X': (1, 0, 0), 'NEG_Z': (0, 0, -1), 'POS_Z': (0, 0, 1),
    }[settings.blush_front])
    tree = BVHTree.FromPolygons(coords, indices, all_triangles=True)
    height = max(max(v.z for v in coords) - min(v.z for v in coords), 1e-4)
    scene_units = max(bpy.context.scene.unit_settings.scale_length, 1e-8)
    object_scale = sum(abs(value) for value in obj.matrix_world.to_scale()) / 3
    metres_per_local_unit = max(object_scale * scene_units, 1e-8)
    length = settings.wet_length / 100 / metres_per_local_unit
    half_width = settings.wet_width / 2000 / metres_per_local_unit
    thickness = settings.wet_thickness / 1000 / metres_per_local_unit * settings.wet_amount
    offset = .00002 / metres_per_local_unit
    step = max(length / 45, height * .0004)
    cumulative = []
    total_area = 0
    for a, b, c in indices:
        total_area += (coords[b] - coords[a]).cross(coords[c] - coords[a]).length / 2
        cumulative.append(total_area)
    if total_area <= 1e-12:
        raise ValueError('皮肤材质没有可用的表面面积')
    rng = random.Random(settings.wet_seed)

    uv_layer = mesh.uv_layers.get(settings.wet_uv) if settings.wet_uv else mesh.uv_layers.active
    mask_image = settings.wet_mask
    pixels = None
    if mask_image and mask_image.size[0] and mask_image.size[1]:
        if not uv_layer:
            raise ValueError('水渍遮罩需要源网格具有 UV')
        pixels = array('f', [0]) * len(mask_image.pixels)
        mask_image.pixels.foreach_get(pixels)

    def sample(point, index):
        tri = indices[index]
        weights = _barycentric(point, *(coords[i] for i in tri))
        normal = sum((normals[i] * w for i, w in zip(tri, weights)), Vector())
        if normal.length_squared < 1e-12:
            normal = (coords[tri[1]] - coords[tri[0]]).cross(coords[tri[2]] - coords[tri[0]])
        normal.normalize()
        allowed = 1.0
        if pixels is not None:
            loops = triangles[index].loops
            uv = sum((uv_layer.data[i].uv * w for i, w in zip(loops, weights)), Vector((0, 0)))
            width, image_height = mask_image.size
            x = min(width - 1, max(0, int((uv.x % 1) * width)))
            y = min(image_height - 1, max(0, int((uv.y % 1) * image_height)))
            start = (y * width + x) * mask_image.channels
            allowed = sum(pixels[start:start + min(3, mask_image.channels)]) / min(3, mask_image.channels)
        return normal, weights, allowed

    vertices, faces, bindings, face_flags = [], [], [], []
    down = Vector((0, 0, -1))
    accepted = 0
    face_accepted = 0
    starts = []
    desired = max(1, round(settings.wet_streams * settings.wet_amount))
    columns = 12
    for attempt in range(desired * 18):
        if accepted >= desired:
            break
        index = min(bisect.bisect_left(cumulative, rng.random() * total_area), len(indices) - 1)
        a, b, c = (coords[i] for i in indices[index])
        root = math.sqrt(rng.random())
        side = rng.random()
        point = a * (1 - root) + b * (root * (1 - side)) + c * (root * side)
        normal, _, allowed = sample(point, index)
        facial = face_triangles[index]
        if abs(normal.z) > .85 or rng.random() > allowed:
            continue
        if facial and normal.dot(face_front) < .55:
            continue
        trail_width = half_width * (.32 if facial else 1)
        trail_thickness = thickness * (.16 if facial else 1)
        trail_step = step * (.35 if facial else 1)
        if any((point - old).length < trail_width * 4 for old in starts):
            continue
        path = []
        phase = rng.random() * math.tau
        target_length = length * rng.uniform(.55, 1.4) * (.35 if facial else 1)
        width_scale = rng.uniform(.65, 1.5)
        for row in range(max(10, round(target_length / trail_step))):
            direction = down - normal * down.dot(normal)
            if direction.length_squared < .015:
                break
            direction.normalize()
            lateral = normal.cross(direction).normalized()
            path.append((point.copy(), normal.copy(), direction.copy(), index))
            drift = lateral * math.sin(phase + row * .20) * trail_step * .18
            target = point + direction * trail_step + drift
            position, _, next_index, distance = tree.find_nearest(target, trail_step * 2)
            if position is None or distance > trail_step * .9:
                break
            next_normal, _, next_allowed = sample(position, next_index)
            if next_allowed < .12 or next_normal.dot(normal) < .6:
                break
            if face_triangles[next_index] != facial or (facial and next_normal.dot(face_front) < .45):
                break
            point, normal, index = position, next_normal, next_index
        if len(path) < 12:
            continue
        top, bottom = [], []
        valid = True
        for row, (center, normal, direction, tri_index) in enumerate(path):
            t = row / (len(path) - 1)
            cap = max(.025, math.sin(math.pi * t) ** .45)
            pool = .42 + .70 * math.exp(-((t - .23) / .24) ** 2) + .6 * math.exp(-((t - .9) / .10) ** 2)
            width = trail_width * width_scale * cap * pool * (1 + .12 * math.sin(t * 19 + phase))
            lateral = normal.cross(direction).normalized()
            top_row, bottom_row = [], []
            for column in range(columns + 1):
                q = column * 2 / columns - 1
                target = center + lateral * (q * width)
                position, _, near_index, distance = tree.find_nearest(target, max(width, trail_step) * 1.3)
                if position is None or distance > max(width * .7, offset * 5):
                    valid = False
                    break
                smooth_normal, weights, _ = sample(position, near_index)
                if face_triangles[near_index] != facial or (facial and smooth_normal.dot(face_front) < .40):
                    valid = False
                    break
                dome = math.sqrt(max(0, 1 - q * q))
                lift = trail_thickness * cap * dome * (.7 + .5 * math.exp(-((t - .9) / .10) ** 2))
                top_row.append(len(vertices))
                vertices.append(position + smooth_normal * (offset + lift))
                bindings.append((near_index, weights))
                bottom_row.append(len(vertices))
                vertices.append(position + smooth_normal * offset * .3)
                bindings.append((near_index, weights))
            if not valid:
                break
            top.append(top_row)
            bottom.append(bottom_row)
        if not valid:
            # Unreferenced vertices are discarded by Blender's mesh cleanup below.
            continue
        first_face = len(faces)
        for row in range(len(top) - 1):
            for col in range(columns):
                faces.append((top[row][col], top[row + 1][col], top[row + 1][col + 1], top[row][col + 1]))
                faces.append((bottom[row][col + 1], bottom[row + 1][col + 1], bottom[row + 1][col], bottom[row][col]))
            for col in (0, columns):
                edge = (top[row][col], bottom[row][col], bottom[row + 1][col], top[row + 1][col])
                faces.append(edge if col == 0 else tuple(reversed(edge)))
        for row in (0, len(top) - 1):
            for col in range(columns):
                edge = (top[row][col], top[row][col + 1], bottom[row][col + 1], bottom[row][col])
                faces.append(edge if row == 0 else tuple(reversed(edge)))
        face_flags.extend([facial] * (len(faces) - first_face))
        starts.append(path[0][0])
        accepted += 1
        face_accepted += int(facial)
    if not faces:
        remove(obj)
        return None

    used = sorted({index for face in faces for index in face})
    remap = {old: new for new, old in enumerate(used)}
    data = bpy.data.meshes.new('水渍 · 液体体积')
    data.from_pydata([vertices[i] for i in used], [], [tuple(remap[i] for i in face) for face in faces])
    data.update()
    for polygon in data.polygons:
        polygon.use_smooth = True
    water = bpy.data.objects.new(obj.name + ' · 水渍', data)
    water['bt_water_surface'] = True
    water['bt_water_trails'] = accepted
    water['bt_face_water_trails'] = face_accepted
    water.parent = obj
    water.hide_select = True
    collection = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
    collection.objects.link(water)
    material = _material(settings, settings.wet_thickness / 1000 / scene_units * settings.wet_amount)
    data.materials.append(material)
    if any(face_flags):
        data.materials.append(_material(settings, settings.wet_thickness / 1000 / scene_units * .16, face=True))
        for polygon, is_facial in zip(data.polygons, face_flags):
            polygon.material_index = int(is_facial)
    source_groups = [{g.group: g.weight for g in vertex.groups} for vertex in mesh.vertices]
    groups = {group.index: water.vertex_groups.new(name=group.name) for group in obj.vertex_groups}
    for new_index, old_index in enumerate(used):
        tri_index, weights = bindings[old_index]
        combined = {}
        for source_index, factor in zip(indices[tri_index], weights):
            for group_index, weight in source_groups[source_index].items():
                combined[group_index] = combined.get(group_index, 0) + factor * weight
        for group_index, value in combined.items():
            if value > 1e-5 and group_index in groups:
                groups[group_index].add([new_index], value, 'REPLACE')
    for modifier in obj.modifiers:
        if modifier.type == 'ARMATURE':
            deform = water.modifiers.new('水渍随骨骼变形', modifier.type)
            deform.object = modifier.object
            deform.use_deform_preserve_volume = modifier.use_deform_preserve_volume
    # Commit only after construction, so a failed build retains the previous layer.
    for child in list(obj.children):
        if child != water and child.get('bt_water_surface'):
            old_mesh = child.data
            old_materials = list(old_mesh.materials)
            bpy.data.objects.remove(child, do_unlink=True)
            if old_mesh.users == 0:
                bpy.data.meshes.remove(old_mesh)
            for old_material in old_materials:
                if old_material and old_material.get('bt_water_surface') and old_material.users == 0:
                    bpy.data.materials.remove(old_material)
    return water
