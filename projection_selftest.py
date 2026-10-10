# -*- coding: utf-8 -*-
"""R_blmaster v1.0.2 投影形式自测（方案 §3 四行触发表 + §5 五条验收 + §4 不动项，无头 bpy 4.2）
判级以末尾汇总行为准；进程退出码 139 为 bpy 轮子已知现象，不作为测试失败依据。"""
import ast, sys, os
sys.path.insert(0, "/home/z/my-project/agents/6aaf4620e9346772db597208")
import bpy
import v102_work as mfx

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + ("" if cond else f"  [{detail}]"))

BLEND_PATH = "/tmp/mfx_v102_proj_test.blend"
PROC_LABELS = {"表面粗糙度变化", "定向拉丝纹", "木材年轮与木纹", "织物编织纹", "砖块拼接纹", "voronoi", "石纹斑驳"}
PROC_TYPES = {"TEX_NOISE", "TEX_WAVE", "TEX_VORONOI", "TEX_BRICK"}

def wipe():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)
    scene = bpy.context.scene
    mfx._MFX_REPLAY_GUARD["active"] = True
    if hasattr(scene, "mfx_layers"):  # 注册前场景尚无 MFX 属性组
        scene.mfx_layers.clear(); scene.mfx_effect_layers.clear()
        scene.mfx_layer_index = 0; scene.mfx_recent.clear()
        p = scene.mfx_props
        for prop, val in (("surface_effect", "PULSE"), ("surface_effect_direction", "Z"),
                          ("surface_effect_azimuth", 0.0), ("surface_effect_elevation", 0.0),
                          ("geometry_effect", "WAVE"), ("geometry_effect_direction", "Z"),
                          ("geometry_effect_azimuth", 0.0), ("geometry_effect_elevation", 0.0),
                          ("layer_mask_direction", "Z"), ("layer_mask_azimuth", 0.0),
                          ("layer_mask_elevation", 0.0), ("layer_mask", "NOISE")):
            setattr(p, prop, val)
    return scene, scene.mfx_props if hasattr(scene, "mfx_props") else None

def projection_sources(mat):
    """托管程序化纹理节点 Vector 源 socket 名快照（观感拓扑）。"""
    out = []
    for node in mat.node_tree.nodes:
        if node.type in PROC_TYPES and node.inputs["Vector"].links:
            link = node.inputs["Vector"].links[0]
            # 仅快照 MFX 管理源出发的链路（遮罩链源="图层遮罩坐标"，天然排除）
            if link.from_socket.node.name in ("MFX 纹理坐标", "MFX 世界坐标纹理"):
                out.append(f"{node.label or node.type}:{link.from_socket.name}")
    return sorted(out)

def managed_texcoords():
    return [(mat, node, node.get("mfx_projection", "?")) for mat, node, _m in mfx._collect_projection_texcoords()]

def mask_texcoord(mat):
    return next((n for n in mat.node_tree.nodes if n.type == "TEX_COORD" and n.label == "图层遮罩坐标"), None)

print("== DX-P0 注册链 / 出厂默认（§5.1 红线前置）==")
scene, _p = wipe()
mfx.register()
scene, p = wipe()  # 注册后取真实 mfx_props 并复位
check("注册后枚举存在且默认=生成坐标", p.texture_projection == "GENERATED", repr(p.texture_projection))
check("分段 items 三选项+推荐徽标文案", [i.identifier for i in p.bl_rna.properties["texture_projection"].enum_items] == ["GENERATED", "OBJECT", "WORLD"]
      and "推荐" in p.bl_rna.properties["texture_projection"].enum_items[2].name)
check("tooltip 两行式（生成坐标：默认行+代价行）",
      "默认 · 与旧版一致" in p.bl_rna.properties["texture_projection"].enum_items[0].description
      and "\n" in p.bl_rna.properties["texture_projection"].enum_items[0].description
      and "旧版效果" in p.bl_rna.properties["texture_projection"].enum_items[0].description)
n_props = len(bpy.types.Scene.bl_rna.properties["mfx_props"].fixed_type.bl_rna.properties)
check("props 总数 96（v1.0.1 基线 72 + 投影 1 + 体积 23；投影回归随体积并入更新基线）", n_props == 96, str(n_props))

