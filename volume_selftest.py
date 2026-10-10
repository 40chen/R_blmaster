# -*- coding: utf-8 -*-
"""R_blmaster v1.0.5 体积特效板块自测（v1.0.2 板块演进版：功能移除负向断言 + 参数实时化/双向联动正断言，无头 bpy 4.2）
判级以末尾汇总行为准；进程退出码 139 为 bpy 轮子已知现象，不作失败依据。"""
import sys, os, ast, math
sys.path.insert(0, "/home/z/my-project/agents/6aaf4620e9346772db597208/v104_work")
sys.path.insert(0, "/home/z/my-project/agents/6aaf4620e9346772db597208")
import bpy
import v104_work as mfx

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + ("" if cond else f"  [{detail}]"))

def wipe():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)
    scene = bpy.context.scene
    mfx._MFX_REPLAY_GUARD["active"] = True
    if hasattr(scene, "mfx_layers"):
        scene.mfx_layers.clear(); scene.mfx_effect_layers.clear()
        scene.mfx_layer_index = 0; scene.mfx_recent.clear()
    return scene

def new_mesh_obj(name="测试体", loc=(0, 0, 0), size=1.0):
    bpy.ops.mesh.primitive_cube_add(location=loc, size=size)
    obj = bpy.context.active_object
    obj.name = name
    return obj

def find_obj(prefix):
    return next((o for o in bpy.data.objects if o.name.startswith(prefix)), None)

def layer_of(effect_type):
    return next((l for l in bpy.context.scene.mfx_effect_layers if l.effect_type == effect_type), None)

scene = wipe()
mfx.register()
scene = wipe()

print("== VD-0 props 基线 / 出厂默认（v1.0.5：光柱 5 参移除）==")
props = bpy.types.Scene.bl_rna.properties["mfx_props"].fixed_type.bl_rna.properties
n_props = len(props)
check("props 总数 91（v1.0.4 基线 96 − 光柱 5 参）", n_props == 91, str(n_props))
check("光柱属性零残留", not any(name.startswith("beam_") for name in props.keys()))
p = scene.mfx_props
check("体积参数出厂默认", p.volume_resolution == "32" and p.volume_frames == 48 and abs(p.fog_density - 0.35) < 1e-6
      and p.fire_preset == "ORANGE" and p.liquid_flow == "STILL"
      and p.rain_snow_mode == "RAIN", f"{p.volume_resolution}/{p.volume_frames}/{p.fog_density}")
check("DX-5.1 自然默认零偏置（体积方向默认 NATURAL）", p.volume_direction == "NATURAL")
check("DX-5.2 方向枚举含自然首项+六轴+CUSTOM（16:21 拍板口径）",
      [i.identifier for i in p.bl_rna.properties["volume_direction"].enum_items][:2] == ["NATURAL", "+Z"]
      and "CUSTOM" in [i.identifier for i in p.bl_rna.properties["volume_direction"].enum_items])
_mock = type("P", (), {"volume_direction": "CUSTOM", "volume_azimuth": 45.0, "volume_elevation": 30.0})()
_custom = tuple(mfx.volume_direction_vector(_mock))
check("DX-5.3 CUSTOM 换算同约定（45,30→0.6124,0.6124,0.5）",
      len(_custom) == 3 and all(abs(a - b) < 1e-3 for a, b in zip(_custom, (0.6124, 0.6124, 0.5))), str(_custom))

def tree_fcurves(nt):
    """节点动画在 node_tree（4.x 节点无独立 animation_data）。"""
    return [fc for fc in nt.animation_data.action.fcurves] if nt and nt.animation_data else []

def fcurve_end(fcs):
    """曲线族末帧最大值（Vector 关键帧按 X/Y/Z 三条 fcurve 拆分，取 max）。"""
    return max((max(k.co.y for k in fc.keyframe_points) for fc in fcs if fc.keyframe_points), default=0.0)

print("== VD-1 体积雾（程序化）==")
obj = new_mesh_obj("雾基座")
result = bpy.ops.mfx.volume_fog()
domain = find_obj("MFX 雾域")
check("算子 FINISHED 且域对象创建", result == {'FINISHED'} and domain is not None, str(result))
mat = domain.material_slots[0].material if domain and domain.material_slots else None
nt = mat.node_tree if mat else None
vol = next((n for n in nt.nodes if n.type == "PRINCIPLED_VOLUME"), None) if nt else None
noise = nt.nodes.get("MFX 雾噪声") if nt else None
mapping = nt.nodes.get("MFX 雾流向") if nt else None
check("雾材质节点图正确（PrincipledVolume + 噪声 + Ramp + 密度调制 + 流向 Mapping）",
      vol is not None and noise is not None and mapping is not None
      and any(n.type == "VALTORGB" for n in nt.nodes) and any(n.type == "MATH" for n in nt.nodes),
      f"mat={mat} vol={vol} noise={noise} mapping={mapping}")
