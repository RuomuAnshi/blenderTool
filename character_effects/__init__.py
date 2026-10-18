"""Independent face blush, water droplets and smooth oil highlights."""
bl_info = {
    'name': '角色脸红、水渍与油',
    'author': 'ruomuanshi',
    'version': (1, 5, 0),
    'blender': (5, 2, 0),
    'location': '3D 视图 > 侧栏 > 角色特效',
    'description': '为角色自动添加脸红、水渍和油光',
    'category': 'Material',
}

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty

from . import blush, wet, oil, water_surface, bath


FRONT_DIRECTIONS = [
    ('NEG_Y', '−Y（常见 MMD）', ''), ('POS_Y', '＋Y', ''),
    ('NEG_Z', '−Z', ''), ('POS_Z', '＋Z', ''),
    ('NEG_X', '−X', ''), ('POS_X', '＋X', ''),
]



class CharacterEffectsSettings(bpy.types.PropertyGroup):
    blush_amount: FloatProperty(name='脸红强度', default=2.2, min=0, max=3)
    blush_color: FloatVectorProperty(name='脸红颜色', subtype='COLOR', size=4,
                                     default=(1, .08, .13, 1), min=0, max=1)
    blush_spacing: FloatProperty(name='两颊间距', default=.25, min=.05, max=.45)
    blush_height: FloatProperty(name='脸红高度', default=.32, min=.05, max=.95)
    blush_width: FloatProperty(name='横向范围', default=.24, min=.03, max=.5)
    blush_radius: FloatProperty(name='纵向范围', default=.145, min=.02, max=.4)
    blush_front: EnumProperty(name='脸部正面', items=FRONT_DIRECTIONS, default='NEG_Y')
    blush_material: PointerProperty(name='额外脸部材质', type=bpy.types.Material,
                                    description='在自动识别之外，将此材质也作为脸部材质')
    blush_mask: PointerProperty(name='自定义脸红遮罩', type=bpy.types.Image,
                                description='白色允许脸红，黑色保护五官')
    blush_uv: StringProperty(name='脸红 UV', description='留空使用活动 UV')

    wet_amount: FloatProperty(name='水渍量', default=.85, min=0, max=1)
    wet_streams: IntProperty(name='流痕数量', default=55, min=1, max=200)
    wet_length: FloatProperty(name='流痕长度（厘米）', default=10, min=.5, max=40)
    wet_width: FloatProperty(name='流痕宽度（毫米）', default=16, min=1, max=40)
    wet_thickness: FloatProperty(name='积水厚度（毫米）', default=1, min=.05, max=3)
    wet_roughness: FloatProperty(name='液面粗糙度', default=.055, min=.015, max=.35)
    wet_refraction: FloatProperty(name='折射强度', default=.04, min=0, max=1,
                                   description='高强度需要渲染器和皮肤材质支持折射；Toon 材质建议保持较低值')
    wet_seed: IntProperty(name='流痕随机种子', default=17, min=0)
    wet_face: BoolProperty(name='脸部也添加水渍', default=False,
                            description='默认跳过脸部，仅处理身体和颈部皮肤')
    wet_material: PointerProperty(name='额外皮肤材质', type=bpy.types.Material,
                                  description='在自动识别之外，将此材质也作为皮肤材质')
    wet_uv: StringProperty(name='水渍 UV', description='留空使用活动 UV')
    wet_mask: PointerProperty(name='水渍灰度遮罩', type=bpy.types.Image,
                               description='建议使用 Non-Color 灰度图；白色允许水渍，黑色保护区域')
    oil_amount: FloatProperty(name='油强度', default=.85, min=0, max=1)
    oil_gloss: FloatProperty(name='油光亮度', default=1, min=0, max=2)
    oil_roughness: FloatProperty(name='油光柔和度', default=.18, min=.03, max=.5)
    oil_face: BoolProperty(name='脸部也添加油', default=False)
    oil_material: PointerProperty(name='额外涂油材质', type=bpy.types.Material)
    oil_uv: StringProperty(name='油 UV', description='留空使用活动 UV')
    oil_mask: PointerProperty(name='油灰度遮罩', type=bpy.types.Image,
                               description='白色允许油光，黑色保护区域')
    bath_amount: FloatProperty(name='沐浴露强度', default=1, min=0, max=1)
    bath_skin: BoolProperty(name='身体皮肤', default=True)
    bath_face: BoolProperty(name='脸部', default=False)
    bath_hair: BoolProperty(name='头发', default=False)
    bath_clothes: BoolProperty(name='衣服', default=False)
    bath_density: FloatProperty(name='流痕密度', default=3, min=.1, max=20)
    bath_location: FloatVectorProperty(name='流痕位置', size=3, default=(0, 0, 0))
    bath_roughness: FloatProperty(name='沐浴露粗糙度', default=.08, min=.02, max=1)
    bath_specular: FloatProperty(name='沐浴露高光', default=1, min=0, max=1)
    bath_opacity: FloatProperty(name='沐浴露不透明度', default=.5, min=0, max=1)
    bath_normal: FloatProperty(name='凸起强度', default=.9, min=0, max=2)
    bath_material: PointerProperty(name='额外应用材质', type=bpy.types.Material)
    bath_mask: PointerProperty(name='沐浴露遮罩', type=bpy.types.Image)
    bath_uv: StringProperty(name='遮罩 UV', description='留空使用活动 UV；流痕贴图使用角色 UV')
    show_advanced: BoolProperty(name='高级设置', default=False)


