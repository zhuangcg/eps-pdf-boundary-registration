## 运行记录模板 / Run log example

`run.log` 由 `scripts/deliver.py` 从本次决策与交付内容生成，不应手工填历史数字。当前文件展示其主要字段；数值以 `qc.json` 为准。

- Source: <source EPS/PDF>
- Reference: <reference GPKG>
- Level: <street/district/city/province/country> (<config/user_intent/map_body_labels/filename>)
- Relationship: <same_extent/shared_boundary> (<config/user_intent>)
- Extraction: <fill/line>, <N> units
- Names: <accepted>/<total> (<complete/no_labels_found/incomplete/not_checked>)
- Name review: <only when no labels or OCR not checked>
- Fit CRS: <metre CRS>; delivered CRS: <reference CRS>
- Scale: <fitted m/pt> (1:<denominator>)
- Outline median/P90: <sampled metres>
- Internal unit boundaries have no independent same-level reference validation.
- Status: <REGISTERED_WITH_QC/REGISTERED_REVIEW_NAMES>

Mode C 的新增面积与断言在 `conformance_qc.json`；`shared_boundary` 的共同弧段长度与未约束比例在 `qc.json.registration.metrics`。没有共同边界或行政面歧义时，不生成这个交付日志，`work/review.json` 保存停机原因。