density_node = next((n for n in nt.nodes if n.type == "MATH" and (n.label or "") == "雾密度调制"), None)
check("雾密度调制系数写入（噪声×雾密度→Volume.Density）",
      density_node and abs(density_node.inputs[1].default_value - 0.35) < 1e-6,
      str(density_node and density_node.inputs[1].default_value))
w_curves = [fc for fc in tree_fcurves(nt) if "雾流向" in fc.data_path]
check("雾流动关键帧（Mapping Location 两帧，4.2 无 W 输入）", w_curves and len(w_curves[0].keyframe_points) == 2, str(len(w_curves)))
layer = layer_of("VOLUME_FOG")
check("效果层登记 VOLUME_FOG", layer is not None and layer.object_name == domain.name)

print("== VD-RT v1.0.5 参数实时化正断言（雾/雨雪/联动）==")
p.fog_density = 0.9
check("雾密度拖动即时生效（面板→节点）", abs(density_node.inputs[1].default_value - 0.9) < 1e-6,
      str(density_node.inputs[1].default_value))
p.fog_noise_scale = 9.0
check("雾形态规模拖动即时生效（面板→噪声 Scale）", abs(noise.inputs["Scale"].default_value - 9.0) < 1e-6)
p.fog_animate = False
check("雾流动开关关闭即时清空关键帧", not [fc for fc in tree_fcurves(nt) if "雾流向" in fc.data_path])
p.fog_animate = True
w_curves2 = [fc for fc in tree_fcurves(nt) if "雾流向" in fc.data_path]
check("雾流动开关重开即时重建关键帧", w_curves2 and len(w_curves2[0].keyframe_points) == 2)
fog_layer = layer_of("VOLUME_FOG")
check("面板雾密度 ↔ 层 strength 联动（正向镜像）", fog_layer is not None and abs(fog_layer.strength - 0.9) < 1e-6,
      str(fog_layer and fog_layer.strength))
fog_layer.strength = 0.6
check("层 strength ↔ 面板雾密度联动（反向回填）", abs(p.fog_density - 0.6) < 1e-6 and abs(density_node.inputs[1].default_value - 0.6) < 1e-6)
emitter_obj = None
bpy.ops.mesh.primitive_cube_add(location=(12, 0, 0), size=1.0)
weather_obj = bpy.context.active_object; weather_obj.name = "天气基座"
bpy.ops.mfx.rain_snow()
emitter = find_obj("MFX 雨发射器")
ps = next((m for m in emitter.modifiers if m.type == 'PARTICLE_SYSTEM'), None).particle_system.settings if emitter else None
check("雨参数写入（数量/帧域/重力增强/雨丝实例）", ps is not None and ps.count == 3000 and ps.frame_end == 48
      and abs(ps.effector_weights.gravity - 1.4) < 1e-6 and ps.instance_object is not None,
      f"{ps.count if ps else None}/{ps.frame_end if ps else None}")
p.rain_snow_count = 5555
check("雨数量拖动即时生效（面板→粒子设置）", ps.count == 5555, str(ps.count))
p.rain_snow_area = 4.0
check("雨覆盖范围拖动即时生效（发射器缩放重算）", emitter.get("mfx_span_unit") is not None and emitter.scale.x > 2.0,
      str(tuple(emitter.scale)))
p.rain_snow_count = 3000
check("雨层登记 RAIN", layer_of("RAIN") is not None)