def active_mesh(context):
    obj = context.active_object
    if not obj or obj.type != 'MESH':
        return None
    return obj


def material_name(material):
    return str(material.get('zd_original_name', material.name)).casefold()


def is_face_material(material, settings):
    if not material:
        return False
    if settings.blush_material and material == settings.blush_material:
        return True
    name = material_name(material)
    return material.get('bt_effect_role') == 'FACE' or any(
        token in name for token in ('face', 'cheek', 'facial', '脸', '面部', '顔', 'かお')
    )


def is_skin_material(material, settings):
    if not material:
        return False
    if settings.wet_material and material == settings.wet_material:
        return True
    if is_face_material(material, settings):
        return settings.wet_face
    return is_body_skin(material)


def is_oil_material(material, settings):
    if not material:
        return False
    if settings.oil_material and material == settings.oil_material:
        return True
    if is_face_material(material, settings):
        return settings.oil_face
    return is_body_skin(material)


def is_body_skin(material):
    if material.get('zd_role') == 'SKIN' or material.get('bt_effect_role') == 'SKIN':
        return True
    name = material_name(material)
    return any(token in name for token in (
        'skin', 'body', 'neck', 'throat', 'nape', 'bozi', '肌', '皮肤', '皮膚',
        '身体', '身_', '脖', '颈', '頸', '喉',
    ))


def target_materials(obj, predicate, settings):
    found = []
    seen = set()
    for index, slot in enumerate(obj.material_slots):
        material = slot.material
        if material and predicate(material, settings) and material.as_pointer() not in seen:
            found.append((index, material))
            seen.add(material.as_pointer())
    return found


class CHARACTERFX_OT_apply_blush(bpy.types.Operator):
    bl_idname = 'characterfx.apply_blush'
    bl_label = '添加／更新脸红'
    bl_description = '自动为角色的脸部材质添加柔和脸红'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_mesh(context) is not None

    def execute(self, context):
        obj = active_mesh(context)
        settings = context.scene.character_effects
        if settings.blush_amount <= 0:
            self.report({'ERROR'}, '请先将脸红强度设为大于 0')
            return {'CANCELLED'}
        targets = target_materials(obj, is_face_material, settings)
        if not targets:
            self.report({'ERROR'}, '没有识别到脸部材质；可在高级设置中指定额外脸部材质')
            return {'CANCELLED'}
        material_indices = {index for index, _ in targets}
        if not settings.blush_mask and not blush.prepare(obj, material_indices, settings):
            self.report({'ERROR'}, '脸部网格不可编辑，或没有脸部材质对应的面')
            return {'CANCELLED'}
        applied = 0
        for _, material in targets:
            if material.library or not material.node_tree:
                continue
            applied += bool(blush.configure(material, settings))
        if not applied:
            self.report({'ERROR'}, '脸部材质没有可用的着色器输出')
            return {'CANCELLED'}
        self.report({'INFO'}, f'已为 {applied} 个脸部材质添加脸红')
        return {'FINISHED'}


class CHARACTERFX_OT_remove_blush(bpy.types.Operator):
    bl_idname = 'characterfx.remove_blush'
    bl_label = '移除脸红'
    bl_description = '恢复活动材质原颜色并移除脸红节点'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_mesh(context) is not None

    def execute(self, context):
        obj = active_mesh(context)
        settings = context.scene.character_effects
        targets = target_materials(obj, is_face_material, settings)
        for _, material in targets:
            if not material.library:
                blush.disconnect(material)
        blush.cleanup_mesh_attribute(obj)
        self.report({'INFO'}, f'已从 {len(targets)} 个脸部材质移除脸红')
        return {'FINISHED'}