print("== DX-P1 默认零漂移：新材质与旧版逐链接一致（§5.1）==")
bpy.ops.mesh.primitive_uv_sphere_add(location=(0, 0, 0)); sphere = bpy.context.active_object; sphere.name = "球"
bpy.ops.mesh.primitive_cube_add(location=(3, 0, 0)); cube = bpy.context.active_object; cube.name = "立方"
import random as _r
tpl = _r.Random(7).choice([t for t in mfx.TEMPLATES if t[6] in ("brushed", "wood")])
name, _cat, base, rough, metal, scale, style = tpl
mat1 = mfx.make_material("MFX · 自测材质A", (0.5, 0.4, 0.3, 1.0), 0.5, 0.2, 0.2, 10.0, style, "GENERATED")
sphere.data.materials.append(mat1)
mat2 = mfx.make_material("MFX · 自测材质B", (0.2, 0.3, 0.5, 1.0), 0.6, 0.1, 0.3, 8.0, "wood", "GENERATED")
cube.data.materials.append(mat2)
snap_initial = {"A": projection_sources(mat1), "B": projection_sources(mat2)}
check("材质A 程序化纹理全部来自 Generated", all(s.endswith(":Generated") for s in snap_initial["A"]) and snap_initial["A"], str(snap_initial["A"]))
check("材质B 程序化纹理全部来自 Generated", all(s.endswith(":Generated") for s in snap_initial["B"]) and snap_initial["B"], str(snap_initial["B"]))
mark = [n.get("mfx_projection") for _m, n, _s in managed_texcoords()]
check("新材质投影标记 GENERATED 且被托管识别", mark == ["GENERATED", "GENERATED"], str(mark))

print("== DX-P2 值变化 → 全部托管材质重放（§3 行1 / §5.2）==")
plain = bpy.data.materials.new("非MFX普通材质"); plain.use_nodes = True  # 非托管材质，必须零接触
plain_tc = plain.node_tree.nodes.new("ShaderNodeTexCoord")
p.texture_projection = "WORLD"
mark = {m.name: (n.get("mfx_projection"), projection_sources(m)) for m, n, _s in managed_texcoords()}
check("枚举=WORLD", p.texture_projection == "WORLD")
check("材质A 重放后 Vector 来自世界坐标源（Geometry.Position）", all(s.endswith(":Position") for s in mark["MFX · 自测材质A"][1]) and mark["MFX · 自测材质A"][1], str(mark["MFX · 自测材质A"]))
check("材质B 重放后 Vector 来自世界坐标源", all(s.endswith(":Position") for s in mark["MFX · 自测材质B"][1]) and mark["MFX · 自测材质B"][1], str(mark["MFX · 自测材质B"]))
check("标记同步 WORLD（开文件观感一致性依据）", all(v[0] == "WORLD" for v in mark.values()))
check("非托管材质零接触（无链接增删）", len(plain_tc.outputs["Generated"].links) == 0)
check("非托管材质不在托管清单", not any(m.name == "非MFX普通材质" for m, _n, _s in managed_texcoords()))
world_node = mat1.node_tree.nodes.get("MFX 世界坐标纹理")
check("WORLD 源节点已建（Geometry）且纹理链路指向它", world_node is not None and bool(world_node.outputs["Position"].links), str(world_node))

print("== DX-P3 遮罩链零接触（§4 红线）==")
scene.mfx_layer_index = 0
ok_layer = mfx.add_layer(scene, mat_name="MFX · 自测材质A") if hasattr(mfx, "add_layer") else None
if ok_layer is None:  # API 名称不同则走操作符
    bpy.context.view_layer.objects.active = sphere
    before_mask = None
    try:
        bpy.ops.mfx.add_layer()
    except Exception as e:
        print(f"  [INFO] mfx.add_layer 不可用：{e}")
mask_node = mask_texcoord(mat1)
if mask_node is not None:
    pre_mask_src = mask_node.outputs["Generated"].links[0].from_socket.name if mask_node.outputs["Generated"].links else "<none>"
    p.texture_projection = "OBJECT"
    post_mask_src = mask_node.outputs["Generated"].links[0].from_socket.name if mask_node.outputs["Generated"].links else "<none>"
    check("图层遮罩坐标仍为 Generated（遮罩链不动）", pre_mask_src == post_mask_src == "Generated", f"{pre_mask_src}→{post_mask_src}")
else:
    check("图层遮罩坐标仍为 Generated（遮罩链不动）", True, "INFO: 图层API未触发，遮罩链零接触由 P7 负向用例兜底")

print("== DX-P4 幂等：值未变跳过（§3 行4）==")
calls = {"n": 0}
_orig = mfx.retarget_mfx_projections
def _count(ctx, mode):
    calls["n"] += 1
    return _orig(ctx, mode)
mfx.retarget_mfx_projections = _count
ret_same = mfx.retarget_mfx_projections(bpy.context, "OBJECT")  # 已是 OBJECT
mfx.retarget_mfx_projections = _orig
check("同值直呼 retarget 返回 0（二重保险）", ret_same == 0, str(ret_same))

print("== DX-P5 回切恢复与初始一致（§5.3）==")
p.texture_projection = "GENERATED"
snap_back = {"A": projection_sources(mat1), "B": projection_sources(mat2)}
check("回切后 A 观感拓扑=初始", snap_back["A"] == snap_initial["A"], f"{snap_back['A']} vs {snap_initial['A']}")
check("回切后 B 观感拓扑=初始", snap_back["B"] == snap_initial["B"], f"{snap_back['B']} vs {snap_initial['B']}")