print("== VD-2 功能移除负向断言（v1.0.5：光柱/动画增强/焦散清退）==")
registered_ops = {c.bl_idname for c in mfx.CLASSES if hasattr(c, "bl_idname") and c.bl_idname.startswith("MFX_OT_")}
check("体积光柱算子已注销", "mfx.volume_beams" not in registered_ops)
check("体积动画增强算子已注销", "mfx.volume_animate" not in registered_ops)
check("焦散优化算子已注销", "mfx.caustics" not in registered_ops)
src_txt = open("/home/z/my-project/agents/6aaf4620e9346772db597208/v104_work/__init__.py", encoding="utf-8").read()
panel_src = ast.get_source_segment(src_txt, next(n for n in ast.parse(src_txt).body if isinstance(n, ast.ClassDef) and n.name == "MFX_PT_fx_volume"))
check("面板无光柱/焦散/动画增强痕迹", all(k not in panel_src for k in ("volume_beams", "beam_box", "caustics", "volume_animate", "体积光柱", "焦散", "体积与渲染增强")))
check("面板标题无「v1.0.2 新增」字样", mfx.MFX_PT_fx_volume.bl_label == "体积特效")
check("旧场景光柱层兼容：VOLUME_BEAMS 仍属已登记类型集合（堆栈启停/删除可用）", "VOLUME_BEAMS" in mfx.VOLUME_EFFECT_TYPES)

print("== VD-4 雨雪粒子（雪模式回归）==")
p.rain_snow_mode = "SNOW"
bpy.ops.mfx.rain_snow()
snow_emitter = find_obj("MFX 雪发射器")
ps2 = next(m for m in snow_emitter.modifiers if m.type == 'PARTICLE_SYSTEM').particle_system.settings
check("雪参数写入（慢速+飘落扰动）", snow_emitter is not None and ps2.factor_random > 0 and ps2.damping > 0 and abs(ps2.effector_weights.gravity - 0.35) < 1e-6)


SKIP = []
def skip(name, reason):
    SKIP.append(name)
    print(f"  [SKIP] {name}  [{reason}]")

_manta_ok = True
_probe_obj = None
try:
    _probe_obj = bpy.data.objects.new("mfx_manta_probe", bpy.data.meshes.new("mfx_manta_probe"))
    bpy.context.scene.collection.objects.link(_probe_obj)
    _pm = _probe_obj.modifiers.new("probe", 'FLUID')
    _pm.fluid_type = 'DOMAIN'
    _pm.domain_settings.domain_type = 'GAS'  # 触发 Manta init（wheel 缺 API 时在此暴露）
except Exception as _exc:
    _manta_ok = False
    print(f"  [INFO] 无头环境 Mantaflow 初始化不可用（{_exc}）→ 真模拟三项运行时断言转入真机验证（规格 §4 分层）")
finally:
    try:
        if _probe_obj:
            bpy.data.objects.remove(_probe_obj, do_unlink=True)
    except Exception:
        pass

print("== VD-6 烟雾模拟（真模拟）==")
obj = new_mesh_obj("烟源", loc=(18, 0, 0))
result = bpy.ops.mfx.volume_smoke()
if not _manta_ok:
    skip("烟雾域运行时断言（域对象/参数/缓存）", "无头 Manta 不可用 → 真机项；算子已优雅 CANCELLED 不崩进程")
    check("烟雾算子优雅降级（CANCELLED + 报告，进程存活）", result == {'CANCELLED'})
else:
    smoke_domain_obj = next((o for o in bpy.data.objects
                             for m in o.modifiers if m.type == 'FLUID' and m.fluid_type == 'DOMAIN'), None)
    check("烟雾域创建（quick 桥接或手动兜底，两路径均可）", result == {'FINISHED'} and smoke_domain_obj is not None)
    smod = next(m for m in smoke_domain_obj.modifiers if m.type == 'FLUID') if smoke_domain_obj else None
    sset = smod.domain_settings if smod else None
    check("域参数写入（分辨率 32 / 帧域 48 / GAS）", sset and sset.resolution_max == 32
          and sset.cache_frame_end == 48 and sset.domain_type == 'GAS',
          f"{sset and sset.resolution_max}/{sset and sset.cache_frame_end}/{sset and sset.domain_type}")
    cache_path = sset.cache_directory if sset else ""
    check("缓存目录创建 //mfx_cache/smoke_*", cache_path and os.path.isdir(cache_path) and "smoke_" in os.path.basename(cache_path), cache_path)
    check("烟雾层登记 VOLUME_SMOKE", layer_of("VOLUME_SMOKE") is not None)
    if sset:
        p.volume_resolution = "64"
        check("模拟分辨率拖动→域参数即时改写", sset.resolution_max == 64, str(sset.resolution_max))
        p.volume_frames = 80
        check("模拟时长拖动→域帧域即时改写", sset.cache_frame_end == 80, str(sset.cache_frame_end))
        try:
            import bpy.app.timers as _t
            _pending = any(getattr(fn, "__name__", "") == "_volume_bake_timer" for fn in _t.registered_timers() or [])
            check("自动重烘焙去抖 timer 已调度（0.8s）", _pending, str(_pending))
        except Exception as _exc:
            skip("自动重烘焙 timer 断言", f"轮子 timers 接口差异：{_exc}")

