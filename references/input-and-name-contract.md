## 输入范围与图面名称契约

### 级别与参考边界关系

| `source_scope` | 几何条件 | 拟合依据 | 交付 |
|---|---|---|---|
| `same_extent` | 源图行政面并集和参考多边形代表同一范围 | 完整外轮廓 | R；必要时追加 C |
| `shared_boundary` | 源图与参考有可信的连续共同外边界弧段 | 经核实地标初始化，再用该弧段拟合 | 仅 R |
| `no_common_boundary` | 源图是参考内部局部区域，外轮廓不接壤 | 无可用轮廓依据 | 停止配准 |

行政级别不决定几何关系；城市面可参照国界，街道面可参照市界，只看是否有实际共同外边界。输入提示词和显式配置优先，文件名、旧标题、原生文字与 OCR 是辅助线索。冲突或仍不确定时输出 `REVIEW_SCOPE`；明确无共同边界时输出 `NO_COMMON_BOUNDARY`。旧 `partial_parent` 是 `shared_boundary` 的别名。Mode C 仅允许同范围。

必要路径是 `source_map`、`reference_boundary`、`output_dir`、`work_dir`；多图层 GPKG 提供 `reference_layer`。默认 `admin_level: auto`、`source_scope: auto`。共享弧段当前需要两处有页坐标、经纬度和来源的可信 `landmarks` 种子；地标只用于初始化，最终仍以边界弧段拟合。参考应有可信 CRS；拟合 CRS 必须能以米量距。EPS/PDF 页面点不是 GIS 坐标。

### 名称证据

1. 读取 PDF/EPS 转换后的原生文字；无原生文字时整页 OCR 一次。OCR 失败应标记未核查，不能说图上没有名称。
2. 仅接受落入唯一行政面的候选标注。图例、道路、旧标题和邻区文字不能直接赋给面。含噪声、缺字、跨面或多个候选时复核相应局部裁片；改字需留下原文及证据。
3. 图上确实无行政名称时交付稳定 `admin_id`、空 `admin_name`，名称 QC 为 `no_labels_found`，不生成 `map_labels`。有标注但无法确定归属时空名保留并列入 `unresolved_admin_ids`。不得凭面积、行政常识或面顺序猜名。
4. `names.mode: required` 要求所有面有图面证据；默认 `auto` 允许空名。旧 `require_map_annotation: true` 对应 `required`。

`administrative_units` 保存 `admin_id`、`admin_name`、`name_status`、`name_source`、`admin_level` 及几何。`map_labels` 仅包含已接受或已复核的标注点、原文、接受文本、来源和裁片路径。QC 的 `names` 记录扫描状态、覆盖率与待复核 ID。深圳“大鹏新区”的竖排字和罗湖“南湖”的漏识是定向裁片复核例子，不应把两例的名称表当作其他图的词典。
