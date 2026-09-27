---
name: eps-vector-boundary-registration
description: Register CRS-free EPS/PDF administrative vector maps against a trusted projected boundary. Census fills, strokes, text and images; extract filled faces or polygonize a selected stroke network; resolve administrative level and shared-boundary evidence; attach only map-backed names when available; deliver Mode R and optional same-extent Mode C with QC.
---

## EPS 矢量行政边界提取与配准

当前可运行入口是 `python scripts/run.py --config <run.yaml>`，支持 EPS 和矢量 PDF。SVG、DXF 与栅格地图尚未接入此入口。页面点坐标没有 CRS；必须先从可靠的共同外边界估计全局变换，再赋予输出 CRS。源数据若已有可靠 CRS，直接使用 GIS 重投影。

### 用途与精度声明

交付结果仅用于科研制图与探索性分析，不能作为标准地图、标注地图原件、法定界线或测绘成果。明确说明配准误差不可能为零，不承诺特定精度；结果受参考边界的准确性与时效、EPS 图面要素复杂程度、制图概化、共同边界长度及人工复核质量影响。参考外边界不能独立验证内部行政界线。每次交付都应提醒用户核查 `qc.json` 和 `overlay.png`，并确认源数据许可允许相应使用。

### 先判定任务

1. 读取用户提示词与显式配置，识别目标行政级别和源图与参考边界的关系。默认 `admin_level: auto`、`source_scope: auto`。显式要求优先；EPS 文件名、旧标题、图面文字只是线索。相互冲突或无法判断时写 `work/review.json`，请用户判定后再运行。
2. 将两者关系定为 `same_extent`（完整同范围）、`shared_boundary`（有可信共同外边界弧段）或 `no_common_boundary`。行政级别可为街道、区、市、省、国；关系由实际几何证据决定。旧值 `partial_parent` 等价于 `shared_boundary`。
3. `no_common_boundary` 立即停止地理配准。只有一个内陆城市轮廓和国界时，上级国界不能确定城市的位置；需要共同边界、已知控制点或其他定位依据。不得把内部边界对整个国界做无意义拟合。
4. 同范围允许 Mode R，且仅在要求外轮廓严格吻合时追加 Mode C。有共同弧段只允许 Mode R；使用经过核实的地标种子，随后由连续共同弧段约束全局变换。内部界线没有同级参考时始终标记为未独立验证。

### 一次普查与提取

运行入口先执行矢量保真转换和页面普查，记录填充、描边、闭合路径、线型、文字和嵌入图像，并缓存 `work/census.json` 与原图预览。EPS 依赖 Ghostscript；PDF 直接读取。请检查预览是否确实包含待提取的行政边界。

`extraction.method: auto` 优先采用可信的填充行政面；无可用填充时，按描边颜色、宽度、虚线样式选择闭合网络，用 `polygonize_full` 面化。单色相邻面保留各自的原始路径边界。道路、水系、图框、文字轮廓属于竞争候选；当两个网络、或填充与描边都同样可信时停止，检查预览及 `work/review_extraction_*.json`，再显式设 `method`、`keep_colours_rgb` 或 `keep_strokes`。颜色不能直接等同于行政面。

默认不补接断线。只有用户在配置中明确设置页面坐标容差 `snap_tolerance_pt` 时才允许端点桥接；每条桥记录在提取报告和 QC。无法形成可信行政面时停止。可选的 `expected_admin_polygon_count`、`keep_colours_rgb`、`split_colours_rgb` 是当前图纸的复核条件，不是通用默认。

### 名称与配准

名称顺序为原生文字、一次整页 OCR、仅对缺失或冲突面做局部裁片复核。OCR 缓存由 PDF 内容哈希和 DPI 标识。区、市、街道等采用同一证据规则；不能根据形状、面积、熟悉的地理位置或面顺序猜名。若图上确认没有名称，交付稳定 `admin_id` 和空 `admin_name`，QC 写明“未发现图面名称”；没有标注时不输出 `map_labels` 图层。若 OCR 环境不可用，应报告“未核查”，不得声称无名称。旧 `require_map_annotation: true` 等价于 `names.mode: required`。

使用完整同范围轮廓或经过核实的共同弧段拟合一个全局相似变换；只有残差改善达到配置门槛且尺度合理时才考虑仿射。所有面使用同一矩阵。拟合和距离计算在米制投影进行，交付回参考数据的 CRS。图上比例尺只作交叉核对。Mode C 单独输出参考外轮廓约束结果，记录新增面积、归属和内部接缝断言；它不能替代保留源图几何的 Mode R。

### 命令与交付

```powershell
python scripts/inspect_environment.py --config <run.yaml>
python scripts/run.py --config <run.yaml> --intent "提取街道边界，源图与市界共线一段"
python scripts/check_output_manifest.py <output_dir> --config <run.yaml>
```

配置从 [通用模板](templates/config.example.yaml) 复制；[深圳](examples/shenzhen.yaml)和[罗湖](examples/luohu.yaml)只保存各自图纸的已核对参数。对应原图与参考数据不随仓库分发。重复输入复用已验证的 EPS 转换、普查、提取、OCR 和完整交付；不同或未完成的交付不会被静默覆盖。新实验写项目内 `runs/`。

Mode R 固定交付 `registered.gpkg`、`qc.json`、`overlay.png`、`run.log`。GPKG 含 `administrative_units`、`registered_outline`、`reference_outline`，仅在接受图面标注时有 `map_labels`。QC 包含提取方法与桥接、级别/范围判定依据、名称覆盖率、拟合尺度、双向边界距离和未受参考约束的比例。Mode C 另加 `conformed.gpkg` 与 `conformance_qc.json`。预览、候选、裁片及缓存留在 `work/`；图件用 Helvetica、12 pt、1.5 pt 线宽和无边框图例。

### 停机与复核

- `REVIEW_SCOPE`：提示词、配置或图面证据冲突；请用户明确目标级别与共同边界关系。
- `REVIEW_EXTRACTION`：不能确认行政面、两个候选网络并存、断线或面数校验失败；检查原图预览及候选样式。
- `NO_COMMON_BOUNDARY`：上级边界不能定位内陆局部图；补充共同边界或定位依据。
- `REVIEW_REGISTRATION`：缺少可靠的共同弧段定位种子，或变换无法可信确定。
- `REGISTERED_REVIEW_NAMES`：几何可交付，但有标注归属冲突或 OCR 未核查；空名和待复核 ID 保留。

详细口径见 [输入与名称契约](references/input-and-name-contract.md)、[方法](references/methodology.md)、[QC](references/qc-spec.md) 和 [双语 README](README.md)。