class CHARACTERFX_OT_apply_wet(bpy.types.Operator):
    bl_idname = 'characterfx.apply_wet'
    bl_label = '添加／更新水渍'
    bl_description = '自动为身体皮肤添加不规则湿斑与纵向流痕'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_mesh(context) is not None

    def execute(self, context):
        obj = active_mesh(context)
        settings = context.scene.character_effects
        targets = target_materials(obj, is_skin_material, settings)
        if not targets:
            self.report({'ERROR'}, '没有识别到身体或皮肤材质；可在高级设置中指定额外皮肤材质')
            return {'CANCELLED'}
        material_indices = {index for index, slot in enumerate(obj.material_slots)
                            if slot.material and is_skin_material(slot.material, settings)}
        try:
            water = water_surface.generate(obj, material_indices, settings)
        except (ValueError, RuntimeError) as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}
        for _, material in targets:
            if not material.library:
                wet.disconnect(material)
        count = water.get('bt_water_trails', 0) if water else 0
        self.report({'INFO'}, f'已生成 {count} 条贴肤透明水渍')
        return {'FINISHED'}


class CHARACTERFX_OT_remove_wet(bpy.types.Operator):
    bl_idname = 'characterfx.remove_wet'
    bl_label = '移除水渍'
    bl_description = '恢复水渍节点前的材质连接'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_mesh(context) is not None

    def execute(self, context):
        obj = active_mesh(context)
        settings = context.scene.character_effects
        targets = target_materials(obj, is_skin_material, settings)
        water_surface.remove(obj)
        for _, material in targets:
            if not material.library:
                wet.disconnect(material)
        self.report({'INFO'}, '已移除水渍液体层')
        return {'FINISHED'}


class CHARACTERFX_OT_apply_oil(bpy.types.Operator):
    bl_idname = 'characterfx.apply_oil'
    bl_label = '添加／更新油'
    bl_description = '为身体皮肤叠加连续平滑的油光'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_mesh(context) is not None

    def execute(self, context):
        settings = context.scene.character_effects
        targets = target_materials(active_mesh(context), is_oil_material, settings)
        count = sum(bool(oil.configure(material, settings)) for _, material in targets
                    if not material.library and material.node_tree)
        if not count:
            self.report({'ERROR'}, '没有可用的皮肤材质；可在高级设置中指定涂油材质')
            return {'CANCELLED'}
        self.report({'INFO'}, f'已为 {count} 个皮肤材质添加油')
        return {'FINISHED'}


class CHARACTERFX_OT_remove_oil(bpy.types.Operator):
    bl_idname = 'characterfx.remove_oil'
    bl_label = '移除油'
    bl_description = '移除油光，保留其他角色特效'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_mesh(context) is not None

    def execute(self, context):
        settings = context.scene.character_effects
        targets = target_materials(active_mesh(context), is_oil_material, settings)
        for _, material in targets:
            if not material.library:
                oil.disconnect(material)
        self.report({'INFO'}, f'已从 {len(targets)} 个皮肤材质移除油')
        return {'FINISHED'}


def is_bath_material(material, settings):
    if material == settings.bath_material:
        return True
    if is_face_material(material, settings):
        return settings.bath_face
    name = material_name(material)
    role = str(material.get('bt_effect_role', material.get('zd_role', ''))).upper()
    if role == 'HAIR' or any(t in name for t in ('hair', 'bangs', '髪', '头发', '頭髮', '发丝', '刘海', '辫')):
        return settings.bath_hair
    if is_body_skin(material):
        return settings.bath_skin
    if role in {'CLOTHES', 'CLOTH', 'CLOTHING'} or any(t in name for t in (
            'cloth', 'shirt', 'pants', 'trouser', 'skirt', 'dress', 'jacket', 'coat',
            '衣', '裤', '裙', '袜', '靴', '鞋', '服', 'stocking', 'shoe', 'boot')):
        return settings.bath_clothes
    return False


class CHARACTERFX_OT_apply_bath(bpy.types.Operator):
    bl_idname = 'characterfx.apply_bath'
    bl_label = '添加／更新沐浴露'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_mesh(context) is not None

    def execute(self, context):
        obj = active_mesh(context)
        settings = context.scene.character_effects
        targets = target_materials(obj, is_bath_material, settings)
        if not targets:
            self.report({'ERROR'}, '未找到勾选部位的材质，可在高级设置指定额外应用材质')
            return {'CANCELLED'}
        try:
            bath.ensure_group()
        except (OSError, RuntimeError) as error:
            self.report({'ERROR'}, f'无法读取沐浴露贴图资源：{error}')
            return {'CANCELLED'}
        wanted = {mat.as_pointer() for _, mat in targets}
        for slot in obj.material_slots:
            mat = slot.material
            if mat and not mat.library and mat.get('bt_bath_active') and mat.as_pointer() not in wanted:
                bath.disconnect(mat)
        count = sum(bool(bath.configure(mat, settings, is_face_material(mat, settings)))
                    for _, mat in targets if not mat.library and mat.node_tree)
        self.report({'INFO'}, f'已更新 {count} 个材质的沐浴露')
        return {'FINISHED'}