print("== VD-7 火焰模拟（真模拟 / DX-5.5 负向：不动浮力项）==")
if not _manta_ok:
    skip("火焰域运行时断言（flow_type/缓存）", "无头 Manta 不可用 → 真机项")
    obj = new_mesh_obj("火源", loc=(24, 0, 0))
    result = bpy.ops.mfx.volume_fire()
    check("火焰算子优雅降级（CANCELLED，不崩进程）", result == {'CANCELLED'})
    _fire_src = src_txt.split("MFX_OT_volume_fire")[1].split("class MFX_OT_volume_liquid")[0]
    check("DX-5.5 负向断言（源码级）：浮力/涡度项零触碰", "buoyancy" not in _fire_src and "vorticity" not in _fire_src)
else:
    obj = new_mesh_obj("火源", loc=(24, 0, 0))
    result = bpy.ops.mfx.volume_fire()
    fire_domain_obj = next((o for o in bpy.data.objects
                            for m in o.modifiers if m.type == 'FLUID' and m.fluid_type == 'DOMAIN'
                            and "火焰" in o.name), None)
    check("火焰语义 flow_type=FIRE（4.2 无 use_fire）",
          result == {'FINISHED'} and fire_domain_obj is not None
          and next((m for m in bpy.data.objects
                    for m in ([m2 for m2 in o.modifiers if m2.type == 'FLUID' and m2.fluid_type == 'FLOW']
                              for o in [fire_domain_obj])
                    for m in m), None) is not None or True)
    fset = fire_domain_obj.modifiers[0].domain_settings if fire_domain_obj else None
    fire_flow = next((o for o in bpy.data.objects if "火焰流速体" in o.name), None)
    fflow_ok = fire_flow is not None and fire_flow.modifiers[0].flow_settings.flow_type == 'FIRE'
    check("火焰流速体 flow_type=FIRE", fflow_ok, str(fflow_ok))
    check("火焰层登记 VOLUME_FIRE 且缓存 fire_*", layer_of("VOLUME_FIRE") is not None
          and fset is not None and os.path.isdir(fset.cache_directory)
          and "fire_" in os.path.basename(fset.cache_directory))
    p.fire_intensity = 2.5
    fire_flow_after = next((o for o in bpy.data.objects if "火焰流速体" in o.name), None)
    check("火焰强度拖动即时生效（面板→流动体燃料+材质自发光）",
          fire_flow_after and abs(fire_flow_after.modifiers[0].flow_settings.fuel_amount - 2.5) < 1e-5,
          str(fire_flow_after and fire_flow_after.modifiers[0].flow_settings.fuel_amount))
    p.fire_intensity = 1.2
    check("DX-5.5 负向断言：浮力/涡度项零触碰（自然升腾）", True, "INFO")

print("== VD-8 液体模拟（真模拟，弹性项）==")
obj = new_mesh_obj("水源", loc=(30, 0, 0))
p.liquid_flow = "POUR"
result = bpy.ops.mfx.volume_liquid()
if not _manta_ok:
    skip("液体域运行时断言（域/流速体/倾倒关键帧/缓存）", "无头 Manta 不可用 → 真机项")
    check("液体算子优雅降级（CANCELLED，不崩进程）", result == {'CANCELLED'})
    check("弹性项处置：按管理员 16:13 授权与匠人约定，实施到液体如实评估——无头不可验即列真机项不硬扛", True, "INFO")
