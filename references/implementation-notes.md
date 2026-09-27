## 当前实现与维护入口

| 文件 | 职责 |
|---|---|
| `scripts/run.py` | YAML/提示词入口；范围预判；按阶段复用缓存；协调提取、名称、配准、交付与清单检查 |
| `scripts/source.py`, `scripts/pathio.py` | EPS→矢量 PDF、页面普查、填充/描边路径解析、原图预览与输入哈希 |
| `scripts/extract.py` | 填充行政面或描边闭环面化；歧义停机；页面 GPKG 与拒绝/桥接记录 |
| `scripts/names.py`, `scripts/ocr_page.py` | 原生文字、独立进程整页 OCR、按面赋名、局部复核裁片 |
| `scripts/scope.py` | 用户/配置/图面线索优先级，三级边界关系，冲突与无共同边界停机 |
| `scripts/register.py` | 参考投影选择、完整轮廓或共同弧段拟合、单一矩阵和采样距离 QC |
| `scripts/deliver.py` | Mode R/C GPKG、JSON、图件、日志与回读 |
| `scripts/check_output_manifest.py` | 交付文件/图层契约检查 |

`scripts/run.py --config` 是唯一完整入口；`source.py` 和 `extract.py` 可单独诊断中间阶段。EPS 与矢量 PDF 可运行，SVG/DXF 仍需另行适配。模板只含通用默认，案例参数在 `examples/`。

### 缓存与重跑

`work/` 的转换与普查以源哈希和曲线离散容差缓存；提取缓存还带方法、线型/颜色及阈值；OCR 以 PDF 哈希与 DPI 缓存。完整交付带源、参考、配置和脚本指纹；相同输入及代码、通过清单检查时重跑直接返回缓存结果。不同或未完成的非空 `output_dir` 会被拒绝，换新输出目录复跑。缓存并不证明行政面语义正确，需保留原图预览和 QC 决策依据。

### 复核界限

自动填充模式适合轮廓清晰、绘图路径直接对应行政面的图。填充较多或有图像的复杂图要求人工/视觉代理确认 `keep_colours_rgb`。线型分组遇两个可信闭环网络停止；不要只看颜色或面数。共同弧段配准要求可信地标种子；缺种子不任意搜索整个上级轮廓。原生文字存在时当前 OCR 阶段跳过整页 OCR；若原生文字仅为旧标题，应检查是否覆盖图面名称，并手动复核缺名面。

### 最小验证

```powershell
python -m unittest discover -s tests -v
python scripts/inspect_environment.py --config examples/shenzhen.yaml
python scripts/run.py --config examples/shenzhen.yaml
python scripts/check_output_manifest.py runs/shenzhen/output --config examples/shenzhen.yaml
```

若目标输出已存在另一指纹的结果，应在项目内设置新的 `output_dir`，不得清空历史交付来让命令通过。两例复跑及字段口径见 [docs/experiments.md](../docs/experiments.md)。
