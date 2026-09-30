<div align="center">

<h2>🗺️ 天地图 EPS 行政区划边界配准</h2>

**把天地图导出的无坐标行政区划 EPS 图，转换成可复核的 GIS 矢量边界**

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![输入](https://img.shields.io/badge/输入-天地图%20EPS-2b6cb0.svg)](#-适用范围)
[![输出](https://img.shields.io/badge/输出-GeoPackage-38a169.svg)](#-输出与质量检查)
[![用途](https://img.shields.io/badge/用途-科研制图-orange.svg)](#️-准确性与使用限制)

*专注天地图行政区划图，配准结果附带可检查的矢量数据与质量记录。*

[🚀 快速开始](#-快速开始) · [🖼️ 案例预览](#️-案例预览) · [🛡️ 准确性与使用限制](#️-准确性与使用限制) · [English](README.en.md)

</div>

---

> [!CAUTION]
> **仅用于科研制图和探索性分析。** 输出不是标准地图、标注地图原件、法定界线或测绘成果，不能替代原始地图数据。配准误差不可能为零，也不承诺达到某一精度。结果受参考边界准确性与时效、EPS 图面要素复杂程度、制图概化、可用共同边界长度和人工复核质量影响。参考外边界不能独立验证内部行政区界。每次使用都应检查 `qc.json` 和 `overlay.png`，并遵守源地图与参考数据的使用许可。

> [!IMPORTANT]
> **运行前先核实两份输入。** 源 EPS/PDF 没有地理 CRS；参考 SHP/GPKG 必须是目标区域、具有可信 CRS 的边界。不能用两份原始 bbox 求交来证明同范围，也不能用同名地区或用户确认代替拟合后的几何复验。证据不足会进入 `REVIEW_*`，此时不交付最终 GPKG。

> [!WARNING]
> **批量预览、空名和 Mode C 补面都需按状态解释。** `batch_preview.gpkg` 只代表已处理城市；`REGISTERED_REVIEW_NAMES` 表示几何已配准但名称未核准；Mode C 新增参考面积没有源图证据。不要把这些产物描述成完整、已核名的省级成果。

## ✨ 项目做什么

本项目面向**无坐标系的行政区划矢量 EPS/PDF 图**，以天地图 EPS 为主要案例：提取图中的区划面，使用用户提供的可信边界数据进行空间配准，再输出 GeoPackage 和质量检查图件。矢量 PDF 可指定 `source_page`；扫描件不适用。

主要流程是一张图纸、一份参考边界、一个全局变换。工具不会直接把参考数据的 CRS 赋给 EPS 页面坐标；没有足够共同边界或其他定位依据时会停止并提示复核。

### 功能特点

- 🧭 **聚焦天地图** — 项目名称、默认配置和案例都围绕天地图行政区划 EPS。
- ✂️ **提取区划矢量** — 读取 EPS 的填充面或边界线，保留可核查的图面几何。
- 📍 **按参考边界定位** — 支持整幅同范围配准，或使用经过核实的共同边界弧段。
- 🧩 **按需批量合并** — 显式 manifest 可逐城市处理 EPS/PDF，并在全局 QC 后合并。
- 📦 **交付可检查结果** — 输出行政区面、参考与配准边界、QC 指标和叠加图。
- 🛑 **证据不足即复核** — 范围、色带内缘、同色离岛、必要名称、配准多解和 Mode C 补面归属各有暂停状态；暂停时不留下部分交付。

## 🎯 适用范围

| 输入 | 支持情况 |
|---|---|
| 天地图导出的无坐标行政区划 EPS | **主要使用场景** |
| 结构完整的矢量 PDF 行政区划图 | 可作为兼容输入；仓库案例仍以天地图 EPS 为准 |
| 扫描件、栅格地图、SVG、DXF 或一般绘图文件 | 不属于当前入口支持范围 |

如果输入本身已有可靠 CRS，应在 GIS 软件中正常重投影，无需使用本项目。

## 🗂️ 配准必须准备两类数据

请把“待配准图”和“参考边界”分开准备；它们不是可以互相替代的多种输入格式：

| 数据 | 必需文件 | 要求 |
|---|---|---|
| 待配准地图 | 天地图导出的无坐标行政区划 `.eps`（主要场景）；结构完整的矢量 `.pdf` 仅作兼容输入 | 图面应包含要提取的行政边界；EPS 页面坐标本身没有地理坐标系 |
| 参考边界 | 与地图属于**同一城市或目标区域**、带有正确空间坐标系的 `.shp` 或 `.gpkg` | 必须能提供地理定位依据；优先选与图面同范围、行政级别相符的边界。Shapefile 的 `.shp/.shx/.dbf/.prj` 需一并保留；GeoPackage 的坐标系应已正确写入 |

`reference_boundary` 填第二类数据的路径。GeoPackage 含多个图层时，再填写 `reference_layer`。两份数据不必使用相同 CRS，程序会以参考数据 CRS 交付；但参考 CRS 必须已知且正确。局部地图只有在与参考数据存在经核实的共同边界弧段或其他可靠定位依据时才能配准；“同一城市”本身不足以定位没有共同边界的内陆图。不要把无坐标 EPS 的页面坐标直接指定为参考数据的 CRS。

程序会列出参考图层、要素组成和范围，并提供图面与参考对照图。源图没有 CRS，无法预先按坐标 bbox 判断相交；范围不清会暂停，请用户确认。若 PDF/EPS 用有宽度的填充面绘制边界，优先采用经确认的行政填色面边界并排除色带；只有色带内缘唯一且可判定朝向目标行政面时才使用该内缘，否则暂停。同色小岛有多个可能归属面时也不会按距离猜测。拟合后还须通过完整范围 IoU、双向残差和变换唯一性检查，未通过不会交付 GPKG。要求名称齐全时，未解决面可通过裁片复核；Mode C 补面归属不唯一时停止。

## 🚀 快速开始

> 环境要求：安装 Skill 需要 Node.js/npm（提供 `npx`）；运行脚本需要 **Python 3.11**。Windows 命令使用 PowerShell。处理 EPS 还需安装 Ghostscript。

### 1. 用 npx 安装到 Codex

```powershell
npx skills@latest add zhuangcg/tianditu-eps-boundary-registration --skill tianditu-eps-boundary-registration --agent codex --global --copy --yes
```

这是 Agent Skills 的 GitHub 安装方式，会把 Skill 与所需脚本放到 Codex 的用户级目录；不需要手动克隆仓库。安装完成后重新打开 Codex 会话。`npx` 会按需运行 [skills CLI](https://www.npmjs.com/package/skills)。

### 2. 安装 Python 运行依赖

在你存放输入数据和输出结果的工作目录创建独立环境。依赖清单直接从 GitHub 读取，无需下载或克隆整个仓库：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r https://raw.githubusercontent.com/zhuangcg/tianditu-eps-boundary-registration/main/requirements.txt
```

macOS/Linux 使用 `python3.11 -m venv .venv`，并将 `.venv\Scripts\python.exe` 换为 `./.venv/bin/python`。若只想手动运行源码，也可从 GitHub 下载仓库后按 `requirements.txt` 安装；这是可选方式。

### 3. 安装 Ghostscript（仅处理 EPS 时需要）

从 [Ghostscript 官方下载页](https://ghostscript.com/releases/)安装，并确认命令可用：

```powershell
gswin64c -version
```

矢量 PDF 不需要 Ghostscript。若 EPS 中的行政区名称已转曲且需要 OCR，可额外安装：

```powershell
.\.venv\Scripts\python.exe -m pip install rapidocr-onnxruntime==1.4.4
```

### 4. 创建案例配置

以下命令按 Codex 默认用户目录设置 Skill 路径；若安装时使用了自定义 `CODEX_HOME`，请按安装位置调整。

```powershell
New-Item -ItemType Directory -Force runs | Out-Null
$skillRoot = Join-Path $HOME ".codex\skills\tianditu-eps-boundary-registration"
Copy-Item "$skillRoot\templates\config.example.yaml" runs/my-case.yaml
```

编辑 `runs/my-case.yaml`，至少填写：

```yaml
source_map: "D:/maps/shenzhen-districts.eps"
reference_boundary: "D:/gis/shenzhen-boundary.gpkg"
reference_layer: null # GPKG 有多个空间图层时填写实际图层名
admin_level: district
source_scope: same_extent
user_intent: "提取深圳市区级边界；图面与深圳市参考边界同范围"
output_dir: "runs/my-case/output"
work_dir: "runs/my-case/work"
```

示例路径和意图仅作格式演示，实际运行时须替换成用户的数据与真实目标。`reference_boundary` 必须是同一城市或目标区域、已定义正确 CRS 的 `.shp` 或 `.gpkg`。`same_extent` 用于源图与参考边界同范围；局部图仅在有经核实的共同边界弧段时使用 `shared_boundary`。`scope_confirmation` 只记录用户已明确确认的范围，不能由 Agent 根据文件名自行填写。二者都不满足时，流程会停止，不会把内陆图强行贴到上级边界。

如果图上次要街道文字与目标区级填色面的级别判断冲突，先核查填色与标注；确有依据时可在 `scope_review.admin_level_conflict` 记录判断。此字段只解释级别冲突，不能替代用户的范围确认。

### 5. 检查输入并运行

```powershell
$skillRoot = Join-Path $HOME ".codex\skills\tianditu-eps-boundary-registration"
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\inspect_environment.py" --config runs/my-case.yaml
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\run.py" --config runs/my-case.yaml
# 仅在 run.py 返回交付成功后执行：
& ".\.venv\Scripts\python.exe" "$skillRoot\scripts\check_output_manifest.py" runs/my-case/output --config runs/my-case.yaml
```

只有 `run.py` 成功交付后才执行最后一行；进入复核状态时先处理 `work/review.json`。`--intent` 只适用于单图，且应传用户真实表述；批量配置请使用 manifest 的 `defaults` 和各 case 的 `options`。

## 🧭 Agent 调用与复核约定

Agent 应从当前安装的 `SKILL.md` 定位脚本，以用户实际请求选择模式：单图用 `config.example.yaml`；**仅在明确要求多城市提取合并时**用 `batch.example.yaml`。先看预览和参考元数据，再按 `##VERDICT` 决定后续动作；已有的用户确认直接记录，不重复询问。遇到证据冲突时暂停，不能靠改标签、降低门槛或换一个形似轮廓来制造通过结果。

| 状态 | 处理方式 |
|---|---|
| `REVIEW_SCOPE` / `NO_COMMON_BOUNDARY` | 看范围对照图和参考图层；证据仍不足时请用户确认或提供有定位依据的参考。 |
| `REVIEW_EXTRACTION` | 核对源图、候选图和颜色/描边；色带无唯一内缘、离岛归属不明时保持暂停。 |
| `REVIEW_NAMES` | 看 `work/review_names.json` 及裁片，只录入有图面证据的名称。 |
| `REVIEW_REGISTRATION` | 核对完整范围 IoU、双向 P90 与多解叠加图；用户确认地区也不能绕过几何复验。 |
| `REVIEW_CONFORMANCE` | 核查 Mode C 补面归属；没有唯一图面依据时不发布 Mode C。 |
| `REGISTERED_REVIEW_NAMES` | GPKG 已交付，但名称不完整；按 `qc.json` 报告空名面，不能称为已核名成果。 |

> [!NOTE]
> **自动放行数值仅控制交付，不是精度保证。** 同范围模式暂以 IoU ≥ 0.95、完整边界双向 P90 均不超过参考面积等效半径的 1%、且变换唯一作为自动交付条件。实际使用仍须查看 `overlay.png`、名称状态、内部区界和参考数据质量。

## 🖼️ 案例预览

| 深圳区级行政区 EPS | 罗湖街道级行政区 EPS |
|:---:|:---:|
| ![深圳案例：天地图 EPS 加参考边界后得到无填充实线矢量结果](docs/images/shenzhen-example.png) | ![罗湖案例：天地图 EPS 加参考边界后得到无填充实线矢量结果](docs/images/luohu-example.png) |
| 同范围配准；提取 10 个区。外轮廓采样距离中位数 12.75 m、P90 72.99 m。没有同级区界参考，不能据此确认内部区界准确。 | 使用约 13.76 km 的已核实共同边界弧段；采样距离中位数 10.90 m、P90 23.63 m。约 73.34% 的源外轮廓采样点未参与拟合。 |

以上数值仅描述对应案例和数据版本，不是其他地图的精度承诺或通过阈值。原 EPS 和参考数据未随仓库发布；复现案例需要自行准备有使用授权的数据。

## 📦 输出与质量检查

| 文件 | 内容 |
|---|---|
| `registered.gpkg` | 配准后的行政区面、配准外轮廓和参考边界 |
| `qc.json` | 输入范围判定、提取方式、名称检查、拟合参数和边界采样指标 |
| `overlay.png` | 源图提取边界与参考边界的叠加核查图 |
| `run.log` | 本次运行摘要 |

默认交付保留源图提取几何。只有确认源图与参考边界完全同范围、并确实需要外轮廓吻合时，才考虑高级 Mode C；该模式会新增没有源图证据的面积，详见[方法说明](references/methodology.md)。

## 🧩 多城市批量合并

用户明确要求多个城市提取并合并时，从 `templates/batch.example.yaml` 建立一份 manifest：统一市级参考图层，每张 EPS/PDF 指定 `parent_id` 和可选页码，通用参数写入 `defaults`，个别城市的复核参数写入 `options`。执行 `python scripts/run.py --config <batch.yaml>`。每个城市保留 Mode R 的 `registered.gpkg` 和 Mode C 的 `conformed.gpkg`；`province_qc.json` 与 `city_adjacency_qc.csv` 检查覆盖、重叠和相邻城市公共边界。只有参考图层全部城市通过单图及全局 QC 才发布 `province_conformed.gpkg`；只处理部分城市时输出 `batch_preview.gpkg`。详见[批量操作说明](references/batch-hierarchical.md)。

> [!WARNING]
> **`parent_id` 不是范围已确认的证据。** 每城仍需核对源图与参考；只在用户明确确认该城同范围时，才把原答复写入该 case 的 `options.scope_confirmation`。任一城市停在复核状态时，先看 `work/batch_review.json` 和该城 `work/<parent_id>/review.json`，不要发布省级合并成果。部分城市通过得到的 `batch_preview.gpkg` 不能称为全省成果。

## 🛡️ 准确性与使用限制

- 配准误差不可能消失；精度取决于参考边界质量、EPS 要素复杂程度、图面概化、共同边界长度和复核质量。
- 参考外边界只能约束整幅位置与外轮廓，不能单独验证内部行政区界。
- 边界距离是采样近似值，不是连续曲线的解析 Hausdorff 距离，也不是通用验收标准。
- 不得把输出当作标注地图原件、法定边界或测绘成果。

## ❓ 常见问题

**能否把没有共同边界的内陆图配准到整个城市或省界？**

不能仅凭上级外边界确定内陆地图位置；需要共同边界、已知控制点或其他可靠定位依据。

**没有识别到区划名称怎么办？**

工具保留稳定的 `admin_id`，名称不确定时不猜测；检查 OCR 状态和 `qc.json` 后再人工复核。

**参考边界准确就代表内部区界也准确吗？**

不代表。内部区界需要独立的同级参考数据才能验证。

## 🗂️ 项目结构

```text
tianditu-eps-boundary-registration/
├── scripts/       # 提取、配准、运行与结果检查
├── templates/     # 通用配置和运行日志模板
├── examples/      # 深圳、罗湖案例参数
├── docs/images/   # README 案例图
├── references/    # 方法、输入契约与 QC 定义
├── tests/         # 自动化测试
├── SKILL.md       # 面向智能体的精简工作规范
├── README.md      # 中文说明
└── README.en.md   # English documentation
```

## 📚 更多文档

| 文档 | 内容 |
|---|---|
| [SKILL.md](SKILL.md) | 天地图 EPS 工作流程与必要边界条件 |
| [通用配置模板](templates/config.example.yaml) | 输入、参考边界、输出目录配置 |
| [案例说明](docs/cases.md) | 深圳与罗湖示例数据口径 |
| [方法说明](references/methodology.md) | 提取、范围判断与配准细节 |
| [QC 指标](references/qc-spec.md) | 质量检查指标定义 |
| [输入契约](references/input-and-name-contract.md) | 输入字段和命名规则 |

</div>
