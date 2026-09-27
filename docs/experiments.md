## 实验与复现记录 / Experiments

所有新结果写在本项目 `runs/`。原始 EPS 与参考数据不随仓库分发；示例配置需要先放入对应授权文件。执行环境先检查 `python scripts/inspect_environment.py --config examples/shenzhen.yaml`。从项目根目录运行：

```powershell
python scripts/run.py --config examples/shenzhen.yaml
python scripts/check_output_manifest.py runs/shenzhen-current/output --config examples/shenzhen.yaml
python scripts/run.py --config examples/luohu.yaml
python scripts/check_output_manifest.py runs/luohu-current/output --config examples/luohu.yaml
python -m unittest discover -s tests -v
```

第二次原样运行 `run.py` 应返回 `cached_delivery`；转换、矢量普查、提取和 OCR 中间结果也按内容哈希复用。例子配置中的填色、面数、裁片和地标只属于那张图。换图从[通用模板](../templates/config.example.yaml)开始。交付目录非空且指纹不同会拒绝覆盖，设置一个新的项目内目录即可。

### 两例统一入口回归（2026-09-26）

| 计算对象 | 深圳区级完整同范围 | 罗湖街道级共同弧段 |
|---|---:|---:|
| 页面行政面 / 已接受图面名称 | 10 / 10 | 10 / 10 |
| 提取方法 | 填充；当前图核对颜色 | 填充；当前图核对颜色 |
| 拟合尺度 | 48.71783 m/pt，约 1:138,098 | 16.32353 m/pt，约 1:46,271 |
| 源→参考采样中位 / P90 | 12.75 / 72.99 m | 10.90 / 23.63 m |
| 对称差 | 13.74464 km²（Mode R） | 不适用，不将单区与全市相减 |
| 共同弧段及未约束比例 | 不适用 | 13.755 km；约 73.34% 外轮廓采样点未进入拟合段 |
| Mode C | 对称差 0；补入 8.47278 km²；断言通过 | 禁止，对全市补成单区会伪造面积 |

这些是 `registration.metrics` 的**配准后采样 QC**，不同于 ICP 迭代内部残差。深圳参考只有市界，不能验证区内界线；罗湖参考只有市界，不能验证街道内部界线。历史深圳中位 12.68 m / 对称差 13.650 km²，历史罗湖共线约 14.08 km / 中位 10.93 m / P90 26.70 m；方法版本、采样和变换略有差异，所以只作对照，不把历史数值设为阈值。见[历史案例](cases.md)。

### 合成 EPS 验收

`tests/test_generalized.py` 用小 EPS 覆盖纯填充同色相邻面、单色线条、混杂水系/道路、断线显式桥接、多候选网络停机、无名称整幅“国家图”交付和无共同边界早停。 `tests/test_workflow_guards.py` 检查提示词/配置冲突与旧名称强制模式。测试将输出写临时目录，不触碰历史成果。若 `REVIEW_EXTRACTION`，看 `work/preview.png`、候选 JSON 与原图；若 `REVIEW_SCOPE`，先请用户明确级别与共同边界关系。不要为满足预期面数或姓名数而猜选。

### 当前验证边界

本轮的合成国家例只有一个连续参考外轮廓，证明“整幅外界 + 内部无名面”可以跑通；未验证跨多个离岛或严重概化国界的自动解。当前共同弧段入口需要两处可信地标初始化；没有这类证据时停机，尚不执行全球/全国大范围自动弧段搜索。图层清单校验只检验交付结构，几何与名称仍按 `qc.json`、GPKG 和图面复核。
