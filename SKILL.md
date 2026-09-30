---
name: tianditu-eps-boundary-registration
description: 将无坐标的行政区划矢量 EPS/PDF 与可信 SHP/GPKG 边界配准并输出可复核 GPKG；用户明确要求多城市合并时运行批量流程。
---

## 适用与模式

适用于天地图等来源的**无 CRS 矢量 EPS/PDF 行政区划图**。扫描图、纯栅格 PDF 和已有可靠 CRS 的 GIS 数据不走此流程。默认处理单张图；只有用户明确要求多个城市提取合并，或提供 `workflow.mode: batch_hierarchical` manifest，才启用[批量流程](references/batch-hierarchical.md)。不要因用户给出多个文件就自行合并。

源图与参考边界是两份不同输入。参考必须是目标区域、CRS 正确的 SHP/GPKG；多空间图层 GPKG 指定 `reference_layer`，多城市图层用 `reference.filter` 选目标城市。页面坐标没有地理 CRS，配准前不能将两份 bbox 求交，也不能直接给页面坐标赋参考 CRS。详细契约见[输入与名称](references/input-and-name-contract.md)。

## 单图执行

1. 从**本 SKILL.md 所在目录**定位 `scripts/` 和 `templates/`；从 `templates/config.example.yaml` 建立用户项目内的配置。为本次运行使用独立 `work_dir` 与空的 `output_dir`，保留已有成果。若用户已经明确确认地区和范围，将原意记入 `scope_confirmation`；不要把文件名相似、批量 `parent_id` 或 Agent 的猜测写成用户确认。
2. 用 `inspect_environment.py --config <run.yaml>` 检查环境与路径。查看源图预览、参考图层/CRS/要素/范围，结合图面标注和用户目标确定提取级别及 `same_extent`、`shared_boundary` 或无共同边界。`shared_boundary` 需要两处可信地标种子；无定位依据时停止。对照图只辅助判断，不能代替拟合后复验。
3. 用 `run.py --config <run.yaml>` 执行。优先从经确认的行政填色面取界；有宽度的边界色带不作为行政面，只有唯一可判定内缘时才使用。名称只来自图面文字、OCR 或带裁片的人工复核。同色离岛归属不明时不按最近距离猜测。
4. 根据终端 `##VERDICT` 与 `work/review.json` 处理复核状态。只调整有证据支持的配置后重跑；不要通过更换标签、改写用户意图或降低几何闸门来强行放行。若图面街道标注与目标区级填色面冲突，核实后可在 `scope_review.admin_level_conflict` 留下具体图面依据；它不能替代 `scope_confirmation`。若用户已确认范围，不重复询问，但仍须通过几何复验。
5. 成功后检查 `qc.json`、`overlay.png` 和交付清单，并明确报告名称覆盖率、未独立验证的内部区界与残余误差。默认 Mode R 保留源图内部几何；单图仅在明确需要同范围外轮廓贴合时使用 Mode C，其新增面积没有源图证据。[方法与门槛](references/methodology.md)及[QC 字段](references/qc-spec.md)按需查阅。只在交付成功后运行 `check_output_manifest.py`。

```powershell
python "<skill-root>/scripts/inspect_environment.py" --config <run.yaml>
python "<skill-root>/scripts/run.py" --config <run.yaml>
# 仅在 run.py 返回交付成功后：
python "<skill-root>/scripts/check_output_manifest.py" <output_dir> --config <run.yaml>
```

## 复核状态怎么处理

| 状态 | 下一步 |
|---|---|
| `REVIEW_SCOPE` | 看 `review.json`、参考元数据和已生成的 `work/scope_comparison.png`；证据仍不足时请用户确认目标范围。 |
| `NO_COMMON_BOUNDARY` | 请求有共同边界的参考或可信定位依据；不能仅凭上级外界定位内部图。 |
| `REVIEW_EXTRACTION` | 看已生成的 `work/review_extraction_*.png/json` 与源图，确认行政填色、描边、色带内缘或离岛归属。 |
| `REVIEW_NAMES` | 看 `work/review_names.json` 和裁片；仅录入有图面证据的 `reviewed_labels`。 |
| `REVIEW_REGISTRATION` | 看 `review.json` 和已生成的 `work/review_registration.png`，核查 IoU、双向 P90、多解及范围/参考；不能绕过闸门。 |
| `REVIEW_CONFORMANCE` | 看 `work/review_conformance.png`；补面归属不唯一时核实图面依据，必要时改为符合用户目标的 Mode R 单图运行。 |

`names.mode: auto` 可交付空名几何，但 `REGISTERED_REVIEW_NAMES` **不是名称已核准**。同范围自动交付的 IoU ≥ 0.95、双向完整边界 P90 ≤ 参考面积等效半径 1% 且变换唯一，只是自动放行条件，不是通用精度保证。暂停状态不交付最终 GPKG。

## 多城市批量

先读[批量操作说明](references/batch-hierarchical.md)，从 `templates/batch.example.yaml` 建立一份 manifest。每个 case 绑定一张 EPS/PDF 和参考城市的 `parent_id`；`defaults` 只放共用单图参数，图面差异放该 case 的 `options`。`parent_id` 只是待核实的映射；仅在用户已明确确认该城市范围时，才在该 case 的 `options.scope_confirmation` 记录答复，不能在 `defaults` 为全部城市伪造确认。批量运行 `python "<skill-root>/scripts/run.py" --config <batch.yaml>`；不要给批量命令附加单图 `--intent`。批量逐城市执行上述闸门并保留 Mode R/C。任一城市需要复核或全局 QC 失败时，不发布省级合并成果；部分城市通过只得到 `batch_preview.gpkg`，全部参考城市通过才得到 `province_conformed.gpkg`。

## 使用限制

成果仅供科研制图和探索性分析，不是法定界线或测绘成果。外边界参考不能独立验证内部行政界、地名与离岛归属；向用户交付时须说明这些未验证项和数据使用许可。
