# -*- coding: utf-8 -*-
"""R_blmaster — Blender 4.2+ 中文材质、特效与模型 CAD 工具集。"""

# ═══════════════════════════════════════════════════════════════════════════════
# 【教学导读】写给第一次读这份代码的你
#   本版为「教学注释版」：相对基线提交 20db8ad（= R_blmaster_v1.0.6.zip 正典源码，
#   __init__.py md5 14fcee83…）【只增注释与 docstring，零逻辑改动】；
#   需要纯净版时 checkout 基线提交即可逐行对照。
#
# 这份文件是什么
#   一个 Blender 4.2+ 扩展（旧称插件），三大能力板块：
#   ① 材质：PS 式图层堆栈（混合/遮罩/不透明度）+ 程序化材质工厂 + PBR 贴图导入；
#   ② 特效：闪电/表面/几何/消散/音频驱动/体积（雾·雨雪·烟·火·液体）等效果层，
#      全部走「创建面板参数 → update 回调实时驱动节点/修改器」的同一套机制；
#   ③ 模型 CAD：网格 ↔ STEP 导入导出（Part21 写出器）、四边形重拓扑、共面融合。
#
# 三条阅读路线（按目的选）
#   · 想懂「拖滑块为什么实时生效、又为什么偶尔被打回」→ 读「核心机制 A」，
#     再读 update_layer_values / _sync_layer_panel_value / update_layer_opacity。
#   · 想加一种新特效 → 读「核心机制 B」+ 任意一个 MFX_OT_volume_* 操作符
#     + register_effect_layer。
#   · 想懂 STEP 导出 → 读「核心机制 D」+ MFX_Part21Writer / step_coplanar_faces。
#
# 核心机制 A：update 回调与守卫哨兵（全文件最精要的一课）
#   Blender 的属性可挂 update=回调：用户在面板【每拖一帧】都会触发，于是
#   「实时调节」是天然的；危险在于【双向同步】——
#     面板 → 层：update_layer_values 把面板参数写进节点（正向，天然实时）；
#     层 → 面板：行条目改层值后要回填面板读数，但「写面板属性」本身又会触发
#     update 回调 → 不拦截的话，层值会被【面板里滞后的旧值】打回（v1.0.5 实证
#     事故：层强度 0.4→0.5 被面板滞后值打回 0.4），或形成无限回环。
#   解法是两个哨兵 dict（_MFX_REPLAY_GUARD / _LIVE_SYNC_GUARD）：回写前置
#   active=True，finally 必复位；所有 update 回调入口先查哨兵再动手。
#   v1.0.6 修复点：update_layer_values 的拦截条件从只查 _MFX_REPLAY_GUARD 扩为
#   「or _LIVE_SYNC_GUARD["active"]」，与同族先例 update_layer_opacity 对齐。
#
# 核心机制 B：特效层生命周期
#   register_effect_layer 登记（layer_id=uuid；节点/物体/集合/修改器打
#   mfx_effect_layer_id 自定义属性，双向可索引）→ update_*_live 家族实时改参
#   （socket / 修改器输入 / 关键帧重映射）→ 删除操作符按 id 标记拆链清理。
#
# 核心机制 C：材质图层链（PS 式）
#   wire_layer 是唯一接线实现：每层 = Principled(本层) + Mix(PS 式颜色混合，
#   A=下层色链 / B=本层色) + 可选遮罩链 + 强度 ColorRamp；层与层用 prev_chain
#   dict 串成链表，函数内「A 端三变体」注释是理解嵌套混合的钥匙。
#
# 核心机制 D：模型 CAD 线
#   导出：step_mesh_data 取评估网格 → step_coplanar_faces 共面融合（BFS 聚类、
#   种子平面锚定防漂移）→ MFX_Part21Writer 按 ISO-10303-21 逐实体写出（×1000 转 mm）；
#   导入：parse_faceted_step 手写解析 → 顶点去重 / T 结点钉扎 → 建 Blender 网格。
#
# 板块目录（无行号——注释会使行号漂移，请用标识符全局搜索定位；按出现顺序）
#   [基础设施] rebuild_preset_items / load_preview_icons / set_input 等小工具
#   [面板↔层同步] _layer_edit_target / sync_layer_nodes / sync_layer_panel /
#                update_layer_wiring / update_layer_values（v1.0.6 修复点）
#   [实时调节·双向联动] _LIVE_SYNC_GUARD 哨兵 + update_*_live 回调全家族
#   [行条目回写链] _mirror_panel_to_layers / update_layer_row_value / _row_color / _opacity
#   [材质工厂] make_texture_material / apply_texture_preset / make_material
#   [投影形式] mfx_projection_socket / retarget_mfx_projections（GENERATED/OBJECT/WORLD）
#   [连线引擎] wire_layer / can_detach / detach / snapshot / replay_layer_chain
#   [数据模型] MFX_Preferences / MFX_MaterialLayer / MFX_EffectLayer 等属性组
#   [层管理操作符] add / update / remove / select / move / clear_orphans / apply_preset
#   [特效操作符] lightning / pbr 导入 / dissolve / energy_flow / surface / geometry /
#               fracture / volume 系列 / audio_drive / bake / export
#   [模型 CAD] import_model / quad_remesh / export_step / MFX_Part21Writer /
#             step_coplanar_faces / parse_faceted_step
#   [预设与团队] import_preset / save_preset / mark_asset / team_pack
#   [UI 面板] MFX_PT_* 家族（N 面板「R_blmaster」分类）
#   [生命周期] register / unregister
# ═══════════════════════════════════════════════════════════════════════════════

bl_info = {
    "name": "R_blmaster",
    "author": "ERDCX",
    "version": (1, 0, 6),
    "blender": (4, 2, 0),
    "location": "3D视图 > 侧栏 > R_blmaster",
    "description": "程序化材质、动态特效、四边面重拓扑与 STEP 导入导出",
    "category": "Material",
}

import bpy
import bmesh
from bpy.props import (
    BoolProperty, EnumProperty, FloatProperty,
    FloatVectorProperty, IntProperty, StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup
import os
import json
import math
import random
import re
import shutil
import struct
import tempfile
from datetime import datetime
import uuid
import wave
import zipfile
from mathutils import Vector
from bpy.utils import previews
from bpy_extras.io_utils import ImportHelper, ExportHelper


CATEGORIES = ["金属", "塑料与橡胶", "石材与建筑", "木材", "玻璃与陶瓷", "自然与织物", "贴图材质", "团队预设"]
# 贴图预设（Poly Haven CC0，1k JPG × Diffuse/nor_gl/Rough 三通道；出处见 textures/CREDITS.md）
TEXTURE_PRESETS = [
    ("砖墙", "brick_4", "外景墙面与室内背景砖，叠遮罩图层可做风化苔痕"),
    ("混凝土墙", "concrete", "清水混凝土墙面，叠底部磨损可做旧厂房质感"),
    ("木地板", "wood_floor_deck", "室内木地板铺装，叠渐变遮罩可做褪色过渡"),
    ("柏油路", "asphalt_01", "道路沥青面层，叠斑块遮罩可做修补痕迹"),
    ("锈蚀金属", "green_metal_rust", "带锈钢板与集装箱表面，叠斑块可强化锈蚀分布"),
    ("碎石地面", "gravel", "户外碎石与砾石小路，叠噪声遮罩可混生苔藓"),
    ("牛仔布", "denim_fabric", "布艺与服饰材质，叠柔光图层可调色"),
    ("瓷砖地面", "brown_floor_tiles", "室内瓷砖铺装，叠棋盘格遮罩可换色分区"),
]
TEMPLATES = [
    ("拉丝不锈钢", "金属", (0.42, 0.46, 0.50, 1), 0.28, 0.92, 22.0, "brushed"),
    ("锈蚀钢铁", "金属", (0.34, 0.12, 0.045, 1), 0.78, 0.72, 5.0, "rust"),
    ("黄铜", "金属", (0.62, 0.37, 0.12, 1), 0.30, 0.88, 32.0, "metal"),
    ("抛光铝", "金属", (0.68, 0.72, 0.77, 1), 0.18, 0.95, 12.0, "metal"),
    ("铸铁", "金属", (0.12, 0.13, 0.14, 1), 0.66, 0.82, 8.0, "cast_iron"),
    ("硬质塑料", "塑料与橡胶", (0.12, 0.24, 0.35, 1), 0.28, 0.0, 34.0, "plastic"),
    ("哑光塑料", "塑料与橡胶", (0.48, 0.12, 0.08, 1), 0.58, 0.0, 42.0, "plastic"),
    ("黑色橡胶", "塑料与橡胶", (0.025, 0.03, 0.035, 1), 0.88, 0.0, 48.0, "rubber"),
    ("混凝土", "石材与建筑", (0.36, 0.35, 0.32, 1), 0.90, 0.0, 3.5, "concrete"),
    ("红砖", "石材与建筑", (0.38, 0.10, 0.055, 1), 0.82, 0.0, 7.0, "brick"),
    ("花岗岩", "石材与建筑", (0.22, 0.23, 0.24, 1), 0.64, 0.0, 5.0, "granite"),
    ("沥青", "石材与建筑", (0.075, 0.08, 0.085, 1), 0.92, 0.0, 11.0, "asphalt"),
    ("深色橡木", "木材", (0.20, 0.075, 0.028, 1), 0.54, 0.0, 7.0, "wood"),
    ("浅色枫木", "木材", (0.66, 0.39, 0.16, 1), 0.48, 0.0, 9.0, "wood"),
    ("胡桃木", "木材", (0.24, 0.105, 0.055, 1), 0.46, 0.0, 11.0, "wood"),
    ("透明玻璃", "玻璃与陶瓷", (0.72, 0.86, 0.92, 1), 0.06, 0.0, 20.0, "glass"),
    ("白色釉面陶瓷", "玻璃与陶瓷", (0.82, 0.80, 0.74, 1), 0.18, 0.0, 16.0, "ceramic"),
    ("大理石", "玻璃与陶瓷", (0.60, 0.58, 0.54, 1), 0.30, 0.0, 5.0, "marble"),
    ("牛皮革", "自然与织物", (0.22, 0.075, 0.04, 1), 0.68, 0.0, 19.0, "leather"),
    ("棉布", "自然与织物", (0.40, 0.34, 0.27, 1), 0.96, 0.0, 26.0, "fabric"),
    ("森林苔藓", "自然与织物", (0.075, 0.19, 0.045, 1), 0.94, 0.0, 11.0, "moss"),
    ("湿润土壤", "自然与织物", (0.20, 0.105, 0.045, 1), 0.98, 0.0, 8.0, "soil"),
    ("细沙", "自然与织物", (0.66, 0.49, 0.25, 1), 0.92, 0.0, 35.0, "sand"),
    ("积雪", "自然与织物", (0.82, 0.88, 0.92, 1), 0.9, 0.0, 24.0, "snow"),
    ("蓝冰", "自然与织物", (0.32, 0.62, 0.78, 1), 0.16, 0.0, 7.0, "ice"),
    ("清澈水面", "自然与织物", (0.025, 0.19, 0.28, 1), 0.08, 0.0, 5.0, "water"),
    ("树皮", "自然与织物", (0.20, 0.085, 0.035, 1), 0.93, 0.0, 15.0, "bark"),
    ("阔叶植被", "自然与织物", (0.055, 0.25, 0.035, 1), 0.78, 0.0, 19.0, "foliage"),
    ("紫铜", "金属", (0.72, 0.32, 0.12, 1), 0.32, 0.92, 18.0, "brushed"),
    ("青铜绿锈", "金属", (0.16, 0.36, 0.28, 1), 0.74, 0.55, 6.0, "rust"),
    ("镀锌钢", "金属", (0.55, 0.58, 0.60, 1), 0.42, 0.88, 28.0, "metal"),
    ("亚克力板", "塑料与橡胶", (0.78, 0.88, 0.90, 1), 0.10, 0.0, 26.0, "glass"),
    ("碳纤维", "塑料与橡胶", (0.045, 0.05, 0.06, 1), 0.24, 0.10, 30.0, "brushed"),
    ("砂岩", "石材与建筑", (0.62, 0.50, 0.32, 1), 0.88, 0.0, 4.0, "concrete"),
    ("抹灰墙面", "石材与建筑", (0.78, 0.76, 0.72, 1), 0.85, 0.0, 3.0, "concrete"),
    ("清漆木面", "木材", (0.30, 0.12, 0.05, 1), 0.22, 0.0, 9.0, "wood"),
    ("竹材", "木材", (0.55, 0.48, 0.20, 1), 0.42, 0.0, 14.0, "wood"),
    ("磨砂玻璃", "玻璃与陶瓷", (0.75, 0.85, 0.90, 1), 0.45, 0.0, 20.0, "glass"),
    ("赤陶土", "玻璃与陶瓷", (0.55, 0.25, 0.14, 1), 0.72, 0.0, 10.0, "ceramic"),
    ("丝绸", "自然与织物", (0.55, 0.20, 0.28, 1), 0.35, 0.0, 22.0, "fabric"),
]
VARIANTS = [("标准", 1.0), ("浅色", 1.24), ("深色", 0.72)]
PREVIEW_COLLECTION = None
PRESET_PREVIEW_IDS = {}
PRESET_ITEMS_BY_CATEGORY = {}
DEFAULT_PRESET_ITEMS = ()
CUSTOM_PRESET_ITEMS = ()
NO_PRESET_ITEMS = (("NO_PRESET_MATCH", "没有匹配的预设", "请修改搜索词或收藏筛选", 0, 0),)


# ─────────────────────────────────────────────────────────────────────────────
# [基础设施层] 预设枚举刷新 / 图标预载 / 通用小工具。
# 教学点：rebuild_preset_items 挂 bpy.app.timers 延迟一拍执行——注册期 bpy.data
# 尚不可靠（见 register() 内原注释），「先注册、后补扫」是 Blender 扩展的
# 标准起手式；load_post 处理器再负责每次开文件后的重扫（见 _mfx_on_load_post）。

def rebuild_preset_items():
    global PRESET_ITEMS_BY_CATEGORY, DEFAULT_PRESET_ITEMS, CUSTOM_PRESET_ITEMS
    by_category = {}
    template_icons = {name: PRESET_PREVIEW_IDS.get(f"{name}_{VARIANTS[0][0]}", 0) for name, *_ in TEMPLATES}
    for category in CATEGORIES:
        items = []
        for name, template_category, _color, _roughness, _metallic, _scale, _style in TEMPLATES:
            if template_category == category:
                for variant, _factor in VARIANTS:
                    identifier = f"{name}_{variant}"
                    label = f"{name} · {variant}"
                    description = f"{template_category}现实材质预设"
                    items.append((identifier, label, description, PRESET_PREVIEW_IDS.get(identifier, template_icons[name]), len(items)))
        by_category[category] = tuple(items)
    tex_items = []
    for name, slug, tip in TEXTURE_PRESETS:
        tex_items.append((slug, name, tip, PRESET_PREVIEW_IDS.get(slug, 0), len(tex_items)))
    by_category["贴图材质"] = tuple(tex_items)
    custom_items = []
    if hasattr(bpy.data, "materials"):  # 注册/注销期 bpy.data 为受限对象（_RestrictData），跳过团队预设扫描
        for material in bpy.data.materials:
            preset_id = material.get("mfx_pack_preset_id", "")
            preview_path = material.get("mfx_pack_preview_path", "")
            if not preset_id:
                continue
            icon_id = PRESET_PREVIEW_IDS.get(preset_id, 0)
            if PREVIEW_COLLECTION is not None and preview_path and os.path.isfile(preview_path) and preset_id not in PRESET_PREVIEW_IDS:
                try:
                    PREVIEW_COLLECTION.load(preset_id, preview_path, "IMAGE")
                    icon_id = PREVIEW_COLLECTION[preset_id].icon_id
                    PRESET_PREVIEW_IDS[preset_id] = icon_id
                except Exception:
                    icon_id = 0
            custom_items.append((preset_id, material.get("mfx_pack_label", material.name),
                                 "已导入的团队材质预设", icon_id, len(custom_items)))
        CUSTOM_PRESET_ITEMS = tuple(custom_items)
        by_category["团队预设"] = CUSTOM_PRESET_ITEMS
    PRESET_ITEMS_BY_CATEGORY = by_category
    DEFAULT_PRESET_ITEMS = by_category[CATEGORIES[0]]


def _mfx_on_load_post(*_args):
    """文件加载后重建预设列表（补上注册期受限于 _RestrictData 而跳过的团队预设扫描）。"""
    rebuild_preset_items()


def preset_items(self, context):
    cat = getattr(self, "category", CATEGORIES[0])
    items = PRESET_ITEMS_BY_CATEGORY.get(cat, DEFAULT_PRESET_ITEMS)
    query = getattr(self, "search", "").strip().casefold()
    if query:
        items = tuple(item for item in items if query in item[1].casefold())
    if getattr(self, "favorite_only", False):
        scene = getattr(self, "id_data", None)
        favorites = {entry.identifier for entry in getattr(scene, "mfx_favorites", [])}
        items = tuple(item for item in items if item[0] in favorites)
    return items or NO_PRESET_ITEMS


def load_preview_icons():
    global PREVIEW_COLLECTION, PRESET_PREVIEW_IDS
    if PREVIEW_COLLECTION is None:
        PREVIEW_COLLECTION = previews.new()
    PRESET_PREVIEW_IDS = {}
    preview_dir = os.path.join(os.path.dirname(__file__), "previews")
    index = 0
    for name, *_rest in TEMPLATES:
        for variant, _factor in VARIANTS:
            identifier = f"{name}_{variant}"
            filepath = os.path.join(preview_dir, f"{index:02d}.png")
            if os.path.isfile(filepath):
                PREVIEW_COLLECTION.load(identifier, filepath, "IMAGE")
                PRESET_PREVIEW_IDS[identifier] = PREVIEW_COLLECTION[identifier].icon_id
            index += 1
    for _name, slug, _tip in TEXTURE_PRESETS:
        filepath = os.path.join(preview_dir, f"{slug}.png")
        if os.path.isfile(filepath):
            PREVIEW_COLLECTION.load(slug, filepath, "IMAGE")
            PRESET_PREVIEW_IDS[slug] = PREVIEW_COLLECTION[slug].icon_id
    rebuild_preset_items()


def active_material(context):
    obj = context.object
    return obj.active_material if obj else None


def effect_start_frame(scene, props):
    """Use a shared frame when set, otherwise begin at the current timeline frame."""
    return props.effect_start_frame if props.effect_start_frame >= 0 else scene.frame_current


def set_input(node, name, value):
    socket = node.inputs.get(name)
    if socket is not None:
        socket.default_value = value


def effect_animation_actions(layer):
    """Return animation actions owned by an effect layer's object/material data."""
    actions = []
    material = bpy.data.materials.get(layer.material_name) if layer.material_name else None
    obj = bpy.data.objects.get(layer.object_name) if layer.object_name else None
    datablocks = [obj, getattr(obj, "data", None) if obj else None, material,
                  getattr(material, "node_tree", None) if material else None]
    if obj and layer.modifier_name:
        modifier = obj.modifiers.get(layer.modifier_name)
        datablocks.append(getattr(modifier, "node_group", None) if modifier else None)
    seen = set()
    for datablock in datablocks:
        animation_data = getattr(datablock, "animation_data", None)
        action = getattr(animation_data, "action", None) if animation_data else None
        if action and action.as_pointer() not in seen:
            actions.append(action)
            seen.add(action.as_pointer())
    return actions


def apply_effect_animation_options(layer):
    """Apply per-layer F-curve interpolation and repetition to owned animations."""
    for action in effect_animation_actions(layer):
        for curve in action.fcurves:
            for key in curve.keyframe_points:
                if layer.easing != "KEEP" and key.interpolation != "CONSTANT":
                    key.interpolation = layer.easing
                if layer.easing == "BEZIER":
                    key.handle_left_type = "AUTO_CLAMPED"
                    key.handle_right_type = "AUTO_CLAMPED"
            cycles = next((modifier for modifier in curve.modifiers if modifier.type == "CYCLES"), None)
            if layer.loop_mode == "NONE":
                if cycles:
                    curve.modifiers.remove(cycles)
            else:
                cycles = cycles or curve.modifiers.new("CYCLES")
                cycles.mode_before = layer.loop_mode
                cycles.mode_after = layer.loop_mode
            curve.update()


def update_effect_layer_animation(layer, context):
    apply_effect_animation_options(layer)


def draw_author_footer(layout):
    row = layout.row()
    row.alignment = "RIGHT"
    row.scale_y = 0.72
    row.label(text="ERDCX")


_MFX_REPLAY_GUARD = {"active": False}


def resolve_layer_material(layer):
    material = bpy.data.materials.get(layer.material_name) if layer.material_name else None
    if material and material.use_nodes and material.node_tree:
        return material
    owner = bpy.data.objects.get(layer.object_name) if layer.object_name else None
    material = owner.active_material if owner else None
    if material and material.use_nodes and material.node_tree and material.node_tree.nodes.get(layer.blend_node):
        return material
    return None


def layer_belongs_to_material(layer, material, obj=None):
    if not material or not material.use_nodes or not material.node_tree:
        return False
    owner = resolve_layer_material(layer)
    if owner:
        return owner == material
    if layer.material_name:
        return False
    if layer.object_name and obj and layer.object_name != obj.name:
        return False
    return material.node_tree.nodes.get(layer.blend_node) is not None


def layer_is_orphan(layer):
    material = resolve_layer_material(layer)
    return not material or not material.node_tree.nodes.get(layer.blend_node)


# ─────────────────────────────────────────────────────────────────────────────
# [面板↔层同步核心] 材质图层编辑的五个关键函数，分工如下：
#   _layer_edit_target —— 「当前在编辑谁」的唯一裁决：活动物体须有节点材质，
#       行索引须在界内，且该层必须真属于活动材质（防残留条目串台）。
#   sync_layer_nodes   —— 正向·改节点：直接更新已有节点的 socket 值，避免拖动
#       时反复拆建整棵链（性能与视图稳定性的关键取舍）。
#   sync_layer_panel   —— 反向·改面板：选中行后把面板控件刷成本层参数；全程举着
#       _MFX_REPLAY_GUARD 哨兵，防止回填动作反向触发 update 回调。
#   update_layer_wiring —— 结构性变更（换遮罩类型等）才走整链重建。
#   update_layer_values —— 数值性变更（颜色/粗糙度/强度/不透明度）走软更新。
#   教学点：「软更新优先、重建兜底」是节点式扩展的通用性能心法。

def _layer_edit_target(context):
    """取「面板参数可编辑」的当前选中图层：必须归属当前活动材质（残留条目返回 None）。"""
    obj = context.object
    if not obj or not obj.active_material or not obj.active_material.use_nodes:
        return None
    scene = context.scene
    layers = scene.mfx_layers
    if not 0 <= scene.mfx_layer_index < len(layers):
        return None
    layer = layers[scene.mfx_layer_index]
    if not layer_belongs_to_material(layer, obj.active_material, obj):
        return None
    return layer


def sync_layer_nodes(material, layer):
    """直接更新当前层参数，避免拖动颜色/强度时反复拆建整棵节点链。"""
    if not material or not material.use_nodes or not material.node_tree:
        return False
    nt = material.node_tree
    shader = nt.nodes.get(layer.shader_node)
    if not shader:
        return False
    set_input(shader, "Base Color", layer.color)
    set_input(shader, "Roughness", layer.roughness)
    color_mix = nt.nodes.get(layer.color_mix_node) if layer.color_mix_node else None
    if color_mix:
        b_socket = next((socket for socket in color_mix.inputs if socket.name == "B" and socket.type == "RGBA"), None)
        if b_socket:
            b_socket.default_value = layer.color
    mask = nt.nodes.get(layer.mask_node) if layer.mask_node else None
    if mask and layer.mask_type in {"NOISE", "OBJECT", "WAVE", "RINGS", "CHECKER", "BLOTCH"}:
        scale_socket = mask.inputs.get("Scale")
        if scale_socket:
            scale_socket.default_value = max(1.0, layer.pattern_scale * 0.4) if layer.mask_type == "BLOTCH" else layer.pattern_scale
    strength_node = nt.nodes.get(layer.strength_node) if layer.strength_node else None
    if strength_node and strength_node.type == "VALTORGB":
        mid = 1.0 - layer.strength
        ramp = strength_node.color_ramp.elements
        ramp[0].position = max(0.0, mid - 0.2)
        ramp[1].position = min(1.0, max(ramp[0].position + 0.05, mid + 0.2))
    return True


def sync_layer_panel(context, layer):
    """选中图层后把面板控件切换到这层当前保存的参数。"""
    props = context.scene.mfx_props
    guard = _MFX_REPLAY_GUARD
    guard["active"] = True
    try:
        props.layer_color = tuple(layer.color)
        props.layer_roughness = layer.roughness
        props.layer_strength = layer.strength
        props.layer_pattern_scale = layer.pattern_scale
        props.layer_opacity = layer.opacity
        props.layer_mask_direction = getattr(layer, "mask_direction", "Z")
        props.layer_mask_azimuth = getattr(layer, "mask_azimuth", 0.0)
        props.layer_mask_elevation = getattr(layer, "mask_elevation", 0.0)
        try:
            props.layer_blend_mode = layer.blend_mode
        except (TypeError, ValueError):
            pass
        try:
            props.layer_mask = layer.mask_type
        except (TypeError, ValueError):
            pass
    finally:
        guard["active"] = False


def update_layer_wiring(props, context):
    """面板 混合模式/智能遮罩 变更：对当前选中层整链重放（v0.9.4 PS 化语义，无残留归属时不动作）。"""
    if _MFX_REPLAY_GUARD["active"]:
        return
    if _layer_edit_target(context) is None:
        return
    props_panel = context.scene.mfx_props
    replay_layer_chain(context, context.scene.mfx_layer_index,
                       {"blend_mode": props_panel.layer_blend_mode, "mask_type": props_panel.layer_mask,
                        "mask_direction": props_panel.layer_mask_direction,
                        "mask_azimuth": props_panel.layer_mask_azimuth, "mask_elevation": props_panel.layer_mask_elevation})


def update_layer_values(props, context):
    """面板颜色/粗糙度/遮罩/不透明度变更：只更新当前层相关节点。

    教学注（v1.0.6 修复点）：本函数是「面板 → 层」的正向入口，被 layer_color /
    layer_roughness / layer_strength / layer_pattern_scale / layer_opacity 等
    面板属性的 update= 挂载，拖动滑块时 Blender 每帧调用一次。若此刻正处于
    「层 → 面板」回填（_LIVE_SYNC_GUARD 活跃，例如行强度滑块回填面板读数），
    面板里躺着的还是【滞后旧值】，任由本函数执行就会把层打回旧值——即 v1.0.5
    的「回弹」事故（实证：层强度 0.4→0.5 被面板滞后值 0.4 打回，对照组正向
    0.8 正常）。修法 = 拦截条件补查 _LIVE_SYNC_GUARD，与同族先例
    update_layer_opacity 对齐：「谁在回填，谁举哨兵；所有正向入口，先看哨兵
    再动手」。
    """
    if _MFX_REPLAY_GUARD["active"] or _LIVE_SYNC_GUARD["active"]:  # v1.0.6：行值回填期间用面板滞后值回写层会回弹，需一并拦截
        return
    layer = _layer_edit_target(context)
    if layer is None:
        return
    panel = context.scene.mfx_props
    guard = _MFX_REPLAY_GUARD
    guard["active"] = True
    try:
        layer.color = tuple(panel.layer_color)
        layer.roughness = panel.layer_roughness
        layer.strength = panel.layer_strength
        layer.pattern_scale = panel.layer_pattern_scale
        layer.opacity = panel.layer_opacity
        material = context.object.active_material
        sync_layer_nodes(material, layer)
    finally:
        guard["active"] = False
    update_layer_opacity(layer, context)


# ── v1.0.5 实时调节与双向联动（管理员 20:45 指令 + 20:48/20:54 扩令，全栈实现）────────
# 设计要点：
# 1) 创建面板参数接 update 回调 → 定位已建特效层 → 直改节点 socket / 修改器输入 / 关键帧；
# 2) 图层堆栈参数改动 → 反向回填面板读数（_LIVE_SYNC_GUARD 防回环，先例 _MFX_REPLAY_GUARD）；
# 3) 结构类参数（拓扑/种子/数量类）保留「重新添加生效」语义，tooltip 已标注，不硬扛引擎机制；
# 4) 模拟分辨率/时长改动 → 失效旧缓存 + 去抖 0.8s 自动重烘焙（timer 驱动，不冻 UI）。

# [哨兵 101] 为什么是 dict 而不是 bool：字典是可变对象，函数内 guard["active"]=True
#   改的是同一个对象，无需 global 声明——全文件哨兵的统一写法。配套纪律：置位与
#   复位必须 try/finally 包夹，回填中途抛异常也绝不把哨兵留在 True，否则面板
#   永久失灵。「回弹」故障模型：面板(旧值) --update--> 层 ← 回填方想写(新值)；
#   层(新) --回填--> 面板(仍显旧值) --update--> 层被打回(旧)。两个哨兵分工：
#   _MFX_REPLAY_GUARD 管「选中行后的面板整体重刷」，_LIVE_SYNC_GUARD 管
#   「实时调节期间的字段级回填」；v1.0.6 起正向入口两边都查。

_LIVE_SYNC_GUARD = {"active": False}
_VOLUME_BAKE_PENDING = {"timer": None}


def _sync_layer_panel_value(context, effect_type, prop_name, value):
    """联动·特效页反向：把层值回填到创建面板对应参数（值恒等，guard 防回环）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    panel = context.scene.mfx_props
    current = getattr(panel, prop_name, None)
    if current is None or abs(float(current) - float(value)) < 1e-6:
        return
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        setattr(panel, prop_name, value)
    except Exception:
        pass
    finally:
        guard["active"] = False
    if getattr(context, "area", None) is not None:
        context.area.tag_redraw()


def _live_layer_materials(context, effect_types):
    """收集指定类型特效层的 (layer, material, obj) 三元组（v1.0.5 实时调节）。"""
    out = []
    for layer in context.scene.mfx_effect_layers:
        if layer.effect_type not in effect_types:
            continue
        material = bpy.data.materials.get(layer.material_name) if layer.material_name else None
        obj = bpy.data.objects.get(layer.object_name) if layer.object_name else None
        out.append((layer, material, obj))
    return out


def _rescale_action_frames(action, old_start, old_span, new_start, new_span):
    """把 action 全部关键帧从 [old_start, old_start+old_span] 线性重映射到新区间。"""
    if not action or old_span <= 0 or new_span <= 0:
        return
    for curve in action.fcurves:
        for key in curve.keyframe_points:
            offset = key.co.x - old_start
            key.co.x = new_start + (offset / old_span) * new_span
        curve.update()


def retarget_layer_frames(layer, new_start=None, new_span=None):
    """帧数/起始帧类参数实时：全局平移起点 + 线性缩放跨度（v1.0.5）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    frames = []
    for action in effect_animation_actions(layer):
        for curve in action.fcurves:
            for key in curve.keyframe_points:
                frames.append(key.co.x)
    if not frames:
        return
    old_start, old_end = min(frames), max(frames)
    old_span = max(old_end - old_start, 1.0)
    target_start = old_start if new_start is None else new_start
    target_span = old_span if new_span is None else max(new_span, 1.0)
    for action in effect_animation_actions(layer):
        _rescale_action_frames(action, old_start, old_span, target_start, target_span)


def update_frames_live(self, context):
    """时长类参数实时：闪电/表面/几何/消散/能量流/碎裂各层动画跨度重排。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    start = effect_start_frame(context.scene, p)
    plans = {
        "LIGHTNING": p.lightning_duration,
        "HOLOGRAM": p.surface_effect_frames, "GLITCH": p.surface_effect_frames,
        "FIRE": p.surface_effect_frames, "FROST": p.surface_effect_frames,
        "CORROSION": p.surface_effect_frames, "PULSE": p.surface_effect_frames,
        "TOON": p.surface_effect_frames, "OUTLINE": p.surface_effect_frames,
        "GEOMETRY": p.geometry_effect_frames, "PARTICLES": p.geometry_effect_frames,
        "DISSOLVE": p.dissolve_frames, "ENERGY": p.flow_frames,
    }
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer in context.scene.mfx_effect_layers:
            span = plans.get(layer.effect_type)
            if span is not None:
                retarget_layer_frames(layer, new_start=start, new_span=span)
            elif layer.effect_type == "FRACTURE":
                retarget_layer_frames(layer, new_start=start, new_span=max(p.fragment_frames, 4) * 2)
    finally:
        guard["active"] = False


def update_start_frame_live(self, context):
    """统一起始帧实时：全部层动画起点平移（负值=跟随当前帧语义，不动作）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    if p.effect_start_frame < 0:
        return
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer in context.scene.mfx_effect_layers:
            frames = []
            for action in effect_animation_actions(layer):
                for curve in action.fcurves:
                    for key in curve.keyframe_points:
                        frames.append(key.co.x)
            if frames:
                old_start = min(frames)
                shift = p.effect_start_frame - old_start
                for action in effect_animation_actions(layer):
                    for curve in action.fcurves:
                        for key in curve.keyframe_points:
                            key.co.x += shift
                        curve.update()
    finally:
        guard["active"] = False


def update_fragment_live(self, context):
    """碎裂重组实时：飞散距离比例缩放 + 时长/起始帧重排（种子/数量为结构类，重新添加生效）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer in context.scene.mfx_effect_layers:
            if layer.effect_type != "FRACTURE":
                continue
            collection = bpy.data.collections.get(layer.collection_name) if layer.collection_name else None
            if not collection:
                continue
            old_distance = layer.get("mfx_fragment_distance", None)
            if old_distance and old_distance > 0 and abs(old_distance - p.fragment_distance) > 1e-6:
                ratio = p.fragment_distance / old_distance
                for shard in collection.objects:
                    action = shard.animation_data.action if shard.animation_data else None
                    if not action:
                        continue
                    for curve in action.fcurves:
                        if curve.data_path != "location":
                            continue
                        keys = curve.keyframe_points
                        if len(keys) < 2:
                            continue
                        # 逐分量：base=起始位置（第一关键帧），后续位置按比例缩放
                        for key_index in (1, 2):
                            if key_index < len(keys):
                                base = keys[0].co.y
                                keys[key_index].co.y = base + (keys[key_index].co.y - base) * ratio
                        curve.update()
            layer["mfx_fragment_distance"] = p.fragment_distance
            retarget_layer_frames(layer, new_start=effect_start_frame(context.scene, p),
                                  new_span=max(p.fragment_frames, 4) * 2)
    finally:
        guard["active"] = False


def update_loop_mode_live(self, context):
    """面板循环/缓动实时：同步应用到全部现有层（v1.0.5）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer in context.scene.mfx_effect_layers:
            changed = False
            if layer.loop_mode != p.effect_loop_mode:
                layer.loop_mode = p.effect_loop_mode
                changed = True
            if layer.easing != p.effect_easing:
                layer.easing = p.effect_easing
                changed = True
            if changed:
                apply_effect_animation_options(layer)
    finally:
        guard["active"] = False


def update_audio_gain_live(self, context):
    """音频增益实时：等比缩放已被音频驱动过的强度关键帧（采样间隔为结构类，重新执行写入生效）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for material in bpy.data.materials:
            node_path = material.get("mfx_audio_curve_path", None)
            old_gain = material.get("mfx_audio_gain_value", None)
            if not node_path or not material.use_nodes:
                continue
            if old_gain and old_gain > 0 and abs(old_gain - p.audio_gain) > 1e-6:
                ratio = p.audio_gain / old_gain
                nt = material.node_tree
                action = nt.animation_data.action if nt.animation_data else None
                if action:
                    for curve in action.fcurves:
                        if curve.data_path == node_path:
                            for key in curve.keyframe_points:
                                key.co.y *= ratio
                            curve.update()
            material["mfx_audio_gain_value"] = p.audio_gain
    finally:
        guard["active"] = False


def update_lightning_live(self, context):
    """雷电实时：颜色/强度（含闪烁关键帧等比缩放）/线宽即时生效（数量/分支/种子为结构类，重新添加生效）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer, material, obj in _live_layer_materials(context, {"LIGHTNING"}):
            if material and material.use_nodes:
                emission = material.node_tree.nodes.get(layer.emission_node) if layer.emission_node else None
                if emission is None:
                    emission = next((n for n in material.node_tree.nodes if n.type == "EMISSION"), None)
                if emission:
                    emission.inputs["Color"].default_value = (p.lightning_color[0], p.lightning_color[1], p.lightning_color[2], 1.0)
                    socket = emission.inputs["Strength"]
                    action = material.node_tree.animation_data.action if material.node_tree.animation_data else None
                    curves = [c for c in action.fcurves if c.data_path.startswith(f'nodes["{emission.name}"]')] if action else []
                    if curves:
                        old = layer.get("mfx_lightning_strength", socket.default_value) or socket.default_value
                        if old > 0:
                            ratio = p.lightning_strength / old
                            for curve in curves:
                                for key in curve.keyframe_points:
                                    key.co.y *= ratio
                                curve.update()
                    socket.default_value = p.lightning_strength
            if obj and obj.type == "CURVE":
                unit = obj.get("mfx_width_unit", None)
                if unit:
                    obj.data.bevel_depth = p.lightning_width * unit
            if abs(layer.strength - p.lightning_strength) > 1e-6:
                layer.strength = p.lightning_strength
            layer.strength_base = p.lightning_strength
            layer["mfx_lightning_strength"] = p.lightning_strength
    finally:
        guard["active"] = False


def update_surface_live(self, context):
    """表面特效实时：颜色/强度/卡通与轮廓落点即时生效（类型/方向为结构类，重新添加生效）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        surface_types = {"HOLOGRAM", "GLITCH", "FIRE", "FROST", "CORROSION", "PULSE", "TOON", "OUTLINE"}
        for layer, material, obj in _live_layer_materials(context, surface_types):
            if material and material.use_nodes:
                nt = material.node_tree
                emission = nt.nodes.get(layer.emission_node) if layer.emission_node else None
                if emission is None:
                    emission = next((n for n in nt.nodes if n.type == "EMISSION"), None)
                if emission:
                    emission.inputs["Color"].default_value = (p.surface_effect_color[0], p.surface_effect_color[1], p.surface_effect_color[2], 1.0)
                    socket = emission.inputs["Strength"]
                    action = nt.animation_data.action if nt.animation_data else None
                    curves = [c for c in action.fcurves if c.data_path.startswith(f'nodes["{emission.name}"]')] if action else []
                    if curves and layer.effect_type == "PULSE":
                        old = layer.get("mfx_surface_strength", socket.default_value) or socket.default_value
                        if old > 0:
                            ratio = p.surface_effect_strength / old
                            for curve in curves:
                                for key in curve.keyframe_points:
                                    key.co.y *= ratio
                                curve.update()
                    if layer.effect_type != "PULSE" or not curves:
                        socket.default_value = p.surface_effect_strength
                if layer.effect_type == "TOON":
                    ramp = next((n for n in nt.nodes if n.type == "VALTORGB" and n.name != "ColorRamp"), None) or next((n for n in nt.nodes if n.type == "VALTORGB"), None)
                    if ramp:
                        elements = ramp.color_ramp.elements
                        base = (p.surface_effect_color[0], p.surface_effect_color[1], p.surface_effect_color[2])
                        elements[-1].color = (*base, 1.0)
                        if len(elements) >= 2:
                            elements[len(elements) // 2].color = (*[c * 0.55 for c in base], 1.0)
                if layer.effect_type == "FIRE":
                    ramp = next((n for n in nt.nodes if n.type == "VALTORGB" and "Fire" in (n.label or "")), None)
                    if ramp:
                        ramp.color_ramp.elements[-1].color = (p.surface_effect_color[0], p.surface_effect_color[1], p.surface_effect_color[2], 1.0)
            if layer.effect_type == "OUTLINE" and obj:
                shell = obj
                if shell.name.startswith("MFX 轮廓光") or "MFX 轮廓光" in shell.name:
                    for modifier in shell.modifiers:
                        if modifier.type == "SOLIDIFY":
                            modifier.thickness = p.surface_effect_strength * 0.004
            if abs(layer.strength - p.surface_effect_strength) > 1e-6:
                layer.strength = p.surface_effect_strength
            layer.strength_base = p.surface_effect_strength
            layer["mfx_surface_strength"] = p.surface_effect_strength
    finally:
        guard["active"] = False


def update_geometry_live(self, context):
    """几何特效实时：强度/粒子密度走层 strength 镜像；粒子半径直改 GN 树（类型/方向为结构类，重新添加生效）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer, material, obj in _live_layer_materials(context, {"GEOMETRY", "PARTICLES"}):
            if obj and layer.modifier_name:
                modifier = obj.modifiers.get(layer.modifier_name)
                if modifier and modifier.node_group:
                    for node in modifier.node_group.nodes:
                        if node.type == "MESH_ICOSPHERE":
                            try:
                                node.inputs["Radius"].default_value = p.geometry_particle_size
                            except Exception:
                                pass
    finally:
        guard["active"] = False


def update_rain_snow_live(self, context):
    """天气粒子实时：数量/覆盖范围/风偏即时生效（类型切换为结构类，重新添加生效）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer, material, obj in _live_layer_materials(context, {"RAIN", "SNOW"}):
            if not obj:
                continue
            for particle_system in obj.particle_systems:
                particle_system.settings.count = p.rain_snow_count
                particle_system.settings.frame_end = max(p.volume_frames, 2)
            unit = obj.get("mfx_span_unit", None)
            if unit:
                span = max(unit * p.rain_snow_area, 1.0)
                obj.scale = (span, span, obj.scale.z if obj.scale.z else 0.05)
            direction = volume_direction_vector(p)
            if direction is not None:
                obj.rotation_euler = (direction.y * math.radians(12.0), -direction.x * math.radians(12.0), 0.0)
    finally:
        guard["active"] = False


def update_fog_live(self, context):
    """雾参数实时：密度/颜色/形态规模/流动开关/方向全部即时生效。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer, material, obj in _live_layer_materials(context, {"VOLUME_FOG"}):
            if not (material and material.use_nodes):
                continue
            nt = material.node_tree
            noise = next((n for n in nt.nodes if n.label == "MFX 雾噪声"), None)
            if noise:
                noise.inputs["Scale"].default_value = p.fog_noise_scale
            vol = next((n for n in nt.nodes if n.type == "PRINCIPLED_VOLUME"), None)
            if vol:
                vol.inputs["Color"].default_value = (p.fog_color[0], p.fog_color[1], p.fog_color[2], 1.0)
            density_node = next((n for n in nt.nodes if n.label == "雾密度调制"), None)
            if density_node:
                density_node.inputs[1].default_value = p.fog_density
            mapping = nt.nodes.get("MFX 雾流向")
            if mapping:
                path = f'nodes["{mapping.name}"].inputs[1].default_value'
                action = nt.animation_data.action if nt.animation_data else None
                if action:
                    for curve in list(action.fcurves):
                        if curve.data_path == path:
                            action.fcurves.remove(curve)
                if p.fog_animate:
                    flow = (volume_direction_vector(p) or Vector((0.0, 0.0, 1.0))) * 2.0
                    loc_in = mapping.inputs["Location"]
                    loc_in.default_value = Vector((0.0, 0.0, 0.0))
                    loc_in.keyframe_insert("default_value", frame=1)
                    loc_in.default_value = flow
                    loc_in.keyframe_insert("default_value", frame=max(p.volume_frames, 2))
                    new_action = nt.animation_data.action if nt.animation_data else None
                    if new_action:
                        for curve in new_action.fcurves:
                            if curve.data_path == path:
                                for key in curve.keyframe_points:
                                    key.interpolation = "LINEAR"
            if abs(layer.strength - p.fog_density) > 1e-6:
                layer.strength = p.fog_density
            layer.strength_base = p.fog_density
    finally:
        guard["active"] = False


def _volume_bake_state_text(context):
    """面板状态行：聚合全部流体域缓存三态（已就绪 / 已失效待重烘焙 / 烘焙中）。"""
    layers = getattr(context.scene, "mfx_effect_layers", [])
    invalid = 0
    baking = 0
    ready = 0
    for layer in layers:
        if layer.effect_type not in {"VOLUME_SMOKE", "VOLUME_FIRE", "VOLUME_LIQUID"}:
            continue
        obj = bpy.data.objects.get(layer.object_name) if layer.object_name else None
        if not obj or not obj.modifiers:
            continue
        try:
            settings = obj.modifiers[0].domain_settings
            info = getattr(settings, "cache_info", None)
        except Exception:
            continue
        if info is None:
            continue
        if "Baking" in str(info):
            baking += 1
        elif info != "Baked":
            invalid += 1
        else:
            ready += 1
    if baking:
        return "自动重烘焙中…（后台进行，勿关闭 Blender）", "TIME"
    if invalid:
        return f"参数已更新：{invalid} 个模拟域缓存失效，约 1 秒后自动重烘焙", "TIME"
    if ready:
        return f"模拟缓存已就绪（{ready} 个域）", "CHECKMARK"
    return "真实模拟：添加烟雾/火焰/液体后在此显示烘焙状态", "PHYSICS"


def _volume_bake_timer():
    """去抖 timer：0.8s 内连续改动只烘焙一次；对全部失效域执行后台重烘焙。"""
    _VOLUME_BAKE_PENDING["timer"] = None
    if bpy.app.background:
        return None
    domains = []
    for scene in bpy.data.scenes:
        for obj in scene.objects:
            for modifier in obj.modifiers:
                if modifier.type == "FLUID" and modifier.fluid_type == "DOMAIN":
                    try:
                        if modifier.domain_settings.cache_info != "Baked":
                            domains.append(obj)
                    except Exception:
                        pass
    if not domains:
        return None
    try:
        view_layer = bpy.context.view_layer
        window = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
        for domain_obj in domains:
            override = {"window": window, "scene": bpy.context.scene, "view_layer": view_layer,
                        "active_object": domain_obj, "object": domain_obj,
                        "selected_objects": [domain_obj], "selected_editable_objects": [domain_obj]}
            bpy.ops.fluid.bake_all(override, 'INVOKE_DEFAULT', use_data=True, use_noise=True, use_mesh=True)
    except Exception:
        pass
    return None


def _volume_schedule_rebake():
    """去抖调度：0.8s 窗口合并连发改动，只烘焙最后一次。"""
    if _VOLUME_BAKE_PENDING["timer"] is not None:
        try:
            bpy.app.timers.unregister(_VOLUME_BAKE_PENDING["timer"])
        except Exception:
            pass
    registered = bpy.app.timers.register(_volume_bake_timer, first_interval=0.8)
    _VOLUME_BAKE_PENDING["timer"] = _volume_bake_timer if registered else None


def update_volume_sim_live(self, context):
    """模拟分辨率/时长实时：改写域参数 → 旧缓存自动失效（引擎行为）→ 去抖自动重烘焙。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer, material, obj in _live_layer_materials(context, {"VOLUME_SMOKE", "VOLUME_FIRE", "VOLUME_LIQUID"}):
            if obj and obj.modifiers:
                settings = None
                try:
                    settings = obj.modifiers[0].domain_settings
                except Exception:
                    settings = None
                if settings is not None:
                    settings.resolution_max = int(p.volume_resolution)
                    try:
                        settings.domain_resolution = (int(p.volume_resolution),) * 3
                    except Exception:
                        pass
                    settings.cache_frame_end = max(p.volume_frames, 2)
                    try:
                        settings.cache_frame_start = 1
                    except Exception:
                        pass
    finally:
        guard["active"] = False
    if not bpy.app.background:
        _volume_schedule_rebake()
    # 分辨率/时长同时影响雾流动终点与粒子发射终点：联动刷新
    update_fog_live(self, context)
    update_rain_snow_live(self, context)


def update_flow_direction_live(self, context):
    """模拟风偏/方向实时：重写全部流动体初速度向量（烟雾/火焰/液体）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    direction = volume_direction_vector(p)
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for obj in bpy.data.objects:
            for modifier in obj.modifiers:
                if modifier.type == "FLUID" and modifier.fluid_type == "FLOW":
                    try:
                        if direction is not None:
                            modifier.flow_settings.use_velocity = True
                            modifier.flow_settings.velocity = direction
                        else:
                            modifier.flow_settings.use_velocity = False
                    except Exception:
                        pass
    finally:
        guard["active"] = False
    update_fog_live(self, context)
    update_rain_snow_live(self, context)


def update_smoke_live(self, context):
    """烟雾实时：颜色/密度即时生效（域材质 + 流动体颜色）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    color4 = (p.smoke_color[0], p.smoke_color[1], p.smoke_color[2], 1.0)
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer, material, obj in _live_layer_materials(context, {"VOLUME_SMOKE"}):
            if material and material.use_nodes:
                vol = next((n for n in material.node_tree.nodes if n.type == "PRINCIPLED_VOLUME"), None)
                if vol:
                    vol.inputs["Color"].default_value = color4
                    vol.inputs["Density"].default_value = p.smoke_density
            if obj:
                flow_obj = _flow_object_of_domain(obj)
                if flow_obj:
                    try:
                        flow_obj.modifiers[0].flow_settings.color = color4
                    except Exception:
                        pass
            if abs(layer.strength - p.smoke_density) > 1e-6:
                layer.strength = p.smoke_density
            layer.strength_base = p.smoke_density
    finally:
        guard["active"] = False


def update_fire_live(self, context):
    """火焰实时：色温/强度即时生效（流动体燃料 + 材质色温坡道与自发光）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    flame_colors = {"ORANGE": (1.0, 0.28, 0.02, 1.0), "BLUE": (0.12, 0.45, 1.0, 1.0)}
    color4 = flame_colors.get(p.fire_preset, flame_colors["ORANGE"])
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer, material, obj in _live_layer_materials(context, {"VOLUME_FIRE"}):
            if material and material.use_nodes:
                for node in material.node_tree.nodes:
                    if node.type == "VALTORGB" and "Fire" in (node.label or ""):
                        node.color_ramp.elements[-1].color = color4
                    elif node.type == "PRINCIPLED_VOLUME":
                        try:
                            node.inputs["Emission Strength"].default_value = p.fire_intensity
                        except Exception:
                            pass
            if obj:
                flow_obj = _flow_object_of_domain(obj)
                if flow_obj:
                    try:
                        flow_obj.modifiers[0].flow_settings.fuel_amount = p.fire_intensity
                    except Exception:
                        pass
            if abs(layer.strength - p.fire_intensity) > 1e-6:
                layer.strength = p.fire_intensity
            layer.strength_base = p.fire_intensity
    finally:
        guard["active"] = False


def update_liquid_live(self, context):
    """液体实时：颜色即时生效（流动体材质 Principled 底色；初始状态为结构类，重新添加生效）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    p = context.scene.mfx_props
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer, material, obj in _live_layer_materials(context, {"VOLUME_LIQUID"}):
            flow_obj = _flow_object_of_domain(obj)
            if flow_obj and flow_obj.material_slots:
                flow_mat = flow_obj.material_slots[0].material
                if flow_mat and flow_mat.use_nodes:
                    bsdf = next((n for n in flow_mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
                    if bsdf:
                        set_input(bsdf, "Base Color", (p.liquid_color[0], p.liquid_color[1], p.liquid_color[2], 1.0))
    finally:
        guard["active"] = False


def _flow_object_of_domain(domain_obj):
    """定位模拟域对应的流动体对象（域名与流名共享前缀，或按场景 FluidFlow 扫描）。"""
    if not domain_obj:
        return None
    for candidate in bpy.data.objects:
        if candidate is domain_obj or not candidate.modifiers:
            continue
        for modifier in candidate.modifiers:
            if modifier.type == "FLUID" and modifier.fluid_type == "FLOW":
                if candidate.name.endswith(domain_obj.name.split(" · ")[-1]) or candidate.parent is domain_obj:
                    return candidate
    return None


def _mirror_panel_to_layers(context, effect_types, value):
    """联动·特效页正向（强度/密度类）：面板值写入对应层 strength（层 update 完成节点落点）。"""
    if _LIVE_SYNC_GUARD["active"]:
        return
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        for layer, material, obj in _live_layer_materials(context, effect_types):
            if abs(layer.strength - value) > 1e-6:
                layer.strength = value
            layer.strength_base = value
    finally:
        guard["active"] = False


def update_geometry_strength_live(self, context):
    """几何强度实时：面板 → 已建几何层镜像（socket/关键帧落点由层回调完成）。"""
    _mirror_panel_to_layers(context, {"GEOMETRY"}, context.scene.mfx_props.geometry_effect_strength)


def update_geometry_density_live(self, context):
    """几何粒子密度实时：面板 → 已建粒子层镜像。"""
    _mirror_panel_to_layers(context, {"PARTICLES"}, context.scene.mfx_props.geometry_particle_density)


def _layer_panel_mirror(context, layer):
    """联动·特效页反向：层 strength/循环/缓动变化 → 面板对应参数跟随（guard 防回环）。"""
    mapping = {
        "LIGHTNING": "lightning_strength",
        "HOLOGRAM": "surface_effect_strength", "GLITCH": "surface_effect_strength",
        "FIRE": "surface_effect_strength", "FROST": "surface_effect_strength",
        "CORROSION": "surface_effect_strength", "PULSE": "surface_effect_strength",
        "OUTLINE": "surface_effect_strength", "TOON": "surface_effect_strength",
        "GEOMETRY": "geometry_effect_strength", "PARTICLES": "geometry_particle_density",
        "VOLUME_FOG": "fog_density", "VOLUME_SMOKE": "smoke_density", "VOLUME_FIRE": "fire_intensity",
    }
    prop_name = mapping.get(layer.effect_type)
    if prop_name:
        _sync_layer_panel_value(context, layer.effect_type, prop_name, layer.strength)


def update_layer_row_value(layer, context):
    """v1.0.5 联动·材质页反向：图层粗糙度/遮罩强度/花纹密度变化 → 面板读数跟随。"""
    if _MFX_REPLAY_GUARD["active"] or _LIVE_SYNC_GUARD["active"]:
        return
    panel = context.scene.mfx_props
    guard = _LIVE_SYNC_GUARD
    guard["active"] = True
    try:
        panel.layer_roughness = layer.roughness
        panel.layer_strength = layer.strength
        panel.layer_pattern_scale = layer.pattern_scale
    except Exception:
        pass
    finally:
        guard["active"] = False
    if getattr(context, "area", None) is not None:
        context.area.tag_redraw()


# ─────────────────────────────────────────────────────────────────────────────
# [行条目回写链] 图层堆栈 UI 行上的控件改层值后的「先改层、再回填面板」三兄弟
# ——回填前必举哨兵，否则面板 update 回调会把层打回：
#   update_layer_row_value —— 行强度 → 层，回填面板 layer_strength；
#   update_layer_row_color —— 行颜色 → 层色节点，回填面板 layer_color；
#       （v1.0.5 归因实证：面板 layer_color 的 RNA update 正是
#       update_layer_values，行回写会触发它——「回写路径存在」由此坐实）
#   update_layer_opacity  —— 行不透明度 → 层；同族先例：除 _MFX_REPLAY_GUARD
#       外还查 _LIVE_SYNC_GUARD，v1.0.6 修复即向它对齐。

def update_layer_row_color(layer, context):
    """图层行颜色块变更：直接刷新该层颜色节点。"""
    if _MFX_REPLAY_GUARD["active"]:
        return
    obj = context.object
    if not obj or not obj.active_material or not obj.active_material.use_nodes:
        return
    if not layer_belongs_to_material(layer, obj.active_material, obj):
        return
    sync_layer_nodes(obj.active_material, layer)
    if not _LIVE_SYNC_GUARD["active"]:  # v1.0.5 联动·材质页反向：层颜色 → 面板跟随
        panel = context.scene.mfx_props
        guard = _LIVE_SYNC_GUARD
        guard["active"] = True
        try:
            panel.layer_color = tuple(layer.color)
        except Exception:
            pass
        finally:
            guard["active"] = False
        if getattr(context, "area", None) is not None:
            context.area.tag_redraw()


def update_layer_opacity(layer, context):
    if _MFX_REPLAY_GUARD["active"]:
        return
    material = resolve_layer_material(layer)
    if not material:
        return
    nt = material.node_tree
    blend = nt.nodes.get(layer.blend_node)
    if not blend:
        return
    if blend.type == "ADD_SHADER":
        index = next((i for i, item in enumerate(context.scene.mfx_layers) if item.blend_node == layer.blend_node), None)
        if index is not None:
            replay_layer_chain(context, index, {"opacity": layer.opacity})
        return
    if blend.type == "MIX_SHADER":
        opacity_node = nt.nodes.get(layer.opacity_node) if layer.opacity_node else None
        if opacity_node and len(opacity_node.inputs) > 1:
            opacity_node.inputs[1].default_value = layer.opacity if layer.enabled else 0.0
        elif blend.inputs[0].is_linked:
            index = next((i for i, item in enumerate(context.scene.mfx_layers) if item.blend_node == layer.blend_node), None)
            if index is not None:
                replay_layer_chain(context, index, {"opacity": layer.opacity})
        else:
            blend.inputs[0].default_value = layer.opacity if layer.enabled else 0.0
    if not _LIVE_SYNC_GUARD["active"]:  # v1.0.5 联动·材质页反向：层不透明度 → 面板跟随
        panel = context.scene.mfx_props
        guard = _LIVE_SYNC_GUARD
        guard["active"] = True
        try:
            panel.layer_opacity = layer.opacity
        except Exception:
            pass
        finally:
            guard["active"] = False
        if getattr(context, "area", None) is not None:
            context.area.tag_redraw()


def update_layer_visibility(layer, context):
    if _MFX_REPLAY_GUARD["active"]:
        return
    material = resolve_layer_material(layer)
    if not material:
        return
    nt = material.node_tree
    blend = nt.nodes.get(layer.blend_node)
    if not blend:
        return
    if blend.type == "ADD_SHADER":
        index = next((i for i, item in enumerate(context.scene.mfx_layers) if item.blend_node == layer.blend_node), None)
        if index is not None:
            replay_layer_chain(context, index, {"enabled": layer.enabled})
        return
    if blend.type != "MIX_SHADER":
        return
    opacity_node = nt.nodes.get(layer.opacity_node) if layer.opacity_node else None
    if opacity_node:
        opacity_node.inputs[1].default_value = layer.opacity if layer.enabled else 0.0
        return
    factor = blend.inputs[0]
    if layer.blend_mode == "ADD":
        factor.default_value = layer.opacity if layer.enabled else 0.0
        return
    if layer.enabled:
        strength_node = nt.nodes.get(layer.strength_node) if layer.strength_node else None
        if strength_node and not factor.is_linked:
            nt.links.new(strength_node.outputs["Color"], factor)
    else:
        for link in list(factor.links):
            nt.links.remove(link)
        factor.default_value = 0.0


def resolve_texture_preset(identifier):
    """按 slug 查找贴图预设定义，未命中返回 None。"""
    return next((t for t in TEXTURE_PRESETS if t[1] == identifier), None)


def make_texture_material(name, slug):
    """按贴图预设规格加载三通道 JPG 并接线（v0.9.3 §2 契约）：
    Diffuse→Base Color(sRGB) / nor_gl→NormalMap→Normal(Non-Color) / Rough→Roughness(Non-Color)。
    单通道缺失跳过不阻塞；全部缺失返回 None。路径基于插件目录相对定位，安装态可用。"""
    base_dir = os.path.join(os.path.dirname(__file__), "textures", slug)
    channels = [("Diffuse", "sRGB"), ("nor_gl", "Non-Color"), ("Rough", "Non-Color")]
    found = [suffix for suffix, _space in channels if os.path.isfile(os.path.join(base_dir, f"{slug}_{suffix}.jpg"))]
    if not found:
        return None
    mat = bpy.data.materials.new(name=f"MFX · {name}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(node for node in nt.nodes if node.type == "BSDF_PRINCIPLED")
    y = 300
    for suffix, color_space in channels:
        path = os.path.join(base_dir, f"{slug}_{suffix}.jpg")
        if not os.path.isfile(path):
            continue
        image = bpy.data.images.load(path, check_existing=True)
        image.colorspace_settings.name = color_space
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.location = (-600, y)
        if suffix == "Diffuse":
            tex.label = "基础色（sRGB）"
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            y -= 300
        elif suffix == "nor_gl":
            tex.label = "法线（OpenGL Y+）"
            nmap = nt.nodes.new("ShaderNodeNormalMap")
            nmap.label = "法线贴图"
            nmap.location = (-350, y)
            nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
            nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
            y -= 300
        else:
            tex.label = "粗糙度"
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Roughness"])
            y -= 300
    return mat


def apply_texture_preset(operator, context, targets, tex):
    """贴图预设统一应用入口：生成材质并挂到目标物体；返回是否成功。"""
    name, slug, _tip = tex
    material = make_texture_material(name, slug)
    if material is None:
        operator.report({'ERROR'}, f"贴图文件缺失：textures/{slug}/，请检查插件安装目录")
        return False
    for obj in targets:
        if obj.data and hasattr(obj.data, "materials"):
            obj.data.materials.append(material)
            obj.active_material_index = len(obj.data.materials) - 1
    operator.report({'INFO'}, f"已应用贴图材质：{name}")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# [材质工厂] make_material：程序化材质「装配线」教学样本。
#   固定骨架：输出 ← Principled BSDF，Base Color/Roughness/Metallic 参数直填；
#   质感层：噪声 Fac 经 MapRange 收敛到「目标粗糙度 ±0.12」窄带再进 Roughness
#   ——「参数定中心、噪声做扰动」是程序化材质不脏面的关键手法；
#   风格层：style 切换图案源（brushed=定向 Wave 拉丝 / wood=年轮…），只替换
#   pattern_height 一根线、骨架不动——「换图案源不换骨架」的可扩展设计；
#   投影层：texcoord["mfx_projection"] 把投影模式持久化为节点自定义属性，
#   自定义属性随 .blend 落盘，开旧文件零重放也能保持观感一致。

def make_material(name, color, roughness, metallic, bump_strength=0.12, noise_scale=12.0, style="noise", projection_mode=None):
    """程序化纹理投影形式（方案 §2.1/§3）：程序化纹理链的投影坐标全局枚举
    （GENERATED=生成坐标·默认 / OBJECT=物体坐标 / WORLD=世界坐标）。
    projection_mode 为 None 时取面板当前枚举（解析失败安全回落 GENERATED=旧行为）。
    红线：默认 GENERATED 与旧版逐链接一致（老场景零漂移，DX-4.1 同源）。"""
    mode = projection_mode if projection_mode in MFX_PROJECTION_SOCKETS else _current_projection_mode()
    mat = bpy.data.materials.new(name=name)
    mat.diffuse_color = color
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (620, 80)
    principled = tree.nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (350, 80)
    set_input(principled, "Base Color", color)
    set_input(principled, "Roughness", roughness)
    set_input(principled, "Metallic", metallic)
    texcoord = tree.nodes.new("ShaderNodeTexCoord")
    texcoord.name = "MFX 纹理坐标"
    texcoord.location = (-700, 0)
    texcoord["mfx_projection"] = mode  # 投影标记持久化在材质节点：开文件零重放的观感一致性依据（方案 §3）
    world_geo = None
    if mode == "WORLD":  # 世界坐标 = Geometry.Position（世界空间位置）：TexCoord 无 World 输出，语义=纹理锚定场景
        world_geo = tree.nodes.new("ShaderNodeNewGeometry")
        world_geo.name = "MFX 世界坐标纹理"
        world_geo.location = (-700, -220)
    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.label = "表面粗糙度变化"
    noise.location = (-470, 200)
    noise.inputs["Scale"].default_value = max(noise_scale, 3.0)
    noise.inputs["Detail"].default_value = 3.0
    ramp = tree.nodes.new("ShaderNodeMapRange")
    ramp.label = "粗糙度自然变化"
    ramp.location = (-40, 180)
    ramp.inputs["From Min"].default_value = 0.0
    ramp.inputs["From Max"].default_value = 1.0
    ramp.inputs["To Min"].default_value = max(0.0, roughness - 0.12)
    ramp.inputs["To Max"].default_value = min(1.0, roughness + 0.12)
    pattern_node = noise
    pattern_height = noise.outputs["Fac"]
    if style == "brushed":
        wave = tree.nodes.new("ShaderNodeTexWave")
        wave.label = "定向拉丝纹"
        wave.location = (-450, -100)
        wave.wave_type = "BANDS"
        wave.bands_direction = "X"
        wave.inputs["Scale"].default_value = 180.0
        wave.inputs["Distortion"].default_value = 1.5
        tree.links.new(_projection_source_socket(tree, texcoord, mode), wave.inputs["Vector"])
        pattern_node, pattern_height = wave, wave.outputs["Fac"]
        bump_strength *= 0.18
    elif style == "wood":
        wave = tree.nodes.new("ShaderNodeTexWave")
        wave.label = "木材年轮与木纹"
        wave.location = (-450, -100)
        wave.wave_type = "BANDS"
        wave.bands_direction = "X"
        wave.inputs["Scale"].default_value = max(8.0, noise_scale * 1.7)
        wave.inputs["Distortion"].default_value = 9.0
        wave.inputs["Detail"].default_value = 4.0
        wave.inputs["Detail Scale"].default_value = 2.0
        tree.links.new(_projection_source_socket(tree, texcoord, mode), wave.inputs["Vector"])
        ramp_color = tree.nodes.new("ShaderNodeValToRGB")
        ramp_color.label = "木纹深浅"
        ramp_color.location = (-100, -60)
        ramp_color.color_ramp.elements[0].color = tuple(c * 0.38 for c in color[:3]) + (1,)
        ramp_color.color_ramp.elements[1].color = tuple(min(1, c * 1.5) for c in color[:3]) + (1,)
        tree.links.new(wave.outputs["Fac"], ramp_color.inputs["Fac"])
        tree.links.new(ramp_color.outputs["Color"], principled.inputs["Base Color"])
        pattern_node, pattern_height = wave, wave.outputs["Fac"]
        bump_strength = max(bump_strength, 0.22)
    elif style == "brick":
        brick = tree.nodes.new("ShaderNodeTexBrick")
        brick.label = "砖块与砂浆缝"
        brick.location = (-450, -100)
        brick.inputs["Color1"].default_value = color
        brick.inputs["Color2"].default_value = tuple(c * 0.72 for c in color[:3]) + (1,)
        brick.inputs["Mortar"].default_value = (0.12, 0.105, 0.09, 1)
        brick.inputs["Scale"].default_value = 7.0
        brick.inputs["Mortar Size"].default_value = 0.035
        tree.links.new(_projection_source_socket(tree, texcoord, mode), brick.inputs["Vector"])
        tree.links.new(brick.outputs["Color"], principled.inputs["Base Color"])
        pattern_node, pattern_height = brick, brick.outputs["Fac"]
        bump_strength = max(bump_strength, 0.38)
    elif style in {"concrete", "granite", "asphalt", "rust", "cast_iron", "marble"}:
        color_ramp = tree.nodes.new("ShaderNodeValToRGB")
        color_ramp.label = {
            "concrete": "混凝土斑驳",
            "granite": "花岗岩矿物颗粒",
            "asphalt": "沥青骨料",
            "rust": "锈蚀色层",
            "cast_iron": "铸铁铸造肌理",
            "marble": "大理石纹理",
        }[style]
        color_ramp.location = (-90, -70)
        dark_factor = 0.35 if style in {"rust", "granite", "marble"} else 0.48
        color_ramp.color_ramp.elements[0].color = tuple(c * dark_factor for c in color[:3]) + (1,)
        color_ramp.color_ramp.elements[1].color = tuple(min(1, c * (1.5 if style == "rust" else 1.28)) for c in color[:3]) + (1,)
        tree.links.new(noise.outputs["Fac"], color_ramp.inputs["Fac"])
        tree.links.new(color_ramp.outputs["Color"], principled.inputs["Base Color"])
        if style == "granite":
            voronoi = tree.nodes.new("ShaderNodeTexVoronoi")
            voronoi.label = "矿物颗粒"
            voronoi.location = (-450, -400)
            voronoi.inputs["Scale"].default_value = 42.0
            tree.links.new(_projection_source_socket(tree, texcoord, mode), voronoi.inputs["Vector"])
            pattern_node, pattern_height = voronoi, voronoi.outputs["Distance"]
        elif style == "marble":
            noise.inputs["Scale"].default_value = 5.0
            noise.inputs["Distortion"].default_value = 6.0
            pattern_node, pattern_height = noise, noise.outputs["Fac"]
        else:
            pattern_node, pattern_height = noise, noise.outputs["Fac"]
    elif style == "leather":
        voronoi = tree.nodes.new("ShaderNodeTexVoronoi")
        voronoi.label = "皮革毛孔"
        voronoi.location = (-450, -100)
        voronoi.inputs["Scale"].default_value = 95.0
        voronoi.distance = "EUCLIDEAN"
        tree.links.new(_projection_source_socket(tree, texcoord, mode), voronoi.inputs["Vector"])
        pattern_node, pattern_height = voronoi, voronoi.outputs["Distance"]
        bump_strength = max(bump_strength, 0.28)
    elif style == "fabric":
        wave = tree.nodes.new("ShaderNodeTexWave")
        wave.label = "织物纤维"
        wave.location = (-450, -100)
        wave.wave_type = "BANDS"
        wave.bands_direction = "X"
        wave.inputs["Scale"].default_value = 180.0
        tree.links.new(_projection_source_socket(tree, texcoord, mode), wave.inputs["Vector"])
        pattern_node, pattern_height = wave, wave.outputs["Fac"]
        bump_strength = max(bump_strength, 0.2)
    elif style in {"moss", "soil", "sand", "snow", "ice", "water", "foliage"}:
        color_ramp = tree.nodes.new("ShaderNodeValToRGB")
        color_ramp.location = (-90, -70)
        noise.inputs["Scale"].default_value = noise_scale
        if style == "moss":
            color_ramp.label = "苔藓深浅与斑块"
            color_ramp.color_ramp.elements[0].color = (0.018, 0.055, 0.012, 1)
            color_ramp.color_ramp.elements[1].color = (0.19, 0.34, 0.055, 1)
            voronoi = tree.nodes.new("ShaderNodeTexVoronoi")
            voronoi.label = "苔藓团簇"
            voronoi.location = (-450, -400)
            voronoi.inputs["Scale"].default_value = 24.0
            tree.links.new(_projection_source_socket(tree, texcoord, mode), voronoi.inputs["Vector"])
            pattern_node, pattern_height = voronoi, voronoi.outputs["Distance"]
            bump_strength = max(bump_strength, 0.55)
        elif style == "soil":
            color_ramp.label = "土壤湿润色层"
            color_ramp.color_ramp.elements[0].color = (0.065, 0.027, 0.009, 1)
            color_ramp.color_ramp.elements[1].color = (0.34, 0.19, 0.075, 1)
            voronoi = tree.nodes.new("ShaderNodeTexVoronoi")
            voronoi.label = "土壤颗粒"
            voronoi.location = (-450, -400)
            voronoi.inputs["Scale"].default_value = 68.0
            tree.links.new(_projection_source_socket(tree, texcoord, mode), voronoi.inputs["Vector"])
            pattern_node, pattern_height = voronoi, voronoi.outputs["Distance"]
            bump_strength = max(bump_strength, 0.4)
        elif style == "sand":
            color_ramp.label = "沙粒色差"
            color_ramp.color_ramp.elements[0].color = (0.34, 0.21, 0.085, 1)
            color_ramp.color_ramp.elements[1].color = (0.83, 0.68, 0.40, 1)
            voronoi = tree.nodes.new("ShaderNodeTexVoronoi")
            voronoi.label = "细沙颗粒"
            voronoi.location = (-450, -400)
            voronoi.inputs["Scale"].default_value = 120.0
            tree.links.new(_projection_source_socket(tree, texcoord, mode), voronoi.inputs["Vector"])
            pattern_node, pattern_height = voronoi, voronoi.outputs["Distance"]
            bump_strength = max(bump_strength, 0.22)
        elif style == "snow":
            color_ramp.label = "雪面冷暖起伏"
            color_ramp.color_ramp.elements[0].color = (0.46, 0.62, 0.73, 1)
            color_ramp.color_ramp.elements[1].color = (0.97, 0.99, 1.0, 1)
            bump_strength = min(bump_strength, 0.16)
        elif style == "ice":
            color_ramp.label = "冰体冷色层"
            color_ramp.color_ramp.elements[0].color = (0.055, 0.22, 0.34, 1)
            color_ramp.color_ramp.elements[1].color = (0.55, 0.82, 0.92, 1)
            set_input(principled, "Transmission Weight", 0.42)
            set_input(principled, "IOR", 1.31)
            set_input(principled, "Coat Weight", 0.45)
            set_input(principled, "Coat Roughness", 0.08)
            bump_strength = max(bump_strength, 0.2)
        elif style == "water":
            color_ramp.label = "水体深浅"
            color_ramp.color_ramp.elements[0].color = (0.006, 0.055, 0.10, 1)
            color_ramp.color_ramp.elements[1].color = (0.08, 0.39, 0.50, 1)
            set_input(principled, "Transmission Weight", 0.82)
            set_input(principled, "IOR", 1.333)
            set_input(principled, "Coat Weight", 0.3)
            noise.inputs["Scale"].default_value = 5.0
            noise.inputs["Distortion"].default_value = 2.5
            bump_strength = max(bump_strength, 0.18)
        else:
            color_ramp.label = "叶片绿阶"
            color_ramp.color_ramp.elements[0].color = (0.018, 0.10, 0.012, 1)
            color_ramp.color_ramp.elements[1].color = (0.15, 0.43, 0.035, 1)
            voronoi = tree.nodes.new("ShaderNodeTexVoronoi")
            voronoi.label = "叶面脉络颗粒"
            voronoi.location = (-450, -400)
            voronoi.inputs["Scale"].default_value = 32.0
            tree.links.new(_projection_source_socket(tree, texcoord, mode), voronoi.inputs["Vector"])
            pattern_node, pattern_height = voronoi, voronoi.outputs["Distance"]
            bump_strength = max(bump_strength, 0.24)
        tree.links.new(noise.outputs["Fac"], color_ramp.inputs["Fac"])
        tree.links.new(color_ramp.outputs["Color"], principled.inputs["Base Color"])
    elif style == "bark":
        wave = tree.nodes.new("ShaderNodeTexWave")
        wave.label = "树皮纵向裂纹"
        wave.location = (-450, -100)
        wave.wave_type = "BANDS"
        wave.bands_direction = "X"
        wave.inputs["Scale"].default_value = max(12.0, noise_scale * 2.0)
        wave.inputs["Distortion"].default_value = 8.0
        wave.inputs["Detail"].default_value = 4.0
        tree.links.new(_projection_source_socket(tree, texcoord, mode), wave.inputs["Vector"])
        color_ramp = tree.nodes.new("ShaderNodeValToRGB")
        color_ramp.label = "树皮深色裂隙"
        color_ramp.location = (-90, -70)
        color_ramp.color_ramp.elements[0].color = (0.055, 0.021, 0.008, 1)
        color_ramp.color_ramp.elements[1].color = (0.34, 0.16, 0.055, 1)
        tree.links.new(wave.outputs["Fac"], color_ramp.inputs["Fac"])
        tree.links.new(color_ramp.outputs["Color"], principled.inputs["Base Color"])
        pattern_node, pattern_height = wave, wave.outputs["Fac"]
        bump_strength = max(bump_strength, 0.48)
    elif style == "glass":
        set_input(principled, "Transmission Weight", 0.96)
        set_input(principled, "IOR", 1.45)
        set_input(principled, "Coat Weight", 0.2)
        bump_strength = 0.0
    elif style == "ceramic":
        set_input(principled, "Coat Weight", 0.35)
        set_input(principled, "Coat Roughness", 0.12)
        bump_strength *= 0.25
    elif style in {"plastic", "rubber"}:
        bump_strength = min(bump_strength, 0.025 if style == "plastic" else 0.12)

    bump = tree.nodes.new("ShaderNodeBump")
    bump.location = (100, -120)
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.08
    tree.links.new(_projection_source_socket(tree, texcoord, mode), noise.inputs["Vector"])
    tree.links.new(pattern_height, bump.inputs["Height"])
    tree.links.new(noise.outputs["Fac"], ramp.inputs["Value"])
    tree.links.new(ramp.outputs["Result"], principled.inputs["Roughness"])
    tree.links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    tree.links.new(principled.outputs["BSDF"], out.inputs["Surface"])
    for node in tree.nodes:
        node.select = False
    return mat


# ── 程序化纹理投影形式（交互方案定稿 §2/§3，全栈实现）─────────────────────────────
# 全局枚举三选项 → 程序化纹理链 Texture Coordinate 输出。作用范围仅 make_material
# 托管程序化材质：PBR 图片链、遮罩链（"图层遮罩坐标"）、m6 三向投影文案不动（§4）。
MFX_PROJECTION_SOCKETS = {"GENERATED": "Generated", "OBJECT": "Object", "WORLD": None}


def mfx_projection_socket(texcoord, mode):
    """按投影枚举返回纹理坐标节点输出；WORLD 走 Geometry.Position（见
    _projection_source_socket），未知值安全回落 Generated（=旧行为红线）。"""
    socket_name = MFX_PROJECTION_SOCKETS.get(mode)
    if socket_name is None:
        socket_name = "Generated"
    return texcoord.outputs[socket_name]


def _projection_source_socket(tree, texcoord, mode):
    """make_material 的统一源解析：WORLD → 专用 Geometry.Position（世界空间，
    纹理锚定场景）；其余 → Texture Coordinate 对应输出。未知值回落 Generated。"""
    if mode == "WORLD":
        geo = tree.nodes.get("MFX 世界坐标纹理")
        if geo is not None:
            return geo.outputs["Position"]
        return texcoord.outputs["Generated"]
    return texcoord.outputs[MFX_PROJECTION_SOCKETS.get(mode, "Generated")]


def _ensure_world_source(tree):
    """确保材质内有世界坐标源节点（重连到 WORLD 时按需创建）。"""
    geo = tree.nodes.get("MFX 世界坐标纹理")
    if geo is None:
        geo = tree.nodes.new("ShaderNodeNewGeometry")
        geo.name = "MFX 世界坐标纹理"
        geo.location = (-700, -220)
    return geo


def _remove_world_source(tree):
    """切离 WORLD 后移除专用 Geometry 节点，保持节点树与旧版结构一致（无残留）。"""
    geo = tree.nodes.get("MFX 世界坐标纹理")
    if geo is not None and not geo.outputs["Position"].links:
        tree.nodes.remove(geo)


def _relink_sources(tree, old_socket, new_socket):
    """把 old_socket 出发的全部链接改接 new_socket（保留目标，只换源，§3 重放最小化）。
    注意：纹理 Vector 均为单输入 socket，links.new 会自动替换旧链接——因此先对
    old_socket.links 做快照、只 new 不手动 remove（旧链接已被 Blender 移除）；
    同源重连（old==new）直接跳过。"""
    if old_socket == new_socket:
        return
    for link in list(old_socket.links):
        tree.links.new(new_socket, link.to_socket)


def _current_projection_mode():
    """读取面板当前投影枚举；后台/受限上下文安全回落 GENERATED（默认=旧行为）。"""
    try:
        mode = bpy.context.scene.mfx_props.texture_projection
    except Exception:
        return "GENERATED"
    return mode if mode in MFX_PROJECTION_SOCKETS else "GENERATED"


def _collect_projection_texcoords():
    """收集全部托管程序化材质：[(material, texcoord_node, stored_mode)]。
    识别依据（§3「全部托管 MFX 材质」的实现口径）：
    1) 新版：make_material 写入的 node["mfx_projection"] 标记（持久化在 .blend），
       材质名 "MFX · " 前缀 + 存在 make_material 强特征节点（label="表面粗糙度变化"）；
    2) 旧版回填：同上特征但无标记的 TEX_COORD（位置 x≤-600 且非"图层遮罩坐标"）
       ——回填 GENERATED（旧版固定 Generated）并命名统一，使老场景切换同样生效；
    3) 贴图链 / 团队预设自定义结构：无强特征，不误伤（§4）。判定失败安全跳过。"""
    found = []
    for mat in bpy.data.materials:
        nt = getattr(mat, "node_tree", None)
        if nt is None or not mat.name.startswith("MFX · "):
            continue
        has_procedural_noise = any(node.type == "TEX_NOISE" and node.label == "表面粗糙度变化"
                                   for node in nt.nodes)
        if not has_procedural_noise:
            continue  # 贴图链 / 团队预设自定义结构 / 无程序化纹理链：不在本方案范围（§4）
        texcoord = next((node for node in nt.nodes
                         if node.type == "TEX_COORD" and node.get("mfx_projection", None) is not None), None)
        if texcoord is None:
            candidates = [node for node in nt.nodes
                          if node.type == "TEX_COORD" and node.get("mfx_projection", None) is None
                          and node.label != "图层遮罩坐标" and node.location.x <= -600]
            if len(candidates) == 1:
                texcoord = candidates[0]
                texcoord.name = "MFX 纹理坐标"
                texcoord["mfx_projection"] = "GENERATED"  # 旧版行为回填
        if texcoord is not None:
            found.append((mat, texcoord, texcoord.get("mfx_projection", "GENERATED")))
    return found


def retarget_mfx_projections(context, mode):
    """§3 四行触发表·主动切换路径：把全部托管程序化材质的纹理投影切换到 mode。
    仅重连纹理源（不重建链路，图层链/遮罩链/PBR 链零接触）；WORLD 模式用专用
    Geometry.Position（世界空间，纹理锚定场景），切离时移除该节点保持树结构干净。
    重连期间窗口底栏进度指示（轻量忙碌态），结束即隐、无弹窗无 toast（§3 表行 2）。
    old == mode 的材质跳过（幂等二重保险，§3 表行 4）。返回实际切换的材质数。"""
    if mode not in MFX_PROJECTION_SOCKETS:
        return 0
    pending = [(mat, node, old) for mat, node, old in _collect_projection_texcoords() if old != mode]
    if not pending:
        return 0
    wm = context.window_manager
    wm.progress_begin(0, len(pending))
    try:
        for step, (mat, node, old) in enumerate(pending, start=1):
            tree = mat.node_tree
            old_socket = _projection_source_socket(tree, node, old)
            if mode == "WORLD":
                new_socket = _ensure_world_source(tree).outputs["Position"]
            else:
                new_socket = mfx_projection_socket(node, mode)
            _relink_sources(tree, old_socket, new_socket)
            if mode != "WORLD":
                _remove_world_source(tree)
            node["mfx_projection"] = mode
            wm.progress_update(step)
    finally:
        wm.progress_end()
    return len(pending)


def update_texture_projection(props, context):
    """§3 四行触发表的枚举 update 回调——只在值真正变化时被 Blender 调用：
    · 会话内主动切换（含切回默认）→ 进入本回调 → 全部托管材质重放生效；
    · 开文件 / 加载场景恢复存储值、点击当前已选项 → 不触发 update（零重放 / 幂等）。
    旧 .blend 中节点标记与实际连线一致，观感不依赖回调，零漂移（DX-4.1 交互侧保障）。"""
    retarget_mfx_projections(context, props.texture_projection)


class MFX_Preferences(PropertyGroup):
    category: EnumProperty(name="分类", items=[(c, c, c) for c in CATEGORIES])
    preset: EnumProperty(name="材质预设", items=preset_items)
    search: StringProperty(name="搜索", description="按名称筛选预设")
    favorite_only: BoolProperty(name="只显示收藏", default=False)
    color: FloatVectorProperty(name="颜色", subtype="COLOR", size=4, min=0, max=1, default=(0.3, 0.35, 0.4, 1))
    roughness: FloatProperty(name="粗糙度", min=0, max=1, default=0.35)
    metallic: FloatProperty(name="金属度", min=0, max=1, default=0.5)
    bump_strength: FloatProperty(name="凹凸强度", min=0, max=1, default=0.15)
    texture_projection: EnumProperty(
        name="纹理投影",
        description="程序化纹理的投影坐标（全局生效：切换后全部托管材质立即重连，重放期间底栏进度指示）",
        items=[
            ("GENERATED", "生成坐标",
             "默认 · 与旧版一致\n纹理贴合物体表面，随物体变换；非立方体物件侧面密度可能不均（旧版效果）"),
            ("OBJECT", "物体坐标",
             "按物体尺寸适配\n纹理跟随物体移动 / 旋转"),
            ("WORLD", "世界坐标 · 推荐",
             "按场景实际尺寸 · 侧面不挤压\n纹理锚定场景，物体移动 / 旋转不跟随（物体坐标则跟随）"),
        ],
        default="GENERATED",
        update=update_texture_projection,
    )
    lightning_color: FloatVectorProperty(name="闪电颜色", subtype="COLOR", size=4, min=0, max=1, default=(0.03, 0.45, 1.0, 1), update=update_lightning_live)
    lightning_strength: FloatProperty(name="发光强度", min=0, max=100, default=12, update=update_lightning_live)
    lightning_arc_count: IntProperty(name="电弧数量（特斯拉）", min=1, max=16, default=8,
                                     description="特斯拉电弧模式下从物体顶点发射的短电弧条数（重新添加特效后生效）")
    lightning_branches: IntProperty(name="分支数量", min=0, max=32, default=8, description="改后需重新添加特效生效")
    lightning_branch_depth: IntProperty(name="分支层级", min=1, max=5, default=2, description="改后需重新添加特效生效")
    lightning_jitter: FloatProperty(name="抖动幅度", min=0, max=1, default=0.35, description="改后需重新添加特效生效")
    lightning_seed: IntProperty(name="随机种子（0为随机）", min=0, max=1000000, default=0, description="改后需重新添加特效生效")
    lightning_duration: IntProperty(name="持续帧数", min=4, max=240, default=48, update=update_frames_live)
    lightning_width: FloatProperty(name="线宽", min=0.001, max=0.15, default=0.018, update=update_lightning_live)
    lightning_mode: EnumProperty(name="闪电模式", items=[
        ("TESLA", "特斯拉电弧", "从物体表面顶点发射多条短电弧，每 2 帧跳变落点，模拟特斯拉线圈电弧"),
        ("DIRECTED", "定向闪电", "一条主干从目标一侧贯穿到另一侧并甩出分支"),
    ], description="改后需重新添加特效生效")
    lightning_animate: BoolProperty(name="添加闪烁关键帧", default=True, description="改后需重新添加特效生效")
    texture_dir: StringProperty(name="贴图目录", subtype="DIR_PATH")
    include_subdirs: BoolProperty(name="扫描子文件夹", default=False)
    bake_resolution: EnumProperty(name="烘焙分辨率", items=[(str(n), f"{n} × {n}", "") for n in (512, 1024, 2048, 4096)], default="1024")
    bake_path: StringProperty(name="烘焙输出", subtype="DIR_PATH")
    bake_device: EnumProperty(name="烘焙设备", items=[
        ("CPU", "CPU", "使用 CPU 执行 Cycles 烘焙"),
        ("GPU", "GPU", "使用 Blender Cycles 偏好设置中启用的 GPU 设备"),
    ], default="CPU")
    export_path: StringProperty(name="导出路径", subtype="DIR_PATH")
    fragment_count: IntProperty(name="碎片数量", min=8, max=200, default=48, description="改后需重新添加特效生效")
    fragment_seed: IntProperty(name="碎片随机种子（0为自动）", min=0, max=1000000, default=0, description="改后需重新添加特效生效")
    fragment_distance: FloatProperty(name="飞散距离", min=0.1, max=20, default=2.0, update=update_fragment_live)
    fragment_frames: IntProperty(name="飞散帧数", min=4, max=120, default=20, update=update_frames_live)
    effect_start_frame: IntProperty(name="特效起始帧（-1为当前帧）", min=-1, default=-1, update=update_start_frame_live)
    effect_loop_mode: EnumProperty(name="动画循环", items=[
        ("NONE", "不循环", "动画只播放一次"),
        ("REPEAT", "重复", "重复播放动画"),
        ("MIRROR", "往返", "交替正向与反向播放"),
        ("REPEAT_OFFSET", "累积重复", "重复时沿曲线数值继续偏移"),
    ], default="NONE", update=update_loop_mode_live)
    effect_easing: EnumProperty(name="动画缓动", items=[
        ("KEEP", "保持原样", "保留特效原有插值"),
        ("BEZIER", "柔和", "使用自动缓动贝塞尔曲线"),
        ("LINEAR", "线性", "匀速变化"),
        ("CONSTANT", "跳变", "在关键帧之间保持数值"),
        ("SINE", "正弦", "平滑正弦插值"),
        ("QUAD", "二次", "二次缓动插值"),
    ], default="KEEP", update=update_loop_mode_live)
    audio_path: StringProperty(name="音频文件", subtype="FILE_PATH", description="用于驱动当前特效发光强度的 PCM WAV 文件")
    audio_gain: FloatProperty(name="音频增益", min=0.01, max=100.0, default=12.0, update=update_audio_gain_live)
    audio_key_step: IntProperty(name="采样帧间隔", min=1, max=12, default=2,
                                description="每隔多少帧建立一个音频强度关键帧；数值越小曲线越细，关键帧越多（重新添加特效后生效）")
    model_target_faces: IntProperty(name="重构目标面数", description="Quadriflow 尝试接近该四边面数；实际输出会因模型形状略有偏差", min=4, max=500000, default=4000)
    model_preserve_sharp: BoolProperty(name="保留锐边", default=True)
    model_preserve_boundary: BoolProperty(name="保留开放边界", default=True)
    model_preserve_attributes: BoolProperty(name="重投影 UV / 属性", default=True)
    model_smooth_normals: BoolProperty(name="平滑法线", default=True)
    model_export_path: StringProperty(name="模型输出目录", subtype="DIR_PATH")
    model_step_merge_coplanar: BoolProperty(
        name="导出 STEP 时共面融合",
        description="把同一平面上的相邻三角面融合为整面再写出，Fusion 360 中不再显示内部切割边；只改导出副本，不影响原模型",
        default=True)
    model_step_merge_angle: FloatProperty(
        name="共面判定角度",
        description="相邻两面法向夹角小于该值且共面时才融合；调小更保守，调大可能吞掉浅折面",
        min=math.radians(0.05), max=math.radians(5.0), default=math.radians(0.5), step=1, precision=2, subtype="ANGLE")
    surface_effect: EnumProperty(name="表面特效", items=[
        ("HOLOGRAM", "全息扫描线", "扫描条纹与发光叠加"),
        ("GLITCH", "故障闪烁", "四维噪声驱动的动态闪烁"),
        ("FIRE", "火焰 / 烟雾扰动", "程序噪声驱动的发光表面纹理"),
        ("FROST", "冰霜结晶", "Voronoi 边缘生成晶体纹理"),
        ("CORROSION", "腐蚀扩散", "噪声锈蚀遮罩与氧化色层"),
        ("PULSE", "自发光脉冲", "发光强度随关键帧脉动"),
        ("OUTLINE", "轮廓光描边", "创建反法线外壳描边对象"),
        ("TOON", "卡通分阶着色", "使用 EEVEE Shader to RGB 分阶着色"),
    ])
    surface_effect_color: FloatVectorProperty(name="特效颜色", subtype="COLOR", size=4, min=0, max=1, default=(0.05, 0.75, 1.0, 1), update=update_surface_live)
    surface_effect_strength: FloatProperty(name="特效强度", min=0.01, max=30, default=4, update=update_surface_live)
    surface_effect_frames: IntProperty(name="特效时长", min=4, max=240, default=48, update=update_frames_live)
    surface_effect_direction: EnumProperty(name="蔓延方向", items=[
        ("Z", "+Z / 向上", "从物体局部 Z 轴负端向正端蔓延"),
        ("-Z", "−Z / 向下", "从物体局部 Z 轴正端向负端蔓延"),
        ("X", "+X", "从物体局部 X 轴负端向正端蔓延"),
        ("-X", "−X", "从物体局部 X 轴正端向负端蔓延"),
        ("Y", "+Y", "从物体局部 Y 轴负端向正端蔓延"),
        ("-Y", "−Y", "从物体局部 Y 轴正端向负端蔓延"),
        ("CUSTOM", "自定义角度", "按下方方位角与俯仰角合成任意方向"),
    ], default="Z", description="改后需重新添加特效生效")
    surface_effect_azimuth: FloatProperty(name="方位角（度）", min=0.0, max=360.0, default=0.0, precision=1,
                                          description="自定义方向的水平方位角：0°=+X，90°=+Y，配合俯仰角合成任意方向（重新添加特效后生效）")
    surface_effect_elevation: FloatProperty(name="俯仰角（度）", min=-90.0, max=90.0, default=0.0, precision=1,
                                            description="自定义方向相对水平面的仰角：0°=水平，90°=正上，-90°=正下（重新添加特效后生效）")
    geometry_effect: EnumProperty(name="几何特效", items=[
        ("WAVE", "波浪 / 旗帜飘动", "添加非破坏式 Geometry Nodes 波动修改器"),
        ("GROWTH", "向上生长 / 消散", "使用 Geometry Nodes 按高度逐步显露网格"),
        ("PARTICLES", "粒子散布 / 消散", "沿表面散布实例并随关键帧逐渐消散"),
    ])
    geometry_effect_strength: FloatProperty(name="幅度 / 范围", min=0.01, max=10.0, default=1.0, update=update_geometry_strength_live)
    geometry_effect_frames: IntProperty(name="几何动画时长", min=4, max=240, default=48, update=update_frames_live)
    geometry_effect_direction: EnumProperty(name="方向", items=[
        ("Z", "+Z / 向上", "沿局部正 Z 方向生长或位移"),
        ("-Z", "-Z / 向下", "沿局部负 Z 方向生长或位移"),
        ("X", "+X", "沿局部正 X 方向生长或位移"),
        ("-X", "-X", "沿局部负 X 方向生长或位移"),
        ("Y", "+Y", "沿局部正 Y 方向生长或位移"),
        ("-Y", "-Y", "沿局部负 Y 方向生长或位移"),
        ("CUSTOM", "自定义角度", "按下方方位角与俯仰角合成任意方向"),
    ], default="Z", description="改后需重新添加特效生效")
    geometry_effect_azimuth: FloatProperty(name="方位角（度）", min=0.0, max=360.0, default=0.0, precision=1,
                                           description="自定义方向的水平方位角：0°=+X，90°=+Y，配合俯仰角合成任意方向（重新添加特效后生效）")
    geometry_effect_elevation: FloatProperty(name="俯仰角（度）", min=-90.0, max=90.0, default=0.0, precision=1,
                                             description="自定义方向相对水平面的仰角：0°=水平，90°=正上，-90°=正下（重新添加特效后生效）")
    geometry_particle_density: FloatProperty(name="粒子密度", min=1.0, max=100.0, default=30.0, update=update_geometry_density_live)
    geometry_particle_size: FloatProperty(name="粒子半径", min=0.005, max=0.5, default=0.06, update=update_geometry_live)
    dissolve_frames: IntProperty(name="消散时长", min=4, max=240, default=24, update=update_frames_live)
    flow_frames: IntProperty(name="流动时长", min=4, max=240, default=48, update=update_frames_live)
    layer_color: FloatVectorProperty(name="新图层颜色", subtype="COLOR", size=4, min=0, max=1, default=(0.12, 0.3, 0.65, 1),
                                     update=update_layer_values)
    layer_roughness: FloatProperty(name="图层粗糙度", min=0, max=1, default=0.35, update=update_layer_values)
    layer_strength: FloatProperty(name="遮罩强度", min=0, max=1, default=0.5, update=update_layer_values,
                                  description="控制新图层的覆盖范围：越大覆盖越多（噪声类遮罩的疏密由花纹密度控制）")
    layer_pattern_scale: FloatProperty(name="花纹密度", min=0.5, max=40.0, default=5.0, update=update_layer_values,
                                       description="噪声类遮罩的花纹疏密：值越大斑块越细密")
    layer_opacity: FloatProperty(name="不透明度", min=0.0, max=1.0, default=1.0, update=update_layer_values)
    layer_mask: EnumProperty(name="智能遮罩", update=update_layer_wiring, items=[
        ("NOISE", "噪声", "程序化噪声遮罩"), ("AO", "环境遮蔽", "使用 Ambient Occlusion 遮罩"),
        ("FACING", "法线朝向", "使用视角法线朝向遮罩"), ("HEIGHT", "高度", "使用生成坐标高度遮罩"),
        ("OBJECT", "物体坐标", "使用物体坐标生成空间遮罩"),
        ("GRADIENT", "渐变", "线性渐变遮罩，沿物体高度方向过渡，适合渐变染色与落尘"),
        ("WAVE", "波纹", "波纹条带遮罩，疏密由花纹密度控制，适合描线与装饰花纹"),
        ("TOP_DUST", "顶部积灰", "物体上半部分渐白，适合落灰积雪"),
        ("BOTTOM_WEAR", "底部磨损", "物体下半部分渐白，适合做旧与泥泞"),
        ("RINGS", "同心环", "同心圆环带遮罩，适合漩涡与年轮纹样"),
        ("CHECKER", "棋盘格", "棋盘格遮罩，适合程序化花纹与贴图检查"),
        ("BLOTCH", "斑块", "Voronoi 细胞斑块遮罩，适合剥落与锈迹分布"),
        ("CURVATURE", "曲率 / 边缘（Cycles / EEVEE）", "Cycles 使用 Pointiness 曲率；EEVEE 使用环境遮蔽近似凸起与凹陷变化"),
    ])
    layer_mask_direction: EnumProperty(name="遮罩方向", update=update_layer_wiring, items=[
        ("X", "+X", "沿物体局部 X 正方向；负方向按钮可反转"),
        ("-X", "−X", "沿物体局部 X 负方向"),
        ("Y", "+Y", "沿物体局部 Y 正方向；负方向按钮可反转"),
        ("-Y", "−Y", "沿物体局部 Y 负方向"),
        ("Z", "+Z", "沿物体局部 Z 正方向，默认向上"),
        ("-Z", "−Z", "沿物体局部 Z 负方向"),
        ("CUSTOM", "自定义", "按下方方位角与俯仰角合成任意渐变方向"),
    ], default="Z")
    layer_mask_azimuth: FloatProperty(name="方位角（度）", min=0.0, max=360.0, default=0.0, precision=1,
                                      update=update_layer_wiring,
                                      description="自定义遮罩方向的水平方位角：0°=+X，90°=+Y")
    layer_mask_elevation: FloatProperty(name="俯仰角（度）", min=-90.0, max=90.0, default=0.0, precision=1,
                                        update=update_layer_wiring,
                                        description="自定义遮罩方向相对水平面的仰角：0°=水平，90°=正上，-90°=正下")
    layer_blend_mode: EnumProperty(name="混合模式", update=update_layer_wiring, items=[
        ("MASK", "正常 · 遮罩", "按智能遮罩把图层混合进下层（PS 正常 + 遮罩）"),
        ("DARKEN", "变暗", "取较暗色，整体压暗基色"),
        ("MULTIPLY", "正片叠底", "压暗叠色，适合污渍、锈迹、印刷叠色"),
        ("BURN", "颜色加深", "更强的压暗，加深缝隙与阴影"),
        ("LIGHTEN", "变亮", "取较亮色，整体提亮基色"),
        ("SCREEN", "滤色", "提亮叠色，适合光斑、发光纹理"),
        ("DODGE", "颜色减淡", "更强的提亮，做高光侵蚀效果"),
        ("LINEAR_DODGE", "线性减淡（添加）", "颜色相加，适合荧光、能量叠加"),
        ("OVERLAY", "叠加", "暗部压暗、亮部提亮，增强纹理对比"),
        ("SOFT_LIGHT", "柔光", "轻柔的对比罩染，适合柔和调色"),
        ("LINEAR_LIGHT", "线性光", "强对比图案强调，慎用高值"),
        ("DIFFERENCE", "差值", "取颜色差绝对值，适合故障、反色特效"),
        ("EXCLUSION", "排除", "柔和的差值，低对比反色"),
        ("SUBTRACT", "减去", "从基色减去图层色，做镂空侵蚀"),
        ("DIVIDE", "划分", "基色除以图层色，做漂白提亮"),
        ("HUE", "色相", "只替换色相保留明暗，做整体变色"),
        ("SATURATION", "饱和度", "只替换饱和度，去灰或增艳"),
        ("COLOR", "颜色", "替换色相与饱和度保留明暗，做上色"),
        ("VALUE", "明度", "只替换明暗保留色相，做光影叠加"),
        ("ADD", "叠加着色", "Blender AddShader：发光层（能量流/光效），不参与颜色混合"),
    ])
    # ── 体积特效板块（规格定稿 §2，全栈 14:11 归档）─────────────────────
    volume_resolution: EnumProperty(name="模拟分辨率", items=[
        ("32", "低 · 32", "预览够用，烘焙快"),
        ("64", "中 · 64", "均衡画质与速度"),
        ("128", "高 · 128", "细节最佳，烘焙较慢"),
    ], default="32", update=update_volume_sim_live)
    volume_frames: IntProperty(name="模拟 / 动画时长（帧）", min=8, max=250, default=48, update=update_volume_sim_live)
    volume_direction: EnumProperty(name="体积方向", items=[
        ("NATURAL", "自然（默认）", "无任何人工偏置，保持引擎原生行为（与 v1.0.1 六轴体系同构的零漂移首项）"),
        ("+Z", "+Z", "沿世界 +Z"),
        ("-Z", "−Z", "沿世界 −Z"),
        ("+X", "+X", "沿世界 +X"),
        ("-X", "−X", "沿世界 −X"),
        ("+Y", "+Y", "沿世界 +Y"),
        ("-Y", "−Y", "沿世界 −Y"),
        ("CUSTOM", "自定义角度", "按方位角与俯仰角合成任意方向"),
    ], default="NATURAL", update=update_flow_direction_live)
    volume_azimuth: FloatProperty(name="方位角（度）", min=0.0, max=360.0, default=0.0, precision=1,
                                  description="自定义方向的水平方位角：0°=+X，90°=+Y（与 v1.0.1 既有换算同约定）", update=update_flow_direction_live)
    volume_elevation: FloatProperty(name="俯仰角（度）", min=-90.0, max=90.0, default=0.0, precision=1,
                                    description="自定义方向相对水平面的仰角：0°=水平，90°=正上", update=update_flow_direction_live)
    fog_density: FloatProperty(name="雾密度", min=0.0, max=2.0, default=0.35, update=update_fog_live)
    fog_color: FloatVectorProperty(name="雾颜色", subtype="COLOR", size=4, min=0, max=1, default=(0.85, 0.87, 0.9, 1), update=update_fog_live)
    fog_noise_scale: FloatProperty(name="雾形态规模", min=0.5, max=20.0, default=4.0, update=update_fog_live)
    fog_animate: BoolProperty(name="雾流动动画", default=True, update=update_fog_live)
    smoke_color: FloatVectorProperty(name="烟颜色", subtype="COLOR", size=4, min=0, max=1, default=(0.35, 0.35, 0.35, 1), update=update_smoke_live)
    smoke_density: FloatProperty(name="烟密度", min=0.05, max=2.0, default=0.4, update=update_smoke_live)
    fire_preset: EnumProperty(name="火焰色温", items=[
        ("ORANGE", "橙红", "经典燃烧色温"),
        ("BLUE", "蓝焰", "高温 / 化学焰色"),
    ], default="ORANGE", update=update_fire_live)
    fire_intensity: FloatProperty(name="火焰强度", min=0.1, max=10.0, default=1.2, update=update_fire_live)
    rain_snow_mode: EnumProperty(name="天气类型", items=[
        ("RAIN", "雨", "快速下落的拉伸雨丝"),
        ("SNOW", "雪", "慢速飘落带湍流扰动"),
    ], default="RAIN", description="改后需重新添加特效生效")
    rain_snow_count: IntProperty(name="粒子数量", min=100, max=20000, default=3000, update=update_rain_snow_live)
    rain_snow_area: FloatProperty(name="覆盖范围（物体尺寸倍数）", min=1.0, max=10.0, default=2.5, update=update_rain_snow_live)
    liquid_color: FloatVectorProperty(name="液体颜色", subtype="COLOR", size=4, min=0, max=1, default=(0.1, 0.35, 0.6, 1), update=update_liquid_live)
    liquid_flow: EnumProperty(name="初始状态", items=[
        ("STILL", "静止", "液面平静起步（推荐首次体验）"),
        ("POUR", "倾倒", "液体从上方落入域内"),
    ], default="STILL", description="改后需重新添加特效生效")


# PS 混合模式（文档 §3 定稿 19 种；MASK 顶替 PS「正常」位、LINEAR_DODGE 承载原生 ADD——原生 ADD identifier 已被发光「叠加着色」占用，保旧 .blend 兼容）
DIRECTIONAL_MASK_TYPES = {"HEIGHT", "GRADIENT", "TOP_DUST", "BOTTOM_WEAR"}
PS_COLOR_BLEND_MODES = frozenset({
    "DARKEN", "MULTIPLY", "BURN", "LIGHTEN", "SCREEN", "DODGE", "LINEAR_DODGE",
    "OVERLAY", "SOFT_LIGHT", "LINEAR_LIGHT", "DIFFERENCE", "EXCLUSION",
    "SUBTRACT", "DIVIDE", "HUE", "SATURATION", "COLOR", "VALUE",
})
PS_BLEND_TYPE_MAP = {"LINEAR_DODGE": "ADD"}


def _direction_vector(azimuth_deg, elevation_deg):
    """方位角/俯仰角（度）→ 单位方向向量：0° 方位=+X，90°=+Y；俯仰 0°=水平，90°=正上。"""
    az = math.radians(azimuth_deg); el = math.radians(elevation_deg)
    return Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))


def _direction_axis_vector(direction_id, azimuth_deg, elevation_deg):
    """六轴枚举 → 单位轴向量；CUSTOM → 角度合成向量。"""
    if direction_id == "CUSTOM":
        return _direction_vector(azimuth_deg, elevation_deg)
    vec = Vector((0.0, 0.0, 0.0))
    vec["XYZ".index(direction_id[-1])] = -1.0 if direction_id.startswith("-") else 1.0
    return vec


def _direction_projection(nt, vector_socket, direction, label, location):
    """把向量坐标投影到自定义方向上（SeparateXYZ → 三乘权重 → 两加合成），返回标量 socket。"""
    sep = nt.nodes.new("ShaderNodeSeparateXYZ"); sep.label = f"{label} · 分量"; sep.location = location
    nt.links.new(vector_socket, sep.inputs["Vector"])
    weighted = []
    for index, comp in enumerate(("X", "Y", "Z")):
        weight = nt.nodes.new("ShaderNodeMath"); weight.operation = "MULTIPLY"
        weight.label = f"{label} · {comp}权重"; weight.location = (location[0] + 180, location[1] - 60 - index * 140)
        weight.inputs[1].default_value = direction[index]
        nt.links.new(sep.outputs[comp], weight.inputs[0])
        weighted.append(weight.outputs["Value"])
    add1 = nt.nodes.new("ShaderNodeMath"); add1.operation = "ADD"; add1.label = f"{label} · 合成"
    add1.location = (location[0] + 360, location[1] - 60)
    nt.links.new(weighted[0], add1.inputs[0]); nt.links.new(weighted[1], add1.inputs[1])
    add2 = nt.nodes.new("ShaderNodeMath"); add2.operation = "ADD"; add2.label = f"{label} · 方向投影"
    add2.location = (location[0] + 540, location[1] - 60)
    nt.links.new(add1.outputs["Value"], add2.inputs[0]); nt.links.new(weighted[2], add2.inputs[1])
    return add2.outputs["Value"]


def _direction_rotation(nt, vector_socket, azimuth_deg, elevation_deg, label, location):
    """绕 Z 旋 −方位角、绕 Y 旋 +俯仰角，把自定义方向对齐到 +X（供条纹类采样），返回向量 socket。"""
    rz = nt.nodes.new("ShaderNodeVectorRotate"); rz.rotation_type = 'Z_AXIS'
    rz.label = f"{label} · 方位旋转"; rz.location = location
    rz.inputs["Angle"].default_value = -math.radians(azimuth_deg)
    nt.links.new(vector_socket, rz.inputs["Vector"])
    ry = nt.nodes.new("ShaderNodeVectorRotate"); ry.rotation_type = 'Y_AXIS'
    ry.label = f"{label} · 俯仰旋转"; ry.location = (location[0] + 170, location[1])
    ry.inputs["Angle"].default_value = math.radians(elevation_deg)
    nt.links.new(rz.outputs["Vector"], ry.inputs["Vector"])
    return ry.outputs["Vector"]


def _orthonormal_sweep_frame(direction):
    """主干方向 → 正交扫掠基 (ey, ez)：ey=dir×Z（平行时退 +X），ez=dir×ey。"""
    sweep_y = direction.cross(Vector((0.0, 0.0, 1.0)))
    if sweep_y.length_squared < 1.0e-8:
        sweep_y = Vector((1.0, 0.0, 0.0))
    sweep_y.normalize()
    sweep_z = direction.cross(sweep_y).normalized()
    return sweep_y, sweep_z


def _axis_support(bounds, direction):
    """包围盒沿单位方向（绝对分量加权）的支撑半宽。"""
    return bounds.x * abs(direction.x) + bounds.y * abs(direction.y) + bounds.z * abs(direction.z)


# ─────────────────────────────────────────────────────────────────────────────
# [连线引擎] wire_layer：全扩展唯一接线实现——新层创建与整链重放共用它，
# 保证「单次创建」与「批量重建」结果一致（教学点：把「怎么接」收敛到一个
# 函数，是节点式扩展防状态分裂的顶层设计）。
# 链式数据流（PS 式图层 = 画家算法的着色器版）：
#   下层 color_mix.Result ──A(底色)──┐
#   本层 params["color"]  ──B(顶色)──┤ Mix(PS式混合) ──Result──▶ 本层
#   Principled.BaseColor；遮罩链 Fac ▶ 强度 ColorRamp（覆盖范围）▶ Mix.Factor。
# prev_chain dict 是「上一层的记忆」：color_mix=可链的混合节点 / fallback_socket=
# 结构缺失时的退路 / base_color=完全不建链时直接抄的值；函数内「A 端三变体」
# 逐一兜底，让任意历史版本的层都能接上新层。

def wire_layer(nt, source_socket, old_target, params, prev_chain, label_index):
    """创建一层完整节点链并接线（add_layer 与整链重放共用的唯一接线实现，v0.9.4 §三）。
    params: dict(blend_mode, mask_type, mask_direction, color, roughness, strength, pattern_scale)
    prev_chain: {"color_mix": 下层color_mix节点|None, "fallback_socket": 输出socket|None, "base_color": 四元组|None}
    返回 dict(shader/blend/color_mix/texcoord/mask/mask_aux/strength)；非法混合模式返回 None（内部已恢复直连）。"""
    blend_mode = params["blend_mode"]
    shader = nt.nodes.new("ShaderNodeBsdfPrincipled"); shader.label = f"MFX图层{label_index}"
    shader.location = (source_socket.node.location.x, source_socket.node.location.y - 300)
    set_input(shader, "Base Color", params["color"]); set_input(shader, "Roughness", params["roughness"])
    color_mix = None
    if blend_mode in PS_COLOR_BLEND_MODES:
        color_mix = nt.nodes.new("ShaderNodeMix"); color_mix.data_type = "RGBA"
        color_mix.blend_type = PS_BLEND_TYPE_MAP.get(blend_mode, blend_mode); color_mix.label = "颜色混合（PS式）"
        color_mix.location = (shader.location.x - 180, shader.location.y + 120)
        next(s for s in color_mix.inputs if s.name == "Factor" and s.type == "VALUE").default_value = 1.0
        a_socket = next(s for s in color_mix.inputs if s.name == "A" and s.type == "RGBA")
        b_socket = next(s for s in color_mix.inputs if s.name == "B" and s.type == "RGBA")
        # A 端（底层色）来源三变体（v0.9.4 §三.2，修复旧 907 行 input→input 无效链接）：
        # a) 下层为 PS 层→链其 color_mix 的 Result；a') 下层记录缺失但 Base Color 有链→回溯 from_socket；
        # b) 下层 MASK/ADD→复制其 Base Color 值（不建链）；c) 首层→灰 0.8。
        a_source = None
        if prev_chain and prev_chain.get("color_mix") is not None:
            a_source = next((s for s in prev_chain["color_mix"].outputs if s.name == "Result" and s.type == "RGBA"), None)
        elif prev_chain and prev_chain.get("fallback_socket") is not None:
            a_source = prev_chain["fallback_socket"]
        if a_source is not None:
            nt.links.new(a_source, a_socket)
        elif prev_chain and prev_chain.get("base_color") is not None:
            a_socket.default_value = prev_chain["base_color"]
        else:
            a_socket.default_value = (0.8, 0.8, 0.8, 1.0)
        b_socket.default_value = params["color"]
        nt.links.new(next(s for s in color_mix.outputs if s.name == "Result" and s.type == "RGBA"), shader.inputs["Base Color"])
    texcoord = mask = mask_aux = strength_node = opacity_node = add_node = None
    if blend_mode != "ADD":
        mask_type = params["mask_type"]
        mask_direction = params.get("mask_direction", "Z")
        direction_custom = mask_direction == "CUSTOM"
        direction_axis = mask_direction[-1] if (not direction_custom and mask_direction[-1:] in {"X", "Y", "Z"}) else "Z"
        direction_reverse = (not direction_custom) and mask_direction.startswith("-")
        if mask_type in {"NOISE", "HEIGHT", "OBJECT", "GRADIENT", "TOP_DUST", "BOTTOM_WEAR"}:
            texcoord = nt.nodes.new("ShaderNodeTexCoord"); texcoord.label = "图层遮罩坐标"; texcoord.location = (shader.location.x - 650, shader.location.y - 80)
        if mask_type == "NOISE":
            mask = nt.nodes.new("ShaderNodeTexNoise"); mask.label = "图层噪声遮罩"; mask.location = (shader.location.x - 430, shader.location.y - 80)
            mask.inputs["Scale"].default_value = params["pattern_scale"]
            nt.links.new(texcoord.outputs["Generated"], mask.inputs["Vector"]); mask_output = mask.outputs["Fac"]
        elif mask_type == "AO":
            mask = nt.nodes.new("ShaderNodeAmbientOcclusion"); mask.label = "环境遮蔽遮罩"; mask.location = (shader.location.x - 430, shader.location.y - 80)
            mask.inputs["Distance"].default_value = 1.0
            mask_output = mask.outputs.get("AO") or mask.outputs.get("Color")
        elif mask_type == "FACING":
            mask = nt.nodes.new("ShaderNodeLayerWeight"); mask.label = "法线朝向遮罩"; mask.location = (shader.location.x - 430, shader.location.y - 80)
            mask_output = mask.outputs["Facing"]
        elif mask_type == "OBJECT":
            mask = nt.nodes.new("ShaderNodeTexNoise"); mask.label = "物体坐标遮罩"; mask.location = (shader.location.x - 430, shader.location.y - 80)
            mask.inputs["Scale"].default_value = params["pattern_scale"]
            nt.links.new(texcoord.outputs["Object"], mask.inputs["Vector"]); mask_output = mask.outputs["Fac"]
        elif mask_type in {"HEIGHT", "GRADIENT", "TOP_DUST", "BOTTOM_WEAR"}:
            if direction_custom:
                mask_output = _direction_projection(nt, texcoord.outputs["Generated"],
                                                    _direction_vector(params.get("mask_azimuth", 0.0), params.get("mask_elevation", 0.0)),
                                                    "定向遮罩", (shader.location.x - 650, shader.location.y - 80))
                mask_aux = mask_output.node
            else:
                mask_aux = nt.nodes.new("ShaderNodeSeparateXYZ")
                mask_aux.label = "方向高度遮罩" if mask_type == "HEIGHT" else "定向渐变坐标"
                mask_aux.location = (shader.location.x - 650, shader.location.y - 80)
                nt.links.new(texcoord.outputs["Generated"], mask_aux.inputs["Vector"])
                mask_output = mask_aux.outputs[direction_axis]
            if mask_type in {"TOP_DUST", "BOTTOM_WEAR"}:
                mask = nt.nodes.new("ShaderNodeValToRGB")
                mask.label = "顶部积灰遮罩" if mask_type == "TOP_DUST" else "底部磨损遮罩"
                mask.location = (shader.location.x - 430, shader.location.y - 80)
                ramp = mask.color_ramp.elements
                if mask_type == "TOP_DUST":
                    ramp[0].position = 0.45; ramp[1].position = 0.75
                else:
                    ramp[0].position = 0.25; ramp[1].position = 0.55
                    ramp[0].color = (1.0, 1.0, 1.0, 1.0); ramp[1].color = (0.0, 0.0, 0.0, 1.0)
                if direction_reverse:
                    low, high = tuple(ramp[0].color), tuple(ramp[1].color)
                    ramp[0].color = high; ramp[1].color = low
                nt.links.new(mask_output, mask.inputs["Fac"])
                mask_output = mask.outputs["Color"]
        elif mask_type == "WAVE":
            mask = nt.nodes.new("ShaderNodeTexWave"); mask.label = "波纹遮罩"; mask.location = (shader.location.x - 430, shader.location.y - 80)
            mask.inputs["Scale"].default_value = params["pattern_scale"]
            mask_output = mask.outputs["Fac"]
        elif mask_type == "RINGS":
            mask = nt.nodes.new("ShaderNodeTexWave"); mask.label = "同心环遮罩"; mask.location = (shader.location.x - 430, shader.location.y - 80)
            mask.wave_type = "RINGS"; mask.inputs["Scale"].default_value = params["pattern_scale"]
            mask_output = mask.outputs["Fac"]
        elif mask_type == "CHECKER":
            mask = nt.nodes.new("ShaderNodeTexChecker"); mask.label = "棋盘格遮罩"; mask.location = (shader.location.x - 430, shader.location.y - 80)
            mask.inputs["Scale"].default_value = params["pattern_scale"]
            mask_output = mask.outputs["Fac"]
        elif mask_type == "BLOTCH":
            mask = nt.nodes.new("ShaderNodeTexVoronoi"); mask.label = "斑块遮罩"; mask.location = (shader.location.x - 430, shader.location.y - 80)
            mask.inputs["Scale"].default_value = max(1.0, params["pattern_scale"] * 0.4)
            mask_output = mask.outputs["Distance"]
        elif mask_type == "CURVATURE":
            if bpy.context.scene and bpy.context.scene.render.engine == "BLENDER_EEVEE_NEXT":
                mask = nt.nodes.new("ShaderNodeAmbientOcclusion"); mask.label = "曲率近似（EEVEE 环境遮蔽）"
                mask.inputs["Distance"].default_value = 0.35
                mask_output = mask.outputs.get("AO") or mask.outputs.get("Color")
            else:
                mask = nt.nodes.new("ShaderNodeNewGeometry"); mask.label = "曲率遮罩（Cycles Pointiness）"
                mask_output = mask.outputs.get("Pointiness")
            mask.location = (shader.location.x - 430, shader.location.y - 80)
            if mask_output is None:
                nt.nodes.remove(mask)
                nt.nodes.remove(shader)
                if color_mix is not None:
                    nt.nodes.remove(color_mix)
                nt.links.new(source_socket, old_target)
                return None
        else:
            mask_aux = nt.nodes.new("ShaderNodeSeparateXYZ"); mask_aux.label = "高度遮罩"; mask_aux.location = (shader.location.x - 430, shader.location.y - 80)
            nt.links.new(texcoord.outputs["Generated"], mask_aux.inputs["Vector"])
            mask = mask_aux; mask_output = mask_aux.outputs["Z"]
        strength_node = nt.nodes.new("ShaderNodeValToRGB"); strength_node.label = "遮罩范围（强度）"; strength_node.location = (shader.location.x - 180, shader.location.y - 80)
        mid = 1.0 - params["strength"]
        ramp = strength_node.color_ramp.elements
        ramp[0].position = max(0.0, mid - 0.2)
        ramp[1].position = min(1.0, max(ramp[0].position + 0.05, mid + 0.2))
        if direction_reverse and mask_type in {"HEIGHT", "GRADIENT"}:
            low, high = tuple(ramp[0].color), tuple(ramp[1].color)
            ramp[0].color = high; ramp[1].color = low
        nt.links.new(mask_output, strength_node.inputs["Fac"])
        opacity_node = nt.nodes.new("ShaderNodeMath"); opacity_node.operation = "MULTIPLY"
        opacity_node.label = "图层不透明度"; opacity_node.location = (shader.location.x + 40, shader.location.y - 100)
        opacity_node.inputs[1].default_value = params.get("opacity", 1.0) if params.get("enabled", True) else 0.0
        nt.links.new(strength_node.outputs["Color"], opacity_node.inputs[0])
        blend = nt.nodes.new("ShaderNodeMixShader"); blend.label = f"图层混合 {label_index}"; blend.location = (source_socket.node.location.x + 240, source_socket.node.location.y)
        nt.links.new(source_socket, blend.inputs[1]); nt.links.new(shader.outputs["BSDF"], blend.inputs[2]); nt.links.new(opacity_node.outputs["Value"], blend.inputs[0])
    elif blend_mode == "ADD":
        add_node = nt.nodes.new("ShaderNodeAddShader"); add_node.label = f"发光叠加 {label_index}"; add_node.location = (source_socket.node.location.x + 80, source_socket.node.location.y - 120)
        nt.links.new(source_socket, add_node.inputs[0]); nt.links.new(shader.outputs["BSDF"], add_node.inputs[1])
        blend = nt.nodes.new("ShaderNodeMixShader"); blend.label = f"图层可见度 {label_index}"; blend.location = (source_socket.node.location.x + 300, source_socket.node.location.y)
        blend.inputs[0].default_value = params.get("opacity", 1.0) if params.get("enabled", True) else 0.0
        nt.links.new(source_socket, blend.inputs[1]); nt.links.new(add_node.outputs[0], blend.inputs[2])
    else:
        nt.nodes.remove(shader)
        if color_mix is not None:
            nt.nodes.remove(color_mix)
        nt.links.new(source_socket, old_target)
        return None
    nt.links.new(blend.outputs[0], old_target)
    return {"shader": shader, "blend": blend, "add": add_node, "color_mix": color_mix, "texcoord": texcoord,
            "mask": mask, "mask_aux": mask_aux, "strength": strength_node, "opacity": opacity_node}


def can_detach_layer_nodes(nt, layer):
    blend = nt.nodes.get(layer.blend_node)
    if blend is None:
        return False
    base_input_index = 0 if blend.type == "ADD_SHADER" else 1
    base_link = next((link for link in nt.links if link.to_node == blend and link.to_socket == blend.inputs[base_input_index]), None)
    return base_link is not None and any(link.from_node == blend for link in nt.links)


def detach_layer_nodes(nt, layer):
    """摘除一个图层并安全重连底材（复用原 remove_layer 重连逻辑；清理 key 七项含 color_mix，v0.9.4 §三.1）。
    成功返回 True；blend 节点缺失或链接不完整（无法安全重连）返回 False，调用方保持链路现状。"""
    blend = nt.nodes.get(layer.blend_node)
    if blend is None or not can_detach_layer_nodes(nt, layer):
        return False
    base_input_index = 0 if blend.type == "ADD_SHADER" else 1
    base_link = next((link for link in nt.links if link.to_node == blend and link.to_socket == blend.inputs[base_input_index]), None)
    if base_link is None:
        return False
    base_socket = base_link.from_socket
    destinations = [(link.to_node, link.to_socket) for link in list(blend.outputs[0].links)]
    if not destinations:
        return False
    for link in list(blend.outputs[0].links):
        nt.links.remove(link)
    for destination_node, destination_socket in destinations:
        nt.links.new(base_socket, destination_socket)
    for key in {layer.blend_node, layer.add_node, layer.shader_node, layer.color_mix_node, layer.mask_node,
                layer.texcoord_node, layer.mask_aux_node, layer.strength_node, layer.opacity_node}:
        node = nt.nodes.get(key)
        if node:
            nt.nodes.remove(node)
    return True


def snapshot_layer(nt, layer):
    """反读图层实际接线参数作为重放快照：节点可读时以节点为准，缺失回落 layer 存储值（旧 .blend 兼容）。"""
    color = tuple(layer.color)
    shader = nt.nodes.get(layer.shader_node)
    color_mix = nt.nodes.get(layer.color_mix_node) if layer.color_mix_node else None
    if color_mix is not None:
        b_socket = next((s for s in color_mix.inputs if s.name == "B" and s.type == "RGBA"), None)
        if b_socket is not None:
            color = tuple(b_socket.default_value)
    elif shader is not None:
        sock = shader.inputs.get("Base Color")
        if sock is not None and not sock.is_linked:
            color = tuple(sock.default_value)
    roughness = float(layer.roughness)
    if shader is not None:
        sock = shader.inputs.get("Roughness")
        if sock is not None and not sock.is_linked:
            roughness = float(sock.default_value)
    scale = float(layer.pattern_scale)
    mask = nt.nodes.get(layer.mask_node) if layer.mask_node else None
    if mask is not None and mask.type in {"TEX_NOISE", "TEX_WAVE", "TEX_CHECKER", "TEX_VORONOI"}:
        sock = mask.inputs.get("Scale")
        if sock is not None:
            raw = float(sock.default_value)
            scale = raw / 0.4 if layer.mask_type == "BLOTCH" else raw
            scale = min(40.0, max(0.5, scale))
    return {"blend_mode": layer.blend_mode, "mask_type": layer.mask_type,
            "mask_direction": getattr(layer, "mask_direction", "Z"), "color": color,
            "roughness": roughness, "strength": float(layer.strength), "pattern_scale": scale,
            "enabled": bool(getattr(layer, "enabled", True)), "opacity": float(getattr(layer, "opacity", 1.0))}


def replay_layer_chain(context, edit_index, overrides):
    """整链重放当前材质的 MFX 图层链（v0.9.4 §三：自顶摘链→自底重放，删除/改模式/改色统一入口）。
    overrides: edit_index 层的参数覆盖（键 = snapshot 键的子集）；其余层按快照原样重放。
    仅重放归属当前活动材质的层；摘链失败保守中止（链路保持原状）。返回 True=已重放。"""
    obj = context.object
    mat = obj.active_material
    layers = context.scene.mfx_layers
    nt = mat.node_tree
    own = [i for i, layer in enumerate(layers) if layer_belongs_to_material(layer, mat, obj)]
    if not own or edit_index not in own:
        return False
    rank = own.index(edit_index)
    snapshots = [(i, snapshot_layer(nt, layers[i])) for i in own]
    for i, snap in snapshots:
        if i == edit_index:
            for key, value in overrides.items():
                if key in snap:
                    snap[key] = value
            snap["pattern_scale"] = min(40.0, max(0.5, snap["pattern_scale"]))
    if any(not can_detach_layer_nodes(nt, layers[i]) for i in own):
        return False
    for i in reversed(own):
        if not detach_layer_nodes(nt, layers[i]):
            return False
    output = next((node for node in nt.nodes if node.type == "OUTPUT_MATERIAL"), None)
    surface_link = next((link for link in nt.links if output and link.to_node == output and link.to_socket.name == "Surface"), None)
    if not surface_link:
        return False
    source_socket = surface_link.from_socket
    old_target = surface_link.to_socket
    nt.links.remove(surface_link)
    meta = [(layers[i].name, layers[i].material_name or mat.name, layers[i].object_name or obj.name) for i in own]
    guard = _MFX_REPLAY_GUARD
    guard["active"] = True
    kept = []
    try:
        prev_chain = None
        for order, (i, snap) in enumerate(snapshots, start=1):
            wired = wire_layer(nt, source_socket, old_target, snap, prev_chain, order)
            if wired is None:
                print(f"[BL-MaterialFX] 图层 {order}（模式 {snap['blend_mode']}）重放失败，已跳过该层")
                continue
            source_socket = wired["blend"].outputs[0]
            prev_chain = ({"color_mix": wired["color_mix"], "fallback_socket": None, "base_color": None}
                          if snap["blend_mode"] in PS_COLOR_BLEND_MODES
                          else {"color_mix": None, "fallback_socket": None, "base_color": tuple(snap["color"])})
            kept.append((meta[order - 1], snap, wired))
        for i in reversed(own):
            layers.remove(i)
        for entry_meta, snap, wired in kept:
            layer = layers.add()
            layer.name = entry_meta[0]; layer.material_name = entry_meta[1]; layer.object_name = entry_meta[2]
            layer.blend_node = wired["blend"].name; layer.shader_node = wired["shader"].name
            layer.blend_mode = snap["blend_mode"]; layer.mask_type = snap["mask_type"]
            layer.mask_direction = snap.get("mask_direction", "Z")
            layer.add_node = wired["add"].name if wired["add"] else ""
            layer.opacity_node = wired["opacity"].name if wired["opacity"] else ""
            layer.color_mix_node = wired["color_mix"].name if wired["color_mix"] else ""
            layer.mask_node = wired["mask"].name if wired["mask"] else ""
            layer.texcoord_node = wired["texcoord"].name if wired["texcoord"] else ""
            layer.mask_aux_node = wired["mask_aux"].name if wired["mask_aux"] else ""
            layer.strength_node = wired["strength"].name if wired["strength"] else ""
            layer.color = tuple(snap["color"]); layer.roughness = snap["roughness"]
            layer.strength = snap["strength"]; layer.pattern_scale = snap["pattern_scale"]
            layer.enabled = snap.get("enabled", True); layer.opacity = snap.get("opacity", 1.0)
        if kept:
            context.scene.mfx_layer_index = min(len(layers) - len(kept) + rank, len(layers) - 1)
        else:
            context.scene.mfx_layer_index = 0
    finally:
        guard["active"] = False
    return True


class MFX_MaterialLayer(PropertyGroup):
    name: StringProperty(name="名称")
    blend_node: StringProperty()
    shader_node: StringProperty()
    mask_node: StringProperty()
    texcoord_node: StringProperty()
    mask_aux_node: StringProperty()
    strength_node: StringProperty()
    opacity_node: StringProperty()
    add_node: StringProperty()
    blend_mode: StringProperty()
    mask_type: StringProperty()
    mask_direction: StringProperty(default="Z")
    enabled: BoolProperty(name="可见", default=True, update=update_layer_visibility)
    opacity: FloatProperty(name="不透明度", min=0.0, max=1.0, default=1.0, update=update_layer_opacity)
    color: FloatVectorProperty(name="颜色", subtype="COLOR", size=4, min=0, max=1, default=(0.12, 0.3, 0.65, 1),
                              update=update_layer_row_color)
    roughness: FloatProperty(name="粗糙度", min=0, max=1, default=0.35, update=update_layer_row_value)
    color_mix_node: StringProperty()
    strength: FloatProperty(name="遮罩强度", min=0, max=1, default=0.5, update=update_layer_row_value)
    pattern_scale: FloatProperty(name="花纹密度", min=0.5, max=40.0, default=5.0, update=update_layer_row_value)
    material_name: StringProperty(name="归属材质")
    object_name: StringProperty(name="归属物体")


class MFX_Favorite(PropertyGroup):
    identifier: StringProperty()
    label: StringProperty()


class MFX_Recent(PropertyGroup):
    identifier: StringProperty()
    label: StringProperty()


def update_effect_layer_enabled(layer, context):
    obj = bpy.data.objects.get(layer.object_name) if layer.object_name else None
    if obj and layer.effect_type in {"LIGHTNING", "OUTLINE"}:
        obj.hide_render = not layer.enabled
        obj.hide_set(not layer.enabled)
    if obj and layer.effect_type == "FRACTURE":
        obj.hide_render = layer.enabled
        obj.hide_set(layer.enabled)
    if layer.collection_name:
        collection = bpy.data.collections.get(layer.collection_name)
        if collection:
            collection.hide_render = not layer.enabled
            collection.hide_viewport = not layer.enabled
    if obj and layer.effect_type in {"GEOMETRY", "PARTICLES"}:
        modifier = obj.modifiers.get(layer.modifier_name) if layer.modifier_name else None
        if modifier:
            modifier.show_viewport = layer.enabled
            modifier.show_render = layer.enabled
    material = bpy.data.materials.get(layer.material_name) if layer.material_name else None
    if material and material.use_nodes:
        nodes = material.node_tree.nodes
        root = nodes.get(layer.root_node) if layer.root_node else None
        emission = nodes.get(layer.emission_node) if layer.emission_node else None
        mask = nodes.get(layer.mask_node) if layer.mask_node else None
        if layer.effect_type == "CORROSION" and mask:
            mask.inputs[1].default_value = layer.strength / 4.0 if layer.enabled else 0.0
        elif layer.effect_type == "TOON" and root:
            root.inputs[0].default_value = 1.0 if layer.enabled else 0.0
        elif layer.effect_type == "DISSOLVE" and root:
            factor = root.inputs[0]
            for link in list(factor.links):
                material.node_tree.links.remove(link)
            factor.default_value = 1.0 if not layer.enabled else 0.0
            if layer.enabled and mask:
                material.node_tree.links.new(mask.outputs["Value"], factor)
        elif root and root.type in {"ADD_SHADER", "MIX_SHADER"}:
            root.mute = not layer.enabled
        if emission and emission.inputs.get("Strength"):
            emission.inputs["Strength"].default_value = layer.strength if layer.enabled else 0.0
    if obj and layer.effect_type == "OUTLINE" and obj.modifiers:
        for modifier in obj.modifiers:
            if modifier.type == "SOLIDIFY" and modifier.name.startswith("MFX"):
                modifier.thickness = max(0.001, layer.strength * 0.004)


def update_effect_layer_strength(layer, context):
    material = bpy.data.materials.get(layer.material_name) if layer.material_name else None
    if material and material.use_nodes and layer.emission_node:
        node = material.node_tree.nodes.get(layer.emission_node)
        if node and node.inputs.get("Strength"):
            node.inputs["Strength"].default_value = layer.strength if layer.enabled else 0.0
            action = material.node_tree.animation_data.action if material.node_tree.animation_data else None
            if action and layer.strength_base > 0.0:
                try:
                    base_curves = json.loads(layer.strength_curve_data or "{}")
                except (TypeError, ValueError):
                    base_curves = {}
                ratio = layer.strength / layer.strength_base
                for curve in action.fcurves:
                    if f'nodes["{node.name}"]' not in curve.data_path or "default_value" not in curve.data_path:
                        continue
                    key = f"{curve.data_path}|{curve.array_index}"
                    base_values = base_curves.get(key)
                    if base_values and len(base_values) == len(curve.keyframe_points):
                        for point, base_value in zip(curve.keyframe_points, base_values):
                            point.co.y = base_value * ratio
                    else:
                        for point in curve.keyframe_points:
                            point.co.y *= ratio
                    curve.update()
    if material and material.use_nodes and layer.effect_type == "CORROSION" and layer.mask_node:
        mask = material.node_tree.nodes.get(layer.mask_node)
        if mask:
            mask.inputs[1].default_value = layer.strength / 4.0 if layer.enabled else 0.0
    if material and material.use_nodes and layer.effect_type == "DISSOLVE" and layer.control_node:
        node = material.node_tree.nodes.get(layer.control_node)
        if node and node.inputs.get("Scale"):
            node.inputs["Scale"].default_value = 4.0 + layer.strength * 10.0
    obj = bpy.data.objects.get(layer.object_name) if layer.object_name else None
    if obj and layer.effect_type == "OUTLINE":
        for modifier in obj.modifiers:
            if modifier.type == "SOLIDIFY" and modifier.name.startswith("MFX"):
                modifier.thickness = max(0.001, layer.strength * 0.004)
    if obj and layer.effect_type in {"GEOMETRY", "PARTICLES"} and layer.modifier_name and layer.modifier_input:
        modifier = obj.modifiers.get(layer.modifier_name)
        if modifier:
            modifier[layer.modifier_input] = layer.strength
            action = obj.animation_data.action if obj.animation_data else None
            if action:
                for curve in action.fcurves:
                    if layer.modifier_input in curve.data_path and layer.modifier_name in curve.data_path and curve.keyframe_points:
                        key = min(curve.keyframe_points, key=lambda point: point.co.x) if layer.effect_type == "PARTICLES" else max(curve.keyframe_points, key=lambda point: point.co.x)
                        key.co.y = layer.strength
                        curve.update()
            obj.update_tag(refresh={"OBJECT", "DATA"})
            if context and context.view_layer:
                context.view_layer.update()
    if layer.effect_type == "VOLUME_FOG" and material and material.use_nodes:
        density_node = next((n for n in material.node_tree.nodes if n.label == "雾密度调制"), None)
        if density_node:
            density_node.inputs[1].default_value = min(max(layer.strength, 0.0), 2.0)
    if layer.effect_type in {"VOLUME_SMOKE", "VOLUME_FIRE"} and material and material.use_nodes:
        vol = next((n for n in material.node_tree.nodes if n.type == "PRINCIPLED_VOLUME"), None)
        if vol:
            if layer.effect_type == "VOLUME_SMOKE":
                vol.inputs["Density"].default_value = min(max(layer.strength, 0.05), 2.0)
            else:
                try:
                    vol.inputs["Emission Strength"].default_value = min(max(layer.strength, 0.1), 10.0)
                except Exception:
                    pass
    _layer_panel_mirror(context, layer)  # v1.0.5 联动·特效页反向：层值 → 面板读数


def update_effect_layer_blend(layer, context):
    material = bpy.data.materials.get(layer.material_name) if layer.material_name else None
    if not material or not material.use_nodes or not layer.blend_source_node:
        return
    nt = material.node_tree
    source = nt.nodes.get(layer.blend_source_node)
    if not source or source.type != "ADD_SHADER":
        return
    current = nt.nodes.get(layer.root_node) if layer.root_node else None
    if layer.blend_mode == "MIX" and current == source:
        base_link = next((link for link in nt.links if link.to_node == source and link.to_socket == source.inputs[0]), None)
        destinations = [(link.to_node, link.to_socket) for link in source.outputs[0].links]
        if not base_link or not destinations:
            return
        base_output = base_link.from_socket
        for link in list(source.outputs[0].links):
            nt.links.remove(link)
        wrapper = nt.nodes.new("ShaderNodeMixShader"); wrapper.label = "特效混合强度"
        wrapper["mfx_effect_layer_id"] = layer.layer_id
        wrapper.inputs[0].default_value = 0.5
        nt.links.new(base_output, wrapper.inputs[1]); nt.links.new(source.outputs[0], wrapper.inputs[2])
        for target, socket in destinations:
            nt.links.new(wrapper.outputs[0], socket)
        layer.root_node = wrapper.name
    elif layer.blend_mode == "ADD" and current and current != source:
        destinations = [(link.to_node, link.to_socket) for link in current.outputs[0].links]
        if not destinations:
            layer.root_node = source.name
            return
        for link in list(current.outputs[0].links):
            nt.links.remove(link)
        for target, socket in destinations:
            nt.links.new(source.outputs[0], socket)
        nt.nodes.remove(current)
        layer.root_node = source.name


class MFX_EffectLayer(PropertyGroup):
    layer_id: StringProperty()
    name: StringProperty(name="名称")
    effect_type: StringProperty()
    object_name: StringProperty()
    collection_name: StringProperty()
    material_name: StringProperty()
    root_node: StringProperty()
    blend_source_node: StringProperty()
    emission_node: StringProperty()
    mask_node: StringProperty()
    control_node: StringProperty()
    modifier_name: StringProperty()
    modifier_input: StringProperty()
    enabled: BoolProperty(name="启用", default=True, update=update_effect_layer_enabled)
    strength: FloatProperty(name="强度", description="实时调节该特效的发光、遮罩或几何节点参数", min=0.0, max=100.0, default=4.0, update=update_effect_layer_strength)
    strength_base: FloatProperty(default=4.0, options={'HIDDEN'})
    strength_curve_data: StringProperty(options={'HIDDEN'})
    blend_mode: EnumProperty(name="叠加方式", items=[("ADD", "叠加", "直接叠加特效输出"), ("MIX", "混合", "将特效结果与原材质混合")], update=update_effect_layer_blend)
    loop_mode: EnumProperty(name="循环", items=[("NONE", "不循环", "只播放一次"), ("REPEAT", "重复", "重复播放"), ("MIRROR", "往返", "往返播放"), ("REPEAT_OFFSET", "累积重复", "重复时累加曲线变化")], default="NONE", update=update_effect_layer_animation)
    easing: EnumProperty(name="缓动", items=[("KEEP", "默认", "保留特效原有插值"), ("BEZIER", "柔和", "自动贝塞尔缓动"), ("LINEAR", "线性", "匀速变化"), ("CONSTANT", "跳变", "阶梯跳变"), ("SINE", "正弦", "正弦缓动"), ("QUAD", "二次", "二次缓动")], default="KEEP", update=update_effect_layer_animation)


# ─────────────────────────────────────────────────────────────────────────────
# [层登记·ID 标记体系] register_effect_layer：特效层的「出生证明」。
#   双向索引设计——层对象里存节点名等字符串字段（层 → 节点），同时给节点、物体、
#   集合、修改器打 ["mfx_effect_layer_id"]=uuid 自定义属性（节点 → 层）；
#   删除时靠标记反查拆链，改参时靠层字段直达节点，两向都是 O(1) 定位。
#   兼容注意：GN 修改器支持自定义属性，FluidModifier 等类型不支持（TypeError
#   捕获后退化），volume 层改用对象级标记关联——不是遗漏，是 Blender 类型差异
#   的现实约束（见函数内原注释）。

def register_effect_layer(scene, name, effect_type, obj=None, collection=None, material=None,
                          root=None, emission=None, mask=None, strength=4.0,
                          modifier=None, modifier_input="", control=None, created_nodes=None):
    layers = scene.mfx_effect_layers
    layer = layers.add()
    layer.layer_id = uuid.uuid4().hex
    layer.name = name
    layer.effect_type = effect_type
    layer.object_name = obj.name if obj else ""
    layer.collection_name = collection.name if collection else ""
    layer.material_name = material.name if material else ""
    layer.root_node = root.name if root else ""
    layer.blend_source_node = root.name if root and root.type == "ADD_SHADER" else ""
    layer.emission_node = emission.name if emission else ""
    layer.mask_node = mask.name if mask else ""
    layer.control_node = control.name if control else ""
    layer.modifier_name = modifier.name if modifier else ""
    layer.modifier_input = modifier_input
    layer.strength_base = max(0.0001, min(100.0, strength))
    layer.strength = max(0.0, min(100.0, strength))
    props = getattr(scene, "mfx_props", None)
    if props:
        layer.loop_mode = props.effect_loop_mode
        layer.easing = props.effect_easing
    if material and material.use_nodes and emission and material.node_tree.animation_data:
        action = material.node_tree.animation_data.action
        base_curves = {}
        for curve in action.fcurves:
            if f'nodes["{emission.name}"]' in curve.data_path and "default_value" in curve.data_path:
                key = f"{curve.data_path}|{curve.array_index}"
                base_curves[key] = [point.co.y for point in curve.keyframe_points]
        layer.strength_curve_data = json.dumps(base_curves)
    if material:
        material_ids = set(filter(None, material.get("mfx_effect_layer_ids", "").split(",")))
        material_ids.add(layer.layer_id)
        material["mfx_effect_layer_ids"] = ",".join(sorted(material_ids))
    tagged_nodes = list(created_nodes or ())
    tagged_names = {node.name for node in tagged_nodes}
    for node in (root, emission, mask, control):
        if node and node.name not in tagged_names:
            tagged_nodes.append(node); tagged_names.add(node.name)
    for node in tagged_nodes:
        if node:
            node["mfx_effect_layer_id"] = layer.layer_id
    if obj:
        obj["mfx_effect_layer_id"] = layer.layer_id
    if collection:
        collection["mfx_effect_layer_id"] = layer.layer_id
        for item in collection.objects:
            item["mfx_effect_layer_id"] = layer.layer_id
    if modifier:
        try:  # GN 修改器支持 id props；FluidModifier 等 4.2 类型不支持，volume 层靠对象标记关联
            modifier["mfx_effect_layer_id"] = layer.layer_id
        except TypeError:
            pass
    apply_effect_animation_options(layer)
    return layer


def remember_preset(scene, identifier, label):
    recent = scene.mfx_recent
    for index, entry in enumerate(recent):
        if entry.identifier == identifier:
            recent.remove(index)
            break
    entry = recent.add(); entry.identifier = identifier; entry.label = label
    recent.move(len(recent) - 1, 0)
    while len(recent) > 5: recent.remove(len(recent) - 1)


class MFX_OT_toggle_favorite(Operator):
    bl_idname = "mfx.toggle_favorite"
    bl_label = "收藏/取消收藏预设"
    def execute(self, context):
        identifier = context.scene.mfx_props.preset
        if identifier == "NO_PRESET_MATCH":
            self.report({'WARNING'}, "当前搜索没有可收藏的预设")
            return {'CANCELLED'}
        favorites = context.scene.mfx_favorites
        index = next((i for i, entry in enumerate(favorites) if entry.identifier == identifier), None)
        if index is not None:
            favorites.remove(index)
            self.report({'INFO'}, "已取消收藏")
        else:
            label = next((item[1] for items in PRESET_ITEMS_BY_CATEGORY.values() for item in items if item[0] == identifier), identifier)
            entry = favorites.add(); entry.identifier = identifier; entry.label = label
            self.report({'INFO'}, "已收藏该预设")
        return {'FINISHED'}


class MFX_OT_apply_recent(Operator):
    bl_idname = "mfx.apply_recent"
    bl_label = "应用最近使用的材质"
    index: IntProperty()
    def execute(self, context):
        recent = context.scene.mfx_recent
        if not 0 <= self.index < len(recent): return {'CANCELLED'}
        entry = recent[self.index]
        for category, items in PRESET_ITEMS_BY_CATEGORY.items():
            if any(item[0] == entry.identifier for item in items):
                context.scene.mfx_props.category = category
                break
        context.scene.mfx_props.search = ""
        context.scene.mfx_props.favorite_only = False
        context.scene.mfx_props.preset = entry.identifier
        return bpy.ops.mfx.apply_preset()


class MFX_OT_add_layer(Operator):
    bl_idname = "mfx.add_layer"
    bl_label = "添加材质图层"
    def execute(self, context):
        obj = context.object
        if not obj or not obj.active_material or not obj.active_material.use_nodes:
            self.report({'ERROR'}, "请先选择有节点材质的物体")
            return {'CANCELLED'}
        layers = context.scene.mfx_layers
        owned_indices = [i for i, layer in enumerate(layers) if layer_belongs_to_material(layer, obj.active_material, obj)]
        if len(owned_indices) >= 8:
            self.report({'ERROR'}, "每个材质最多添加 8 个图层")
            return {'CANCELLED'}
        nt = obj.active_material.node_tree
        output = next((node for node in nt.nodes if node.type == "OUTPUT_MATERIAL"), None)
        surface_link = next((link for link in nt.links if output and link.to_node == output and link.to_socket.name == "Surface"), None)
        if not surface_link:
            self.report({'ERROR'}, "当前材质没有表面着色器连接")
            return {'CANCELLED'}
        p = context.scene.mfx_props
        params = {"blend_mode": p.layer_blend_mode, "mask_type": p.layer_mask,
                  "mask_direction": p.layer_mask_direction,
                  "mask_azimuth": p.layer_mask_azimuth, "mask_elevation": p.layer_mask_elevation,
                  "color": tuple(p.layer_color),
                  "roughness": p.layer_roughness, "strength": p.layer_strength, "pattern_scale": p.layer_pattern_scale,
                  "enabled": True, "opacity": p.layer_opacity}
        prev = next((layers[i] for i in reversed(owned_indices)), None)
        prev_chain = None
        if prev is not None:
            prev_color_mix = nt.nodes.get(prev.color_mix_node) if prev.color_mix_node else None
            if prev_color_mix is not None:
                prev_chain = {"color_mix": prev_color_mix, "fallback_socket": None, "base_color": None}
            else:
                prev_shader = nt.nodes.get(prev.shader_node)
                prev_base = prev_shader.inputs.get("Base Color") if prev_shader else None
                if prev_base is not None and prev_base.is_linked:
                    prev_chain = {"color_mix": None, "fallback_socket": prev_base.links[0].from_socket, "base_color": None}
                else:
                    prev_chain = {"color_mix": None, "fallback_socket": None,
                                  "base_color": tuple(prev_base.default_value) if prev_base is not None else None}
        source_socket = surface_link.from_socket
        old_target = surface_link.to_socket
        nt.links.remove(surface_link)
        guard = _MFX_REPLAY_GUARD
        guard["active"] = True
        try:
            wired = wire_layer(nt, source_socket, old_target, params, prev_chain, len(owned_indices) + 1)
            if wired is None:
                self.report({'ERROR'}, f"未知的图层混合模式：{params['blend_mode']}")
                return {'CANCELLED'}
            layer = layers.add(); layer.name = f"{obj.name} · 图层 {len(layers)}"
            layer.blend_node = wired["blend"].name; layer.shader_node = wired["shader"].name
            layer.blend_mode = params["blend_mode"]; layer.mask_type = params["mask_type"]
            layer.mask_direction = params["mask_direction"]
            layer.add_node = wired["add"].name if wired["add"] else ""
            layer.opacity_node = wired["opacity"].name if wired["opacity"] else ""
            layer.color_mix_node = wired["color_mix"].name if wired["color_mix"] else ""
            layer.mask_node = wired["mask"].name if wired["mask"] else ""; layer.texcoord_node = wired["texcoord"].name if wired["texcoord"] else ""
            layer.mask_aux_node = wired["mask_aux"].name if wired["mask_aux"] else ""
            layer.strength_node = wired["strength"].name if wired["strength"] else ""
            layer.color = params["color"]; layer.roughness = params["roughness"]; layer.strength = params["strength"]
            layer.pattern_scale = params["pattern_scale"]; layer.enabled = params["enabled"]; layer.opacity = params["opacity"]
            layer.material_name = obj.active_material.name; layer.object_name = obj.name
        finally:
            guard["active"] = False
        context.scene.mfx_layer_index = len(layers) - 1
        self.report({'INFO'}, f"已添加图层 {len(owned_indices) + 1} / 8")
        return {'FINISHED'}


class MFX_OT_update_layer(Operator):
    bl_idname = "mfx.update_layer"
    bl_label = "同步当前图层参数"
    def execute(self, context):
        layer = _layer_edit_target(context)
        if layer is None:
            self.report({'ERROR'}, "请选择一个已添加的图层")
            return {'CANCELLED'}
        p = context.scene.mfx_props
        guard = _MFX_REPLAY_GUARD
        guard["active"] = True
        try:
            layer.color = tuple(p.layer_color); layer.roughness = p.layer_roughness
            layer.strength = p.layer_strength; layer.pattern_scale = p.layer_pattern_scale
            layer.opacity = p.layer_opacity; layer.mask_direction = p.layer_mask_direction
            layer.mask_azimuth = p.layer_mask_azimuth; layer.mask_elevation = p.layer_mask_elevation
        finally:
            guard["active"] = False
        if not sync_layer_nodes(context.object.active_material, layer):
            self.report({'ERROR'}, "找不到该图层节点，请检查当前材质")
            return {'CANCELLED'}
        update_layer_opacity(layer, context)
        self.report({'INFO'}, f"已更新：{layer.name}")
        return {'FINISHED'}


class MFX_OT_remove_layer(Operator):
    bl_idname = "mfx.remove_layer"
    bl_label = "移除所选图层"
    bl_description = "移除选中的图层并安全重连底材；残留条目会在其归属材质上摘链，节点缺失时仅移除列表条目"
    index: IntProperty(default=-1, options={'HIDDEN'})
    def execute(self, context):
        obj = context.object; scene = context.scene
        layers = scene.mfx_layers
        index = self.index if self.index >= 0 else scene.mfx_layer_index
        if not layers or not 0 <= index < len(layers):
            self.report({'ERROR'}, "没有可移除的图层")
            return {'CANCELLED'}
        layer = layers[index]
        owner = resolve_layer_material(layer)
        if not owner or not detach_layer_nodes(owner.node_tree, layer):
            layers.remove(index)
            scene.mfx_layer_index = max(0, min(index, len(layers) - 1))
            self.report({'WARNING'}, "节点链缺失，已仅移除该列表条目")
            return {'FINISHED'}
        layers.remove(index)
        scene.mfx_layer_index = max(0, min(index, len(layers) - 1))
        self.report({'INFO'}, f"已移除图层（剩余 {len(layers)} 层）")
        return {'FINISHED'}


class MFX_OT_select_layer(Operator):
    bl_idname = "mfx.select_layer"
    bl_label = "选中图层"
    bl_description = "选中该图层：面板的混合模式/遮罩/强度等参数将实时编辑此层（v0.9.4 PS 化语义）"
    index: IntProperty(default=-1, options={'HIDDEN'})
    def execute(self, context):
        if 0 <= self.index < len(context.scene.mfx_layers):
            context.scene.mfx_layer_index = self.index
            layer = context.scene.mfx_layers[self.index]
            if _layer_edit_target(context) is not None:
                sync_layer_panel(context, layer)
        return {'FINISHED'}


class MFX_OT_move_layer(Operator):
    bl_idname = "mfx.move_layer"
    bl_label = "调整图层顺序"
    bl_description = "在当前材质的图层堆栈中上移或下移一层"
    index: IntProperty(default=-1, options={'HIDDEN'})
    direction: IntProperty(default=1, min=-1, max=1, options={'HIDDEN'})
    def execute(self, context):
        obj = context.object
        scene = context.scene
        layers = scene.mfx_layers
        if not obj or not obj.active_material or not 0 <= self.index < len(layers):
            self.report({'ERROR'}, "请先选择当前材质中的图层")
            return {'CANCELLED'}
        if not layer_belongs_to_material(layers[self.index], obj.active_material, obj):
            self.report({'ERROR'}, "只能调整当前材质的图层")
            return {'CANCELLED'}
        owned = [i for i, layer in enumerate(layers) if layer_belongs_to_material(layer, obj.active_material, obj)]
        rank = owned.index(self.index)
        target_rank = rank + self.direction
        if not 0 <= target_rank < len(owned):
            return {'CANCELLED'}
        target = owned[target_rank]
        layers.move(self.index, target)
        scene.mfx_layer_index = target
        if not replay_layer_chain(context, target, {}):
            layers.move(target, self.index)
            scene.mfx_layer_index = self.index
            self.report({'ERROR'}, "节点链不完整，未调整图层顺序")
            return {'CANCELLED'}
        sync_layer_panel(context, scene.mfx_layers[scene.mfx_layer_index])
        self.report({'INFO'}, "已调整图层顺序")
        return {'FINISHED'}


class MFX_OT_clear_orphan_layers(Operator):
    bl_idname = "mfx.clear_orphan_layers"
    bl_label = "清空残留图层"
    bl_description = "删除所有不属于当前活动材质的图层条目；归属材质仍在时同时摘除其节点链，缺失时仅清记录"
    def execute(self, context):
        obj = context.object
        if not obj or not obj.active_material:
            self.report({'ERROR'}, "请先选择物体")
            return {'CANCELLED'}
        mat = obj.active_material
        layers = context.scene.mfx_layers
        victims = [i for i, layer in enumerate(layers) if layer_is_orphan(layer)]
        if not victims:
            self.report({'INFO'}, "没有残留条目")
            return {'CANCELLED'}
        for i in reversed(victims):
            layer = layers[i]
            owner = resolve_layer_material(layer)
            if owner:
                detach_layer_nodes(owner.node_tree, layer)
        for i in reversed(victims):
            layers.remove(i)
        scene = context.scene
        scene.mfx_layer_index = max(0, min(scene.mfx_layer_index, len(layers) - 1)) if layers else 0
        self.report({'INFO'}, f"已清理 {len(victims)} 条残留条目")
        return {'FINISHED'}


class MFX_OT_apply_preset(Operator):
    bl_idname = "mfx.apply_preset"
    bl_label = "生成并应用材质"
    bl_description = "创建可编辑的程序化材质并应用到当前物体"

    def execute(self, context):
        obj = context.object
        if obj is None:
            self.report({'ERROR'}, "请先选择一个物体")
            return {'CANCELLED'}
        props = context.scene.mfx_props
        if props.preset == "NO_PRESET_MATCH":
            self.report({'ERROR'}, "当前搜索条件没有匹配的材质预设")
            return {'CANCELLED'}
        custom = next((material for material in bpy.data.materials
                       if material.get("mfx_pack_preset_id", "") == props.preset), None)
        if custom:
            material = custom.copy(); material.name = f"MFX · {custom.name}"
            obj.data.materials.append(material)
            obj.active_material_index = len(obj.data.materials) - 1
            remember_preset(context.scene, props.preset, custom.get("mfx_pack_label", custom.name))
            self.report({'INFO'}, f"已应用团队预设：{custom.get('mfx_pack_label', custom.name)}")
            return {'FINISHED'}
        tex = resolve_texture_preset(props.preset)
        if tex:
            if apply_texture_preset(self, context, [obj], tex):
                remember_preset(context.scene, props.preset, tex[0])
                return {'FINISHED'}
            return {'CANCELLED'}
        name, category, base, rough, metal, scale, style = next((x for x in TEMPLATES if x[0] + "_" in props.preset), TEMPLATES[0])
        variant = props.preset.rsplit("_", 1)[-1]
        factor = next((f for label, f in VARIANTS if label == variant), 1.0)
        color = tuple(min(1.0, c * factor) for c in base[:3]) + (1.0,)
        mat = make_material(f"MFX · {name} · {variant}", color, rough, metal, props.bump_strength, scale, style, props.texture_projection)
        if obj.data and hasattr(obj.data, "materials"):
            obj.data.materials.append(mat)
            obj.active_material_index = len(obj.data.materials) - 1
        props.color, props.roughness, props.metallic = color, rough, metal
        remember_preset(context.scene, props.preset, f"{name} · {variant}")
        self.report({'INFO'}, f"已应用：{name} · {variant}")
        return {'FINISHED'}


def finalize_lightning_curve(context, obj, p, seed, local_paths, bounds, label, morph=None, width_scale=1.0):
    """创建闪电曲线对象、发光材质与闪烁/形态动画并登记特效层。morph(time_step) 返回该轮的全新路径。"""
    rng = random.Random(seed * 31 + 7)
    curve = bpy.data.curves.new("MFX 雷电曲线", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = p.lightning_width * width_scale * max(bounds.length, 0.5)
    curve.bevel_resolution = 3
    for path in local_paths:
        spline = curve.splines.new("POLY")
        spline.points.add(len(path) - 1)
        for point, local in zip(spline.points, path):
            world = obj.matrix_world @ local
            point.co = (world.x, world.y, world.z, 1.0)
    fx_obj = bpy.data.objects.new("MFX 雷电特效", curve)
    context.collection.objects.link(fx_obj)
    fx_obj["mfx_width_unit"] = width_scale * max(bounds.length, 0.5)  # v1.0.5：线宽实时调节的比例基准
    fx_obj["mfx_random_seed"] = seed
    fx_obj["mfx_duration_frames"] = p.lightning_duration
    mat = bpy.data.materials.new("MFX 雷电发光")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    created_nodes = []
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    created_nodes.append(out)
    emission = nt.nodes.new("ShaderNodeEmission")
    created_nodes.append(emission)
    emission.inputs["Color"].default_value = p.lightning_color
    emission.inputs["Strength"].default_value = p.lightning_strength
    nt.links.new(emission.outputs["Emission"], out.inputs["Surface"])
    curve.materials.append(mat)
    if p.lightning_animate:
        frame = effect_start_frame(context.scene, p)
        strength = emission.inputs["Strength"]
        strength.keyframe_insert(data_path="default_value", frame=frame)
        elapsed = 0
        while elapsed < p.lightning_duration:
            burst_frame = min(frame + p.lightning_duration - 1, frame + elapsed + rng.randint(2, 6))
            strength.default_value = p.lightning_strength * rng.uniform(0.45, 1.2)
            strength.keyframe_insert(data_path="default_value", frame=burst_frame)
            off_frame = min(frame + p.lightning_duration, burst_frame + rng.randint(1, 3))
            strength.default_value = 0.0
            strength.keyframe_insert(data_path="default_value", frame=off_frame)
            elapsed = off_frame - frame + rng.randint(1, 5)
        strength.default_value = 0.0
        strength.keyframe_insert(data_path="default_value", frame=frame + p.lightning_duration)
        if morph:
            time_step = 0
            while time_step * 2 <= p.lightning_duration:
                target_frame = frame + time_step * 2
                for spline, path in zip(curve.splines, morph(time_step)):
                    for point, local in zip(spline.points, path):
                        world = obj.matrix_world @ local
                        point.co = (world.x, world.y, world.z, 1.0)
                        point.keyframe_insert(data_path="co", frame=target_frame)
                time_step += 1
            action = curve.animation_data.action if curve.animation_data else None
            if action:
                for fcurve in action.fcurves:
                    if fcurve.data_path.startswith("splines["):
                        for keyframe in fcurve.keyframe_points:
                            keyframe.interpolation = 'CONSTANT'
    register_effect_layer(context.scene, label, "LIGHTNING", obj=fx_obj,
                          material=mat, emission=emission, strength=p.lightning_strength,
                          created_nodes=created_nodes)
    bpy.ops.object.select_all(action="DESELECT")
    fx_obj.select_set(True)
    context.view_layer.objects.active = fx_obj
    return fx_obj


class MFX_OT_lightning(Operator):
    bl_idname = "mfx.lightning"
    bl_label = "生成雷电特效"
    bl_description = "生成特斯拉顶点电弧或定向分支闪电，可添加闪烁与形态跳变动画"
    def execute(self, context):
        obj, p = context.object, context.scene.mfx_props
        if not obj:
            self.report({'ERROR'}, "请先选择一个物体")
            return {'CANCELLED'}
        seed = p.lightning_seed or random.SystemRandom().randrange(1, 1000001)
        rng = random.Random(seed)
        bounds = Vector(tuple(max(abs(corner[axis]) for corner in obj.bound_box) for axis in range(3)))
        bounds = Vector(tuple(max(value, 0.05) for value in bounds))
        if p.lightning_mode == "TESLA":
            if obj.type != "MESH":
                self.report({'ERROR'}, "特斯拉电弧需要网格（MESH）物体")
                return {'CANCELLED'}
            mesh = obj.data
            if not len(mesh.vertices):
                self.report({'ERROR'}, "物体没有可用的顶点")
                return {'CANCELLED'}
            arc_total = min(p.lightning_arc_count, len(mesh.vertices))
            arc_specs = []
            for vi in rng.sample(range(len(mesh.vertices)), arc_total):
                vertex = mesh.vertices[vi]
                normal = vertex.normal.normalized() if vertex.normal.length > 0 else Vector((0.0, 0.0, 1.0))
                arc_specs.append((vertex.co.copy(), normal))

            def build_tesla_frame(time_step):
                """每轮为每条弧重新抽取源点姿态与抖动形态；段数固定保证关键帧结构一致。"""
                paths = []
                reach = max(bounds.length, 0.4)
                for i, (base_co, normal) in enumerate(arc_specs):
                    arc_rng = random.Random(seed + i * 977 + time_step * 6151)
                    start = base_co + normal * reach * 0.01
                    length = reach * arc_rng.uniform(0.12, 0.38)
                    direction = (normal + Vector((arc_rng.uniform(-1, 1), arc_rng.uniform(-1, 1),
                                                  arc_rng.uniform(-1, 1))) * p.lightning_jitter * 0.7).normalized()
                    target = start + direction * length
                    if arc_rng.random() < 0.4:
                        other = arc_specs[arc_rng.randrange(len(arc_specs))][0]
                        target = base_co.lerp(other, 0.85) + (other - base_co).normalized() * length * 0.1
                    path = [start.copy()]
                    step_vec = (target - start) / 5.0
                    for s in range(1, 6):
                        point = start + step_vec * s
                        if s < 5:
                            point += Vector((arc_rng.uniform(-1, 1), arc_rng.uniform(-1, 1),
                                             arc_rng.uniform(-1, 1))) * length * p.lightning_jitter * 0.22
                        path.append(point.copy())
                    paths.append(path)
                return paths

            finalize_lightning_curve(context, obj, p, seed, build_tesla_frame(0), bounds,
                                     label="特斯拉电弧 · " + obj.name,
                                     morph=build_tesla_frame, width_scale=0.65)
            self.report({'INFO'}, f"已生成特斯拉电弧：{arc_total} 条顶点弧，每 2 帧跳变落点，种子 {seed}，持续 {p.lightning_duration} 帧")
            return {'FINISHED'}
        segment_count = rng.randint(16, 26)
        local_paths = []
        trunk_dir = _direction_axis_vector(p.surface_effect_direction, p.surface_effect_azimuth, p.surface_effect_elevation)
        sweep_y, sweep_z = _orthonormal_sweep_frame(trunk_dir)
        span_x = _axis_support(bounds, trunk_dir)
        span_y = _axis_support(bounds, sweep_y)
        span_z = _axis_support(bounds, sweep_z)
        trunk = []
        for i in range(segment_count + 1):
            t = i / segment_count
            point = trunk_dir * (-span_x + 2.0 * span_x * t)
            if i not in (0, segment_count):
                point += sweep_y * (-span_y + 2.0 * span_y * t)
                point += sweep_z * (-span_z * 0.5 + span_z * t)
                point += sweep_y * (rng.uniform(-span_y, span_y) * p.lightning_jitter * 0.45)
                point += sweep_z * (rng.uniform(-span_z, span_z) * p.lightning_jitter * 0.45)
            trunk.append(point)
        local_paths.append(trunk)
        path_count = [1]
        def make_branch(origin, target, depth):
            branch_points = [origin.copy()]
            steps = rng.randint(3, 6)
            for step in range(1, steps + 1):
                t = step / steps
                point = origin.lerp(target, t)
                if step < steps:
                    point.x += rng.uniform(-1, 1) * bounds.x * p.lightning_jitter * 0.24
                    point.y += rng.uniform(-1, 1) * bounds.y * p.lightning_jitter * 0.3
                    point.z += rng.uniform(-1, 1) * bounds.z * p.lightning_jitter * 0.3
                branch_points.append(point)
            local_paths.append(branch_points)
            path_count[0] += 1
            if depth > 1 and path_count[0] < 256 and len(branch_points) > 3:
                for _ in range(rng.randint(1, 2)):
                    split = rng.randint(1, len(branch_points) - 2)
                    branch_origin = branch_points[split]
                    child_length = rng.uniform(0.15, 0.42) / max(1.0, depth * 0.55)
                    child_target = branch_origin + Vector((
                        rng.uniform(-0.55, 0.55) * bounds.x * child_length,
                        rng.uniform(-1.0, 1.0) * bounds.y * child_length,
                        rng.uniform(-1.0, 1.0) * bounds.z * child_length,
                    ))
                    make_branch(branch_origin, child_target, depth - 1)

        for _branch_index in range(p.lightning_branches):
            base_index = rng.randint(2, segment_count - 2)
            origin = trunk[base_index].copy()
            side = rng.choice((-1.0, 1.0))
            length = rng.uniform(0.2, 0.68)
            target = origin + Vector((rng.uniform(-0.7, 0.7) * bounds.x * length,
                                      side * bounds.y * length,
                                      rng.uniform(-0.8, 0.8) * bounds.z * length))
            make_branch(origin, target, p.lightning_branch_depth)
        finalize_lightning_curve(context, obj, p, seed, local_paths, bounds,
                                 label="雷电 · " + obj.name)
        self.report({'INFO'}, f"已生成定向闪电：1条主电弧 + {path_count[0] - 1}条随机分支，种子 {seed}，持续 {p.lightning_duration} 帧")
        return {'FINISHED'}


CHANNELS = {
    "basecolor": ("BaseColor", "Base Color", "sRGB"), "albedo": ("BaseColor", "Base Color", "sRGB"),
    "base_color": ("BaseColor", "Base Color", "sRGB"), "bc": ("BaseColor", "Base Color", "sRGB"),
    "diffuse": ("BaseColor", "Base Color", "sRGB"), "roughness": ("Roughness", "Roughness", "Non-Color"),
    "r": ("Roughness", "Roughness", "Non-Color"),
    "metallic": ("Metallic", "Metallic", "Non-Color"), "metalness": ("Metallic", "Metallic", "Non-Color"), "m": ("Metallic", "Metallic", "Non-Color"),
    "normal": ("Normal", "Normal", "Non-Color"), "nrm": ("Normal", "Normal", "Non-Color"), "nor": ("Normal", "Normal", "Non-Color"), "n": ("Normal", "Normal", "Non-Color"),
    "height": ("Height", "Height", "Non-Color"), "h": ("Height", "Height", "Non-Color"),
    "displacement": ("Height", "Height", "Non-Color"), "ao": ("AO", "AO", "Non-Color"),
    "emissive": ("Emissive", "Emissive", "sRGB"), "emission": ("Emissive", "Emissive", "sRGB"), "emit": ("Emissive", "Emissive", "sRGB"),
}


def collect_images(directory, recursive=False):
    files = []
    walker = os.walk(directory) if recursive else [(directory, [], os.listdir(directory))]
    for root, _, names in walker:
        for filename in names:
            if filename.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".bmp")):
                files.append(os.path.join(root, filename))
    return files


def identify_channel(path):
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    tokens = stem.replace("-", "_").replace(".", "_").split("_")
    for token in reversed(tokens):
        if token in CHANNELS:
            return CHANNELS[token]
    for token, info in CHANNELS.items():
        if len(token) > 1 and stem.endswith(token):
            return info
    return None


class MFX_OT_import_pbr(Operator):
    bl_idname = "mfx.import_pbr"
    bl_label = "扫描并连接贴图"
    bl_description = "按文件名通道后缀扫描目录，连接BaseColor、Roughness、Metallic、Normal、Height、AO和Emissive"
    def execute(self, context):
        p, obj = context.scene.mfx_props, context.object
        if not obj:
            self.report({'ERROR'}, "请先选择一个物体")
            return {'CANCELLED'}
        if not p.texture_dir or not os.path.isdir(bpy.path.abspath(p.texture_dir)):
            self.report({'ERROR'}, "请先选择有效的贴图目录")
            return {'CANCELLED'}
        files = collect_images(bpy.path.abspath(p.texture_dir), p.include_subdirs)
        found = {}
        for path in sorted(files):
            channel = identify_channel(path)
            if channel:
                udim_path = re.sub(r"([._-])1\d{3}(?=[._-]|$)", r"\1<UDIM>", path)
                found.setdefault(channel[0], (udim_path, channel))
        if not found:
            self.report({'WARNING'}, "没有识别到贴图；文件名需包含 BaseColor、Roughness、Metallic、Normal、Height、AO 或 Emissive 等后缀")
            return {'CANCELLED'}
        mat = bpy.data.materials.new("MFX · PBR贴图材质"); mat.use_nodes = True
        nt = mat.node_tree; bsdf = nt.nodes.get("Principled BSDF")
        bsdf.location = (360, 80); nt.nodes.get("Material Output").location = (650, 80)
        texcoord = nt.nodes.new("ShaderNodeTexCoord")
        texcoord.label = "自动三向投影坐标"
        texcoord.location = (-920, 0)
        image_nodes = {}
        for index, (key, (path, info)) in enumerate(found.items()):
            image = bpy.data.images.load(path, check_existing=True)
            image.colorspace_settings.name = info[2]
            if "<UDIM>" in path:
                image.source = "TILED"
            node = nt.nodes.new("ShaderNodeTexImage")
            node.label = f"{info[0]} 贴图 · 自动三向投影"
            node.image = image
            node.projection = "BOX"
            node.projection_blend = 0.3
            node.location = (-620, 300 - index * 230)
            nt.links.new(texcoord.outputs["Object"], node.inputs["Vector"])
            image_nodes[key] = node
        if "BaseColor" in image_nodes: nt.links.new(image_nodes["BaseColor"].outputs["Color"], bsdf.inputs["Base Color"])
        if "Roughness" in image_nodes: nt.links.new(image_nodes["Roughness"].outputs["Color"], bsdf.inputs["Roughness"])
        if "Metallic" in image_nodes: nt.links.new(image_nodes["Metallic"].outputs["Color"], bsdf.inputs["Metallic"])
        if "Emissive" in image_nodes:
            sock = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
            if sock: nt.links.new(image_nodes["Emissive"].outputs["Color"], sock)
        if "Normal" in image_nodes:
            normal = nt.nodes.new("ShaderNodeNormalMap"); normal.location = (-80, -300)
            nt.links.new(image_nodes["Normal"].outputs["Color"], normal.inputs["Color"]); nt.links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
        if "Height" in image_nodes:
            bump = nt.nodes.new("ShaderNodeBump"); bump.location = (120, -220)
            nt.links.new(image_nodes["Height"].outputs["Color"], bump.inputs["Height"])
            if "Normal" in image_nodes:
                nt.links.new(normal.outputs["Normal"], bump.inputs["Normal"])
            nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        if "AO" in image_nodes and "BaseColor" in image_nodes:
            multiply = nt.nodes.new("ShaderNodeMixRGB"); multiply.blend_type = "MULTIPLY"; multiply.inputs[0].default_value = 1.0; multiply.location = (100, 350)
            nt.links.new(image_nodes["BaseColor"].outputs["Color"], multiply.inputs[1]); nt.links.new(image_nodes["AO"].outputs["Color"], multiply.inputs[2]); nt.links.new(multiply.outputs["Color"], bsdf.inputs["Base Color"])
        obj.data.materials.append(mat); obj.active_material_index = len(obj.data.materials) - 1
        self.report({'INFO'}, f"已识别并连接 {len(found)} 个贴图通道")
        return {'FINISHED'}


class MFX_OT_apply_selected(Operator):
    bl_idname = "mfx.apply_selected"
    bl_label = "应用到所选物体"
    def execute(self, context):
        p = context.scene.mfx_props
        if p.preset == "NO_PRESET_MATCH":
            self.report({'ERROR'}, "当前搜索条件没有匹配的材质预设")
            return {'CANCELLED'}
        selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not selected:
            self.report({'ERROR'}, "请至少选择一个网格物体")
            return {'CANCELLED'}
        tex = resolve_texture_preset(p.preset)
        if tex:
            return {'FINISHED'} if apply_texture_preset(self, context, selected, tex) else {'CANCELLED'}
        name, _category, base, rough, metal, scale, style = next((x for x in TEMPLATES if x[0] + "_" in p.preset), TEMPLATES[0])
        variant = p.preset.rsplit("_", 1)[-1]
        factor = next((f for label, f in VARIANTS if label == variant), 1.0)
        color = tuple(min(1.0, c * factor) for c in base[:3]) + (1.0,)
        material = make_material(f"MFX · {name} · {variant}", color, rough, metal, p.bump_strength, scale, style, p.texture_projection)
        for obj in selected:
            obj.data.materials.append(material)
            obj.active_material_index = len(obj.data.materials) - 1
        self.report({'INFO'}, f"已将 {name} 应用到 {len(selected)} 个物体")
        return {'FINISHED'}


class MFX_OT_random_assign(Operator):
    bl_idname = "mfx.random_assign"
    bl_label = "随机分配材质"
    bl_description = "从当前材质库为所选网格分别生成并分配随机材质"
    def execute(self, context):
        selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not selected:
            self.report({'ERROR'}, "请至少选择一个网格物体")
            return {'CANCELLED'}
        rng = random.Random(context.scene.frame_current + len(selected))
        p = context.scene.mfx_props
        for obj in selected:
            name, _category, base, rough, metal, scale, style = rng.choice(TEMPLATES)
            variant, factor = rng.choice(VARIANTS)
            color = tuple(min(1.0, c * factor) for c in base[:3]) + (1.0,)
            material = make_material(f"MFX · {name} · {variant}", color, rough, metal, 0.15, scale, style, p.texture_projection)
            obj.data.materials.append(material)
            obj.active_material_index = len(obj.data.materials) - 1
        self.report({'INFO'}, f"已随机分配 {len(selected)} 个材质")
        return {'FINISHED'}


class MFX_OT_apply_collection(Operator):
    bl_idname = "mfx.apply_collection"
    bl_label = "应用到活动集合"
    def execute(self, context):
        obj, p = context.object, context.scene.mfx_props
        if not obj or not obj.users_collection:
            self.report({'ERROR'}, "请选择集合中的物体")
            return {'CANCELLED'}
        collection = obj.users_collection[0]
        targets = [item for item in collection.all_objects if item.type == "MESH"]
        if not targets:
            self.report({'ERROR'}, "活动集合中没有网格物体")
            return {'CANCELLED'}
        if p.preset == "NO_PRESET_MATCH":
            self.report({'ERROR'}, "当前搜索条件没有匹配的材质预设")
            return {'CANCELLED'}
        tex = resolve_texture_preset(p.preset)
        if tex:
            return {'FINISHED'} if apply_texture_preset(self, context, targets, tex) else {'CANCELLED'}
        name, _category, base, rough, metal, scale, style = next((x for x in TEMPLATES if x[0] + "_" in p.preset), TEMPLATES[0])
        variant = p.preset.rsplit("_", 1)[-1]; factor = next((f for label, f in VARIANTS if label == variant), 1.0)
        color = tuple(min(1.0, c * factor) for c in base[:3]) + (1.0,)
        material = make_material(f"MFX · {name} · {variant}", color, rough, metal, p.bump_strength, scale, style, p.texture_projection)
        for target in targets:
            target.data.materials.append(material); target.active_material_index = len(target.data.materials) - 1
        self.report({'INFO'}, f"已应用到集合“{collection.name}”中的 {len(targets)} 个物体")
        return {'FINISHED'}


class MFX_OT_apply_scene(Operator):
    bl_idname = "mfx.apply_scene"
    bl_label = "应用到整个场景"
    def execute(self, context):
        p = context.scene.mfx_props
        targets = [obj for obj in context.scene.objects if obj.type == "MESH"]
        if not targets:
            self.report({'ERROR'}, "场景中没有网格物体")
            return {'CANCELLED'}
        if p.preset == "NO_PRESET_MATCH":
            self.report({'ERROR'}, "当前搜索条件没有匹配的材质预设")
            return {'CANCELLED'}
        tex = resolve_texture_preset(p.preset)
        if tex:
            return {'FINISHED'} if apply_texture_preset(self, context, targets, tex) else {'CANCELLED'}
        name, _category, base, rough, metal, scale, style = next((x for x in TEMPLATES if x[0] + "_" in p.preset), TEMPLATES[0])
        variant = p.preset.rsplit("_", 1)[-1]; factor = next((f for label, f in VARIANTS if label == variant), 1.0)
        color = tuple(min(1.0, c * factor) for c in base[:3]) + (1.0,)
        material = make_material(f"MFX · {name} · {variant}", color, rough, metal, p.bump_strength, scale, style, p.texture_projection)
        for target in targets:
            target.data.materials.append(material); target.active_material_index = len(target.data.materials) - 1
        self.report({'INFO'}, f"已应用到场景中的 {len(targets)} 个物体")
        return {'FINISHED'}


class MFX_OT_dissolve(Operator):
    bl_idname = "mfx.dissolve"
    bl_label = "添加消散动画"
    bl_description = "复制当前材质并添加噪声溶解边缘与关键帧"
    def execute(self, context):
        obj, p = context.object, context.scene.mfx_props
        if not obj or not obj.active_material:
            self.report({'ERROR'}, "请先选择带材质的物体")
            return {'CANCELLED'}
        mat = obj.active_material.copy()
        mat.name = f"{mat.name} · 消散"
        obj.active_material = mat
        nt = mat.node_tree
        existing_nodes = {node.name for node in nt.nodes}
        output = next((node for node in nt.nodes if node.type == "OUTPUT_MATERIAL"), None)
        source_link = next((link for link in nt.links if output and link.to_node == output and link.to_socket.name == "Surface"), None)
        if not source_link:
            self.report({'ERROR'}, "材质节点没有可混合的表面着色器")
            return {'CANCELLED'}
        shader_node, shader_socket = source_link.from_node, source_link.from_socket
        nt.links.remove(source_link)
        texcoord = nt.nodes.new("ShaderNodeTexCoord"); texcoord.label = "消散坐标"; texcoord.location = (-800, -420)
        noise = nt.nodes.new("ShaderNodeTexNoise"); noise.label = "消散边缘噪声"; noise.location = (-580, -420)
        noise.inputs["Scale"].default_value = 8.0
        value = nt.nodes.new("ShaderNodeValue"); value.label = "消散进度（动画）"; value.location = (-580, -620)
        compare = nt.nodes.new("ShaderNodeMath"); compare.operation = "GREATER_THAN"; compare.label = "边缘阈值"; compare.location = (-300, -420)
        transparent = nt.nodes.new("ShaderNodeBsdfTransparent"); transparent.location = (0, -580)
        mix = nt.nodes.new("ShaderNodeMixShader"); mix.label = "消散混合"; mix.location = (220, -120)
        nt.links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
        nt.links.new(noise.outputs["Fac"], compare.inputs[0]); nt.links.new(value.outputs["Value"], compare.inputs[1])
        nt.links.new(compare.outputs["Value"], mix.inputs[0]); nt.links.new(transparent.outputs["BSDF"], mix.inputs[1])
        nt.links.new(shader_socket, mix.inputs[2]); nt.links.new(mix.outputs["Shader"], output.inputs["Surface"])
        value.outputs["Value"].default_value = 0.0
        start = effect_start_frame(context.scene, p)
        value.outputs["Value"].keyframe_insert(data_path="default_value", frame=start)
        value.outputs["Value"].default_value = 1.0
        value.outputs["Value"].keyframe_insert(data_path="default_value", frame=start + p.dissolve_frames)
        try:
            mat.surface_render_method = "DITHERED"
        except (AttributeError, TypeError):
            pass
        register_effect_layer(context.scene, "消散 · " + obj.name, "DISSOLVE", obj=obj,
                              material=mat, root=mix, mask=compare, strength=0.4, control=noise,
                              created_nodes=[node for node in nt.nodes if node.name not in existing_nodes])
        self.report({'INFO'}, f"消散动画已添加：第 {start} 至 {start + p.dissolve_frames} 帧")
        return {'FINISHED'}


class MFX_OT_energy_flow(Operator):
    bl_idname = "mfx.energy_flow"
    bl_label = "添加能量流动"
    bl_description = "在材质表面叠加带关键帧的发光扫描条纹"
    def execute(self, context):
        obj, p = context.object, context.scene.mfx_props
        if not obj or not obj.active_material:
            self.report({'ERROR'}, "请先选择带材质的物体")
            return {'CANCELLED'}
        mat = obj.active_material.copy(); mat.name = f"{mat.name} · 能量流"
        obj.active_material = mat
        nt = mat.node_tree
        existing_nodes = {node.name for node in nt.nodes}
        output = next((node for node in nt.nodes if node.type == "OUTPUT_MATERIAL"), None)
        old_link = next((link for link in nt.links if output and link.to_node == output and link.to_socket.name == "Surface"), None)
        if not old_link:
            self.report({'ERROR'}, "找不到材质表面输出")
            return {'CANCELLED'}
        old_shader, out_socket = old_link.from_socket, old_link.to_socket
        nt.links.remove(old_link)
        texcoord = nt.nodes.new("ShaderNodeTexCoord"); texcoord.label = "能量流坐标"; texcoord.location = (-800, -800)
        mapping = nt.nodes.new("ShaderNodeMapping"); mapping.label = "动画流向"; mapping.location = (-600, -800)
        wave = nt.nodes.new("ShaderNodeTexWave"); wave.label = "能量扫描线"; wave.location = (-360, -800)
        wave.wave_type = "BANDS"; wave.inputs["Scale"].default_value = 14.0
        wave.inputs["Distortion"].default_value = 2.0; wave.inputs["Detail"].default_value = 3.0
        flow_dir = _direction_axis_vector(p.surface_effect_direction, p.surface_effect_azimuth, p.surface_effect_elevation)
        if p.surface_effect_direction == "CUSTOM":
            rotated = _direction_rotation(nt, mapping.outputs["Vector"], p.surface_effect_azimuth, p.surface_effect_elevation, "能量流方向", (-480, -620))
            nt.links.new(rotated, wave.inputs["Vector"])
        else:
            wave.bands_direction = p.surface_effect_direction[-1]
            nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
        threshold = nt.nodes.new("ShaderNodeMath"); threshold.operation = "GREATER_THAN"; threshold.inputs[1].default_value = 0.72; threshold.location = (-100, -800)
        transparent = nt.nodes.new("ShaderNodeBsdfTransparent"); transparent.location = (80, -900)
        emission = nt.nodes.new("ShaderNodeEmission"); emission.location = (80, -700)
        emission.inputs["Color"].default_value = p.lightning_color; emission.inputs["Strength"].default_value = p.lightning_strength
        stripe = nt.nodes.new("ShaderNodeMixShader"); stripe.location = (300, -800)
        add = nt.nodes.new("ShaderNodeAddShader"); add.label = "能量流叠加"; add.location = (500, -200)
        nt.links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
        nt.links.new(wave.outputs["Fac"], threshold.inputs[0])
        nt.links.new(threshold.outputs["Value"], stripe.inputs[0]); nt.links.new(transparent.outputs["BSDF"], stripe.inputs[1])
        nt.links.new(emission.outputs["Emission"], stripe.inputs[2])
        nt.links.new(old_shader, add.inputs[0]); nt.links.new(stripe.outputs["Shader"], add.inputs[1])
        nt.links.new(add.outputs["Shader"], out_socket)
        start = effect_start_frame(context.scene, p)
        location = mapping.inputs["Location"]
        location.default_value = (0, 0, 0); location.keyframe_insert(data_path="default_value", frame=start)
        location.default_value = tuple(4.0 * c for c in flow_dir); location.keyframe_insert(data_path="default_value", frame=start + p.flow_frames)
        register_effect_layer(context.scene, "能量流 · " + obj.name, "ENERGY", obj=obj,
                              material=mat, root=add, emission=emission, strength=p.lightning_strength,
                              created_nodes=[node for node in nt.nodes if node.name not in existing_nodes])
        self.report({'INFO'}, f"能量流已添加并设置动画：{p.flow_frames} 帧")
        return {'FINISHED'}


class MFX_OT_surface_effect(Operator):
    bl_idname = "mfx.surface_effect"
    bl_label = "添加表面特效"
    bl_description = "将程序化动态特效叠加到当前材质；卡通着色仅支持 EEVEE"

    def execute(self, context):
        obj, p = context.object, context.scene.mfx_props
        if not obj or obj.type != "MESH":
            self.report({'ERROR'}, "请先选择带材质的网格物体")
            return {'CANCELLED'}
        if p.surface_effect == "OUTLINE":
            source_material = obj.active_material
            shell = obj.copy(); shell.data = obj.data.copy()
            shell.name = f"MFX 轮廓光 · {obj.name}"
            context.collection.objects.link(shell)
            mat = bpy.data.materials.new(f"MFX 轮廓发光 · {obj.name}"); mat.diffuse_color = p.surface_effect_color; mat.use_nodes = True
            nt = mat.node_tree; nt.nodes.clear()
            output = nt.nodes.new("ShaderNodeOutputMaterial"); emission = nt.nodes.new("ShaderNodeEmission")
            emission.inputs["Color"].default_value = p.surface_effect_color
            emission.inputs["Strength"].default_value = p.surface_effect_strength
            nt.links.new(emission.outputs["Emission"], output.inputs["Surface"])
            shell.data.materials.clear(); shell.data.materials.append(mat)
            solidify = shell.modifiers.new("MFX 反法线描边", "SOLIDIFY")
            solidify.thickness = max(0.001, p.surface_effect_strength * 0.004)
            solidify.use_flip_normals = True
            try: mat.use_backface_culling = True
            except AttributeError: pass
            shell["mfx_effect"] = "OUTLINE"
            shell["mfx_source_object"] = obj.name
            register_effect_layer(context.scene, "轮廓光 · " + obj.name, "OUTLINE", obj=shell,
                                  material=mat, emission=emission, strength=p.surface_effect_strength,
                                  created_nodes=list(nt.nodes))
            self.report({'INFO'}, "已创建独立轮廓光外壳；可在视口中单独开关和调整")
            return {'FINISHED'}

        if not obj.active_material:
            self.report({'ERROR'}, "请先为物体指定材质")
            return {'CANCELLED'}
        effect_label = {
            "HOLOGRAM": "全息扫描", "GLITCH": "故障闪烁", "FIRE": "火焰烟雾",
            "FROST": "冰霜结晶", "CORROSION": "腐蚀扩散", "PULSE": "发光脉冲",
            "TOON": "卡通着色",
        }.get(p.surface_effect, "特效")
        mat = obj.active_material.copy(); mat.name = f"{mat.name} · {effect_label}"
        obj.active_material = mat
        nt = mat.node_tree
        existing_nodes = {node.name for node in nt.nodes}
        output = next((node for node in nt.nodes if node.type == "OUTPUT_MATERIAL"), None)
        old_link = next((link for link in nt.links if output and link.to_node == output and link.to_socket.name == "Surface"), None)
        if not old_link:
            self.report({'ERROR'}, "当前材质没有连接到表面输出")
            return {'CANCELLED'}
        old_shader, surface = old_link.from_socket, old_link.to_socket
        nt.links.remove(old_link)
        start = effect_start_frame(context.scene, p)
        end = start + p.surface_effect_frames
        nodes = nt.nodes

        if p.surface_effect == "TOON":
            if context.scene.render.engine != "BLENDER_EEVEE_NEXT":
                nt.links.new(old_shader, surface)
                self.report({'ERROR'}, "卡通分阶着色需要先将渲染器切换到 EEVEE")
                return {'CANCELLED'}
            diffuse = nodes.new("ShaderNodeBsdfDiffuse"); diffuse.label = "卡通漫反射"
            to_rgb = nodes.new("ShaderNodeShaderToRGB"); to_rgb.label = "EEVEE 光照转颜色"
            ramp = nodes.new("ShaderNodeValToRGB"); ramp.label = "卡通色阶"
            ramp.color_ramp.interpolation = "CONSTANT"
            ramp.color_ramp.elements[0].position = 0.22
            ramp.color_ramp.elements[0].color = (0.035, 0.05, 0.09, 1)
            ramp.color_ramp.elements[1].position = 0.72
            ramp.color_ramp.elements[1].color = tuple(p.surface_effect_color)
            middle = ramp.color_ramp.elements.new(0.48); middle.color = tuple(v * 0.45 for v in p.surface_effect_color[:3]) + (1,)
            emission = nodes.new("ShaderNodeEmission"); emission.label = "卡通着色输出"
            nt.links.new(diffuse.outputs["BSDF"], to_rgb.inputs["Shader"])
            nt.links.new(to_rgb.outputs["Color"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], emission.inputs["Color"])
            blend = nodes.new("ShaderNodeMixShader"); blend.label = "卡通效果层"
            blend.inputs[0].default_value = 1.0
            nt.links.new(old_shader, blend.inputs[1]); nt.links.new(emission.outputs["Emission"], blend.inputs[2])
            nt.links.new(blend.outputs["Shader"], surface)
            register_effect_layer(context.scene, "卡通着色 · " + obj.name, "TOON", obj=obj,
                                  material=mat, root=blend, emission=emission, strength=p.surface_effect_strength,
                                  created_nodes=[node for node in nt.nodes if node.name not in existing_nodes])
            self.report({'INFO'}, "已添加 EEVEE 卡通分阶着色节点")
            return {'FINISHED'}

        texcoord = nodes.new("ShaderNodeTexCoord"); texcoord.label = "特效坐标"
        mapping = nodes.new("ShaderNodeMapping"); mapping.label = "特效动画控制"
        nt.links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
        emission = nodes.new("ShaderNodeEmission"); emission.label = "特效自发光"
        emission.inputs["Color"].default_value = p.surface_effect_color
        emission.inputs["Strength"].default_value = p.surface_effect_strength
        mask = None
        if p.surface_effect == "HOLOGRAM":
            pattern = nodes.new("ShaderNodeTexWave"); pattern.label = "全息扫描条纹"
            pattern.wave_type = "BANDS"
            pattern.inputs["Scale"].default_value = 22; pattern.inputs["Distortion"].default_value = 3
            if p.surface_effect_direction == "CUSTOM":
                rotated = _direction_rotation(nt, mapping.outputs["Vector"], p.surface_effect_azimuth, p.surface_effect_elevation, "全息方向", (-520, 240))
                nt.links.new(rotated, pattern.inputs["Vector"])
                scan_vec = (4.0, 0.0, 0.0)
            else:
                pattern.bands_direction = p.surface_effect_direction[-1]
                nt.links.new(mapping.outputs["Vector"], pattern.inputs["Vector"])
                scan_vec = [0.0, 0.0, 0.0]
                scan_vec["XYZ".index(p.surface_effect_direction[-1])] = (-4.0 if p.surface_effect_direction.startswith("-") else 4.0)
            mask = nodes.new("ShaderNodeMath"); mask.operation = "GREATER_THAN"; mask.inputs[1].default_value = 0.76; mask.label = "扫描线遮罩"
            nt.links.new(pattern.outputs["Fac"], mask.inputs[0])
            mapping.inputs["Location"].default_value = (0, 0, 0)
            mapping.inputs["Location"].keyframe_insert(data_path="default_value", frame=start)
            mapping.inputs["Location"].default_value = tuple(scan_vec)
            mapping.inputs["Location"].keyframe_insert(data_path="default_value", frame=end)
        elif p.surface_effect == "GLITCH":
            channel_nodes = []
            channel_masks = []
            combine = nodes.new("ShaderNodeCombineColor"); combine.mode = "RGB"; combine.label = "RGB 色差分离"
            glitch_dir = _direction_axis_vector(p.surface_effect_direction, p.surface_effect_azimuth, p.surface_effect_elevation)
            offsets = (tuple(-0.035 * c for c in glitch_dir), (0.0, 0.0, 0.0), tuple(0.035 * c for c in glitch_dir))
            channel_sockets = ("Red", "Green", "Blue")
            for index, (offset, channel) in enumerate(zip(offsets, channel_sockets)):
                vector_source = mapping.outputs["Vector"]
                if any(offset):
                    shift = nodes.new("ShaderNodeVectorMath"); shift.operation = "ADD"
                    shift.label = f"色差偏移 {channel}"
                    shift.inputs[1].default_value = offset
                    nt.links.new(vector_source, shift.inputs[0])
                    vector_source = shift.outputs["Vector"]
                pattern = nodes.new("ShaderNodeTexNoise")
                pattern.label = f"故障通道噪声 {channel}"
                pattern.noise_dimensions = "4D"; pattern.inputs["Scale"].default_value = 32
                nt.links.new(vector_source, pattern.inputs["Vector"])
                threshold = nodes.new("ShaderNodeMath"); threshold.operation = "GREATER_THAN"
                threshold.inputs[1].default_value = 0.72; threshold.label = f"通道闪烁遮罩 {channel}"
                nt.links.new(pattern.outputs["Fac"], threshold.inputs[0])
                nt.links.new(threshold.outputs["Value"], combine.inputs[channel])
                pattern.inputs["W"].default_value = 0
                pattern.inputs["W"].keyframe_insert(data_path="default_value", frame=start)
                pattern.inputs["W"].default_value = 18
                pattern.inputs["W"].keyframe_insert(data_path="default_value", frame=end)
                channel_nodes.append(pattern); channel_masks.append(threshold)
            nt.links.new(combine.outputs["Color"], emission.inputs["Color"])
            mask_union = nodes.new("ShaderNodeMath"); mask_union.operation = "MAXIMUM"; mask_union.label = "RGB 故障遮罩"
            nt.links.new(channel_masks[0].outputs["Value"], mask_union.inputs[0])
            nt.links.new(channel_masks[1].outputs["Value"], mask_union.inputs[1])
            mask = nodes.new("ShaderNodeMath"); mask.operation = "MAXIMUM"; mask.label = "RGB 故障总遮罩"
            nt.links.new(mask_union.outputs["Value"], mask.inputs[0])
            nt.links.new(channel_masks[2].outputs["Value"], mask.inputs[1])
        elif p.surface_effect == "FIRE":
            pattern = nodes.new("ShaderNodeTexNoise"); pattern.label = "火焰与烟雾扰动"
            pattern.noise_dimensions = "4D"; pattern.inputs["Scale"].default_value = 5
            pattern.inputs["Detail"].default_value = 4
            nt.links.new(mapping.outputs["Vector"], pattern.inputs["Vector"])
            ramp = nodes.new("ShaderNodeValToRGB"); ramp.label = "火焰温度色带"
            ramp.color_ramp.elements[0].color = (0.025, 0.002, 0.001, 1)
            ramp.color_ramp.elements[1].color = (1.0, 0.7, 0.08, 1)
            hot = ramp.color_ramp.elements.new(0.76); hot.color = (1.0, 0.12, 0.008, 1)
            nt.links.new(pattern.outputs["Fac"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], emission.inputs["Color"])
            mask = nodes.new("ShaderNodeMath"); mask.operation = "GREATER_THAN"; mask.inputs[1].default_value = 0.53; mask.label = "火焰边界"
            nt.links.new(pattern.outputs["Fac"], mask.inputs[0])
            fire_dir = _direction_axis_vector(p.surface_effect_direction, p.surface_effect_azimuth, p.surface_effect_elevation)
            mapping.inputs["Location"].default_value = (0, 0, 0)
            mapping.inputs["Location"].keyframe_insert(data_path="default_value", frame=start)
            mapping.inputs["Location"].default_value = tuple(3.0 * c for c in fire_dir)
            mapping.inputs["Location"].keyframe_insert(data_path="default_value", frame=end)
        elif p.surface_effect == "FROST":
            pattern = nodes.new("ShaderNodeTexVoronoi"); pattern.label = "冰晶边缘"
            pattern.feature = "DISTANCE_TO_EDGE"; pattern.inputs["Scale"].default_value = 9
            nt.links.new(mapping.outputs["Vector"], pattern.inputs["Vector"])
            crystal = nodes.new("ShaderNodeMath"); crystal.operation = "LESS_THAN"; crystal.inputs[1].default_value = 0.055; crystal.label = "结晶纹路遮罩"
            nt.links.new(pattern.outputs["Distance"], crystal.inputs[0])
            if p.surface_effect_direction == "CUSTOM":
                axis = _direction_projection(nt, texcoord.outputs["Generated"],
                                             _direction_vector(p.surface_effect_azimuth, p.surface_effect_elevation),
                                             "冰霜蔓延方向", (-760, 40))
            else:
                direction = nodes.new("ShaderNodeSeparateXYZ"); direction.label = "冰霜蔓延方向"
                nt.links.new(texcoord.outputs["Generated"], direction.inputs["Vector"])
                axis = direction.outputs[p.surface_effect_direction[-1]]
                if p.surface_effect_direction.startswith("-"):
                    reverse = nodes.new("ShaderNodeMath"); reverse.operation = "SUBTRACT"; reverse.inputs[0].default_value = 1.0
                    nt.links.new(axis, reverse.inputs[1]); axis = reverse.outputs["Value"]
            control = nodes.new("ShaderNodeValue"); control.label = "冰霜蔓延进度"
            control.outputs["Value"].default_value = 0.0
            control.outputs["Value"].keyframe_insert(data_path="default_value", frame=start)
            control.outputs["Value"].default_value = 1.0
            control.outputs["Value"].keyframe_insert(data_path="default_value", frame=end)
            front = nodes.new("ShaderNodeMath"); front.operation = "LESS_THAN"; front.label = "定向蔓延前沿"
            nt.links.new(axis, front.inputs[0]); nt.links.new(control.outputs["Value"], front.inputs[1])
            mask = nodes.new("ShaderNodeMath"); mask.operation = "MULTIPLY"; mask.label = "冰霜结晶 × 蔓延范围"
            nt.links.new(crystal.outputs["Value"], mask.inputs[0]); nt.links.new(front.outputs["Value"], mask.inputs[1])
            emission.inputs["Color"].default_value = (0.38, 0.82, 1.0, 1)
        elif p.surface_effect == "CORROSION":
            pattern = nodes.new("ShaderNodeTexNoise"); pattern.label = "腐蚀扩散噪声"
            pattern.inputs["Scale"].default_value = 7; pattern.inputs["Detail"].default_value = 5
            nt.links.new(mapping.outputs["Vector"], pattern.inputs["Vector"])
            ramp = nodes.new("ShaderNodeValToRGB"); ramp.label = "锈蚀氧化色"
            ramp.color_ramp.elements[0].color = (0.055, 0.075, 0.035, 1)
            ramp.color_ramp.elements[1].color = (0.46, 0.13, 0.028, 1)
            oxidized = ramp.color_ramp.elements.new(0.58); oxidized.color = (0.16, 0.23, 0.09, 1)
            nt.links.new(pattern.outputs["Fac"], ramp.inputs["Fac"])
            rust = nodes.new("ShaderNodeBsdfPrincipled"); rust.label = "氧化与锈蚀层"
            rust.inputs["Roughness"].default_value = 0.83
            nt.links.new(ramp.outputs["Color"], rust.inputs["Base Color"])
            corrosion = nodes.new("ShaderNodeMath"); corrosion.operation = "GREATER_THAN"; corrosion.inputs[1].default_value = 0.44; corrosion.label = "腐蚀斑点"
            nt.links.new(pattern.outputs["Fac"], corrosion.inputs[0])
            if p.surface_effect_direction == "CUSTOM":
                axis = _direction_projection(nt, texcoord.outputs["Generated"],
                                             _direction_vector(p.surface_effect_azimuth, p.surface_effect_elevation),
                                             "腐蚀蔓延方向", (-760, 40))
            else:
                direction = nodes.new("ShaderNodeSeparateXYZ"); direction.label = "腐蚀蔓延方向"
                nt.links.new(texcoord.outputs["Generated"], direction.inputs["Vector"])
                axis = direction.outputs[p.surface_effect_direction[-1]]
                if p.surface_effect_direction.startswith("-"):
                    reverse = nodes.new("ShaderNodeMath"); reverse.operation = "SUBTRACT"; reverse.inputs[0].default_value = 1.0
                    nt.links.new(axis, reverse.inputs[1]); axis = reverse.outputs["Value"]
            control = nodes.new("ShaderNodeValue"); control.label = "腐蚀蔓延进度"
            control.outputs["Value"].default_value = 0.0
            control.outputs["Value"].keyframe_insert(data_path="default_value", frame=start)
            control.outputs["Value"].default_value = 1.0
            control.outputs["Value"].keyframe_insert(data_path="default_value", frame=end)
            front = nodes.new("ShaderNodeMath"); front.operation = "LESS_THAN"; front.label = "定向蔓延前沿"
            nt.links.new(axis, front.inputs[0]); nt.links.new(control.outputs["Value"], front.inputs[1])
            mask = nodes.new("ShaderNodeMath"); mask.operation = "MULTIPLY"; mask.label = "腐蚀斑点 × 蔓延范围"
            nt.links.new(corrosion.outputs["Value"], mask.inputs[0]); nt.links.new(front.outputs["Value"], mask.inputs[1])
            mask_strength = nodes.new("ShaderNodeMath"); mask_strength.operation = "MULTIPLY"; mask_strength.label = "腐蚀层强度"
            mask_strength.inputs[1].default_value = p.surface_effect_strength / 4.0
            nt.links.new(mask.outputs["Value"], mask_strength.inputs[0])
            blend = nodes.new("ShaderNodeMixShader"); blend.label = "锈蚀材质混合"
            nt.links.new(mask_strength.outputs["Value"], blend.inputs[0]); nt.links.new(old_shader, blend.inputs[1]); nt.links.new(rust.outputs["BSDF"], blend.inputs[2])
            nt.links.new(blend.outputs["Shader"], surface)
            register_effect_layer(context.scene, "腐蚀扩散 · " + obj.name, "CORROSION", obj=obj,
                                  material=mat, root=blend, mask=mask_strength, strength=p.surface_effect_strength, control=control,
                                  created_nodes=[node for node in nt.nodes if node.name not in existing_nodes])
            self.report({'INFO'}, "已添加程序化锈蚀色层和扩散遮罩")
            return {'FINISHED'}
        elif p.surface_effect == "PULSE":
            emission.inputs["Color"].default_value = p.surface_effect_color
            strength = emission.inputs["Strength"]
            strength.default_value = p.surface_effect_strength * 0.15
            strength.keyframe_insert(data_path="default_value", frame=start)
            strength.default_value = p.surface_effect_strength
            strength.keyframe_insert(data_path="default_value", frame=start + max(1, p.surface_effect_frames // 2))
            strength.default_value = p.surface_effect_strength * 0.15
            strength.keyframe_insert(data_path="default_value", frame=end)
            add = nodes.new("ShaderNodeAddShader"); add.label = "脉冲发光叠加"
            nt.links.new(old_shader, add.inputs[0]); nt.links.new(emission.outputs["Emission"], add.inputs[1]); nt.links.new(add.outputs["Shader"], surface)
            register_effect_layer(context.scene, "发光脉冲 · " + obj.name, "PULSE", obj=obj,
                                  material=mat, root=add, emission=emission, strength=p.surface_effect_strength,
                                  created_nodes=[node for node in nt.nodes if node.name not in existing_nodes])
            self.report({'INFO'}, f"自发光脉冲已添加，动画帧 {start}–{end}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "未知的表面特效类型")
            nt.links.new(old_shader, surface)
            return {'CANCELLED'}

        transparent = nodes.new("ShaderNodeBsdfTransparent"); transparent.label = "特效透明区域"
        mix = nodes.new("ShaderNodeMixShader"); mix.label = "特效纹理混合"
        nt.links.new(mask.outputs["Value"], mix.inputs[0])
        nt.links.new(transparent.outputs["BSDF"], mix.inputs[1])
        nt.links.new(emission.outputs["Emission"], mix.inputs[2])
        add = nodes.new("ShaderNodeAddShader"); add.label = "表面特效叠加"
        nt.links.new(old_shader, add.inputs[0]); nt.links.new(mix.outputs["Shader"], add.inputs[1]); nt.links.new(add.outputs["Shader"], surface)
        try: mat.surface_render_method = "DITHERED"
        except (AttributeError, TypeError): pass
        register_effect_layer(context.scene, effect_label + " · " + obj.name, p.surface_effect,
                              obj=obj, material=mat, root=add, emission=emission,
                              mask=mask, control=control if p.surface_effect == "FROST" else None,
                              strength=p.surface_effect_strength,
                              created_nodes=[node for node in nt.nodes if node.name not in existing_nodes])
        self.report({'INFO'}, f"已添加表面特效，动画帧 {start}–{end}")
        return {'FINISHED'}


class MFX_OT_geometry_effect(Operator):
    bl_idname = "mfx.geometry_effect"
    bl_label = "添加几何节点特效"
    bl_description = "为所选网格创建可编辑的非破坏式 Geometry Nodes 修改器"

    def execute(self, context):
        obj, p = context.object, context.scene.mfx_props
        if not obj or obj.type != "MESH":
            self.report({'ERROR'}, "请先选择网格物体")
            return {'CANCELLED'}
        start = effect_start_frame(context.scene, p)
        end = start + p.geometry_effect_frames
        is_growth = p.geometry_effect == "GROWTH"
        is_particles = p.geometry_effect == "PARTICLES"
        label = "几何生长" if is_growth else ("粒子散布消散" if is_particles else "波浪旗帜")
        axis_key = p.geometry_effect_direction[-1] if p.geometry_effect_direction != "CUSTOM" else "Z"
        axis_index = {"X": 0, "Y": 1, "Z": 2}[axis_key]
        axis_sign = -1.0 if (p.geometry_effect_direction != "CUSTOM" and p.geometry_effect_direction.startswith("-")) else 1.0
        group = bpy.data.node_groups.new(f"MFX · {label} · {obj.name}", "GeometryNodeTree")
        group.interface.new_socket(name="几何", in_out="INPUT", socket_type="NodeSocketGeometry")
        group.interface.new_socket(name="几何", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        effect_socket = group.interface.new_socket(
            name="生长范围" if is_growth else ("粒子密度" if is_particles else "波动幅度"),
            in_out="INPUT", socket_type="NodeSocketFloat")
        effect_socket.default_value = p.geometry_particle_density if is_particles else p.geometry_effect_strength
        effect_socket.min_value = -1000.0 if is_growth else 0.0
        effect_socket.max_value = 100.0 if is_particles else (1000.0 if is_growth else 10.0)
        nodes, links = group.nodes, group.links
        group_input = nodes.new("NodeGroupInput"); group_input.location = (-800, 100)
        group_output = nodes.new("NodeGroupOutput"); group_output.location = (500, 100)
        if is_growth:
            delete = nodes.new("GeometryNodeDeleteGeometry"); delete.label = "按高度生长显露"
            delete.domain = "POINT"; delete.location = (240, 100)
            position = nodes.new("GeometryNodeInputPosition"); position.location = (-800, -140)
            above = nodes.new("ShaderNodeMath"); above.operation = "GREATER_THAN"; above.label = "超过生长前沿"; above.location = (-340, -80)
            links.new(group_input.outputs["几何"], delete.inputs["Geometry"])
            if p.geometry_effect_direction == "CUSTOM":
                growth_dir = _direction_vector(p.geometry_effect_azimuth, p.geometry_effect_elevation)
                axis_output = _direction_projection(group, position.outputs["Position"], growth_dir, "生长方向", (-600, -140))
                axis_values = [vertex.co.dot(growth_dir) for vertex in obj.data.vertices]
            else:
                separate = nodes.new("ShaderNodeSeparateXYZ"); separate.location = (-600, -140)
                links.new(position.outputs["Position"], separate.inputs["Vector"])
                axis_output = separate.outputs[axis_key]
                if axis_sign < 0.0:
                    invert = nodes.new("ShaderNodeMath"); invert.operation = "MULTIPLY"; invert.inputs[1].default_value = -1.0
                    invert.label = "反向生长轴"; invert.location = (-470, -300)
                    links.new(axis_output, invert.inputs[0])
                    axis_output = invert.outputs["Value"]
                axis_values = [vertex.co[axis_index] * axis_sign for vertex in obj.data.vertices]
            links.new(axis_output, above.inputs[0])
            links.new(group_input.outputs[effect_socket.name], above.inputs[1])
            links.new(above.outputs["Value"], delete.inputs["Selection"])
            links.new(delete.outputs["Geometry"], group_output.inputs["几何"])
            axis_min = min(axis_values, default=-1.0)
            axis_max = max(axis_values, default=1.0)
            padding = max((axis_max - axis_min) * 0.01, 0.01)
            growth_start = axis_min - padding
            max_height = axis_min + (axis_max - axis_min + padding * 2.0) * p.geometry_effect_strength
        elif is_particles:
            distribute = nodes.new("GeometryNodeDistributePointsOnFaces"); distribute.label = "表面粒子分布"
            distribute.location = (-240, 100)
            sphere = nodes.new("GeometryNodeMeshIcoSphere"); sphere.label = "粒子实例"
            sphere.inputs["Radius"].default_value = p.geometry_particle_size; sphere.inputs["Subdivisions"].default_value = 1
            sphere.location = (-240, -220)
            instance = nodes.new("GeometryNodeInstanceOnPoints"); instance.label = "实例化粒子"
            instance.location = (120, 100)
            join = nodes.new("GeometryNodeJoinGeometry"); join.label = "保留原模型并叠加粒子"; join.location = (340, 100)
            links.new(group_input.outputs["几何"], distribute.inputs["Mesh"])
            links.new(group_input.outputs[effect_socket.name], distribute.inputs["Density"])
            links.new(distribute.outputs["Points"], instance.inputs["Points"])
            links.new(sphere.outputs["Mesh"], instance.inputs["Instance"])
            links.new(group_input.outputs["几何"], join.inputs["Geometry"])
            links.new(instance.outputs["Instances"], join.inputs["Geometry"])
            links.new(join.outputs["Geometry"], group_output.inputs["几何"])
            max_height = p.geometry_particle_density
        else:
            position = nodes.new("GeometryNodeInputPosition"); position.location = (-800, -180)
            frequency = nodes.new("ShaderNodeMath"); frequency.operation = "MULTIPLY"; frequency.inputs[1].default_value = 3.5; frequency.location = (-420, -180)
            clock = nodes.new("GeometryNodeInputSceneTime"); clock.location = (-620, -430)
            speed = nodes.new("ShaderNodeMath"); speed.operation = "MULTIPLY"; speed.inputs[1].default_value = 1.8; speed.location = (-420, -430)
            phase = nodes.new("ShaderNodeMath"); phase.operation = "ADD"; phase.location = (-220, -180)
            sine = nodes.new("ShaderNodeMath"); sine.operation = "SINE"; sine.location = (-40, -180)
            amplitude = nodes.new("ShaderNodeMath"); amplitude.operation = "MULTIPLY"; amplitude.location = (140, -180)
            set_position = nodes.new("GeometryNodeSetPosition"); set_position.label = "旗帜波动位移"; set_position.location = (340, 100)
            links.new(group_input.outputs["几何"], set_position.inputs["Geometry"])
            links.new(clock.outputs["Seconds"], speed.inputs[0])
            links.new(frequency.outputs["Value"], phase.inputs[0]); links.new(speed.outputs["Value"], phase.inputs[1])
            links.new(phase.outputs["Value"], sine.inputs[0])
            links.new(sine.outputs["Value"], amplitude.inputs[0]); links.new(group_input.outputs[effect_socket.name], amplitude.inputs[1])
            if p.geometry_effect_direction == "CUSTOM":
                wave_dir = _direction_vector(p.geometry_effect_azimuth, p.geometry_effect_elevation)
                spread = wave_dir.cross(Vector((0.0, 0.0, 1.0)))
                if spread.length_squared < 1.0e-8:
                    spread = Vector((1.0, 0.0, 0.0))
                spread.normalize()
                links.new(_direction_projection(group, position.outputs["Position"], spread, "波浪传播", (-620, -180)), frequency.inputs[0])
                scale_vec = nodes.new("ShaderNodeVectorMath"); scale_vec.operation = "MULTIPLY"; scale_vec.label = "波动方向缩放"
                scale_vec.location = (340, -180)
                links.new(amplitude.outputs["Value"], scale_vec.inputs[0])
                scale_vec.inputs[1].default_value = wave_dir
                links.new(scale_vec.outputs["Vector"], set_position.inputs["Offset"])
            else:
                separate = nodes.new("ShaderNodeSeparateXYZ"); separate.location = (-620, -180)
                offset = nodes.new("ShaderNodeCombineXYZ"); offset.location = (340, -180)
                links.new(position.outputs["Position"], separate.inputs["Vector"])
                phase_axis = next(axis for axis in ("X", "Y", "Z") if axis != axis_key)
                links.new(separate.outputs[phase_axis], frequency.inputs[0])
                links.new(amplitude.outputs["Value"], offset.inputs[axis_key])
                links.new(offset.outputs["Vector"], set_position.inputs["Offset"])
            links.new(set_position.outputs["Geometry"], group_output.inputs["几何"])
            max_height = p.geometry_effect_strength
        modifier = obj.modifiers.new(f"MFX · {label}", "NODES")
        modifier.node_group = group
        modifier[effect_socket.identifier] = growth_start if is_growth else (p.geometry_particle_density if is_particles else p.geometry_effect_strength)
        if is_growth or is_particles:
            modifier.keyframe_insert(data_path=f'["{effect_socket.identifier}"]', frame=start)
            modifier[effect_socket.identifier] = 0.0 if is_particles else max_height
            modifier.keyframe_insert(data_path=f'["{effect_socket.identifier}"]', frame=end)
        register_effect_layer(context.scene, label + " · " + obj.name, "PARTICLES" if is_particles else "GEOMETRY", obj=obj,
                              strength=p.geometry_particle_density if is_particles else (max_height if is_growth else p.geometry_effect_strength),
                              modifier=modifier, modifier_input=effect_socket.identifier)
        self.report({'INFO'}, f"已添加非破坏式{label} Geometry Nodes 修改器")
        return {'FINISHED'}


class MFX_OT_fracture_reassemble(Operator):
    bl_idname = "mfx.fracture_reassemble"
    bl_label = "创建碎裂与重组动画"
    bl_description = "使用 Voronoi 半空间切割生成带封口的真实碎片网格，并设置飞散和重组关键帧"
    def execute(self, context):
        source, p = context.object, context.scene.mfx_props
        if not source or source.type != "MESH" or not source.data.polygons:
            self.report({'ERROR'}, "请选择包含面的网格物体")
            return {'CANCELLED'}
        polygons = list(source.data.polygons)
        requested = min(p.fragment_count, len(polygons))
        if requested < 2:
            self.report({'ERROR'}, "网格面数过少，无法生成碎片")
            return {'CANCELLED'}
        rng = random.Random(p.fragment_seed or (context.scene.frame_current + len(polygons)))
        source_matrix = source.matrix_world.copy()
        local_centers = [sum((source.data.vertices[index].co for index in poly.vertices), Vector((0.0, 0.0, 0.0))) / len(poly.vertices) for poly in polygons]
        seeds = [local_centers[index].copy() for index in rng.sample(range(len(local_centers)), requested)]
        collection = bpy.data.collections.new(f"MFX 碎片 · {source.name}")
        context.scene.collection.children.link(collection)
        start = effect_start_frame(context.scene, p)
        created = 0
        for chunk_index, seed in enumerate(seeds):
            bm = bmesh.new()
            bm.from_mesh(source.data)
            for other in seeds:
                if other == seed or not bm.faces:
                    continue
                normal = other - seed
                if normal.length_squared < 1.0e-10:
                    continue
                normal.normalize()
                plane_co = (seed + other) * 0.5
                result = bmesh.ops.bisect_plane(
                    bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                    dist=1.0e-6, plane_co=plane_co, plane_no=normal,
                    clear_inner=False, clear_outer=True)
                cut_edges = [edge for edge in result.get("geom_cut", ())
                             if isinstance(edge, bmesh.types.BMEdge) and edge.is_valid]
                if cut_edges:
                    bmesh.ops.holes_fill(bm, edges=cut_edges, sides=0)
            if not bm.faces or len(bm.verts) < 4:
                bm.free()
                continue
            world_coords = [source_matrix @ vertex.co for vertex in bm.verts]
            center = sum(world_coords, Vector((0.0, 0.0, 0.0))) / len(world_coords)
            for vertex, world_co in zip(bm.verts, world_coords):
                vertex.co = world_co - center
            bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
            mesh = bpy.data.meshes.new(f"MFX 碎片网格 {chunk_index:03d}")
            bm.to_mesh(mesh); bm.free(); mesh.update()
            for material in source.data.materials:
                mesh.materials.append(material)
            shard = bpy.data.objects.new(f"MFX 碎片 {chunk_index:03d}", mesh)
            collection.objects.link(shard)
            shard.location = center
            shard["mfx_fragment_source"] = source.name
            shard["mfx_fragment_index"] = chunk_index
            shard.keyframe_insert(data_path="location", frame=start)
            shard.keyframe_insert(data_path="rotation_euler", frame=start)
            direction = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
            if direction.length_squared < 0.0001:
                direction = Vector((0, 0, 1))
            direction.normalize()
            shard.location = center + direction * p.fragment_distance
            shard.rotation_euler = (rng.uniform(-2.5, 2.5), rng.uniform(-2.5, 2.5), rng.uniform(-2.5, 2.5))
            shard.keyframe_insert(data_path="location", frame=start + p.fragment_frames)
            shard.keyframe_insert(data_path="rotation_euler", frame=start + p.fragment_frames)
            shard.location = center
            shard.rotation_euler = (0, 0, 0)
            shard.keyframe_insert(data_path="location", frame=start + p.fragment_frames * 2)
            shard.keyframe_insert(data_path="rotation_euler", frame=start + p.fragment_frames * 2)
            created += 1
        source.hide_render = True
        source.hide_set(True)
        source["mfx_hidden_for_fragments"] = True
        register_effect_layer(context.scene, "碎裂重组 · " + source.name, "FRACTURE",
                              obj=source, collection=collection, strength=1.0)
        self.report({'INFO'}, f"已用 Voronoi 切割生成 {created} 个封口碎片；动画会飞散并在后续帧重组")
        return {'FINISHED'}


class MFX_OT_restore_fractured(Operator):
    bl_idname = "mfx.restore_fractured"
    bl_label = "恢复原物体"
    def execute(self, context):
        sources = [obj for obj in context.scene.objects if obj.get("mfx_hidden_for_fragments")]
        if not sources:
            self.report({'WARNING'}, "场景中没有隐藏的碎裂源物体")
            return {'CANCELLED'}
        source_names = {obj.name for obj in sources}
        for obj in sources:
            obj.hide_render = False; obj.hide_set(False); del obj["mfx_hidden_for_fragments"]
        for obj in list(context.scene.objects):
            if obj.get("mfx_fragment_source") in source_names:
                bpy.data.objects.remove(obj, do_unlink=True)
        for collection in list(bpy.data.collections):
            if collection.name.startswith("MFX 碎片 · ") and not collection.objects and not collection.children:
                bpy.data.collections.remove(collection)
        layers = context.scene.mfx_effect_layers
        for index in reversed(range(len(layers))):
            if layers[index].effect_type == "FRACTURE":
                layers.remove(index)
        self.report({'INFO'}, "已恢复源物体并移除碎片")
        return {'FINISHED'}


class MFX_OT_delete_effect_layer(Operator):
    bl_idname = "mfx.delete_effect_layer"
    bl_label = "删除特效层"
    bl_description = "删除堆栈中的效果，并清理对应节点、修改器或特效对象"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()

    def execute(self, context):
        layers = context.scene.mfx_effect_layers
        if not 0 <= self.index < len(layers):
            return {'CANCELLED'}
        layer = layers[self.index]
        layer_id = layer.layer_id
        effect_type = layer.effect_type
        root_name = layer.root_node
        object_name = layer.object_name
        collection_name = layer.collection_name
        modifier_name = layer.modifier_name
        removed_name = layer.name

        for material in list(bpy.data.materials):
            if not material.use_nodes:
                continue
            nt = material.node_tree
            tagged_names = [node.name for node in nt.nodes if node.get("mfx_effect_layer_id") == layer_id]
            root = nt.nodes.get(root_name)
            legacy_root = not layer_id and material.name == layer.material_name
            if root and (root.get("mfx_effect_layer_id") == layer_id or legacy_root):
                if legacy_root and root.name not in tagged_names:
                    tagged_names.append(root.name)
                if root.type == "ADD_SHADER":
                    base_index = 0
                elif effect_type == "DISSOLVE":
                    base_index = 2
                else:
                    base_index = 1
                base_link = next((link for link in nt.links
                                  if link.to_node == root and link.to_socket == root.inputs[base_index]), None)
                destinations = [(link.to_node, link.to_socket) for link in list(root.outputs[0].links)]
                for link in list(root.outputs[0].links):
                    nt.links.remove(link)
                if base_link:
                    base_socket = base_link.from_socket
                    for target, socket in destinations:
                        nt.links.new(base_socket, socket)
            for node_name in tagged_names:
                node = nt.nodes.get(node_name)
                if node and node.get("mfx_effect_layer_id") == layer_id:
                    nt.nodes.remove(node)

        obj = bpy.data.objects.get(object_name) if object_name else None
        if effect_type in {"LIGHTNING", "OUTLINE"} and obj and (obj.get("mfx_effect_layer_id") == layer_id or not layer_id):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data and data.users == 0:
                if data.bl_rna.identifier == "Curve": bpy.data.curves.remove(data)
                elif data.bl_rna.identifier == "Mesh": bpy.data.meshes.remove(data)
        elif effect_type in {"GEOMETRY", "PARTICLES"} and obj:
            modifier = obj.modifiers.get(modifier_name) if modifier_name else None
            if modifier:
                group = modifier.node_group if modifier.type == "NODES" else None
                obj.modifiers.remove(modifier)
                action = obj.animation_data.action if obj.animation_data else None
                if action:
                    for curve in list(action.fcurves):
                        if modifier_name in curve.data_path:
                            action.fcurves.remove(curve)
                if group and group.users == 0:
                    bpy.data.node_groups.remove(group)
        elif effect_type == "FRACTURE":
            collection = bpy.data.collections.get(collection_name) if collection_name else None
            if collection:
                for fragment in list(collection.objects):
                    if fragment.get("mfx_effect_layer_id") == layer_id or not layer_id:
                        bpy.data.objects.remove(fragment, do_unlink=True)
                bpy.data.collections.remove(collection)
            if obj and obj.get("mfx_hidden_for_fragments"):
                obj.hide_render = False; obj.hide_set(False)
                del obj["mfx_hidden_for_fragments"]
        elif effect_type in VOLUME_EFFECT_TYPES:
            # 规格定稿 §3：移除=删域对象与同层附属对象（灯/粒子原型）+ 材质随 users==0 自动清；缓存目录保留用户手动清
            for candidate in list(bpy.data.objects):
                if candidate.get("mfx_effect_layer_id") == layer_id:
                    bpy.data.objects.remove(candidate, do_unlink=True)
        obj = bpy.data.objects.get(object_name) if object_name else None
        if obj and obj.get("mfx_effect_layer_id") == layer_id:
            del obj["mfx_effect_layer_id"]

        for material in list(bpy.data.materials):
            material_ids = set(filter(None, material.get("mfx_effect_layer_ids", "").split(",")))
            if material.users == 0 and layer_id and layer_id in material_ids:
                bpy.data.materials.remove(material)

        layers.remove(self.index)
        self.report({'INFO'}, f"已删除特效层：{removed_name}")
        return {'FINISHED'}


# ── 体积特效板块（规格定稿 §2 + 管理员 16:12 扩项，全栈实现）──────────────
VOLUME_EFFECT_TYPES = {"VOLUME_FOG", "VOLUME_BEAMS", "VOLUME_SMOKE", "VOLUME_FIRE", "VOLUME_LIQUID", "RAIN", "SNOW"}


# [体积特效] 教学补注：本板块统一走「域对象(Domain) + 修改器」路线——先建带
# 边界补偿的域物体（_volume_domain_object，pad 参数防流体穿帮），效果由修改器/
# 流体设置驱动，登记收口在 _volume_finish_register；实时性由 update_*_live 改
# 修改器输入实现；分辨率/时长类参数改动 → 失效缓存 + 0.8s 去抖 timer 重烘焙
# （_volume_bake_timer / _VOLUME_BAKE_PENDING），烘焙进度经 _volume_bake_state_text
# 画进面板，全程不阻塞 UI 线程。

def volume_direction_vector(p):
    """DX-5.2 方向解析：NATURAL=原生(None)；六轴=单位向量；CUSTOM=沿用 v1.0.1 既有换算约定
    （方位角自 X 轴向 Y、俯仰自水平面起算，与 _direction_vector 同源，CUSTOM(45,30)→(0.6124,0.6124,0.5)）。"""
    if p.volume_direction == "NATURAL":
        return None
    if p.volume_direction == "CUSTOM":
        return _direction_vector(p.volume_azimuth, p.volume_elevation)
    d = p.volume_direction
    return Vector((float(d == "+X") - float(d == "-X"),
                   float(d == "+Y") - float(d == "-Y"),
                   float(d == "+Z") - float(d == "-Z")))


def volume_cache_dir(kind, obj_name):
    """规格 §2 缓存目录约定 //mfx_cache/<kind>_<物体名>；未保存文件回落 Blender 临时目录。"""
    blend_dir = bpy.path.abspath("//") if bpy.data.filepath else ""
    root = os.path.join(blend_dir, "mfx_cache") if blend_dir else os.path.join(bpy.app.tempdir, "mfx_cache")
    path = os.path.join(root, f"{kind}_{obj_name}")
    os.makedirs(path, exist_ok=True)
    return path


def volume_bounds(obj):
    """物体世界包围盒 (min, max, size)。"""
    coords = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mn = Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
    mx = Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
    return mn, mx, mx - mn


def _volume_link_object(context, obj, new_obj):
    (obj.users_collection or [context.collection])[0].objects.link(new_obj)
    new_obj["mfx_effect_layer_id"] = "pending"


def _volume_domain_object(context, source, label, pad=1.6):
    """包裹源物体包围盒的体积域立方体（放大 pad 倍，居中对齐）。"""
    mn, mx, size = volume_bounds(source)
    domain = bpy.data.objects.new(f"MFX {label}域 · {source.name}",
                                  bpy.data.meshes.new(f"MFX {label}域 · {source.name}"))
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(domain.data)
    bm.free()
    domain.scale = Vector((max(size.x * pad, 0.2), max(size.y * pad, 0.2), max(size.z * pad, 0.2)))
    domain.location = (mn + mx) / 2
    _volume_link_object(context, source, domain)
    return domain


def _volume_finish_register(context, layer_name, effect_type, obj, material, modifier=None, strength=4.0):
    obj["mfx_effect_layer_id"] = "pending"  # 由 register_effect_layer 统一落 layer_id
    layer = register_effect_layer(context.scene, layer_name, effect_type, obj=obj, material=material,
                                  modifier=modifier, strength=strength)
    obj["mfx_effect_layer_id"] = layer.layer_id
    return layer


class MFX_OT_volume_fog(Operator):
    bl_idname = "mfx.volume_fog"
    bl_label = "添加体积雾"
    bl_description = "包裹选中物体生成程序化体积雾（免烘焙，默认带流动动画）"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH"

    def execute(self, context):
        obj = context.object
        p = context.scene.mfx_props
        domain = _volume_domain_object(context, obj, "雾")
        mat = bpy.data.materials.new(f"MFX · 体积雾 · {obj.name}")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (500, 0)
        vol = nt.nodes.new("ShaderNodeVolumePrincipled"); vol.location = (280, 0)
        vol.inputs["Color"].default_value = (p.fog_color[0], p.fog_color[1], p.fog_color[2], 1.0)
        noise = nt.nodes.new("ShaderNodeTexNoise"); noise.name = "MFX 雾噪声"; noise.label = "MFX 雾噪声"
        noise.location = (-260, 0)
        noise.inputs["Scale"].default_value = p.fog_noise_scale
        noise.inputs["Detail"].default_value = 4.0
        ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.location = (40, 0)
        ramp.color_ramp.elements[0].position = 0.35
        density = nt.nodes.new("ShaderNodeMath"); density.operation = "MULTIPLY"; density.location = (140, -160)
        density.label = "雾密度调制"
        density.inputs[1].default_value = p.fog_density
        tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-480, 0)
        mapping = nt.nodes.new("ShaderNodeMapping"); mapping.name = "MFX 雾流向"; mapping.label = "MFX 雾流向"
        mapping.location = (-380, 0)
        nt.links.new(tc.outputs["Object"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], density.inputs[0])
        nt.links.new(density.outputs["Value"], vol.inputs["Density"])
        nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
        domain.data.materials.append(mat)
        if p.fog_animate:
            # 4.2 TexNoise 无 W 输入：流动动画=Mapping 采样位置位移（默认 Z 轴上飘，DX-5.2 位移轴随方向）
            flow_vec = (volume_direction_vector(p) or Vector((0.0, 0.0, 1.0))) * 2.0
            loc_in = mapping.inputs["Location"]
            loc_in.default_value = Vector((0.0, 0.0, 0.0))
            loc_in.keyframe_insert("default_value", frame=1)
            loc_in.default_value = flow_vec
            loc_in.keyframe_insert("default_value", frame=max(p.volume_frames, 2))
        _volume_finish_register(context, f"体积雾 · {obj.name}", "VOLUME_FOG", domain, mat, strength=p.fog_density)
        self.report({'INFO'}, f"已添加体积雾：{domain.name}")
        return {'FINISHED'}


class MFX_OT_rain_snow(Operator):
    bl_idname = "mfx.rain_snow"
    bl_label = "添加雨 / 雪粒子"
    bl_description = "按选中物体尺寸生成覆盖性天气粒子（雨丝 / 雪花，Blender 原生粒子系统）"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH"

    def execute(self, context):
        obj = context.object
        p = context.scene.mfx_props
        is_rain = p.rain_snow_mode == "RAIN"
        mn, mx, size = volume_bounds(obj)
        label = "雨" if is_rain else "雪"
        emitter_mesh = bpy.data.meshes.new(f"MFX {label}发射器 · {obj.name}")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(emitter_mesh)
        bm.free()
        emitter = bpy.data.objects.new(f"MFX {label}发射器 · {obj.name}", emitter_mesh)
        span = max(max(size.x, size.y) * p.rain_snow_area, 1.0)
        emitter.scale = Vector((span, span, 0.05))
        emitter["mfx_span_unit"] = max(size.x, size.y)  # v1.0.5：覆盖范围实时调节的比例基准
        emitter.location = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mx.z + max(size.z, 1.0) * 0.8))
        _volume_link_object(context, obj, emitter)
        direction = volume_direction_vector(p)
        if direction is not None:  # DX-5.2：倾斜向量（雨丝风偏），±Z=垂直下落原生
            emitter.rotation_euler = Vector((direction.y * math.radians(12.0), -direction.x * math.radians(12.0), 0.0))
        particle = emitter.modifiers.new(f"MFX {label}", 'PARTICLE_SYSTEM')
        settings = particle.particle_system.settings
        settings.count = p.rain_snow_count
        settings.frame_start = 1
        settings.frame_end = max(p.volume_frames, 2)
        settings.lifetime = settings.frame_end
        settings.particle_size = 0.02 if is_rain else 0.035
        settings.normal_factor = -1.0
        settings.physics_type = 'NEWTON'
        settings.render_type = 'OBJECT'
        if is_rain:
            settings.effector_weights.gravity = 1.4
            settings.mass = 1.0
        else:
            settings.effector_weights.gravity = 0.35
            settings.factor_random = 0.6   # 飘落扰动（4.2 实证属性名：factor_random=初速随机 + damping 空气阻尼）
            settings.damping = 0.7
        drop = bpy.data.objects.new(f"MFX {label}粒子原型", bpy.data.meshes.new(f"MFX {label}粒子原型"))
        pbm = bmesh.new()
        if is_rain:
            bmesh.ops.create_cube(pbm, size=1.0)
            drop.scale = Vector((0.012, 0.012, 0.09))
        else:
            bmesh.ops.create_icosphere(pbm, subdivisions=1, radius=0.02)
        pbm.to_mesh(drop.data)
        pbm.free()
        (obj.users_collection or [context.collection])[0].objects.link(drop)
        settings.instance_object = drop
        mat = bpy.data.materials.new(f"MFX · {label} · {obj.name}")
        mat.use_nodes = True
        bsdf = next(node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        set_input(bsdf, "Base Color", (0.55, 0.7, 0.9, 1.0) if is_rain else (0.92, 0.94, 1.0, 1.0))
        set_input(bsdf, "Roughness", 0.15 if is_rain else 0.7)
        set_input(bsdf, "Metallic", 0.3 if is_rain else 0.0)
        drop.data.materials.append(mat)
        layer = _volume_finish_register(context, f"{label} · {obj.name}", "RAIN" if is_rain else "SNOW", emitter, mat)
        drop["mfx_effect_layer_id"] = layer.layer_id  # 粒子原型随层删除
        self.report({'INFO'}, f"已添加{label}粒子：{emitter.name}（播放动画查看效果）")
        return {'FINISHED'}


def _volume_quick_base(context, kind):
    """quick_smoke / quick_liquid 桥接；返回 (used_quick, domain, flow)。
    RNA 实证前置（规格 §5 风险预案）；无头环境 Mantaflow API 不全（LevelsetGrid.setConst
    缺失实测）直接走手动建域路径；GUI 真机 4.2 完整仍走 quick 桥接。"""
    if bpy.app.background:
        return False, None, None
    obj = context.object
    before = set(bpy.data.objects)
    op = getattr(bpy.ops.object, f"quick_{kind}", None)
    try:
        if op is not None and op.poll() if hasattr(op, "poll") else op is not None:
            op({'object': obj, 'active_object': obj, 'selected_objects': [obj],
                'selected_editable_objects': [obj], 'scene': context.scene,
                'view_layer': context.view_layer, 'collection': context.collection,
                'active_collection': context.collection}, 'EXEC_DEFAULT')
    except Exception:
        return False, None, None
    domain = flow = None
    for created in set(bpy.data.objects) - before:
        for modifier in created.modifiers:
            if modifier.type == 'FLUID' and modifier.fluid_type == 'DOMAIN':
                domain = created
            elif modifier.type == 'FLUID' and modifier.fluid_type == 'FLOW':
                flow = created
    return domain is not None, domain, flow


def _volume_manual_base(context, kind):
    """手动建域兜底路径（quick_* 不可用 / RNA 缺失）：域 + 流速体 + 关键参数。"""
    obj = context.object
    kind_label = {"smoke": "烟雾", "fire": "火焰", "liquid": "液体"}[kind]
    domain = _volume_domain_object(context, obj, kind_label)
    modifier = domain.modifiers.new("MFX 体积模拟", 'FLUID')
    modifier.fluid_type = 'DOMAIN'  # 4.2 FluidModifier 契约：fluid_type 先行，domain_settings 才可用
    modifier.domain_settings.domain_type = 'GAS' if kind in ("smoke", "fire") else 'LIQUID'
    flow_obj = bpy.data.objects.new(f"MFX {kind_label}流速体 · {obj.name}", obj.data.copy())
    flow_obj.location = obj.location
    flow_obj.scale = Vector((0.9, 0.9, 0.9))
    flow_modifier = flow_obj.modifiers.new("MFX 流速体", 'FLUID')
    flow_modifier.fluid_type = 'FLOW'
    flow_modifier.flow_settings.flow_type = 'FIRE' if kind == "fire" else ('LIQUID' if kind == "liquid" else 'SMOKE')
    _volume_link_object(context, obj, flow_obj)
    return domain, flow_obj


def _volume_apply_common(domain, kind, p):
    """域参数统一写入（分辨率 / 时长 / 缓存目录），供真模拟三算子复用。"""
    settings = domain.modifiers[0].domain_settings if domain.modifiers else None
    if settings is None:
        return None
    settings.resolution_max = int(p.volume_resolution)  # 4.2 实证：resolution_max（标量上限，域自动立方）
    try:
        settings.domain_resolution = (int(p.volume_resolution),) * 3
    except Exception:
        pass
    settings.cache_frame_end = max(p.volume_frames, 2)
    try:
        settings.cache_directory = volume_cache_dir(kind, domain.name.split(" · ")[-1])
    except Exception:
        pass
    return settings


class MFX_OT_volume_smoke(Operator):
    bl_idname = "mfx.volume_smoke"
    bl_label = "烟雾模拟"
    bl_description = "Mantaflow 真实烟雾模拟（动态升腾烟团，需播放/烘焙后呈现）"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH"

    def execute(self, context):
        obj = context.object
        p = context.scene.mfx_props
        try:
            used_quick, domain, flow = _volume_quick_base(context, "smoke")
            if not used_quick:
                domain, flow = _volume_manual_base(context, "smoke")
            settings = _volume_apply_common(domain, "smoke", p)
        except Exception as exc:
            self.report({'ERROR'}, f"当前环境 Mantaflow 初始化不可用（{exc}）；请在 GUI 真机运行，或改用程序化体积雾")
            return {'CANCELLED'}
        if settings is None:
            self.report({'ERROR'}, "烟雾域创建失败")
            return {'CANCELLED'}
        if flow:
            direction = volume_direction_vector(p)  # DX-5.2：初速度分量（±Z=原生浮力主导，风偏写水平分量）
            if direction is not None:
                try:
                    flow.modifiers[0].flow_settings.use_velocity = True
                    flow.modifiers[0].flow_settings.velocity = direction
                except Exception:
                    pass
            try:
                flow.modifiers[0].flow_settings.color = (p.smoke_color[0], p.smoke_color[1], p.smoke_color[2], 1.0)
            except Exception:
                pass
        for slot in list(domain.material_slots):
            mat = slot.material
            if mat and mat.use_nodes:
                vol = next((n for n in mat.node_tree.nodes if n.type == "PRINCIPLED_VOLUME"), None)
                if vol:
                    vol.inputs["Color"].default_value = (p.smoke_color[0], p.smoke_color[1], p.smoke_color[2], 1.0)
                    vol.inputs["Density"].default_value = p.smoke_density
        if not domain.material_slots:
            mat = bpy.data.materials.new(f"MFX · 烟雾 · {obj.name}")
            mat.use_nodes = True
            vol = mat.node_tree.nodes.new("ShaderNodeVolumePrincipled")
            out = mat.node_tree.nodes["Material Output"]
            mat.node_tree.links.new(vol.outputs["Volume"], out.inputs["Volume"])
            vol.inputs["Color"].default_value = (p.smoke_color[0], p.smoke_color[1], p.smoke_color[2], 1.0)
            vol.inputs["Density"].default_value = p.smoke_density
            domain.data.materials.append(mat)
        _volume_finish_register(context, f"烟雾 · {obj.name}", "VOLUME_SMOKE", domain, None,
                                modifier=domain.modifiers[0] if domain.modifiers else None, strength=p.smoke_density)
        self.report({'INFO'}, f"烟雾模拟就绪：{domain.name}（播放或烘焙查看升腾）")
        return {'FINISHED'}


class MFX_OT_volume_fire(Operator):
    bl_idname = "mfx.volume_fire"
    bl_label = "火焰模拟"
    bl_description = "Mantaflow 真实火焰模拟（燃料与色温可调，不动浮力项保持自然升腾）"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH"

    def execute(self, context):
        obj = context.object
        p = context.scene.mfx_props
        try:
            used_quick, domain, flow = _volume_quick_base(context, "smoke")  # 火焰复用 quick_smoke 底座（规格 §2.2）
            if not used_quick:
                domain, flow = _volume_manual_base(context, "fire")
            settings = _volume_apply_common(domain, "fire", p)
        except Exception as exc:
            self.report({'ERROR'}, f"当前环境 Mantaflow 初始化不可用（{exc}）；请在 GUI 真机运行")
            return {'CANCELLED'}
        if settings is None:
            self.report({'ERROR'}, "火焰域创建失败")
            return {'CANCELLED'}
        if flow:  # 4.2 火焰语义由 flow_type='FIRE' 表达（域侧无 use_fire 属性，实测）
            try:
                flow.modifiers[0].flow_settings.flow_type = 'FIRE'
            except Exception:
                pass
            direction = volume_direction_vector(p)  # DX-5.2：风偏初速度；浮力项不动（5.5 白名单）
            if direction is not None:
                try:
                    flow.modifiers[0].flow_settings.use_velocity = True
                    flow.modifiers[0].flow_settings.velocity = direction
                except Exception:
                    pass
            try:
                flow.modifiers[0].flow_settings.fuel_amount = p.fire_intensity
            except Exception:
                pass
        flame_colors = {"ORANGE": (1.0, 0.28, 0.02, 1.0), "BLUE": (0.12, 0.45, 1.0, 1.0)}
        for slot in list(domain.material_slots):
            mat = slot.material
            if mat and mat.use_nodes:
                for node in mat.node_tree.nodes:
                    if node.type == "VALTORGB" and "Fire" in (node.label or ""):
                        node.color_ramp.elements[-1].color = flame_colors.get(p.fire_preset, flame_colors["ORANGE"])
                    elif node.type == "PRINCIPLED_VOLUME":
                        try:
                            node.inputs["Emission Strength"].default_value = p.fire_intensity
                        except Exception:
                            pass
        _volume_finish_register(context, f"火焰 · {obj.name}", "VOLUME_FIRE", domain, None,
                                modifier=domain.modifiers[0] if domain.modifiers else None, strength=p.fire_intensity)
        self.report({'INFO'}, f"火焰模拟就绪：{domain.name}")
        return {'FINISHED'}


class MFX_OT_volume_liquid(Operator):
    bl_idname = "mfx.volume_liquid"
    bl_label = "液体模拟"
    bl_description = "Mantaflow 液体模拟（静止 / 倾倒二选一；烘焙较重，建议低分辨率起步）"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "MESH"

    def execute(self, context):
        obj = context.object
        p = context.scene.mfx_props
        try:
            used_quick, domain, flow = _volume_quick_base(context, "liquid")
            if not used_quick:
                domain, flow = _volume_manual_base(context, "liquid")
            settings = _volume_apply_common(domain, "liquid", p)
        except Exception as exc:
            self.report({'ERROR'}, f"当前环境 Mantaflow 初始化不可用（{exc}）；请在 GUI 真机运行")
            return {'CANCELLED'}
        if settings is None:
            self.report({'ERROR'}, "液体域创建失败")
            return {'CANCELLED'}
        if flow:
            direction = volume_direction_vector(p)  # DX-5.2：入流速度（NATURAL/±Z=沿重力轴原生）
            if direction is not None:
                try:
                    flow.modifiers[0].flow_settings.use_velocity = True
                    flow.modifiers[0].flow_settings.velocity = direction
                except Exception:
                    pass
            flow_mat = flow.material_slots[0].material if flow.material_slots else None
            if flow_mat is None:
                flow_mat = bpy.data.materials.new(f"MFX · 液体 · {obj.name}")
                flow_mat.use_nodes = True
                flow.data.materials.append(flow_mat)
            bsdf = next((n for n in flow_mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf:
                set_input(bsdf, "Base Color", (p.liquid_color[0], p.liquid_color[1], p.liquid_color[2], 1.0))
            if p.liquid_flow == "POUR":
                _mn, _mx, size = volume_bounds(domain)
                start = flow.location.copy()
                flow.location = Vector((start.x, start.y, start.z + max(size.z, 1.0) * 0.8))
                flow.keyframe_insert("location", frame=1)
                flow.location = start
                flow.keyframe_insert("location", frame=12)
        _volume_finish_register(context, f"液体 · {obj.name}", "VOLUME_LIQUID", domain, None,
                                modifier=domain.modifiers[0] if domain.modifiers else None)
        self.report({'INFO'}, f"液体模拟就绪：{domain.name}")
        return {'FINISHED'}


class MFX_OT_audio_drive(Operator):
    bl_idname = "mfx.audio_drive"
    bl_label = "用音频驱动特效"
    bl_description = "分析 PCM WAV 音量并生成该特效发光强度关键帧"
    layer_index: IntProperty(default=-1, options={'HIDDEN'})

    def execute(self, context):
        scene, props = context.scene, context.scene.mfx_props
        index = self.layer_index
        if index < 0 or index >= len(scene.mfx_effect_layers):
            self.report({'ERROR'}, "请从特效堆栈中选择要驱动的图层")
            return {'CANCELLED'}
        layer = scene.mfx_effect_layers[index]
        material = bpy.data.materials.get(layer.material_name) if layer.material_name else None
        if not props.audio_path or not os.path.isfile(bpy.path.abspath(props.audio_path)):
            self.report({'ERROR'}, "请选择有效的 WAV 音频文件")
            return {'CANCELLED'}
        if not material or not material.use_nodes or not material.node_tree:
            self.report({'ERROR'}, "该特效层没有可供音频驱动的材质")
            return {'CANCELLED'}
        emission = material.node_tree.nodes.get(layer.emission_node) if layer.emission_node else None
        strength = emission.inputs.get("Strength") if emission else None
        if strength is None:
            self.report({'ERROR'}, "该特效层不包含发光强度输入")
            return {'CANCELLED'}
        filepath = bpy.path.abspath(props.audio_path)
        try:
            with wave.open(filepath, "rb") as audio:
                channels = audio.getnchannels()
                sample_rate = audio.getframerate()
                width = audio.getsampwidth()
                frame_count = audio.getnframes()
                if width not in (1, 2, 3, 4) or channels < 1 or sample_rate < 1:
                    raise ValueError("只支持 8/16/24/32 位 PCM WAV")
                samples = audio.readframes(frame_count)
        except Exception as exc:
            self.report({'ERROR'}, f"读取 WAV 失败：{exc}")
            return {'CANCELLED'}

        bytes_per_frame = width * channels
        effective_fps = scene.render.fps / scene.render.fps_base
        duration_frames = max(1, round(frame_count / sample_rate * effective_fps))
        if duration_frames > 10000:
            self.report({'ERROR'}, "音频过长；请先裁剪到约 5 分钟以内再驱动特效")
            return {'CANCELLED'}
        start = effect_start_frame(scene, props)
        key_step = props.audio_key_step
        peak = float(1 << (width * 8 - 1)) if width > 1 else 128.0
        windows = []
        max_rms = 0.0
        for frame in range(0, duration_frames + 1, key_step):
            sample_start = min(frame_count, round(frame / effective_fps * sample_rate))
            sample_end = min(frame_count, round((frame + key_step) / effective_fps * sample_rate))
            byte_start = sample_start * bytes_per_frame
            byte_end = min(len(samples), sample_end * bytes_per_frame)
            chunk = samples[byte_start:byte_end]
            count = len(chunk) // width
            if not count:
                rms = 0.0
            else:
                total = 0.0
                for offset in range(0, count * width, width):
                    raw = chunk[offset:offset + width]
                    sample = (raw[0] - 128) if width == 1 else int.from_bytes(raw, "little", signed=True)
                    normalized = sample / peak
                    total += normalized * normalized
                rms = (total / count) ** 0.5
            windows.append((frame, rms))
            max_rms = max(max_rms, rms)
        if max_rms <= 1e-8:
            self.report({'ERROR'}, "音频没有检测到有效音量")
            return {'CANCELLED'}

        node_path = strength.path_from_id("default_value")
        node_tree = material.node_tree
        action = node_tree.animation_data.action if node_tree.animation_data else None
        if action:
            for curve in list(action.fcurves):
                if curve.data_path == node_path:
                    action.fcurves.remove(curve)
        for frame, rms in windows:
            normalized = min(1.0, rms / max_rms)
            strength.default_value = min(100.0, normalized * props.audio_gain)
            strength.keyframe_insert(data_path="default_value", frame=start + frame)
        if node_tree.animation_data and node_tree.animation_data.action:
            for curve in node_tree.animation_data.action.fcurves:
                if curve.data_path == node_path:
                    for key in curve.keyframe_points:
                        key.interpolation = "LINEAR"
        layer.easing = "LINEAR"
        layer.material["mfx_audio_curve_path"] = node_path  # v1.0.5：增益实时调节定位标记
        layer.material["mfx_audio_gain_value"] = props.audio_gain
        apply_effect_animation_options(layer)
        self.report({'INFO'}, f"已为“{layer.name}”生成 {len(windows)} 个音频强度关键帧（增益 {props.audio_gain:g}）")
        return {'FINISHED'}


class MFX_OT_bake(Operator):
    bl_idname = "mfx.bake"
    bl_label = "烘焙 Base Color"
    bl_description = "使用 Cycles 将当前材质颜色烘焙至新图像（需要 UV；设备由 CPU/GPU 选项控制）"
    def execute(self, context):
        obj, p, scene = context.object, context.scene.mfx_props, context.scene
        if not obj or obj.type != "MESH":
            self.report({'ERROR'}, "请先选择网格物体")
            return {'CANCELLED'}
        material = obj.active_material
        if not material or not material.use_nodes:
            self.report({'ERROR'}, "当前物体没有节点材质")
            return {'CANCELLED'}
        if not obj.data.uv_layers:
            try:
                for selected in context.selected_objects: selected.select_set(False)
                obj.hide_set(False); obj.select_set(True); context.view_layer.objects.active = obj
                if obj.mode != "OBJECT": bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                bpy.ops.uv.smart_project(island_margin=0.02)
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception as exc:
                self.report({'ERROR'}, f"自动 UV 展开失败：{exc}")
                return {'CANCELLED'}
        old_engine = scene.render.engine
        old_cycles_device = getattr(scene.cycles, "device", "CPU")
        gpu_use_states = []
        image_nodes = []
        bake_completed = False
        image = bpy.data.images.new(f"{obj.name}_BaseColor_Bake", width=int(p.bake_resolution), height=int(p.bake_resolution), alpha=True)
        bake_materials = {slot.material for slot in obj.material_slots if slot.material and slot.material.use_nodes}
        for bake_material in bake_materials:
            image_node = bake_material.node_tree.nodes.new("ShaderNodeTexImage")
            image_nodes.append((bake_material.node_tree, image_node))
            image_node.label = "烘焙目标图像"
            image_node.image = image
            for node in bake_material.node_tree.nodes: node.select = False
            image_node.select = True
            bake_material.node_tree.nodes.active = image_node
        try:
            if obj.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            for selected in context.selected_objects:
                selected.select_set(False)
            obj.hide_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            scene.render.engine = "CYCLES"
            if p.bake_device == "GPU":
                cycles_preferences = context.preferences.addons.get("cycles")
                cycles_preferences = cycles_preferences.preferences if cycles_preferences else None
                if not cycles_preferences:
                    raise RuntimeError("Cycles 偏好设置不可用，请启用 Blender 的 Cycles 扩展")
                try:
                    cycles_preferences.get_devices()
                except Exception:
                    pass
                devices = getattr(cycles_preferences, "devices", ())
                flat_devices = [device for group in devices for device in group] if devices and isinstance(devices[0], (list, tuple)) else list(devices)
                gpu_devices = [device for device in flat_devices if getattr(device, "type", "CPU") != "CPU"]
                if not gpu_devices:
                    raise RuntimeError("Cycles 没有可用 GPU；请在 Blender > 偏好设置 > 系统中启用 CUDA/OptiX/HIP/Metal/oneAPI 设备")
                for device in gpu_devices:
                    gpu_use_states.append((device, device.use))
                    device.use = True
                scene.cycles.device = "GPU"
            else:
                scene.cycles.device = "CPU"
            scene.cycles.samples = 16
            scene.render.bake.use_pass_color = True
            scene.render.bake.use_pass_direct = False
            scene.render.bake.use_pass_indirect = False
            bpy.ops.object.bake(type="DIFFUSE")
            bake_completed = True
            if p.bake_path:
                directory = bpy.path.abspath(p.bake_path)
                os.makedirs(directory, exist_ok=True)
                image.filepath_raw = os.path.join(directory, f"{obj.name}_BaseColor.png")
                image.file_format = "PNG"
                image.save()
            self.report({'INFO'}, "Base Color 烘焙完成")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f"烘焙失败：{exc}")
            return {'CANCELLED'}
        finally:
            scene.render.engine = old_engine
            scene.cycles.device = old_cycles_device
            for device, was_enabled in gpu_use_states:
                try:
                    device.use = was_enabled
                except ReferenceError:
                    pass
            for node_tree, image_node in image_nodes:
                try:
                    node_tree.nodes.remove(image_node)
                except (ReferenceError, RuntimeError):
                    pass
            if not bake_completed and image.name in bpy.data.images:
                bpy.data.images.remove(image)


class MFX_OT_export(Operator):
    bl_idname = "mfx.export"
    bl_label = "导出所选物体"
    format: EnumProperty(name="格式", items=[("GLB", "glTF 二进制", ""), ("FBX", "FBX", ""), ("USD", "USD", "")])
    def execute(self, context):
        p = context.scene.mfx_props
        directory = bpy.path.abspath(p.export_path) if p.export_path else bpy.path.abspath("//")
        os.makedirs(directory, exist_ok=True)
        obj_name = context.object.name if context.object else "MaterialFX"
        extension = {"GLB": ".glb", "FBX": ".fbx", "USD": ".usd"}[self.format]
        filepath = os.path.join(directory, bpy.path.clean_name(obj_name) + extension)
        try:
            if self.format == "GLB":
                bpy.ops.export_scene.gltf(filepath=filepath, export_format="GLB", use_selection=True)
            elif self.format == "FBX":
                bpy.ops.export_scene.fbx(filepath=filepath, use_selection=True, path_mode="COPY")
            else:
                bpy.ops.wm.usd_export(filepath=filepath, selected_objects_only=True)
            self.report({'INFO'}, f"已导出：{filepath}")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f"导出失败：{exc}")
            return {'CANCELLED'}


def _bm_delete_loose(bm):
    """清除游离几何（孤立点 + 无面边）。C 组缺陷修复（助手 16:14 冒烟实证）：
    bmesh.ops.delete_loose 在 bpy 4.2 已移除（operator doesn't exist），旧版保留兼容分支；
    4.2 用 bmesh.ops.delete 按 VERTS/EDGES 语义等价实现，删边后复扫新悬空点。"""
    if hasattr(bmesh.ops, "delete_loose"):  # Blender < 4.x 原生路径
        bmesh.ops.delete_loose(bm, verts=list(bm.verts), edges=list(bm.edges), faces=list(bm.faces))
        return
    loose_verts = [v for v in bm.verts if not v.link_edges]
    if loose_verts:
        bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")
    loose_edges = [e for e in bm.edges if not e.link_faces]
    if loose_edges:
        bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")
    loose_verts = [v for v in bm.verts if not v.link_edges]
    if loose_verts:
        bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")


def parse_faceted_step(filepath):
    """解析分面 B-rep STEP（本插件导出格式）为网格数据。

    返回 [(vertices_mm, faces), ...]，faces 为三角顶点索引。
    仅支持直线边（LINE）与平面环；遇到圆弧/NURBS 实体时明确报错。
    带洞平面（FACE_OUTER_BOUND + FACE_BOUND）通过平面三角化正确填充。
    """
    import re as _re
    try:
        text = open(filepath, "r", encoding="ascii", errors="replace").read()
    except OSError as exc:
        raise ValueError(f"无法读取 STEP 文件：{exc}")
    if "ISO-10303-21" not in text:
        raise ValueError("不是 STEP 文件（缺少 ISO-10303-21 标头）")

    entities = {}
    for match in _re.finditer(r"#(\d+)\s*=\s*([A-Z_0-9]+)\s*\(([^;]*?)\);", text):
        entities[int(match.group(1))] = (match.group(2), match.group(3))
    if not entities:
        raise ValueError("STEP 文件中未解析到实体")

    def refs(args):
        return [int(value) for value in _re.findall(r"#(\d+)", args)]

    coord_re = _re.compile(r"\(\s*([^()]*)\)\s*$")
    points = {}
    vertex_points = {}
    edge_curves = {}
    oriented_edges = {}
    edge_loops = {}
    bounds = {}
    advanced_faces = {}
    shells = {}
    solids = []
    for eid, (etype, args) in entities.items():
        if etype == "CARTESIAN_POINT":
            m = coord_re.search(args)
            if m:
                values = [float(v) for v in m.group(1).split(",")]
                points[eid] = tuple(values[:3])
        elif etype == "VERTEX_POINT":
            refs_list = refs(args)
            if refs_list:
                vertex_points[eid] = refs_list[0]
        elif etype == "EDGE_CURVE":
            refs_list = refs(args)
            if len(refs_list) >= 3:
                edge_curves[eid] = (refs_list[0], refs_list[1], refs_list[2])
        elif etype == "ORIENTED_EDGE":
            refs_list = refs(args)
            if refs_list:
                sense = args.rsplit(",", 1)[-1].strip() != ".F."
                oriented_edges[eid] = (refs_list[-1], sense)
        elif etype == "EDGE_LOOP":
            edge_loops[eid] = refs(args)
        elif etype in ("FACE_OUTER_BOUND", "FACE_BOUND"):
            refs_list = refs(args)
            if refs_list:
                orientation = args.rsplit(",", 1)[-1].strip() != ".F."
                bounds[eid] = (refs_list[0], orientation, etype == "FACE_OUTER_BOUND")
        elif etype == "ADVANCED_FACE":
            advanced_faces[eid] = refs(args)
        elif etype == "CLOSED_SHELL":
            shells[eid] = refs(args)
        elif etype == "MANIFOLD_SOLID_BREP":
            refs_list = refs(args)
            if refs_list:
                solids.append(refs_list[0])
    if not solids:
        raise ValueError("STEP 中没有分面实体（MANIFOLD_SOLID_BREP）；可能是参数化 CAD 实体")

    def loop_vertex_ids(loop_id, orientation):
        chain = []
        for oe in edge_loops.get(loop_id, []):
            if oe not in oriented_edges:
                raise ValueError("面环引用缺失，STEP 结构不完整")
            edge_ref, sense = oriented_edges[oe]
            if edge_ref not in edge_curves:
                raise ValueError("面环边缺失，STEP 结构不完整")
            v_low, v_high, curve_ref = edge_curves[edge_ref]
            curve_type = entities.get(curve_ref, ("", ""))[0]
            if curve_type != "LINE":
                raise ValueError("STEP 包含非直线边（圆弧/NURBS）；当前仅支持分面 STEP，请在 Fusion 360 中改用网格导出（STL/OBJ/分面 STEP）")
            a, b = (v_low, v_high) if sense else (v_high, v_low)
            if not orientation:
                a, b = b, a
            chain.append((a, b))
        return [item[0] for item in chain]

    # 顶点去重（外部文件可能多个 VERTEX_POINT 重合）
    vertex_index = {}
    vertex_coords = []
    def vertex_id(point_ref):
        coord = points.get(vertex_points.get(point_ref))
        if coord is None:
            raise ValueError("顶点缺少坐标，STEP 结构不完整")
        key = (round(coord[0], 6), round(coord[1], 6), round(coord[2], 6))
        if key not in vertex_index:
            vertex_index[key] = len(vertex_coords)
            vertex_coords.append(coord)
        return vertex_index[key]

    results = []
    for shell_id in solids:
        face_defs = []
        for bound_ref in shells.get(shell_id, []):
            if bound_ref not in advanced_faces:
                continue
            outer_loop = None
            hole_loops = []
            for bound_id in advanced_faces[bound_ref]:
                if bound_id not in bounds:
                    continue
                loop_ref, orientation, is_outer = bounds[bound_id]
                verts = [vertex_id(v) for v in loop_vertex_ids(loop_ref, orientation)]
                if len(verts) < 3:
                    continue
                if is_outer:
                    outer_loop = verts
                else:
                    hole_loops.append(verts)
            if outer_loop is None:
                raise ValueError("STEP 面缺少外环（FACE_OUTER_BOUND）")
            face_defs.append((outer_loop, hole_loops))
        if not face_defs:
            raise ValueError("STEP 实体没有可用的面")

        # 面构建：无洞面直接输出 n-gon（快路径，零三角化）；带洞面用单面 bmesh
        # triangle_fill（单平面多环是其设计场景；整体 fill 会跨面误连丢面）。
        faces_out = []
        vertex_used = set()
        for outer_loop, hole_loops in face_defs:
            if not hole_loops:
                faces_out.append(tuple(outer_loop))
                vertex_used.update(outer_loop)
                continue
            local_ids = []
            local_index = {}
            for vid in list(outer_loop) + [v for hole in hole_loops for v in hole]:
                if vid not in local_index:
                    local_index[vid] = len(local_ids)
                    local_ids.append(vid)
            bm = bmesh.new()
            try:
                bm_verts = [bm.verts.new(vertex_coords[vid]) for vid in local_ids]
                bm.verts.ensure_lookup_table()
                fill_edges = []
                for loop in [outer_loop] + list(hole_loops):
                    size = len(loop)
                    for i in range(size):
                        a, b = bm_verts[local_index[loop[i]]], bm_verts[local_index[loop[(i + 1) % size]]]
                        try:
                            fill_edges.append(bm.edges.new((a, b)))
                        except ValueError:
                            pass
                bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=fill_edges)
                bmesh.ops.triangulate(bm, faces=list(bm.faces))
                bm.verts.ensure_lookup_table()
                for face in bm.faces:
                    faces_out.append(tuple(local_ids[v.index] for v in face.verts))
                    vertex_used.update(local_ids[v.index] for v in face.verts)
            finally:
                bm.free()
        if not faces_out:
            raise ValueError("STEP 面构建结果为空")
        # 压缩未引用顶点（孤立 VERTEX_POINT 不进网格）
        remap = {}
        compact_verts = []
        for old_index in sorted(vertex_used):
            remap[old_index] = len(compact_verts)
            compact_verts.append(vertex_coords[old_index])
        compact_faces = [tuple(remap[v] for v in face) for face in faces_out]
        results.append((compact_verts, compact_faces))
    return results


class MFX_OT_import_model(Operator, ImportHelper):
    bl_idname = "mfx.import_model"
    bl_label = "导入网格模型"
    bl_description = "导入 STL、分面 STEP、FBX、OBJ、PLY、glTF、USD 或 Alembic 网格"
    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl;*.step;*.stp;*.fbx;*.obj;*.ply;*.glb;*.gltf;*.usd;*.usda;*.usdc;*.abc", options={'HIDDEN'})

    def execute(self, context):
        filepath = bpy.path.abspath(self.filepath)
        extension = os.path.splitext(filepath)[1].lower()
        before = {item.name for item in context.scene.objects}
        try:
            if extension == ".stl":
                bpy.ops.wm.stl_import(filepath=filepath, use_mesh_validate=True)
            elif extension == ".fbx":
                bpy.ops.import_scene.fbx(filepath=filepath)
            elif extension == ".obj":
                bpy.ops.wm.obj_import(filepath=filepath)
            elif extension == ".ply":
                bpy.ops.wm.ply_import(filepath=filepath)
            elif extension in {".glb", ".gltf"}:
                bpy.ops.import_scene.gltf(filepath=filepath)
            elif extension in {".usd", ".usda", ".usdc"}:
                bpy.ops.wm.usd_import(filepath=filepath)
            elif extension == ".abc":
                bpy.ops.wm.alembic_import(filepath=filepath)
            elif extension in {".step", ".stp"}:
                solids = parse_faceted_step(filepath)
                created = []
                for solid_index, (verts_mm, tri_faces) in enumerate(solids, start=1):
                    mesh_data = bpy.data.meshes.new(f"STEP 实体 {solid_index}")
                    mesh_data.from_pydata([(x / 1000.0, y / 1000.0, z / 1000.0) for x, y, z in verts_mm], [], tri_faces)
                    mesh_data.validate()
                    mesh_data.update()
                    obj_new = bpy.data.objects.new(f"STEP 实体 {solid_index}", mesh_data)
                    context.collection.objects.link(obj_new)
                    created.append(obj_new)
                if not created:
                    raise RuntimeError("STEP 中没有可导入的实体")
            else:
                raise RuntimeError(f"不支持的文件格式：{extension or '无扩展名'}")
        except Exception as exc:
            self.report({'ERROR'}, f"模型导入失败：{exc}")
            return {'CANCELLED'}
        imported = [item for item in context.scene.objects if item.name not in before]
        if imported:
            bpy.ops.object.select_all(action="DESELECT")
            for item in imported:
                item.select_set(True)
            active = next((item for item in imported if item.type == "MESH"), imported[0])
            context.view_layer.objects.active = active
        self.report({'INFO'}, f"已导入 {len(imported)} 个对象" if imported else "导入完成")
        return {'FINISHED'}


def _exoside_available():
    """探测已安装的 Exoside QuadRemesher（正版引擎桥接，实时探测不缓存）。

    bpy.ops 是动态代理，仅凭 hasattr 会把不存在的算子误判为真；
    必须以 get_rna_type() 能取到真实 RNA 定义为准。"""
    try:
        if not hasattr(bpy.ops.qremesher, "remesh"):
            return False
        return bpy.ops.qremesher.remesh.get_rna_type() is not None
    except Exception:
        return False


class MFX_OT_quad_remesh(Operator):
    bl_idname = "mfx.quad_remesh"
    bl_label = "生成四边面副本（Quadriflow）"
    bl_description = "用 Blender Quadriflow 为活动网格生成规整四边面副本，并保留原模型；执行前自动清洗非流形结构"

    _poll_interval = 0.5
    _timeout = 120.0

    @classmethod
    def poll(cls, context):
        return bool(context.object and context.object.type == "MESH")

    def _cleanup(self, context, result):
        if result is not None:
            try:
                mesh = result.data
                bpy.data.objects.remove(result, do_unlink=True)
                if mesh and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
            except ReferenceError:
                pass

    def execute(self, context):
        import time
        source = context.object
        props = context.scene.mfx_props
        if source.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        result = None
        try:
            depsgraph = context.evaluated_depsgraph_get()
            evaluated = source.evaluated_get(depsgraph)
            mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
            if not mesh or not mesh.vertices or not mesh.polygons:
                if mesh and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
                raise RuntimeError("评估后的网格为空")
            mesh.name = f"{source.name} · Quad Mesh"
            result = bpy.data.objects.new(f"{source.name} · 四边面", mesh)
            collections = list(source.users_collection) or [context.collection]
            for collection in collections:
                collection.objects.link(result)
            result.matrix_world = source.matrix_world.copy()
            bpy.ops.object.select_all(action="DESELECT")
            result.select_set(True)
            context.view_layer.objects.active = result
            result.update_tag(refresh={"OBJECT", "DATA"})

            # 预处理管线：CAD 导入网格常见的重合点/游离几何/法线不一致会让 Quadriflow 拒载
            bounds = [vert.co for vert in mesh.vertices]
            diagonal = 0.0
            for axis in range(3):
                values = [co[axis] for co in bounds]
                diagonal += (max(values) - min(values)) ** 2
            diagonal = diagonal ** 0.5
            weld_dist = max(diagonal * 1e-6, 1e-9)
            bm = bmesh.new()
            try:
                bm.from_mesh(result.data)
                bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=weld_dist)
                _bm_delete_loose(bm)  # C 组缺陷修复：4.2 无 delete_loose，走等价实现
                if not bm.faces:
                    raise RuntimeError("清洗重合点与游离几何后没有可用的面；请检查模型")
                bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
                bm.to_mesh(result.data)
            finally:
                bm.free()
            result.data.update()

            self._original_mesh = result.data
            self._result_name = result.name
            self._source_name = source.name
            self._started = time.monotonic()
            self._next_check = 0.0
            self._target_faces = props.model_target_faces
            qflow_result = bpy.ops.object.quadriflow_remesh(
                mode="FACES", target_faces=props.model_target_faces,
                use_mesh_symmetry=False,
                use_preserve_sharp=props.model_preserve_sharp,
                use_preserve_boundary=props.model_preserve_boundary,
                preserve_attributes=props.model_preserve_attributes,
                smooth_normals=props.model_smooth_normals)
            if "FINISHED" not in qflow_result:
                raise RuntimeError("Quadriflow 没有完成重拓扑")
        except Exception as exc:
            self._cleanup(context, result)
            self.report({'ERROR'}, f"四边面重拓扑失败：{exc}")
            return {'CANCELLED'}
        # Blender 4.x 的 Quadriflow 是异步 job：ops 返回 FINISHED ≠ 重拓扑完成。
        # 用 modal 轮询真实完成状态，杜绝"把原网格复制品当结果"的假成功。
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, "Quadriflow 正在后台重构，完成后会自动报告结果")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        import time
        now = time.monotonic()
        if now < self._next_check:
            return {'PASS_THROUGH'}
        self._next_check = now + self._poll_interval
        try:
            result = context.scene.objects.get(self._result_name)
        except Exception:
            result = None
        if result is None or result.type != "MESH":
            return {'FINISHED'}  # 用户已手动删除副本，静默结束
        if result.data is not self._original_mesh:
            quads = sum(1 for polygon in result.data.polygons if len(polygon.vertices) == 4)
            total = len(result.data.polygons)
            if total == 0 or quads == 0:
                self._cleanup(context, result)
                self.report({'ERROR'}, "Quadriflow 结果校验失败（四边面占比为 0），已清理副本；请检查网格非流形结构后重试")
                return {'FINISHED'}
            self.report({'INFO'}, f"已保留原模型并生成 {total} 面副本（四边面 {quads}，目标 {self._target_faces}）")
            return {'FINISHED'}
        if now - self._started > self._timeout:
            self._cleanup(context, result)
            self.report({'ERROR'}, "Quadriflow 后台重构超时未完成：网格可能存在非流形结构；请检查后重试，或改用 Exoside 引擎")
            return {'FINISHED'}
        return {'PASS_THROUGH'}

    def cancel(self, context):
        try:
            result = context.scene.objects.get(self._result_name) if getattr(self, "_result_name", None) else None
        except Exception:
            result = None
        if result is not None and result.data is getattr(self, "_original_mesh", None):
            pass  # job 仍在进行，保留副本让 job 自然结束
        return None


class MFX_OT_quad_remesh_exoside(Operator):
    bl_idname = "mfx.quad_remesh_exoside"
    bl_label = "用 Exoside 引擎重构"
    bl_description = "调用已安装的 Exoside QuadRemesher 执行四边面重构；引擎异步执行，结果出现前请稍候"

    @classmethod
    def poll(cls, context):
        return bool(context.object and context.object.type == "MESH") and _exoside_available()

    def execute(self, context):
        source = context.object
        if source.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if not hasattr(context.scene, "qremesher"):
            self.report({'ERROR'}, "Exoside QuadRemesher 未完成注册；请先在偏好设置中启用该插件")
            return {'CANCELLED'}
        # 收紧选区到单一活动网格：Exoside 对多选会自动 join、对非网格会 convert，均属破坏性副作用
        bpy.ops.object.select_all(action="DESELECT")
        source.select_set(True)
        context.view_layer.objects.active = source
        try:
            bpy.ops.qremesher.remesh()
        except Exception as exc:
            self.report({'ERROR'}, f"Exoside 引擎启动失败：{exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Exoside 引擎已启动（异步执行）；引擎完成时会自行选中结果对象（首次使用若需下载引擎，按其提示再次点击）")
        return {'FINISHED'}


class MFX_OT_export_model_mesh(Operator):
    bl_idname = "mfx.export_model_mesh"
    bl_label = "导出模型网格"
    format: EnumProperty(name="格式", items=[
        ("STL", "STL", "用于打印或 Fusion 网格转换"),
        ("FBX", "FBX", "交换模型与骨骼动画"),
        ("OBJ", "OBJ", "交换静态网格与法线/贴图"),
        ("GLB", "GLB", "导出 glTF 二进制模型"),
    ])

    def execute(self, context):
        props = context.scene.mfx_props
        selected = [item for item in context.selected_objects if item.type == "MESH"]
        if not selected:
            self.report({'ERROR'}, "请先选择要导出的网格物体")
            return {'CANCELLED'}
        directory = bpy.path.abspath(props.model_export_path) if props.model_export_path else bpy.path.abspath("//")
        os.makedirs(directory, exist_ok=True)
        active = context.object if context.object in selected else selected[0]
        extension = {"STL": ".stl", "FBX": ".fbx", "OBJ": ".obj", "GLB": ".glb"}[self.format]
        filepath = os.path.join(directory, bpy.path.clean_name(active.name) + extension)
        previous_selected = list(context.selected_objects)
        previous_active = context.view_layer.objects.active
        try:
            for item in previous_selected:
                item.select_set(False)
            for item in selected:
                item.select_set(True)
            context.view_layer.objects.active = active if active in selected else selected[0]
            if self.format == "STL":
                bpy.ops.wm.stl_export(filepath=filepath, export_selected_objects=True, apply_modifiers=True)
            elif self.format == "FBX":
                bpy.ops.export_scene.fbx(filepath=filepath, use_selection=True, use_mesh_modifiers=True)
            elif self.format == "OBJ":
                bpy.ops.wm.obj_export(filepath=filepath, export_selected_objects=True, apply_modifiers=True)
            else:
                bpy.ops.export_scene.gltf(filepath=filepath, export_format="GLB", use_selection=True)
        except Exception as exc:
            self.report({'ERROR'}, f"{self.format} 导出失败：{exc}")
            return {'CANCELLED'}
        finally:
            for item in context.selected_objects:
                item.select_set(False)
            for item in previous_selected:
                if item.name in bpy.data.objects:
                    item.select_set(True)
            if previous_active and previous_active.name in bpy.data.objects:
                context.view_layer.objects.active = previous_active
        self.report({'INFO'}, f"已导出：{filepath}")
        return {'FINISHED'}


def step_number(value):
    value = float(value)
    if abs(value) < 5e-13:
        value = 0.0
    return format(value, ".12g")


# ─────────────────────────────────────────────────────────────────────────────
# [CAD·STEP 写出器] MFX_Part21Writer：手写 ISO-10303-21（STEP Part 21）实体写出器。
#   格式一课：STEP 主体是「#N=实体类型(参数);」的实体表，拓扑自底向上——
#   CARTESIAN_POINT（坐标 ×1000：Blender 米 → STEP 毫米）→ DIRECTION → 面环 →
#   EDGE/PLANE → ADVANCED_FACE → CLOSED_SHELL → MANIFOLD_SOLID_BREP；
#   add() 自增发号并返回 id，各方法返回 id 供上层引用，实体间构成引用图。
#   鲁棒性两件套：_loop_normal 用 Newell 法求非凸平面环法线（比单边叉积稳健）；
#   _collect_pins 用空间哈希分桶找 T 型连接（外部顶点落在面边上）——漏掉钉扎
#   会让相邻面共享边断开，CAD 软件报拓扑错误。零 numpy 依赖，任何发行版可用。

class MFX_Part21Writer:
    def __init__(self):
        self.entities = []
        self.next_id = 1

    def add(self, expression):
        entity_id = self.next_id
        self.next_id += 1
        self.entities.append(f"#{entity_id}={expression};")
        return entity_id

    def point(self, xyz):
        xyz = tuple(step_number(value * 1000.0) for value in xyz)
        return self.add(f"CARTESIAN_POINT('',({','.join(xyz)}))")

    def direction(self, xyz):
        xyz = tuple(step_number(value) for value in xyz)
        return self.add(f"DIRECTION('',({','.join(xyz)}))")

    @staticmethod
    def _loop_normal(vertices, loop):
        """Newell 法线：对非凸平面环稳健，方向与环绕向成右手系。"""
        normal = Vector((0.0, 0.0, 0.0))
        size = len(loop)
        for i in range(size):
            prev = Vector(vertices[loop[i - 1]])
            cur = Vector(vertices[loop[i]])
            normal += (prev - cur).cross(prev + cur)
        return normal

    @staticmethod
    def _pins_on_segment(vertices, buckets, cell, a, b, dist_tol):
        pa = vertices[a]
        pb = vertices[b]
        abx, aby, abz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
        length2 = abx * abx + aby * aby + abz * abz
        if length2 <= 0.0:
            return []
        length = math.sqrt(length2)
        t_min = dist_tol / length
        steps = max(1, int(length / cell) + 1)
        candidates = set()
        for step in range(steps + 1):
            t = step / steps
            bx = int((pa[0] + abx * t) // cell)
            by = int((pa[1] + aby * t) // cell)
            bz = int((pa[2] + abz * t) // cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        bucket = buckets.get((bx + dx, by + dy, bz + dz))
                        if bucket:
                            candidates.update(bucket)
        pins = []
        tol2 = dist_tol * dist_tol
        for idx in candidates:
            if idx == a or idx == b:
                continue
            co = vertices[idx]
            apx, apy, apz = co[0] - pa[0], co[1] - pa[1], co[2] - pa[2]
            t = (apx * abx + apy * aby + apz * abz) / length2
            if t <= t_min or t >= 1.0 - t_min:
                continue
            ddx = apx - abx * t
            ddy = apy - aby * t
            ddz = apz - abz * t
            if ddx * ddx + ddy * ddy + ddz * ddz <= tol2:
                pins.append((t, idx))
        pins.sort()
        return [idx for _, idx in pins]

    @classmethod
    def _collect_pins(cls, vertices, face_defs, dist_tol, pin_map):
        """扫描面环上被外部顶点钉住的边（几何 T-junction），供写出层做共线分段。

        纯 Python + 空间哈希分桶：线段沿桶采样，候选顶点降到常数级，
        不依赖 numpy（保持扩展零硬依赖，任何 Blender 发行版可用）。"""
        if not vertices:
            return
        xs = [co[0] for co in vertices]
        ys = [co[1] for co in vertices]
        zs = [co[2] for co in vertices]
        diagonal = math.sqrt((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2 + (max(zs) - min(zs)) ** 2)
        cell = max(diagonal * 1e-4, dist_tol * 64.0, 1e-12)
        buckets = {}
        for index, co in enumerate(vertices):
            key = (int(co[0] // cell), int(co[1] // cell), int(co[2] // cell))
            buckets.setdefault(key, []).append(index)
        seen = set()
        for face_def in face_defs:
            for loop in [face_def["outer"]] + list(face_def["holes"]):
                size = len(loop)
                for i in range(size):
                    a, b = loop[i], loop[(i + 1) % size]
                    key = (min(a, b), max(a, b))
                    if key in seen:
                        continue
                    seen.add(key)
                    pins = cls._pins_on_segment(vertices, buckets, cell, a, b, dist_tol)
                    if pins:
                        pin_map[key] = pins

    def mesh_solid(self, vertices, face_defs, solid_index, pin_tol=None):
        point_ids = [self.point(vertex) for vertex in vertices]
        vertex_ids = [self.add(f"VERTEX_POINT('',#{point_id})") for point_id in point_ids]
        edge_ids = {}
        edge_uses = {}

        pin_map = {}
        if pin_tol is not None:
            self._collect_pins(vertices, face_defs, pin_tol, pin_map)

        def edge_curve(a, b):
            key = (min(a, b), max(a, b))
            if key not in edge_ids:
                low, high = key
                delta = Vector(vertices[high]) - Vector(vertices[low])
                length_mm = delta.length * 1000.0
                if length_mm <= 1e-9:
                    raise ValueError("网格中存在长度为零的边")
                line_direction = self.direction(delta.normalized())
                line_vector = self.add(f"VECTOR('',#{line_direction},{step_number(length_mm)})")
                line = self.add(f"LINE('',#{point_ids[low]},#{line_vector})")
                edge_ids[key] = self.add(f"EDGE_CURVE('',#{vertex_ids[low]},#{vertex_ids[high]},#{line},.T.)")
                edge_uses[key] = 0
            edge_uses[key] += 1
            return edge_ids[key]

        face_ids = []
        for face_def in face_defs:
            outer = face_def["outer"]
            holes = face_def["holes"]
            if len(outer) == 3 and not holes:
                a, b, c = outer
                va, vb, vc = (Vector(vertices[index]) for index in outer)
                raw_normal = (vb - va).cross(vc - va)
                if raw_normal.length <= 1e-18:
                    raise ValueError("网格中存在面积为零的三角面")
                normal = raw_normal.normalized()
                basis = min((Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))), key=lambda axis: abs(axis.dot(normal)))
                reference = normal.cross(basis).normalized()
                center = (va + vb + vc) / 3.0
            else:
                normal = self._loop_normal(vertices, outer)
                if normal.length <= 1e-18:
                    raise ValueError("存在退化面环，无法写出 STEP")
                normal = normal.normalized()
                basis = min((Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))), key=lambda axis: abs(axis.dot(normal)))
                reference = normal.cross(basis).normalized()
                center = sum((Vector(vertices[index]) for index in outer), Vector()) / len(outer)
            plane_origin = self.point(center)
            normal_id = self.direction(normal)
            reference_id = self.direction(reference)
            placement = self.add(f"AXIS2_PLACEMENT_3D('',#{plane_origin},#{normal_id},#{reference_id})")
            plane = self.add(f"PLANE('',#{placement})")

            def make_bound(loop, bound_type):
                oriented = []
                size = len(loop)
                for i in range(size):
                    start, end = loop[i], loop[(i + 1) % size]
                    curve = edge_curve(start, end)
                    same_sense = ".T." if start < end else ".F."
                    oriented.append(self.add(f"ORIENTED_EDGE('',*,*,#{curve},{same_sense})"))
                loop_id = self.add(f"EDGE_LOOP('',({','.join(f'#{item}' for item in oriented)}))")
                return self.add(f"{bound_type}('',#{loop_id},.T.)")

            bounds = [make_bound(outer, "FACE_OUTER_BOUND")]
            for hole in holes:
                bounds.append(make_bound(hole, "FACE_BOUND"))
            face_ids.append(self.add(f"ADVANCED_FACE('',({','.join(f'#{item}' for item in bounds)}),#{plane},.T.)"))

        broken = [key for key, count in edge_uses.items() if count != 2]
        if broken:
            raise ValueError(f"STEP 壳校验失败：{len(broken)} 条边的引用计数不为 2")
        shell = self.add(f"CLOSED_SHELL('MFX Shell {solid_index}',({','.join(f'#{item}' for item in face_ids)}))")
        return self.add(f"MANIFOLD_SOLID_BREP('MFX Solid {solid_index}',#{shell})")

    def serialize(self, solid_ids, output_name):
        context = self.add("APPLICATION_CONTEXT('configuration controlled 3d designs of mechanical parts and assemblies')")
        self.add(f"APPLICATION_PROTOCOL_DEFINITION('international standard','config_control_design',1994,#{context})")
        product_context = self.add(f"PRODUCT_CONTEXT('',#{context},'mechanical')")
        product = self.add(f"PRODUCT('RBM-STEP-001','R_blmaster Faceted Mesh','',(#{product_context}))")
        formation = self.add(f"PRODUCT_DEFINITION_FORMATION('','',#{product})")
        definition_context = self.add(f"PRODUCT_DEFINITION_CONTEXT('part definition',#{context},'design')")
        definition = self.add(f"PRODUCT_DEFINITION('design','',#{formation},#{definition_context})")
        shape_definition = self.add(f"PRODUCT_DEFINITION_SHAPE('','',#{definition})")
        length_unit = self.add("(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.))")
        angle_unit = self.add("(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.))")
        solid_angle_unit = self.add("(NAMED_UNIT(*) SOLID_ANGLE_UNIT() SI_UNIT($,.STERADIAN.))")
        uncertainty = self.add(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-5),#{length_unit},'distance_accuracy_value','')")
        rep_context = self.add(
            f"(GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{uncertainty})) "
            f"GLOBAL_UNIT_ASSIGNED_CONTEXT((#{length_unit},#{angle_unit},#{solid_angle_unit})) REPRESENTATION_CONTEXT('',''))"
        )
        origin = self.point((0, 0, 0))
        z_axis = self.direction((0, 0, 1))
        x_axis = self.direction((1, 0, 0))
        placement = self.add(f"AXIS2_PLACEMENT_3D('',#{origin},#{z_axis},#{x_axis})")
        representation = self.add(f"ADVANCED_BREP_SHAPE_REPRESENTATION('Faceted B-rep',({','.join([f'#{placement}'] + [f'#{item}' for item in solid_ids])}),#{rep_context})")
        self.add(f"SHAPE_DEFINITION_REPRESENTATION(#{shape_definition},#{representation})")
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        safe_name = "R_blmaster_Faceted_Export.step"
        return "\n".join((
            "ISO-10303-21;", "HEADER;",
            "FILE_DESCRIPTION(('R_blmaster faceted B-rep export'),'2;1');",
            f"FILE_NAME('{safe_name}','{timestamp}',('ERDCX'),(''),'R_blmaster','Blender','');",
            "FILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));", "ENDSEC;", "DATA;",
            *self.entities, "ENDSEC;", "END-ISO-10303-21;", ""
        ))


def step_coplanar_faces(vertices, faces, angle_rad, diagonal):
    """共面融合：把同一平面上的相邻三角面聚合成整面（外环+内环），供 STEP 写出器生成单一 FACE。

    设计约束（v1.0.0 需求⑤，规格 docs/v1.0.0_需求5_共面融合算法规格_通用助手.md）：
    - 零形变：不增删改任何顶点，仅重组写出层面的面拓扑；
    - 环全部由原网格边构成 → 接口边两侧共享同一 EDGE_CURVE 实体，面-面拓扑天然一致；
    - 环 walk 采用面扇形配对（入边→同面角出边），多簇交汇顶点（立方体角点度=3）合法；
    - 任一簇校验失败只回退该簇为逐三角面（"尽量"语义），不影响整体导出。
    返回 (face_defs, stats)；face_defs 元素 = {"outer": (v0,v1,...), "holes": [(...), ...]}。
    """
    stats = {"merged": 0, "fallback": 0, "clusters": 0}
    tri_count = len(faces)
    if tri_count == 0:
        return [], stats
    dist_tol = max(diagonal * 1e-7, 1e-12)
    stats["dist_tol"] = dist_tol
    angle_cos = math.cos(min(max(angle_rad, math.radians(0.01)), math.radians(5.0)))
    points = [Vector(co) for co in vertices]

    normals = [None] * tri_count
    areas = [0.0] * tri_count
    for index, face in enumerate(faces):
        a, b, c = face
        raw = (points[b] - points[a]).cross(points[c] - points[a])
        length = raw.length
        if length > 1e-18:
            normals[index] = raw / length
            areas[index] = length * 0.5

    edge_faces = {}
    for index, face in enumerate(faces):
        for start, end in zip(face, face[1:] + face[:1]):
            key = (min(start, end), max(start, end))
            edge_faces.setdefault(key, []).append(index)

    # BFS 聚类：种子按面积降序（规格 §3.1），参考平面固定为种子平面，防链式漂移
    #   教学补注：若每并入邻居就改用邻居平面做判定，A 贴 B、B 贴 C…长链累积
    #   角度误差，走到链尾平面可能肉眼可见地歪（链式漂移）；锚定种子平面 =
    #   全体成员跟同一基准比，聚类边界稳定可复现。法向夹角（angle_cos）与
    #   平面距离（dist_tol）双阈值联合判定，「共面」才算数。
    cluster_of = [-1] * tri_count
    clusters = []
    seed_order = sorted((index for index in range(tri_count) if normals[index] is not None), key=lambda i: (-areas[i], i))
    for seed in seed_order:
        if cluster_of[seed] >= 0:
            continue
        cluster_id = len(clusters)
        plane_normal = normals[seed]
        plane_point = points[faces[seed][0]]
        members = [seed]
        cluster_of[seed] = cluster_id
        pending = [seed]
        while pending:
            current = pending.pop()
            for start, end in zip(faces[current], faces[current][1:] + faces[current][:1]):
                key = (min(start, end), max(start, end))
                for neighbor in edge_faces.get(key, ()):
                    if neighbor == current or cluster_of[neighbor] >= 0 or normals[neighbor] is None:
                        continue
                    if normals[neighbor].dot(plane_normal) < angle_cos:
                        continue
                    if abs((points[faces[neighbor][0]] - plane_point).dot(plane_normal)) > dist_tol:
                        continue
                    cluster_of[neighbor] = cluster_id
                    members.append(neighbor)
                    pending.append(neighbor)
        clusters.append(members)
    stats["clusters"] = len(clusters)

    def fallback_cluster(member_list):
        for face_index in member_list:
            face_defs.append({"outer": faces[face_index], "holes": []})
        stats["fallback"] += 1

    face_defs = []
    for members in clusters:
        if len(members) == 1:
            face_defs.append({"outer": faces[members[0]], "holes": []})
            continue

        boundary = {}
        for face_index in members:
            for start, end in zip(faces[face_index], faces[face_index][1:] + faces[face_index][:1]):
                key = (min(start, end), max(start, end))
                if key in boundary:
                    del boundary[key]  # 簇内共享边，不进环
                else:
                    boundary[key] = (start, end)

        # 环 walk：下一边界边 = 起点匹配（封闭流形单簇边界在顶点处出边唯一；
        # 多候选=8 字自接触等病态 → 簇回退，符合"尽量"语义与冒烟裁定）
        outgoing = {}
        for directed in boundary.values():
            outgoing.setdefault(directed[0], []).append(directed)
        loops = []
        ok = True
        used = set()
        for seed_edge in boundary.values():
            if seed_edge in used:
                continue
            loop = [seed_edge[0]]
            cursor = seed_edge
            closed = False
            while True:
                used.add(cursor)
                loop.append(cursor[1])
                if cursor[1] == seed_edge[0]:
                    closed = True  # 回到起点顶点，环闭合
                    break
                candidates = [edge for edge in outgoing.get(cursor[1], ()) if edge not in used]
                if not candidates:
                    break
                if len(candidates) > 1:
                    break  # 环顶点歧义：多环共享顶点（8 字簇），回退
                cursor = candidates[0]
            if not closed or loop[-1] != loop[0]:
                ok = False
                break
            loops.append(loop[:-1])
        if not ok or not loops:
            fallback_cluster(members)
            continue

        # 外/内环分类：面绕向下外环有向面积为正、内环为负（规格 §6）
        cluster_normal = normals[members[0]]
        outer = None
        holes = []
        for loop in loops:
            signed = 0.0
            size = len(loop)
            for i in range(size):
                signed += points[loop[i]].cross(points[loop[(i + 1) % size]]).dot(cluster_normal)
            if signed > 0.0:
                if outer is None:
                    outer = loop
                else:
                    outer = None  # 多个正环（8 字自接触簇）：ADVANCED_FACE 仅允许单外环，回退
                    break
            else:
                holes.append(loop)
        if outer is None:
            fallback_cluster(members)
            continue
        face_defs.append({"outer": tuple(outer), "holes": [tuple(hole) for hole in holes]})
        stats["merged"] += 1
    return face_defs, stats


def step_mesh_data(obj, depsgraph, merge_coplanar=True, merge_angle=math.radians(0.5)):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=False, depsgraph=depsgraph)
    if not mesh:
        raise ValueError(f"无法读取网格：{obj.name}")
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.transform(obj.matrix_world)
        if not bm.faces:
            raise ValueError(f"物体没有可导出的面：{obj.name}")
        bounds = [vert.co for vert in bm.verts]
        diagonal = (max((point.x for point in bounds), default=0) - min((point.x for point in bounds), default=0)) ** 2
        diagonal += (max((point.y for point in bounds), default=0) - min((point.y for point in bounds), default=0)) ** 2
        diagonal += (max((point.z for point in bounds), default=0) - min((point.z for point in bounds), default=0)) ** 2
        weld_distance = max((diagonal ** 0.5) * 1e-9, 1e-12)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=weld_distance)
        # v1.0.5（STEP 修复①）：导出前自动清理退化元素（零长度边/零面积面/孤立元素），
        # 杜绝含零面积面的模型在下游流形校验与分面写出时塌缩报错。
        try:
            degenerate = bmesh.ops.dissolve_degenerate(bm, dist=max(weld_distance * 100.0, 1e-9), edges=list(bm.edges))
            degenerate_cleaned = len(degenerate.get("edges", ())) + len(degenerate.get("verts", ()))
        except Exception:
            degenerate_cleaned = 0
        # 零面积面兜底清理：纯 bmesh 实现，不依赖任何被 4.2 移除的 ops API
        try:
            for face in [f for f in bm.faces if f.calc_area() <= 1e-20]:
                bm.faces.remove(face)
            bm.faces.ensure_lookup_table()
        except Exception:
            pass
        _bm_delete_loose(bm)  # v1.0.5：走插件等价实现（4.2 官方版无 bmesh.ops.delete_loose）
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='BEAUTY', ngon_method='BEAUTY')
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()
        bm.faces.ensure_lookup_table()
        vertices = [tuple(vert.co) for vert in bm.verts]
        faces = [tuple(vert.index for vert in face.verts) for face in bm.faces]
        if not faces:
            raise ValueError(f"三角化后网格为空：{obj.name}")

        uses = {}
        for face_index, face in enumerate(faces):
            for start, end in zip(face, face[1:] + face[:1]):
                key = (min(start, end), max(start, end))
                uses.setdefault(key, []).append((face_index, 1 if start < end else -1))
        invalid = [edge for edge, edge_uses in uses.items() if len(edge_uses) != 2 or edge_uses[0][1] == edge_uses[1][1]]
        if invalid:
            raise ValueError(f"“{obj.name}”不是封闭且一致定向的流形网格；请先修复边界/非流形边")

        adjacency = [[] for _ in faces]
        for edge_uses in uses.values():
            first, second = edge_uses[0][0], edge_uses[1][0]
            adjacency[first].append(second)
            adjacency[second].append(first)
        seen = set()
        components = 0
        for start in range(len(faces)):
            if start in seen:
                continue
            components += 1
            pending = [start]
            seen.add(start)
            while pending:
                current = pending.pop()
                for neighbor in adjacency[current]:
                    if neighbor not in seen:
                        seen.add(neighbor)
                        pending.append(neighbor)
        if components != 1:
            raise ValueError(f"“{obj.name}”包含多个互不相连的壳体；请拆成独立物体后导出 STEP")

        volume = 0.0
        for a, b, c in faces:
            va, vb, vc = Vector(vertices[a]), Vector(vertices[b]), Vector(vertices[c])
            volume += va.dot(vb.cross(vc)) / 6.0
        if abs(volume) <= 1e-24:
            raise ValueError(f"“{obj.name}”体积为零，无法创建 STEP 实体")
        if volume < 0:
            faces = [(face[0], face[2], face[1]) for face in faces]
        diagonal_value = diagonal ** 0.5
        if merge_coplanar:
            face_defs, merge_stats = step_coplanar_faces(vertices, faces, merge_angle, diagonal_value)
        else:
            face_defs = [{"outer": face, "holes": []} for face in faces]
            merge_stats = {"merged": 0, "fallback": 0, "clusters": 0}
        merge_stats["degenerate_cleaned"] = degenerate_cleaned  # v1.0.5：退化清理统计，导出侧汇报
        return vertices, faces, face_defs, merge_stats
    finally:
        bm.free()
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


class MFX_OT_export_step(Operator):
    bl_idname = "mfx.export_step"
    bl_label = "导出 STEP 实体"
    bl_description = "把封闭网格写成 AP203 分面 B-rep STEP，可直接导入 Fusion 继续编辑"

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context):
        props = context.scene.mfx_props
        selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
        if not selected:
            self.report({'ERROR'}, "请先选择要导出的网格")
            return {'CANCELLED'}
        directory = bpy.path.abspath(props.model_export_path) if props.model_export_path else bpy.path.abspath("//")
        active = context.object if context.object in selected else selected[0]
        filepath = os.path.join(directory, bpy.path.clean_name(active.name) + ".step")
        try:
            # v1.0.5（STEP 修复②）：目录/盘符预检移入 try——无效路径（坏盘符等）走统一错误汇报，不再裸崩
            os.makedirs(directory, exist_ok=True)
            depsgraph = context.evaluated_depsgraph_get()
            merge_on = props.model_step_merge_coplanar
            merge_angle = props.model_step_merge_angle
            results = []
            source_triangle_count = 0
            face_count = 0
            merged_total = 0
            fallback_total = 0
            degenerate_total = 0
            for index, obj in enumerate(selected, start=1):
                vertices, faces, face_defs, merge_stats = step_mesh_data(obj, depsgraph, merge_on, merge_angle)
                results.append((vertices, faces, face_defs, merge_stats))
                source_triangle_count += len(faces)
                face_count += len(face_defs)
                merged_total += merge_stats["merged"]
                fallback_total += merge_stats["fallback"]
                degenerate_total += merge_stats.get("degenerate_cleaned", 0)
            if face_count > 60000:
                raise ValueError("STEP 分面实体超过 60,000 个面；请先用四边面重构降低模型面数")
            writer = MFX_Part21Writer()
            solids = []
            index = 0
            for vertices, faces, face_defs, merge_stats in results:
                index += 1
                pin_tol = merge_stats.get("dist_tol") if (merge_on and merge_stats["merged"] > 0) else None
                try:
                    solids.append(writer.mesh_solid(vertices, face_defs, index, pin_tol=pin_tol))
                except ValueError as exc:
                    if "引用计数" in str(exc) and merge_on:
                        writer = MFX_Part21Writer()
                        solids = []
                        for fallback_index, (fallback_verts, fallback_faces, _fd, _st) in enumerate(results, start=1):
                            solids.append(writer.mesh_solid(fallback_verts, [{"outer": face, "holes": []} for face in fallback_faces], fallback_index))
                        merged_total = 0
                        fallback_total = 0
                        face_count = source_triangle_count
                        self.report({'WARNING'}, "共面融合壳校验失败，已整体回退为逐三角面导出")
                        break
                    raise
            content = writer.serialize(solids, filepath)
            with open(filepath, "w", encoding="ascii", newline="\n") as handle:
                handle.write(content)
        except Exception as exc:
            self.report({'ERROR'}, f"STEP 导出失败：{exc}")
            return {'CANCELLED'}
        detail = f"已导出 STEP 分面实体：{filepath}（{len(solids)} 个实体，{face_count} 面"
        if merge_on and merged_total > 0:
            detail += f"；共面融合 {merged_total} 簇"
            if fallback_total > 0:
                detail += f"，{fallback_total} 簇回退逐三角"
        if degenerate_total > 0:
            detail += f"；已自动清理 {degenerate_total} 处退化元素"
        detail += "）"
        self.report({'INFO'}, detail)
        return {'FINISHED'}


class MFX_OT_import_preset(Operator, ImportHelper):
    bl_idname = "mfx.import_preset"
    bl_label = "从JSON导入材质"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})
    def execute(self, context):
        obj = context.object
        if not obj or not hasattr(obj.data, "materials"):
            self.report({'ERROR'}, "请先选择可接收材质的物体")
            return {'CANCELLED'}
        try:
            with open(self.filepath, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            material = bpy.data.materials.new(data.get("name", "MFX · 导入预设"))
            material.diffuse_color = data.get("diffuse_color", (0.5, 0.5, 0.5, 1))
            material.use_nodes = True
            nt = material.node_tree; nt.nodes.clear(); nodes = {}
            for item in data.get("nodes", []):
                try:
                    node = nt.nodes.new(item["type"])
                except Exception:
                    continue
                node.name = item.get("name", node.name); node.label = item.get("label", "")
                if "location" in item: node.location = item["location"]
                if item.get("image_filepath") and node.type == "TEX_IMAGE":
                    try: node.image = bpy.data.images.load(bpy.path.abspath(item["image_filepath"]), check_existing=True)
                    except Exception: pass
                for socket_name, value in item.get("inputs", {}).items():
                    socket = node.inputs.get(socket_name)
                    if socket and hasattr(socket, "default_value"):
                        try: socket.default_value = value
                        except (TypeError, ValueError): pass
                nodes[item.get("name", node.name)] = node
            for link in data.get("links", []):
                source = nodes.get(link.get("from_node")); target = nodes.get(link.get("to_node"))
                if source and target:
                    out = source.outputs.get(link.get("from_socket")); inp = target.inputs.get(link.get("to_socket"))
                    if out and inp: nt.links.new(out, inp)
            obj.data.materials.append(material); obj.active_material_index = len(obj.data.materials) - 1
            self.report({'INFO'}, "材质节点预设已导入")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f"导入失败：{exc}")
            return {'CANCELLED'}


class MFX_OT_mark_asset(Operator):
    bl_idname = "mfx.mark_asset"
    bl_label = "加入资产浏览器"
    def execute(self, context):
        material = active_material(context)
        if not material:
            self.report({'ERROR'}, "当前物体没有活动材质")
            return {'CANCELLED'}
        if not material.asset_data:
            material.asset_mark()
        material.asset_data.description = "R_blmaster 中文材质预设"
        self.report({'INFO'}, "材质已标记为资产；可在资产浏览器当前文件中查看")
        return {'FINISHED'}


class MFX_OT_save_preset(Operator):
    bl_idname = "mfx.save_preset"
    bl_label = "保存当前材质为JSON预设"
    filepath: StringProperty(subtype="FILE_PATH", default="materialfx_preset.json")
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})
    def invoke(self, context, event): return context.window_manager.invoke_props_dialog(self)
    def draw(self, context): self.layout.prop(self, "filepath", text="保存到")
    def execute(self, context):
        mat = active_material(context)
        if not mat:
            self.report({'ERROR'}, "当前物体没有活动材质")
            return {'CANCELLED'}
        data = {"name": mat.name, "diffuse_color": list(mat.diffuse_color), "nodes": []}
        if mat.use_nodes:
            for node in mat.node_tree.nodes:
                values = {}
                for socket in node.inputs:
                    value = getattr(socket, "default_value", None)
                    if isinstance(value, (float, int, str, bool)): values[socket.name] = value
                    elif hasattr(value, "__len__") and len(value) in (3, 4): values[socket.name] = list(value)
                node_data = {"type": node.bl_idname, "name": node.name, "label": node.label, "location": list(node.location), "inputs": values}
                if node.type == "TEX_IMAGE" and node.image:
                    node_data["image_filepath"] = bpy.path.abspath(node.image.filepath)
                data["nodes"].append(node_data)
            data["links"] = [
                {"from_node": link.from_node.name, "from_socket": link.from_socket.name,
                 "to_node": link.to_node.name, "to_socket": link.to_socket.name}
                for link in mat.node_tree.links
            ]
        with open(bpy.path.abspath(self.filepath), "w", encoding="utf-8") as handle: json.dump(data, handle, ensure_ascii=False, indent=2)
        self.report({'INFO'}, "材质参数已导出为JSON")
        return {'FINISHED'}


def render_material_sphere_thumbnail(material, filepath):
    """Render a real material sphere in a temporary scene, leaving the user's scene alone."""
    preview_scene = bpy.data.scenes.new("MFX 临时材质预览")
    mesh = bpy.data.meshes.new("MFX 预览球网格")
    sphere = camera = world = camera_data = None
    light_data = []
    created_objects = []
    bm = bmesh.new()
    try:
        bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=40, radius=1.0)
        bm.normal_update(); bm.to_mesh(mesh); bm.free()
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        sphere = bpy.data.objects.new("MFX 材质球", mesh)
        preview_scene.collection.objects.link(sphere); created_objects.append(sphere)
        sphere.data.materials.append(material)

        camera_data = bpy.data.cameras.new("MFX 预览相机")
        camera = bpy.data.objects.new("MFX 预览相机", camera_data)
        preview_scene.collection.objects.link(camera); created_objects.append(camera)
        camera.location = (0.0, -3.7, 0.45)
        camera.rotation_euler = (Vector((0, 0, 0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera_data.type = "ORTHO"; camera_data.ortho_scale = 2.75
        preview_scene.camera = camera

        for name, location, energy, size, color in (
                ("主光", (-3.0, -4.0, 4.0), 520.0, 4.0, (1.0, 0.82, 0.68)),
                ("补光", (3.5, -2.0, 1.2), 260.0, 3.0, (0.62, 0.78, 1.0)),
                ("轮廓光", (0.5, 2.5, 3.0), 650.0, 2.5, (1.0, 1.0, 1.0))):
            light = bpy.data.lights.new(f"MFX {name}", "AREA")
            light.energy = energy; light.shape = "DISK"; light.size = size; light.color = color
            light_obj = bpy.data.objects.new(f"MFX {name}", light)
            preview_scene.collection.objects.link(light_obj); created_objects.append(light_obj)
            light_obj.location = location
            light_obj.rotation_euler = (Vector((0, 0, 0)) - light_obj.location).to_track_quat("-Z", "Y").to_euler()
            light_data.append(light)

        world = bpy.data.worlds.new("MFX 预览世界"); world.use_nodes = True
        background = world.node_tree.nodes.get("Background")
        if background:
            background.inputs["Color"].default_value = (0.035, 0.045, 0.06, 1.0)
            background.inputs["Strength"].default_value = 0.45
        preview_scene.world = world
        preview_scene.render.engine = "CYCLES"
        preview_scene.cycles.device = "CPU"
        preview_scene.cycles.samples = 16
        preview_scene.render.resolution_x = 160; preview_scene.render.resolution_y = 160
        preview_scene.render.resolution_percentage = 100
        preview_scene.render.image_settings.file_format = "PNG"
        preview_scene.render.image_settings.color_mode = "RGBA"
        preview_scene.render.film_transparent = False
        preview_scene.render.filepath = filepath
        preview_scene.render.image_settings.color_depth = "8"
        preview_scene.cycles.use_denoising = False
        try:
            bpy.ops.render.render(write_still=True, scene=preview_scene.name)
        except Exception:
            preview_scene.render.engine = "BLENDER_EEVEE_NEXT"
            try:
                preview_scene.eevee.taa_render_samples = 16
            except (AttributeError, TypeError):
                pass
            bpy.ops.render.render(write_still=True, scene=preview_scene.name)
        if not os.path.isfile(filepath) or os.path.getsize(filepath) < 256:
            raise RuntimeError("Blender 没有生成有效的预览图")
    finally:
        if bm.is_valid:
            bm.free()
        for item in created_objects:
            if item.name in bpy.data.objects:
                bpy.data.objects.remove(item, do_unlink=True)
        if preview_scene.name in bpy.data.scenes:
            bpy.data.scenes.remove(preview_scene)
        if mesh.name in bpy.data.meshes and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        if camera_data and camera_data.users == 0:
            bpy.data.cameras.remove(camera_data)
        for light in light_data:
            if light.users == 0:
                bpy.data.lights.remove(light)
        if world and world.users == 0:
            bpy.data.worlds.remove(world)


def copy_material_with_packed_images(material):
    """Make an export-only material copy with private, packed image dependencies."""
    copied = material.copy()
    copied.name = f"MFXPACK · {material.name}"
    copied.use_fake_user = False
    images = {}
    try:
        if copied.use_nodes and copied.node_tree:
            for node in copied.node_tree.nodes:
                source = getattr(node, "image", None) if node.type == "TEX_IMAGE" else None
                if not source:
                    continue
                key = source.as_pointer()
                image = images.get(key)
                if image is None:
                    image = source.copy(); image.name = f"MFXPACK · {source.name}"
                    try:
                        if not image.packed_file:
                            image.pack()
                    except Exception as exc:
                        raise RuntimeError(f"贴图“{source.name}”无法打包：{exc}")
                    images[key] = image
                node.image = image
        return copied, list(images.values())
    except Exception:
        if copied.users == 0:
            bpy.data.materials.remove(copied)
        for image in images.values():
            if image.users == 0:
                bpy.data.images.remove(image)
        raise


def team_preview_directory():
    root = bpy.utils.user_resource("CONFIG", path="materialfx_suite/team_previews", create=True)
    if not root:
        root = bpy.utils.user_resource("DATAFILES", path="materialfx_suite/team_previews", create=True)
    if not root:
        raise RuntimeError("Blender 无法定位预览图保存目录")
    return root


class MFX_OT_export_team_pack(Operator, ExportHelper):
    bl_idname = "mfx.export_team_pack"
    bl_label = "导出团队材质包"
    bl_description = "打包当前材质、贴图依赖与自动渲染的材质球缩略图"
    filename_ext = ".mfxpack"
    filter_glob: StringProperty(default="*.mfxpack", options={'HIDDEN'})

    def execute(self, context):
        material = active_material(context)
        if not material or not material.use_nodes:
            self.report({'ERROR'}, "请先选择带节点材质的物体")
            return {'CANCELLED'}
        filepath = bpy.path.abspath(self.filepath)
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="mfxpack_") as temp_dir:
                blend_path = os.path.join(temp_dir, "material.blend")
                preview_path = os.path.join(temp_dir, "preview.png")
                manifest_path = os.path.join(temp_dir, "manifest.json")
                copied, copied_images = copy_material_with_packed_images(material)
                try:
                    bpy.data.libraries.write(blend_path, {copied}, fake_user=True, compress=True)
                    render_material_sphere_thumbnail(material, preview_path)
                    manifest = {
                        "format": "MaterialFXTeamPack", "version": 1,
                        "material": copied.name, "label": material.name,
                        "thumbnail": "preview.png", "preview_size": [256, 256],
                    }
                    with open(manifest_path, "w", encoding="utf-8") as handle:
                        json.dump(manifest, handle, ensure_ascii=False, indent=2)
                    with zipfile.ZipFile(filepath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                        archive.write(manifest_path, "manifest.json")
                        archive.write(blend_path, "material.blend")
                        archive.write(preview_path, "preview.png")
                finally:
                    if copied.users == 0:
                        bpy.data.materials.remove(copied)
                    for image in copied_images:
                        if image.users == 0:
                            bpy.data.images.remove(image)
        except Exception as exc:
            self.report({'ERROR'}, f"团队材质包导出失败：{exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"已导出材质包和球体预览：{filepath}")
        return {'FINISHED'}


class MFX_OT_import_team_pack(Operator, ImportHelper):
    bl_idname = "mfx.import_team_pack"
    bl_label = "导入团队材质包"
    bl_description = "导入 .mfxpack 中的材质、贴图与材质球预览"
    filename_ext = ".mfxpack"
    filter_glob: StringProperty(default="*.mfxpack", options={'HIDDEN'})

    def execute(self, context):
        obj = context.object
        if not obj or not hasattr(obj.data, "materials"):
            self.report({'ERROR'}, "请先选择可接收材质的物体")
            return {'CANCELLED'}
        filepath = bpy.path.abspath(self.filepath)
        try:
            with zipfile.ZipFile(filepath, "r") as archive:
                required = {"manifest.json", "material.blend", "preview.png"}
                if not required.issubset(set(archive.namelist())):
                    raise ValueError("材质包缺少 manifest、Blender 材质库或预览图")
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                if manifest.get("format") != "MaterialFXTeamPack" or manifest.get("version") != 1:
                    raise ValueError("不支持此版本的团队材质包")
                with tempfile.TemporaryDirectory(prefix="mfxpack_import_") as temp_dir:
                    blend_path = os.path.join(temp_dir, "material.blend")
                    thumbnail_bytes = archive.read("preview.png")
                    if not thumbnail_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise ValueError("材质球预览图不是有效 PNG")
                    with open(blend_path, "wb") as handle:
                        handle.write(archive.read("material.blend"))
                    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
                        if manifest.get("material") not in data_from.materials:
                            raise ValueError("材质库中找不到清单指定的材质")
                        data_to.materials = [manifest["material"]]
                    material = next((item for item in data_to.materials if item), None)
                    if not material:
                        raise ValueError("Blender 无法追加此材质")
                    preview_root = team_preview_directory()
                    os.makedirs(preview_root, exist_ok=True)
                    preset_id = "TEAM_" + uuid.uuid4().hex[:16]
                    preview_path = os.path.join(preview_root, preset_id + ".png")
                    with open(preview_path, "wb") as handle:
                        handle.write(thumbnail_bytes)
                    material["mfx_pack_preset_id"] = preset_id
                    material["mfx_pack_label"] = manifest.get("label", material.name)
                    material["mfx_pack_preview_path"] = preview_path
                    PREVIEW_COLLECTION.load(preset_id, preview_path, "IMAGE")
                    PRESET_PREVIEW_IDS[preset_id] = PREVIEW_COLLECTION[preset_id].icon_id
                    rebuild_preset_items()
                    obj.data.materials.append(material)
                    obj.active_material_index = len(obj.data.materials) - 1
                    props = context.scene.mfx_props
                    props.category = "团队预设"
                    props.preset = preset_id
        except Exception as exc:
            self.report({'ERROR'}, f"团队材质包导入失败：{exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"已导入并应用团队预设：{material.get('mfx_pack_label', material.name)}")
        return {'FINISHED'}


class MFX_OT_export_blend_preset(Operator, ExportHelper):
    bl_idname = "mfx.export_blend_preset"
    bl_label = "导出为Blender材质库"
    filename_ext = ".blend"
    filter_glob: StringProperty(default="*.blend", options={'HIDDEN'})

    def execute(self, context):
        material = active_material(context)
        if not material:
            self.report({'ERROR'}, "请先选择带有活动材质的物体")
            return {'CANCELLED'}
        try:
            bpy.data.libraries.write(bpy.path.abspath(self.filepath), {material}, fake_user=True, compress=True)
        except Exception as exc:
            self.report({'ERROR'}, f"Blender材质库导出失败：{exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "已导出可追加的 .blend 材质库")
        return {'FINISHED'}


class MFX_OT_import_blend_preset(Operator, ImportHelper):
    bl_idname = "mfx.import_blend_preset"
    bl_label = "从Blender材质库导入"
    filename_ext = ".blend"
    filter_glob: StringProperty(default="*.blend", options={'HIDDEN'})

    def execute(self, context):
        obj = context.object
        if not obj or not hasattr(obj.data, "materials"):
            self.report({'ERROR'}, "请先选择可接收材质的物体")
            return {'CANCELLED'}
        try:
            with bpy.data.libraries.load(bpy.path.abspath(self.filepath), link=False) as (data_from, data_to):
                if not data_from.materials:
                    self.report({'ERROR'}, "该 .blend 文件中没有材质")
                    return {'CANCELLED'}
                data_to.materials = [data_from.materials[0]]
            material = next((item for item in data_to.materials if item), None)
            if not material:
                self.report({'ERROR'}, "无法从文件追加材质")
                return {'CANCELLED'}
            obj.data.materials.append(material)
            obj.active_material_index = len(obj.data.materials) - 1
        except Exception as exc:
            self.report({'ERROR'}, f"Blender材质库导入失败：{exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"已导入材质：{material.name}")
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────────────────────
# [UI 面板] MFX_PT_* 家族：N 面板「R_blmaster」分类下的一组 Panel。
#   教学点：bl_space_type/bl_region_type 决定挂载位置（VIEW_3D+UI=N 面板），
#   bl_category 定分类名，子面板经 bl_parent_id 归组折叠；draw() 每帧重画、
#   只读 context 不缓存布局——Blender UI 是即时模式（immediate mode），
#   「布局即状态、重画即刷新」与常规 GUI 框架的保留模式截然不同。

class MFX_PT_material(Panel):
    bl_label = "材质"
    bl_idname = "MFX_PT_material"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"
    def draw(self, context):
        layout = self.layout
        p = context.scene.mfx_props
        obj = context.object
        if not obj:
            layout.label(text="先选择一个物体", icon="INFO")
        box = layout.box(); box.label(text=f"现实材质预设 · {len(TEMPLATES) * len(VARIANTS)}种 · 贴图 {len(TEXTURE_PRESETS)}套", icon="MATERIAL")
        box.prop(p, "category", text="分类"); box.prop(p, "search", text="搜索")
        row = box.row(align=True); row.prop(p, "favorite_only", text="只看收藏"); row.operator("mfx.toggle_favorite", text="收藏/取消", icon="SOLO_ON")
        box.template_icon_view(p, "preset", show_labels=True, scale=5, scale_popup=6)
        box.operator("mfx.apply_preset", icon="MATERIAL")
        box.label(text="程序化纹理投影（全局）", icon="ORIENTATION_VIEW")
        box.row(align=True).prop(p, "texture_projection", text="", expand=True)  # §2.1 挂载位=生成按钮旁全局设置位（16:2x 纠偏：留预设库原位，推荐徽标同屏可见）


class MFX_PT_mat_layers(Panel):
    bl_label = "PS 材质图层编辑"
    bl_idname = "MFX_PT_mat_layers"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"
    bl_parent_id = "MFX_PT_material"
    def draw(self, context):
        layout = self.layout
        p = context.scene.mfx_props
        obj = context.object
        all_layers = context.scene.mfx_layers
        material = obj.active_material if obj else None
        owned = [i for i, layer in enumerate(all_layers) if layer_belongs_to_material(layer, material, obj)]
        orphaned = [i for i, layer in enumerate(all_layers) if layer_is_orphan(layer)]
        other_material_count = len(all_layers) - len(owned) - len(orphaned)
        layers_box = layout.box(); layers_box.label(text=f"PS 材质图层 · {len(owned)}/8 层", icon="NODE_MATERIAL")
        if not owned:
            layers_box.label(text="当前材质还没有图层", icon="INFO")
        for rank in range(len(owned) - 1, -1, -1):
            index = owned[rank]
            layer = all_layers[index]
            row = layers_box.row(align=True)
            row.prop(layer, "enabled", text="", icon="HIDE_OFF" if layer.enabled else "HIDE_ON", emboss=False)
            row.prop(layer, "color", text="")
            sel = row.operator("mfx.select_layer", text=layer.name, icon="NODE", depress=index == context.scene.mfx_layer_index)
            sel.index = index
            up_slot = row.row(align=True); up_slot.enabled = rank < len(owned) - 1
            up = up_slot.operator("mfx.move_layer", text="", icon="TRIA_UP")
            up.index = index; up.direction = 1
            down_slot = row.row(align=True); down_slot.enabled = rank > 0
            down = down_slot.operator("mfx.move_layer", text="", icon="TRIA_DOWN")
            down.index = index; down.direction = -1
            remove_op = row.operator("mfx.remove_layer", text="", icon="X")
            remove_op.index = index
        if orphaned:
            orphan_box = layers_box.box(); orphan_box.label(text=f"无效图层记录：{len(orphaned)}", icon="ERROR")
            for index in reversed(orphaned):
                row = orphan_box.row(align=True); row.label(text=all_layers[index].name, icon="GHOST_ENABLED")
                remove_op = row.operator("mfx.remove_layer", text="", icon="X"); remove_op.index = index
        if other_material_count:
            layers_box.label(text=f"另有 {other_material_count} 层属于其他材质", icon="MATERIAL_DATA")
        selected_layer = _layer_edit_target(context) if obj else None
        controls = layers_box.column()
        controls.enabled = selected_layer is not None
        controls.prop(p, "layer_blend_mode"); controls.prop(p, "layer_mask")
        if p.layer_mask in DIRECTIONAL_MASK_TYPES:
            direction_row = controls.row(align=True)
            direction_row.label(text="方向")
            direction_row.prop(p, "layer_mask_direction", text="", expand=True)
            if p.layer_mask_direction == "CUSTOM":
                controls.prop(p, "layer_mask_azimuth", slider=True)
                controls.prop(p, "layer_mask_elevation", slider=True)
        controls.prop(p, "layer_opacity", slider=True)
        controls.prop(p, "layer_color"); controls.prop(p, "layer_roughness"); controls.prop(p, "layer_strength"); controls.prop(p, "layer_pattern_scale")
        row = layers_box.row(align=True)
        row.operator("mfx.add_layer", text="添加层", icon="ADD")
        row.operator("mfx.update_layer", text="同步参数", icon="FILE_REFRESH")
        row.operator("mfx.remove_layer", text="移除所选", icon="REMOVE")
        if orphaned:
            layers_box.operator("mfx.clear_orphan_layers", text="清理无效记录", icon="TRASH")
        layers_box.label(text="眼睛切换可见性；不透明度、混合模式与遮罩可逐层编辑。", icon="INFO")


class MFX_PT_mat_manage(Panel):
    bl_label = "预设管理与分享"
    bl_idname = "MFX_PT_mat_manage"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"
    bl_parent_id = "MFX_PT_material"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        layout = self.layout
        p = context.scene.mfx_props
        box = layout.box(); box.label(text="存档与分享", icon="PACKAGE")
        row = box.row(align=True); row.operator("mfx.save_preset", text="导出JSON", icon="EXPORT"); row.operator("mfx.import_preset", text="导入JSON", icon="IMPORT")
        row = box.row(align=True); row.operator("mfx.export_blend_preset", text="导出.blend", icon="EXPORT"); row.operator("mfx.import_blend_preset", text="导入.blend", icon="IMPORT")
        box.operator("mfx.mark_asset", text="标记为资产", icon="ASSET_MANAGER")
        row = box.row(align=True)
        row.operator("mfx.export_team_pack", text="导出团队材质包", icon="PACKAGE")
        row.operator("mfx.import_team_pack", text="导入团队材质包", icon="IMPORT")
        if context.scene.mfx_recent:
            recent_box = layout.box(); recent_box.label(text="最近使用", icon="TIME")
            for index, entry in enumerate(context.scene.mfx_recent[:3]):
                op = recent_box.operator("mfx.apply_recent", text=entry.label, icon="FILE_REFRESH"); op.index = index


class MFX_PT_mat_texture(Panel):
    bl_label = "贴图与烘焙"
    bl_idname = "MFX_PT_mat_texture"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"
    bl_parent_id = "MFX_PT_material"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        layout = self.layout
        p = context.scene.mfx_props
        batch_box = layout.box(); batch_box.label(text="批量应用", icon="GROUP_VERTEX")
        row = batch_box.row(align=True)
        row.operator("mfx.apply_selected", text="所选物体", icon="GROUP_VERTEX")
        row.operator("mfx.apply_collection", text="活动集合", icon="OUTLINER_COLLECTION")
        row.operator("mfx.apply_scene", text="整个场景", icon="SCENE_DATA")
        batch_box.operator("mfx.random_assign", text="随机分配到所选物体", icon="MOD_PARTICLES")
        pbr_box = layout.box(); pbr_box.label(text="PBR贴图自动连接", icon="IMAGE_DATA")
        pbr_box.prop(p, "texture_dir", text="贴图目录"); pbr_box.prop(p, "include_subdirs")
        pbr_box.operator("mfx.import_pbr", icon="FILE_FOLDER")
        pbr_box.label(text="自动三向投影 · 无需 UV", icon="ORIENTATION_NORMAL")
        pbr_box.label(text="通道：颜色 / 粗糙度 / 金属度 / 法线 / 高度 / 环境遮蔽 / 自发光", icon="INFO")
        bake_box = layout.box(); bake_box.label(text="Cycles 烘焙", icon="RENDER_STILL")
        bake_box.prop(p, "bake_resolution"); bake_box.prop(p, "bake_path", text="贴图输出目录")
        bake_box.prop(p, "bake_device", text="Cycles 设备")
        bake_box.operator("mfx.bake", text="Cycles 烘焙 Base Color", icon="RENDER_STILL")
        bake_box.label(text="Blender 4.2 的材质烘焙由 Cycles 提供；GPU 需先在系统偏好中启用。", icon="INFO")


class MFX_PT_effects(Panel):
    bl_label = "特效"
    bl_idname = "MFX_PT_effects"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"
    def draw(self, context):
        layout = self.layout
        p = context.scene.mfx_props
        layout.prop(p, "effect_start_frame")
        layout.label(text="-1 = 从当前帧开始", icon="TIME")
        row = layout.row(align=True); row.prop(p, "effect_loop_mode", text="动画循环"); row.prop(p, "effect_easing", text="缓动")
        stack = layout.box(); stack.label(text=f"特效层堆栈 · {len(context.scene.mfx_effect_layers)} 层", icon="NODETREE")
        if not context.scene.mfx_effect_layers:
            stack.label(text="添加特效后可在此启用、停用和调节强度", icon="INFO")
        for index, layer in enumerate(context.scene.mfx_effect_layers):
            layer_box = stack.box()
            row = layer_box.row(align=True)
            row.prop(layer, "enabled", text=layer.name, toggle=True)
            if layer.blend_source_node:
                row.prop(layer, "blend_mode", text="")
            remove = row.operator("mfx.delete_effect_layer", text="删除", icon="X")
            remove.index = index
            if layer.effect_type != "FRACTURE":
                layer_box.prop(layer, "strength", text="强度", slider=True)
            row = layer_box.row(align=True)
            row.prop(layer, "loop_mode", text="循环")
            row.prop(layer, "easing", text="缓动")
            if layer.material_name and layer.emission_node:
                drive = row.operator("mfx.audio_drive", text="音频驱动", icon="SOUND")
                drive.layer_index = index
        draw_author_footer(layout)


class MFX_PT_fx_lightning(Panel):
    bl_label = "雷电特效"
    bl_idname = "MFX_PT_fx_lightning"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"
    bl_parent_id = "MFX_PT_effects"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        layout = self.layout
        p = context.scene.mfx_props
        bolt_box = layout.box(); bolt_box.label(text="生成独立曲线对象", icon="LIGHT")
        bolt_box.prop(p, "lightning_mode", text="模式")
        if p.lightning_mode == "TESLA":
            bolt_box.prop(p, "lightning_arc_count")
        else:
            bolt_box.prop(p, "lightning_branches")
            bolt_box.prop(p, "lightning_branch_depth")
        bolt_box.prop(p, "lightning_jitter")
        bolt_box.prop(p, "lightning_seed")
        bolt_box.prop(p, "lightning_color")
        bolt_box.prop(p, "lightning_strength")
        bolt_box.prop(p, "lightning_width")
        bolt_box.prop(p, "lightning_animate")
        if p.lightning_animate:
            bolt_box.prop(p, "lightning_duration")
        bolt_box.operator("mfx.lightning", icon="SHADERFX", text="生成雷电特效")
        bolt_box.label(text="起始帧可统一指定；曲线可单独编辑和渲染。", icon="INFO")


class MFX_PT_fx_surface(Panel):
    bl_label = "程序化表面特效"
    bl_idname = "MFX_PT_fx_surface"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"
    bl_parent_id = "MFX_PT_effects"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        layout = self.layout
        p = context.scene.mfx_props
        surface_box = layout.box(); surface_box.label(text="材质表面动态效果", icon="SHADERFX")
        surface_box.prop(p, "surface_effect", text="效果")
        surface_box.prop(p, "surface_effect_color")
        surface_box.prop(p, "surface_effect_strength")
        surface_box.prop(p, "surface_effect_frames")
        if p.surface_effect in {"FROST", "CORROSION", "HOLOGRAM", "FIRE", "GLITCH"}:
            surface_box.prop(p, "surface_effect_direction")
            if p.surface_effect_direction == "CUSTOM":
                surface_box.prop(p, "surface_effect_azimuth", slider=True)
                surface_box.prop(p, "surface_effect_elevation", slider=True)
        surface_box.operator("mfx.surface_effect", text="添加到当前材质", icon="ADD")
        surface_box.label(text="卡通着色需 EEVEE；轮廓光会创建独立描边对象。", icon="INFO")


class MFX_PT_fx_geometry(Panel):
    bl_label = "几何节点特效"
    bl_idname = "MFX_PT_fx_geometry"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"
    bl_parent_id = "MFX_PT_effects"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        layout = self.layout
        p = context.scene.mfx_props
        geometry_box = layout.box(); geometry_box.label(text="非破坏式几何动画", icon="MODIFIER")
        geometry_box.prop(p, "geometry_effect", text="效果")
        if p.geometry_effect in {"GROWTH", "WAVE"}:
            geometry_box.prop(p, "geometry_effect_direction")
            if p.geometry_effect_direction == "CUSTOM":
                geometry_box.prop(p, "geometry_effect_azimuth", slider=True)
                geometry_box.prop(p, "geometry_effect_elevation", slider=True)
            geometry_box.prop(p, "geometry_effect_strength")
        elif p.geometry_effect == "PARTICLES":
            geometry_box.prop(p, "geometry_particle_density")
            geometry_box.prop(p, "geometry_particle_size")
        geometry_box.prop(p, "geometry_effect_frames")
        geometry_box.operator("mfx.geometry_effect", text="添加几何节点修改器", icon="MODIFIER")


class MFX_PT_fx_dissolve(Panel):
    bl_label = "消散 / 碎裂重组"
    bl_idname = "MFX_PT_fx_dissolve"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"
    bl_parent_id = "MFX_PT_effects"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        layout = self.layout
        p = context.scene.mfx_props
        dissolve_box = layout.box(); dissolve_box.label(text="能量流与消散", icon="MOD_EXPLODE")
        dissolve_box.prop(p, "flow_frames")
        dissolve_box.prop(p, "surface_effect_direction", text="能量流方向")
        if p.surface_effect_direction == "CUSTOM":
            dissolve_box.prop(p, "surface_effect_azimuth", text="方位角", slider=True)
            dissolve_box.prop(p, "surface_effect_elevation", text="俯仰角", slider=True)
        dissolve_box.operator("mfx.energy_flow", text="添加能量流动", icon="FORCE_CHARGE")
        dissolve_box.prop(p, "dissolve_frames")
        dissolve_box.operator("mfx.dissolve", text="给当前材质添加消散动画", icon="SHADERFX")
        dissolve_box.label(text="碎裂重组", icon="MOD_EXPLODE")
        dissolve_box.prop(p, "fragment_count"); dissolve_box.prop(p, "fragment_seed"); dissolve_box.prop(p, "fragment_distance"); dissolve_box.prop(p, "fragment_frames")
        dissolve_box.operator("mfx.fracture_reassemble", text="碎裂并重组", icon="MOD_EXPLODE")
        dissolve_box.operator("mfx.restore_fractured", text="恢复原物体", icon="LOOP_BACK")


class MFX_PT_fx_audio(Panel):
    bl_label = "音频驱动"
    bl_idname = "MFX_PT_fx_audio"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"
    bl_parent_id = "MFX_PT_effects"
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        layout = self.layout
        p = context.scene.mfx_props
        audio_box = layout.box(); audio_box.label(text="WAV 音量写入关键帧", icon="SOUND")
        audio_box.prop(p, "audio_path", text="音频文件"); audio_box.prop(p, "audio_gain")
        audio_box.prop(p, "audio_key_step")
        audio_box.label(text="在堆栈中点选“音频驱动”将 WAV 音量写入发光强度关键帧。", icon="INFO")


class MFX_PT_fx_volume(Panel):
    bl_label = "体积特效"
    bl_idname = "MFX_PT_fx_volume"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"
    bl_parent_id = "MFX_PT_effects"
    def draw(self, context):
        layout = self.layout
        p = context.scene.mfx_props
        fog_box = layout.box(); fog_box.label(text="程序化体积 · 免烘焙（参数拖动即时生效）", icon="PARTICLES")
        fog_box.prop(p, "fog_density", slider=True); fog_box.prop(p, "fog_color"); fog_box.prop(p, "fog_noise_scale")
        fog_box.prop(p, "fog_animate")
        fog_box.prop(p, "volume_direction", text="方向")
        if p.volume_direction == "CUSTOM":
            fog_box.prop(p, "volume_azimuth", slider=True); fog_box.prop(p, "volume_elevation", slider=True)
        fog_box.operator("mfx.volume_fog", text="添加体积雾（包裹选中物体）", icon="VOLUME_DATA")
        weather_box = layout.box(); weather_box.label(text="天气粒子 · 参数拖动即时生效", icon="MOD_PARTICLES")
        weather_box.prop(p, "rain_snow_mode", text="类型")
        weather_box.prop(p, "rain_snow_count"); weather_box.prop(p, "rain_snow_area", slider=True)
        weather_box.prop(p, "volume_direction", text="方向")
        if p.volume_direction == "CUSTOM":
            weather_box.prop(p, "volume_azimuth", slider=True); weather_box.prop(p, "volume_elevation", slider=True)
        weather_box.operator("mfx.rain_snow", text="添加雨 / 雪", icon="WORLD")
        sim_box = layout.box(); sim_box.label(text="真实模拟 · Mantaflow", icon="PHYSICS")
        sim_box.prop(p, "volume_resolution", text="分辨率")
        sim_box.prop(p, "volume_frames")
        col = sim_box.column(align=True)
        col.prop(p, "volume_direction", text="方向")
        if p.volume_direction == "CUSTOM":
            col.prop(p, "volume_azimuth", slider=True); col.prop(p, "volume_elevation", slider=True)
        col.prop(p, "smoke_color"); col.prop(p, "smoke_density", slider=True)
        col.operator("mfx.volume_smoke", text="烟雾模拟（需播放 / 烘焙）", icon="MOD_FLUID")
        col.separator()
        col.prop(p, "volume_direction", text="方向·仅风偏（浮力原生向上）")
        if p.volume_direction == "CUSTOM":
            col.prop(p, "volume_azimuth", slider=True); col.prop(p, "volume_elevation", slider=True)
        col.prop(p, "fire_preset", text="色温"); col.prop(p, "fire_intensity", slider=True)
        col.operator("mfx.volume_fire", text="火焰模拟（需播放 / 烘焙）", icon="SHADERFX")
        col.separator()
        col.prop(p, "volume_direction", text="方向")
        if p.volume_direction == "CUSTOM":
            col.prop(p, "volume_azimuth", slider=True); col.prop(p, "volume_elevation", slider=True)
        col.prop(p, "liquid_color"); col.prop(p, "liquid_flow", text="初始状态")
        col.operator("mfx.volume_liquid", text="液体模拟（烘焙较重）", icon="MOD_FLUID")
        bake_state, bake_icon = _volume_bake_state_text(context)
        sim_box.label(text=bake_state, icon=bake_icon)
        sim_box.label(text="改分辨率/时长后自动失效旧缓存并在约 1 秒后自动重烘焙，无需手动操作。", icon="INFO")
        sim_box.label(text="缓存目录：//mfx_cache/，移除特效层即删域对象，缓存需手动清理。", icon="FILE_FOLDER")


class MFX_PT_model(Panel):
    bl_label = "模型 / CAD"
    bl_idname = "MFX_PT_model"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "R_blmaster"

    def draw(self, context):
        layout = self.layout
        props = context.scene.mfx_props
        box = layout.box(); box.label(text="导入模型", icon="IMPORT")
        box.operator("mfx.import_model", text="导入 STL / STEP / FBX / OBJ…", icon="FILE_FOLDER")
        export_box = layout.box(); export_box.label(text="场景导出（原材质页移入）", icon="EXPORT")
        export_box.prop(props, "export_path", text="模型导出目录")
        row = export_box.row(align=True)
        op = row.operator("mfx.export", text="GLB", icon="EXPORT"); op.format = "GLB"
        op = row.operator("mfx.export", text="FBX", icon="EXPORT"); op.format = "FBX"
        op = row.operator("mfx.export", text="USD", icon="EXPORT"); op.format = "USD"
        box.label(text="也支持 glTF、USD、Alembic 和 PLY", icon="INFO")

        box = layout.box(); box.label(text="四边面重拓扑", icon="MOD_REMESH")
        box.label(text="活动网格会保留；结果生成独立副本。", icon="DUPLICATE")
        box.prop(props, "model_target_faces", text="重构目标面数")
        if _exoside_available():
            box.label(text="检测到 Exoside QuadRemesher 引擎", icon="CHECKMARK")
            box.operator("mfx.quad_remesh_exoside", text="用 Exoside 引擎重构", icon="MOD_REMESH")
        box.label(text="结果面数接近目标值，算法不保证精确相等。", icon="INFO")
        box.prop(props, "model_preserve_sharp")
        box.prop(props, "model_preserve_boundary")
        box.prop(props, "model_preserve_attributes")
        box.prop(props, "model_smooth_normals")
        box.operator("mfx.quad_remesh", text="生成四边面副本（Quadriflow）", icon="MOD_REMESH")

        box = layout.box(); box.label(text="导出网格", icon="EXPORT")
        box.prop(props, "model_export_path", text="输出目录")
        row = box.row(align=True)
        for fmt in ("STL", "FBX", "OBJ", "GLB"):
            op = row.operator("mfx.export_model_mesh", text=fmt)
            op.format = fmt
        box.operator("mfx.export_step", text="导出 STEP 实体（供 Fusion 编辑）", icon="EXPORT")
        box.prop(props, "model_step_merge_coplanar")
        row = box.row(align=True)
        row.enabled = props.model_step_merge_coplanar
        row.prop(props, "model_step_merge_angle")

        box = layout.box(); box.label(text="Fusion 360 / STEP", icon="FILE_3D")
        box.label(text="STEP 为分面 B-rep；共面融合默认开启，同一平面在 Fusion 中为整面、无内部切割线。", icon="INFO")
        box.label(text="要求封闭流形网格；开放边或多个壳体需先修复/拆分。")
        box.label(text="结果不会重建参数化 CAD 特征树；高面数请先重拓扑减面。")
        draw_author_footer(layout)


CLASSES = (MFX_Favorite, MFX_Recent, MFX_MaterialLayer, MFX_EffectLayer, MFX_Preferences,
           MFX_OT_toggle_favorite, MFX_OT_apply_recent, MFX_OT_add_layer, MFX_OT_update_layer, MFX_OT_remove_layer,
           MFX_OT_select_layer, MFX_OT_move_layer, MFX_OT_clear_orphan_layers,
           MFX_OT_apply_preset, MFX_OT_apply_selected, MFX_OT_apply_collection, MFX_OT_apply_scene, MFX_OT_random_assign,
           MFX_OT_lightning, MFX_OT_dissolve, MFX_OT_fracture_reassemble,
           MFX_OT_energy_flow, MFX_OT_surface_effect, MFX_OT_geometry_effect,
           MFX_OT_restore_fractured, MFX_OT_delete_effect_layer, MFX_OT_import_pbr, MFX_OT_audio_drive, MFX_OT_bake, MFX_OT_export,
           MFX_OT_import_model, MFX_OT_quad_remesh, MFX_OT_quad_remesh_exoside, MFX_OT_export_model_mesh, MFX_OT_export_step,
           MFX_OT_import_preset, MFX_OT_mark_asset, MFX_OT_save_preset, MFX_OT_export_team_pack,
           MFX_OT_import_team_pack, MFX_OT_export_blend_preset, MFX_OT_import_blend_preset,
           MFX_OT_volume_fog, MFX_OT_rain_snow,
           MFX_OT_volume_smoke, MFX_OT_volume_fire, MFX_OT_volume_liquid,
           MFX_PT_material, MFX_PT_mat_layers, MFX_PT_mat_manage, MFX_PT_mat_texture,
           MFX_PT_effects, MFX_PT_fx_lightning, MFX_PT_fx_surface, MFX_PT_fx_geometry,
           MFX_PT_fx_dissolve, MFX_PT_fx_audio, MFX_PT_fx_volume, MFX_PT_model)

# ─────────────────────────────────────────────────────────────────────────────
# [生命周期] register/unregister：扩展的装载与卸载。
#   register：类批量注册 → Scene 挂 4 个 CollectionProperty + 1 个 PointerProperty
#   + 索引 IntProperty（扩展全部运行时状态都挂 Scene，随 .blend 存取）→
#   timer 补扫团队预设 → load_post 挂钩。unregister 严格逆序（del 属性、逆序
#   注销类、释放图标集合）——教学点：卸载不对称会在「重载扩展」时留幽灵属性
#   与重复注册类，Blender 控制台报 Warning 的根源多在此。

def register():
    load_preview_icons()
    for cls in CLASSES: bpy.utils.register_class(cls)
    bpy.types.Scene.mfx_props = bpy.props.PointerProperty(type=MFX_Preferences)
    bpy.types.Scene.mfx_layers = bpy.props.CollectionProperty(type=MFX_MaterialLayer)
    bpy.types.Scene.mfx_favorites = bpy.props.CollectionProperty(type=MFX_Favorite)
    bpy.types.Scene.mfx_recent = bpy.props.CollectionProperty(type=MFX_Recent)
    bpy.types.Scene.mfx_effect_layers = bpy.props.CollectionProperty(type=MFX_EffectLayer)
    bpy.types.Scene.mfx_layer_index = IntProperty(name="当前图层", default=0)
    bpy.app.timers.register(rebuild_preset_items, first_interval=0)  # 注册期 bpy.data 受限，启用完成后补扫团队预设
    bpy.app.handlers.load_post.append(_mfx_on_load_post)

def unregister():
    if _mfx_on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_mfx_on_load_post)
    del bpy.types.Scene.mfx_layer_index
    del bpy.types.Scene.mfx_recent
    del bpy.types.Scene.mfx_effect_layers
    del bpy.types.Scene.mfx_favorites
    del bpy.types.Scene.mfx_layers
    del bpy.types.Scene.mfx_props
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
    global PREVIEW_COLLECTION
    if PREVIEW_COLLECTION is not None:
        previews.remove(PREVIEW_COLLECTION)
        PREVIEW_COLLECTION = None
    rebuild_preset_items()

if __name__ == "__main__": register()
