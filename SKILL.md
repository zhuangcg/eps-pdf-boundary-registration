---
name: tianditu-eps-boundary-registration
description: 专门处理天地图导出的无坐标系行政区划 EPS 图：提取行政区面，以用户提供的可信参考边界执行空间配准，输出科研制图用 GeoPackage 与 QC 图件。
---

## 用途

本 skill 面向从天地图获取的无坐标行政区划 EPS 图。项目默认配置和示例以天地图 EPS 为中心；结构完整的矢量 PDF 可作为次级兼容输入。扫描件和栅格地图不属于当前流程。

输出仅用于科研制图与探索性分析，不是标准地图、标注地图原件、法定界线或测绘成果。配准误差不可能为零，也不承诺特定精度；参考边界的准确性、EPS 图面复杂程度、图面概化、可用共同边界和人工检查都会影响结果。参考外边界不能独立验证内部行政区界。

## 核心流程

1. 检查 EPS、参考边界的 CRS/图层和用户指定行政级别；先检查页面预览是否确实包含待提取的行政区划。
2. 判断源图与参考边界是 `same_extent`、`shared_boundary` 还是 `no_common_boundary`。范围不清楚时先复核；没有可信共同边界或其他定位依据时停止，不强行拟合。
3. 从填充面或经确认的闭合边界提取行政区几何。名称只使用图面文字或 OCR 证据；不能按形状、面积、地理常识或面顺序猜名。
4. 在米制投影中估计一个作用于整张源图的全局变换，再转换到参考数据 CRS。禁止直接把参考 CRS 赋给 EPS 页面坐标。
5. 每次交付 `registered.gpkg`、`qc.json`、`overlay.png` 和 `run.log`；说明未验证的内部区界、名称状态和配准限制。

## 运行与复核

```powershell
python scripts/inspect_environment.py --config <run.yaml>
python scripts/run.py --config <run.yaml> --intent "提取天地图区级边界；图面范围与参考边界相同"
python scripts/check_output_manifest.py <output_dir> --config <run.yaml>
```

默认使用保留源图几何的 Mode R。只有确认源图与参考边界完全同范围，且明确需要贴合外轮廓时，才考虑高级 Mode C；解释见 [方法说明](references/methodology.md)。运行前从 `templates/config.example.yaml` 复制配置；案例参数见 `examples/`。

详细的输入契约、算法口径、停机条件和 QC 字段分别见 [输入契约](references/input-and-name-contract.md)、[方法说明](references/methodology.md) 与 [QC 定义](references/qc-spec.md)。
