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

## ✨ 项目做什么

本项目专门面向**从天地图获取、没有坐标系的行政区划 EPS 图**：提取图中的区划面，使用用户提供的可信边界数据进行空间配准，再输出 GeoPackage 和质量检查图件。

主要流程是一张图纸、一份参考边界、一个全局变换。工具不会直接把参考数据的 CRS 赋给 EPS 页面坐标；没有足够共同边界或其他定位依据时会停止并提示复核。

### 功能特点

- 🧭 **聚焦天地图** — 项目名称、默认配置和案例都围绕天地图行政区划 EPS。
- ✂️ **提取区划矢量** — 读取 EPS 的填充面或边界线，保留可核查的图面几何。
- 📍 **按参考边界定位** — 支持整幅同范围配准，或使用经过核实的共同边界弧段。
- 📦 **交付可检查结果** — 输出行政区面、参考与配准边界、QC 指标和叠加图。

## 🎯 适用范围

| 输入 | 支持情况 |
|---|---|
| 天地图导出的无坐标行政区划 EPS | **主要使用场景** |
| 结构完整的矢量 PDF 行政区划图 | 可作为兼容输入；仓库案例仍以天地图 EPS 为准 |
| 扫描件、栅格地图、SVG、DXF 或一般绘图文件 | 不属于当前入口支持范围 |

如果输入本身已有可靠 CRS，应在 GIS 软件中正常重投影，无需使用本项目。

## 🚀 快速开始

> 环境要求：**Python 3.11**。Windows 命令使用 PowerShell。处理 EPS 还需安装 Ghostscript。

### 1. 克隆并安装依赖

```powershell
git clone https://github.com/zhuangcg/tianditu-eps-boundary-registration.git
cd tianditu-eps-boundary-registration
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS/Linux：用 `python3.11 -m venv .venv` 创建环境，后续把 `.venv\Scripts\python.exe` 换为 `./.venv/bin/python`。

### 2. 安装 Ghostscript

从 [Ghostscript 官方下载页](https://ghostscript.com/releases/)安装，并确认命令可用：

```powershell
gswin64c -version
```

矢量 PDF 不需要 Ghostscript。若 EPS 中的行政区名称已转曲且需要 OCR，可额外安装：

```powershell
.\.venv\Scripts\python.exe -m pip install rapidocr-onnxruntime==1.4.4
```

### 3. 创建案例配置

```powershell
New-Item -ItemType Directory -Force runs | Out-Null
Copy-Item templates/config.example.yaml runs/my-case.yaml
```

编辑 `runs/my-case.yaml`，至少填写：

```yaml
source_map: "D:/maps/tianditu-districts.eps"
reference_boundary: "D:/gis/reference.gpkg"
reference_layer: boundaries
admin_level: district
source_scope: same_extent
output_dir: "runs/my-case/output"
work_dir: "runs/my-case/work"
```

`reference_layer` 在参考 GeoPackage 含多个图层时填写。`same_extent` 用于源图与参考边界范围相同的情况；局部图只有在存在**经核实的共同边界弧段**时才使用 `shared_boundary`。两者都不满足时，流程会停止，不会把内陆图强行贴到上级边界。

### 4. 检查输入并运行

```powershell
.\.venv\Scripts\python.exe scripts/inspect_environment.py --config runs/my-case.yaml
.\.venv\Scripts\python.exe scripts/run.py --config runs/my-case.yaml --intent "提取区级边界；图面范围与参考区界相同"
.\.venv\Scripts\python.exe scripts/check_output_manifest.py runs/my-case/output --config runs/my-case.yaml
```

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
