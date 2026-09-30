## 多城市批量处理

只在用户要求**提取并合并多个城市**，或明确提供 `workflow.mode: batch_hierarchical` 批量配置时使用。单图继续用 `templates/config.example.yaml`。批量流程会逐城检查和交付，再检查合并结果；它不会因为收到了多个文件就自动开始合并。

### 1. 填写城市清单

复制 `templates/batch.example.yaml`。`parent_reference` 指向一份带正确坐标系的市级参考数据；`id_field` 是其中的城市编号字段。一个城市若由多块面组成，相同编号的面会合并以保留岛屿；不同城市若有面积重叠，运行前就会停止。GPKG 有多个空间图层时必须写明 `layer`。

`cases` 至少列出两个不同城市。每项填写一张矢量 EPS/PDF 的 `source_map` 和参考图层中对应的 `parent_id`；PDF 可用从 1 开始的 `page` 选页，默认第 1 页。路径相对于批量配置文件的位置。`defaults` 写所有城市共用的单图设置，某城不同的设置写在该项的 `options`；不要在 `options` 中重复源文件、页码、参考或输出路径。

**`parent_id` 只是待核实的城市对应关系，不是范围已确认的证据。** 每张源图都要与对应参考城市核对。只有用户已经明确确认某城源图与参考均覆盖该城完整范围，才能在该城市的 `options.scope_confirmation` 记录原答复。没有答复时，文件名、图面标注和参考名称只能提供线索；线索不足就进入 `REVIEW_SCOPE`。不要在 `defaults` 为所有城市写同一条确认。

### 2. 逐城运行和复核

运行 `python scripts/run.py --config <batch.yaml>`，不要附加单图命令的 `--intent`。批量流程为每城提取区级行政面，要求源图与该城参考表示同一个完整城市（`same_extent`），并使用统一的米制拟合坐标系。每城会检查范围、填色或线条、名称、配准和 Mode C 的边缘面积归属。

每个**成功的城市**在 `output/cities/<parent_id>/` 保留 `registered.gpkg`（保留原图边界的 Mode R）、`conformed.gpkg`（外轮廓贴合参考的 Mode C）及检查报告。Mode C 新增的边缘面积来自参考，不是原图证据。若图上无法确认某个区名，默认名称模式可保留该区几何并将 `admin_name` 留空；合并成果也不能称为已核名。

任一城市暂停时，不发布合并 GPKG。查看 `work/batch_review.json`，再看该城市 `work/<parent_id>/review.json` 和相应预览图。只有依据充分时才修改该城市设置后重跑。

### 3. 判断合并结果

所有本次提交的城市都通过后，程序检查行政区面是否覆盖对应市界，以及城市之间的缝隙、重叠、无效几何和公共边界差异。`province_qc.json` 保存总体检查；`city_adjacency_qc.csv` 保存相邻城市的边界检查。检查阶段不会悄悄修改几何，失败时只保留已通过的城市成果和诊断文件。

| 条件 | 合并文件 | 含义 |
|---|---|---|
| 本次仅提交参考数据中的一部分城市，且这些城市及合并检查全部通过 | `batch_preview.gpkg` | **只包含本次提交的城市**，不能称为全省成果。 |
| 参考数据中的每个城市都已提交，且全部城市及合并检查通过 | `province_conformed.gpkg` | 包含 `district_units`、`city_units` 和 `province_outline` 图层。 |
| 任一城市暂停或合并检查失败 | 无合并 GPKG | 按复核文件排查后重跑。 |

合并的区级图层带 `parent_id`，用于标明所属参考城市。市级参考外轮廓不能独立证明原图内部区界或区名正确。面积与长度检查使用现有 Mode C 容差，具体数值见[QC 说明](qc-spec.md)。