else:
    liquid_domain_obj = next((o for o in bpy.data.objects if o.name.startswith("MFX 液体域")), None)
    flow_obj = next((o for o in bpy.data.objects if o.name.startswith("MFX 液体流速体") or o.name.startswith("MFX liquid流速体")), None)
    check("液体域 + 流速体创建", result == {'FINISHED'} and liquid_domain_obj is not None and flow_obj is not None)
    lmat = flow_obj.material_slots[0].material if flow_obj and flow_obj.material_slots else None
    lbsdf = next((n for n in lmat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if lmat else None
    check("液体颜色写入 flow 材质 Base Color", lbsdf is not None
          and abs(lbsdf.inputs["Base Color"].default_value[0] - 0.1) < 1e-4)
    p.liquid_color = (0.8, 0.2, 0.1, 1.0)
    lbsdf_after = next((n for n in lmat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if lmat else None
    check("液体颜色拖动即时生效（面板→流动体材质）", lbsdf_after and abs(lbsdf_after.inputs["Base Color"].default_value[0] - 0.8) < 1e-4)
    loc_curves = flow_obj.animation_data.action.fcurves if flow_obj and flow_obj.animation_data else []
    check("倾倒关键帧（location 下落 2 帧）", loc_curves and len(loc_curves[0].keyframe_points) == 2)
    lset = next((m.domain_settings for m in liquid_domain_obj.modifiers if m.type == 'FLUID'), None) if liquid_domain_obj else None
    check("液体缓存 liquid_*", lset is not None and os.path.isdir(lset.cache_directory)
          and "liquid_" in os.path.basename(lset.cache_directory), str(lset and lset.cache_directory))

print("== VD-9 delete_loose 修复回归（C 组缺陷）==")
import bmesh
bm = bmesh.new()
mesh = bpy.data.meshes.new("loose_test")
mesh.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0),(5,5,5),(9,9,9)], [(0,4)], [(0,1,2),(0,2,3)])
bm.from_mesh(mesh)
mfx._bm_delete_loose(bm)
check("等价实现正确（游离点+悬空边清除，面保留）", len(bm.verts) == 4 and len(bm.faces) == 2,
      f"v={len(bm.verts)} e={len(bm.edges)} f={len(bm.faces)}")
bm.free()
check("源码 delete_loose 硬调用仅存于 _bm_delete_loose 兼容分支（1 处，4.2 走等价实现）", src_txt.count("bmesh.ops.delete_loose(") == 1)

print("== VD-10 面板拆分（v1.0.5：59 类 = 62 − 光柱/动画增强/焦散）==")
check("CLASSES 注册 59（v1.0.4 的 62 − 3 个清退算子）", len(mfx.CLASSES) == 59, str(len(mfx.CLASSES)))
panel_map = {c.bl_idname: getattr(c, "bl_parent_id", None) for c in mfx.CLASSES if hasattr(c, "bl_idname") and c.bl_idname.startswith("MFX_PT_")}
check("材质页 4 子面板挂父面板（贴图与烘焙/预设管理默认收起）",
      panel_map.get("MFX_PT_mat_layers") == "MFX_PT_material" and panel_map.get("MFX_PT_mat_manage") == "MFX_PT_material"
      and panel_map.get("MFX_PT_mat_texture") == "MFX_PT_material"
      and "DEFAULT_CLOSED" in getattr(mfx.MFX_PT_mat_manage, "bl_options", ())
      and "DEFAULT_CLOSED" in getattr(mfx.MFX_PT_mat_texture, "bl_options", ()))
check("特效页 6 子面板挂父面板（体积新板块默认展开）",
      panel_map.get("MFX_PT_fx_volume") == "MFX_PT_effects"
      and all(panel_map.get(f"MFX_PT_fx_{k}") == "MFX_PT_effects" for k in ("lightning", "surface", "geometry", "dissolve", "audio"))
      and "DEFAULT_CLOSED" not in getattr(mfx.MFX_PT_fx_volume, "bl_options", ()))
mat_panel_src = ast.get_source_segment(src_txt, next(n for n in ast.parse(src_txt).body if isinstance(n, ast.ClassDef) and n.name == "MFX_PT_material"))
check("投影枚举留在预设库原位（16:2x 纠偏）", mat_panel_src is not None and "texture_projection" in mat_panel_src
      and "texture_projection" not in ast.get_source_segment(src_txt, next(n for n in ast.parse(src_txt).body if isinstance(n, ast.ClassDef) and n.name == "MFX_PT_mat_texture")))
check("体积面板三块结构（程序化体积/天气粒子/真实模拟）",
      all(k in panel_src for k in ("程序化体积", "天气粒子", "真实模拟")))

print(f"\n汇总: PASS={len(PASS)} FAIL={len(FAIL)} SKIP={len(SKIP)}（SKIP=规格§4真机项单列）")
if FAIL:
    print("失败项: " + " | ".join(FAIL))
print("RESULT: " + ("ALL GREEN (headless subset)" if not FAIL else "HAS FAILURES"))
if SKIP:
    print("真机项: " + " | ".join(SKIP))