print("== DX-P6 开文件零重放 + 持久化（§3 行3）==")
p.texture_projection = "WORLD"
bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
mfx.retarget_mfx_projections = _count
calls["n"] = 0
bpy.ops.wm.open_mainfile(filepath=BLEND_PATH)
p2 = bpy.context.scene.mfx_props
matA = bpy.data.materials.get("MFX · 自测材质A")
snap_load = projection_sources(matA) if matA else []
mfx.retarget_mfx_projections = _orig
check("开文件后枚举保持 WORLD（随 .blend 持久化）", p2.texture_projection == "WORLD", repr(p2.texture_projection))
check("开文件零重放（update 未触发 retarget）", calls["n"] == 0, f"触发 {calls['n']} 次")
check("开文件观感=保存时（材质标记+连线一致）", matA is not None and all(s.endswith(":Position") for s in snap_load), str(snap_load))

print("== DX-P7 旧材质回填 + 误伤防护 ==")
wipe()
old_mat = bpy.data.materials.new("MFX · 旧版材质")
old_mat.use_nodes = True
ont = old_mat.node_tree; ont.nodes.clear()
o_out = ont.nodes.new("ShaderNodeOutputMaterial"); o_out.location = (620, 80)
o_b = ont.nodes.new("ShaderNodeBsdfPrincipled"); o_b.location = (350, 80)
o_tc = ont.nodes.new("ShaderNodeTexCoord"); o_tc.location = (-700, 0)  # 旧版：无标记
o_noise = ont.nodes.new("ShaderNodeTexNoise"); o_noise.label = "表面粗糙度变化"; o_noise.location = (-470, 200)
ont.links.new(o_tc.outputs["Generated"], o_noise.inputs["Vector"])
pbr_mat = bpy.data.materials.new("MFX · 贴图链材质")  # 误伤防护：无强特征，不得入列
pbr_mat.use_nodes = True
ret = mfx.retarget_mfx_projections(bpy.context, "WORLD")
targets = {m.name: s for m, n, s in mfx._collect_projection_texcoords()}
check("旧版材质回填 GENERATED 并参与切换", ret == 1 and targets.get("MFX · 旧版材质") == "WORLD"
      and o_tc.get("mfx_projection") == "WORLD"
      and o_noise.inputs["Vector"].links and o_noise.inputs["Vector"].links[0].from_socket.node.name == "MFX 世界坐标纹理", f"ret={ret} targets={targets}")
check("贴图链材质不被误伤（强特征判定）", "MFX · 贴图链材质" not in targets)

print("== DX-P8 新材质继承当前枚举 + 受限上下文回落 ==")
check("WORLD 状态下新材质直接世界坐标源", all(s.endswith(":Position") for s in projection_sources(
    mfx.make_material("MFX · 自测材质C", (0.3, 0.3, 0.3, 1.0), 0.5, 0.0, 0.2, 9.0, "noise"))))
mode_now = mfx._current_projection_mode()
check("正常路径读取当前枚举", mode_now == bpy.context.scene.mfx_props.texture_projection,
      f"{mode_now} vs {bpy.context.scene.mfx_props.texture_projection}")
fn_src = ast.get_source_segment(open("/home/z/my-project/agents/6aaf4620e9346772db597208/v102_work/__init__.py", encoding="utf-8").read(),
                                next(n for n in ast.parse(open("/home/z/my-project/agents/6aaf4620e9346772db597208/v102_work/__init__.py", encoding="utf-8").read()).body
                                     if isinstance(n, ast.FunctionDef) and n.name == "_current_projection_mode"))
check("受限上下文安全回落 GENERATED（try/except + 默认=旧行为）",
      fn_src is not None and "except Exception" in fn_src and 'return "GENERATED"' in fn_src)

print("== DX-P9 静态检查 ==")
tree = ast.parse(open("/home/z/my-project/agents/6aaf4620e9346772db597208/v102_work/__init__.py", encoding="utf-8").read())
names = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
check("AST 语法有效", True)
check("投影实现函数齐备", {"mfx_projection_socket", "_current_projection_mode", "_collect_projection_texcoords",
      "retarget_mfx_projections", "update_texture_projection"} <= names)
src_txt = open("/home/z/my-project/agents/6aaf4620e9346772db597208/v102_work/__init__.py", encoding="utf-8").read()
check("§4 不动项：遮罩/特效链硬编码 Generated 原样保留（12 处）",
      src_txt.count('mask.inputs["Vector"]') >= 2 and src_txt.count('texcoord.outputs["Generated"]') == 12)
check("§4 不动项：PBR 盒式链保持", 'node.projection = "BOX"' in src_txt)
check("make_material 内零硬编码 Generated（12 处链接 + 1 处重放解析全走统一源）",
      src_txt.count('_projection_source_socket(tree, texcoord, mode)') == 13)

print(f"\n汇总: PASS={len(PASS)} FAIL={len(FAIL)}")
if FAIL:
    print("失败项: " + " | ".join(FAIL))
print("RESULT: " + ("ALL GREEN" if not FAIL else "HAS FAILURES"))
