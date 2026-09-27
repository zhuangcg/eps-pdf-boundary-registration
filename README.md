## 从天地图 EPS 到可核查的 GIS 边界

[English](README.en.md)

面向从天地图获取的无坐标 EPS 行政区划图，也支持矢量 PDF。工具先提取图面行政区，再依据可信参考边界估计页面坐标到地图坐标的全局变换，最后输出可复核的 GeoPackage 和 QC 图件。

> [!CAUTION]
> **仅用于科研制图和探索性分析。** 输出结果不是标准地图、标注地图原件、法定界线或测绘成果，不能替代原始地图数据。配准误差不可能为零，也不承诺达到某一精度。实际表现取决于参考边界的准确性与时效、EPS 图面要素的复杂程度、制图概化、共同边界长度及人工复核质量。参考外边界不能独立验证内部区界。请逐案检查 `qc.json` 和 `overlay.png`，并遵守源地图与参考数据的使用许可。

### 从输入到结果

三幅图依次展示：**EPS 矢量图 + 参考边界数据 = 配准后的矢量结果**。中间和右侧均以无填充实线展示边界，右侧直接给出结果、不放图例；具体数据与质量检查信息见 GeoPackage 和 QC 文件。

![深圳案例流程图：EPS 矢量图 + 参考边界数据 = 配准后的矢量结果](docs/images/shenzhen-example.png)

工具当前支持 EPS 和矢量 PDF；不支持 SVG、DXF 或栅格地图。EPS 转换需要 Ghostscript。源文件和参考数据不随仓库分发。

### 安装

需要 Python 3.11；依赖清单按 Python 3.11 环境锁定。以下命令使用 Windows PowerShell。

先从 GitHub 克隆或下载仓库，并在终端进入 `eps-vector-boundary-registration` 根目录，然后运行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS/Linux：用 `python3.11 -m venv .venv` 创建环境，并将后续命令中的 `.venv\Scripts\python.exe` 替换为 `./.venv/bin/python`。复制配置时使用 `mkdir -p runs` 和 `cp templates/config.example.yaml runs/my-case.yaml`。

若处理 EPS，请从 [Ghostscript 官方下载页](https://ghostscript.com/releases/)安装 Ghostscript，并确保 `gswin64c`（Windows）或 `gs`（macOS/Linux）可从终端调用。检查命令：

```powershell
gswin64c -version
```

矢量 PDF 不需要 Ghostscript。若行政区名称已转曲、需要 OCR，可额外安装可选依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install rapidocr-onnxruntime==1.4.4
```

### 运行一个新案例

从仓库根目录复制通用配置，然后把输入路径和图层改成自己的文件。参考 GPKG 若含多个图层，应填写 `reference_layer`。路径建议使用绝对路径。

```powershell
New-Item -ItemType Directory -Force runs | Out-Null
Copy-Item templates/config.example.yaml runs/my-case.yaml
```

在 `runs/my-case.yaml` 中至少填写：

```yaml
source_map: "D:/maps/my-map.eps"
reference_boundary: "D:/gis/reference.gpkg"
reference_layer: reference_layer
admin_level: district
source_scope: same_extent
output_dir: "runs/my-case/output"
work_dir: "runs/my-case/work"
```

按真实关系设置 `admin_level` 和 `source_scope`：完整同范围用 `same_extent`；有可信连续共同外边界时用 `shared_boundary`，并提供两处经核实地标；没有共同边界时流程会停止，不会把内陆图硬套到上级边界。若无法判断，保留 `auto` 并根据复核提示确认。

```powershell
.\.venv\Scripts\python.exe scripts/inspect_environment.py --config runs/my-case.yaml
.\.venv\Scripts\python.exe scripts/run.py --config runs/my-case.yaml --intent "提取区级边界；整幅源图与参考边界覆盖同一范围"
.\.venv\Scripts\python.exe scripts/check_output_manifest.py runs/my-case/output --config runs/my-case.yaml
```

典型 Mode R 输出为 `registered.gpkg`、`qc.json`、`overlay.png` 和 `run.log`。只有确认 EPS 与参考边界同范围时才考虑 Mode C；Mode C 贴合外轮廓所增加的面积没有源图证据，必须与保留源图几何的 Mode R 分开解释。

### 两个案例

#### 深圳区级图：整幅外边界配准

统一入口从图面提取 10 个区面并识别 10 个名称。该次 QC 的外轮廓采样中位距离为 12.75 m、P90 为 72.99 m；区界没有同级参考数据，不能据此认定内部区界准确。数值只描述此案例与此数据版本。

#### 罗湖街道图：局部图与共同边界弧段

![罗湖案例流程图：EPS 矢量图 + 参考边界数据 = 配准后的街道边界结果](docs/images/luohu-example.png)

该案例用约 13.76 km 的已核实共同边界弧段定位。弧段采样中位距离为 10.90 m、P90 为 23.63 m；约 73.34% 的源图外轮廓采样点未参与拟合，参考数据也不能验证街道内部界线。数值不是其他地图的通过阈值。

案例参数与计算口径见[案例说明](docs/cases.md)和[实验记录](docs/experiments.md)。原 EPS 与参考 GPKG 未包含在仓库中；复跑示例需自行准备具有使用授权的对应数据。

### 配准边界与复核

- 一个全局变换作用于所有提取面；不会把参考 CRS 直接贴到页面坐标上。
- 完整同范围用外轮廓拟合；局部图只用经核实的共同边界弧段。上级边界不能单独确定内部地图的位置。
- `overlay.png` 用于观察错位；`qc.json` 记录范围判定、提取方法、名称覆盖率、采样距离和未受参考约束的比例。
- 边界采样指标是近似值，不是连续曲线的解析 Hausdorff 距离，也不是精度保证。
- 图件采用 Helvetica、12 pt 基础字号和 1.5 pt 默认线宽；流程示意图不放图例，由分栏标题说明各阶段。

### 文档

- [Skill 工作规范](SKILL.md)
- [通用配置模板](templates/config.example.yaml)
- [输入与名称契约](references/input-and-name-contract.md)
- [方法说明](references/methodology.md)
- [QC 指标定义](references/qc-spec.md)
- [实验复现记录](docs/experiments.md)
