## QC 口径 / Quality-control definitions

### 当前统一入口实际计算

所有距离在 `registration.fit_crs` 所示的米制投影内计算。Mode R 的行政面使用同一个页面到地图矩阵。 `registration.metrics` 的 `median_m`、`p75_m`、`p90_m`、`p95_m` 和 `max_m` 来自源外轮廓采样点到参考外轮廓密集采样点的最近邻距离；`reverse_median_m`、`reverse_p90_m` 是反方向采样。它们是**采样近似**，并非对连续曲线的解析 Hausdorff 距离。

`same_extent` 对两个完整面计算 `symmetric_difference_km2` 与 `iou`。 `shared_boundary` 只在已识别的共同弧段计算距离；给出 `shared_arc_km`、`shared_fraction`、`unconstrained_fraction`。后者是未进入共同弧段拟合的源外轮廓采样比例，不应被表述为“街道总边长中已独立验证的比例”。部分源图与整个上级面之间的 IoU 或对称差没有可比意义，因此不计算。

`same_extent` 的 `full_p90_m`、`full_reverse_p90_m` 覆盖全部多面外环，并按各段边长加权；`registration.gate` 记录 IoU ≥ 0.95、双向 P90 ≤ 参考面积等效半径 1% 以及候选变换唯一性的自动放行结果。未过时 `work/review.json` 保存理由和指标，`work/review_registration.png` 保存候选叠加图，交付目录不生成 GPKG。

`registration.scale` 存 `m_per_pt`、`scale_denominator`、反射和各向异性。比例换算是 `scale_denominator = m_per_pt × 72 / 25.4 × 1000`；旧罗湖报告一处将 16.343 m/pt 误记成 1:21,586，正确约为 1:46,300。图纸印刷比例尺只能核对，不应固定拟合尺度。

### 提取、范围与名称

`decision.evidence` 与 `decision.hints` 指明级别及共同边界关系的依据；标题和文件名只是线索。 `extraction.method`、`extraction.admin_units`、`extraction.bridges` 与 `overlap_area_pt2` 说明提取路径和拓扑。桥接只在显式页面容差下运行，每条记录起终点和长度。

`decision.reference` 记录参考图层、CRS、要素数、连通片数、范围和读入/投影后是否修复；明显改变面积的参考修复会停在 `REVIEW_SCOPE`。`decision.scope_confirmation` 仅保存用户明确的范围答复。`extraction.boundary_source` 为行政填色、色带内环或描边；`excluded_band_drawings` 和 `inner_edge_drawing` 说明色带取舍。未能判定时看 `work/scope_comparison.png`、`work/review_extraction_*.png`，不要将预览当成配准完成证据。

Shapefile 的 `inputs.reference_sha256` 与交付缓存指纹包含同名 `.shp/.shx/.dbf/.prj/.cpg` 中实际存在的文件，避免只改属性或 CRS 后复用旧成果。

`names.scan_status` 为 `native`、`ocr`、`native+ocr` 或 `ocr_unavailable`；`named_units/total_units` 是覆盖率。 `no_labels_found` 仅在扫描成功且无标签时成立，此时允许空名几何和无 `map_labels`。`not_checked` 表示 OCR 环境失败，不能解释为无名；`incomplete` 给出 `unresolved_admin_ids`。显式 `names.mode: required` 只有全名通过才交付；否则 `REVIEW_NAMES` 在 `work/review_names.json` 列出未解决面、局部裁片和附近的识别文本，不写最终 GPKG。

### Mode C 与解释边界

Mode C 仅用于同范围。 `conformance_qc.json` 检查对称差、外溢、漏覆盖、行政面重叠、面积和、内部接缝漂移及无效几何，并记录无源图证据补块。无法唯一决定补面归属时返回 `REVIEW_CONFORMANCE` 与 `work/review_conformance.png`，不写最终 GPKG；全部交付文件先经临时目录检查，避免留下部分成果。浮点面积断言允许极小数值余量；“对称差 0”只表示面覆盖一致，不表示顶点序列一致，更不证明内部行政界线准确。

绘制 `overlay.png` 应显示源与参考的残留偏差，不能用 Mode C 掩盖 Mode R。统一 Helvetica、12 pt 基础字号、1.5 pt 默认线宽、无边框图例。历史深圳与罗湖指标只是各自版本的样本，不能做跨地图通用通过阈值。交付清单检查只核查文件和图层契约；科学解释仍应查图、查残差空间结构及参考数据年代与概化差异。

### 批量层级化 QC

`province_qc.json` 在统一米制拟合 CRS 中检查区级面并集与市级参考并集的对称差、漏覆盖、外溢、区级面积重叠、无效几何及逐城市覆盖差异。`city_adjacency_qc.csv` 对有参考公共线段的城市，记录双方交付边界的不一致线长、缝隙和重叠面积。面积与长度沿用 Mode C 的 `1e-3 m²` 与 `1 m` 断言；QC 不修改几何。任何城市停在复核状态或全局检查失败时不发布省级合并 GPKG；城市只覆盖参考图层的一部分时仅生成预览。
