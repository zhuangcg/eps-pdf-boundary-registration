## 多城市层级化流程

此文档只在用户要求多个城市提取并合并，或提供 `workflow.mode: batch_hierarchical` manifest 时使用。单图任务继续使用 `templates/config.example.yaml` 和单图入口；不要自行启用 Mode C 或省级合并。

从 `templates/batch.example.yaml` 建立一份 manifest，执行 `python scripts/run.py --config <batch.yaml>`。路径相对于 manifest 所在目录。`parent_reference` 必须是统一市级参考图层，含非空 `id_field` 和可信 CRS；同一个 ID 的多个面会合并以保留岛屿，城市间有面积重叠则预检失败。`cases` 至少有两个不同 `parent_id`，每个对应一张矢量 EPS/PDF。PDF 的 `page` 从 1 开始，默认 1。`defaults` 和每个 case 的 `options` 使用现有单图配置字段；后者覆盖前者的同名设置。源文件、页码、参考和输出路径由 manifest 的固定字段控制，不放进 `options`。

每个城市必须先复核图面范围及提取候选。`parent_id` 只是待核实的参考城市映射，不自动成为用户确认；只有用户已经明确确认某城源图与参考同范围，才能在该 case 的 `options.scope_confirmation` 记录其答复。没有该答复时由文件名、图面标注和参考名称提供线索，不足则停在 `REVIEW_SCOPE`。不得在 `defaults` 中给所有城市写一个通用确认。批量处理强制区级、`same_extent`、Mode C，并统一使用一个米制拟合 CRS；出现范围、提取、名称、配准或 Mode C 补面复核状态时停在该城市，查看 `work/batch_review.json` 和对应城市的 `work/<parent_id>/review.json`。每个城市的 `output/cities/<parent_id>/` 保留 `registered.gpkg`、`conformed.gpkg` 和各自 QC，不以 Mode C 覆盖 Mode R。图面无证据的补充面积仍按现有 conformance 报告披露；未证实的区名仍保持空白。

城市级均通过后，`province_qc.json` 报告覆盖差异、行政面重叠、无效几何及缺失城市，`city_adjacency_qc.csv` 按参考公共线段列出相邻城市的线段不一致长度、缝隙和重叠面积。面积与长度采用现有 Mode C 的米制容差，不在 QC 阶段改写几何。任一检查失败时只保留城市成果和诊断，不发布合并 GPKG。

仅处理参考图层的一部分城市且全部通过时，输出 `batch_preview.gpkg`；它不是省级完整成果。参考图层的每个城市都在 cases 中且所有检查通过时，才输出 `province_conformed.gpkg`，包含 `district_units`、`city_units`、`province_outline`。合并后的区级图层带 `parent_id`；源图内部区界仍未经独立的同级参考验证。
