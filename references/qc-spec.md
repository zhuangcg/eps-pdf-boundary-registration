## QC 口径 / Quality-control definitions

### 当前统一入口实际计算

所有距离在 `registration.fit_crs` 所示的米制投影内计算。Mode R 的行政面使用同一个页面到地图矩阵。 `registration.metrics` 的 `median_m`、`p75_m`、`p90_m`、`p95_m` 和 `max_m` 来自源外轮廓采样点到参考外轮廓密集采样点的最近邻距离；`reverse_median_m`、`reverse_p90_m` 是反方向采样。它们是**采样近似**，并非对连续曲线的解析 Hausdorff 距离。

`same_extent` 对两个完整面计算 `symmetric_difference_km2` 与 `iou`。 `shared_boundary` 只在已识别的共同弧段计算距离；给出 `shared_arc_km`、`shared_fraction`、`unconstrained_fraction`。后者是未进入共同弧段拟合的源外轮廓采样比例，不应被表述为“街道总边长中已独立验证的比例”。部分源图与整个上级面之间的 IoU 或对称差没有可比意义，因此不计算。

`registration.scale` 存 `m_per_pt`、`scale_denominator`、反射和各向异性。比例换算是 `scale_denominator = m_per_pt × 72 / 25.4 × 1000`；旧罗湖报告一处将 16.343 m/pt 误记成 1:21,586，正确约为 1:46,300。图纸印刷比例尺只能核对，不应固定拟合尺度。

### 提取、范围与名称

`decision.evidence` 与 `decision.hints` 指明级别及共同边界关系的依据；标题和文件名只是线索。 `extraction.method`、`extraction.admin_units`、`extraction.bridges` 与 `overlap_area_pt2` 说明提取路径和拓扑。桥接只在显式页面容差下运行，每条记录起终点和长度。

`names.scan_status` 为 `native`、`ocr`、`native+ocr` 或 `ocr_unavailable`；`named_units/total_units` 是覆盖率。 `no_labels_found` 仅在扫描成功且无标签时成立，此时允许空名几何和无 `map_labels`。`not_checked` 表示 OCR 环境失败，不能解释为无名；`incomplete` 给出 `unresolved_admin_ids`，按相关裁片复核。显式 `names.mode: required` 只有全名通过才交付。

### Mode C 与解释边界

Mode C 仅用于同范围。 `conformance_qc.json` 检查对称差、外溢、漏覆盖、行政面重叠、面积和、内部接缝漂移及无效几何，并记录无源图证据补块。浮点面积断言允许极小数值余量；“对称差 0”只表示面覆盖一致，不表示顶点序列一致，更不证明内部行政界线准确。

绘制 `overlay.png` 应显示源与参考的残留偏差，不能用 Mode C 掩盖 Mode R。统一 Helvetica、12 pt 基础字号、1.5 pt 默认线宽、无边框图例。历史深圳与罗湖指标只是各自版本的样本，不能做跨地图通用通过阈值。交付清单检查只核查文件和图层契约；科学解释仍应查图、查残差空间结构及参考数据年代与概化差异。