class CHARACTERFX_OT_remove_bath(bpy.types.Operator):
    bl_idname = 'characterfx.remove_bath'
    bl_label = '移除沐浴露'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return active_mesh(context) is not None

    def execute(self, context):
        for slot in active_mesh(context).material_slots:
            if slot.material and not slot.material.library:
                bath.disconnect(slot.material)
        return {'FINISHED'}


class CHARACTERFX_PT_panel(bpy.types.Panel):
    bl_label = '角色效果'
    bl_idname = 'CHARACTERFX_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = '角色特效'

    def draw(self, context):
        layout = self.layout
        obj = active_mesh(context)
        if not obj:
            layout.label(text='请先激活角色网格物体', icon='INFO')
            return

        settings = context.scene.character_effects
        blush_box = layout.box()
        blush_box.label(text='脸红', icon='BRUSH_DATA')
        blush_box.prop(settings, 'blush_amount', slider=True)
        row = blush_box.row(align=True)
        row.operator('characterfx.apply_blush', icon='ADD')
        row.operator('characterfx.remove_blush', icon='REMOVE')

        water_box = layout.box()
        water_box.label(text='水渍', icon='MATERIAL')
        water_box.prop(settings, 'wet_amount', slider=True)
        row = water_box.row(align=True)
        row.operator('characterfx.apply_wet', icon='ADD')
        row.operator('characterfx.remove_wet', icon='REMOVE')

        oil_box = layout.box()
        oil_box.label(text='油', icon='MATERIAL')
        oil_box.prop(settings, 'oil_amount', slider=True)
        row = oil_box.row(align=True)
        row.operator('characterfx.apply_oil', icon='ADD')
        row.operator('characterfx.remove_oil', icon='REMOVE')

        bath_box = layout.box()
        bath_box.label(text='沐浴露', icon='MATERIAL')
        bath_box.prop(settings, 'bath_amount', slider=True)
        row = bath_box.row(align=True)
        row.prop(settings, 'bath_skin')
        row.prop(settings, 'bath_face')
        row = bath_box.row(align=True)
        row.prop(settings, 'bath_hair')
        row.prop(settings, 'bath_clothes')
        row = bath_box.row(align=True)
        row.operator('characterfx.apply_bath', icon='ADD')
        row.operator('characterfx.remove_bath', icon='REMOVE')

        layout.prop(settings, 'show_advanced' , icon='TRIA_DOWN' if settings.show_advanced else 'TRIA_RIGHT',
                    emboss=False)
        if settings.show_advanced:
            box = layout.box()
            box.label(text='脸红')
            for name in ('blush_color', 'blush_front', 'blush_spacing', 'blush_height',
                         'blush_width', 'blush_radius', 'blush_mask', 'blush_uv'):
                box.prop(settings, name)
            box.prop(settings, 'blush_material')
            box = layout.box()
            box.label(text='水渍')
            for name in ('wet_streams', 'wet_length', 'wet_width', 'wet_thickness', 'wet_roughness',
                         'wet_refraction', 'wet_seed', 'wet_face', 'wet_mask', 'wet_uv'):
                box.prop(settings, name)
            box.prop(settings, 'wet_material')
            box = layout.box()
            box.label(text='油')
            for name in ('oil_gloss', 'oil_roughness', 'oil_face', 'oil_mask', 'oil_uv', 'oil_material'):
                box.prop(settings, name)
            box = layout.box()
            box.label(text='沐浴露 · 贴图节点原作：瑞鵆')
            for name in ('bath_density', 'bath_location', 'bath_roughness', 'bath_specular',
                         'bath_opacity', 'bath_normal', 'bath_material', 'bath_mask', 'bath_uv'):
                box.prop(settings, name)
            layout.label(text='调整参数后，点击“添加／更新”重建效果。')


CLASSES = (
    CharacterEffectsSettings,
    CHARACTERFX_OT_apply_blush,
    CHARACTERFX_OT_remove_blush,
    CHARACTERFX_OT_apply_wet,
    CHARACTERFX_OT_remove_wet,
    CHARACTERFX_OT_apply_oil,
    CHARACTERFX_OT_remove_oil,
    CHARACTERFX_OT_apply_bath,
    CHARACTERFX_OT_remove_bath,
    CHARACTERFX_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.character_effects = PointerProperty(type=CharacterEffectsSettings)


def unregister():
    del bpy.types.Scene.character_effects
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
