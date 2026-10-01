# tidal_fig.10

K2-261 b（EPIC 201498078，Brahm 历史名称 K2-161b）的 Figure 10 潮汐演化研究代码。

包含 Jackson (2009) 轨道平均方程、REBOUND BS 和 SciPy DOP853 对照、REBOUNDx 常时间滞后诊断、图像数字化、实验记录及测试。中心曲线已有初步数值与图像比较；完整联合后验、恒星轨迹来源和物理 Q 映射仍未验证。见 [第一阶段报告](docs/science/fig10_stage1_results.md)。

## 目录

- `src/k2_261b/`：物理求解器与实验记录模块。
- `scripts/`、`tests/`：运行、数字化、构建、验证入口和测试。
- `configs/`：论文报告值、复现配置、敏感性扫描设计和合成记录模板。
- `data/raw/stellar_tracks/`、`legacy/tidal/`：恒星轨迹与历史代码。
- `data/processed/fig10/`：用于图像比较的数字化点和校准记录。
- `references/papers/`：历史论文文字源文件；论文 PDF 需自行获取。
- `docs/`：模型适用范围、参数约定、记录格式和 Windows 构建说明。
- `vendor/reboundx/`、`artifacts/`：本机 MSVC 适配源码、补丁及上游版本证据。

## 环境与运行

目标环境：Windows x64、Python 3.12。核心库为 PyYAML、NumPy、SciPy、Matplotlib、REBOUND 5.2.1、REBOUNDx 5.1.0；观察到的环境版本见 `requirements/environment-observed.txt`。REBOUNDx 版本号不足以重建本机适配版，按 [环境说明](docs/environment/README.md) 和 [MSVC 构建说明](docs/environment/REBOUNDx_MSVC.md) 使用随附源码和补丁。

本仓库不包含虚拟环境、论文 PDF 和第三方文档图片。运行测试或模拟前，需在 `configs/parameters/paper_truth.yaml` 所列路径放入对应论文 PDF（来源 DOI 见同一配置）。必需文件为 `references/papers/brahm2018/published.pdf`、`references/papers/theory/jackson2009.pdf`、`references/papers/theory/penev2018.pdf`、`references/papers/theory/lainey2009.pdf`。数字化 CSV、恒星轨迹、补丁和代码已随附。

在新检出的项目中准备论文输入和 `.venv` 后运行：

```powershell
.\.venv\Scripts\python.exe scripts/experiment.py doctor
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/experiment.py simulate --config configs/reproductions/fig10_pilot.yaml
.\.venv\Scripts\python.exe scripts/experiment.py simulate --config configs/reproductions/fig10_bs_backward.yaml
.\.venv\Scripts\python.exe scripts/experiment.py simulate --config configs/reproductions/fig10_bs_forward.yaml
.\.venv\Scripts\python.exe scripts/experiment.py ctl-check --config configs/reproductions/fig10_ctl_diagnostic.yaml
.\.venv\Scripts\python.exe scripts/reproduce_fig10.py --ensemble 32 --budget-seconds 180 --label fig10_new
```

完整 suite 需要数字化 CSV 和 JSON，已随附。重新提取 PDF 时，在安装了 pdfplumber、Pillow、NumPy 的独立环境执行 `scripts/digitize_fig10.py`。新模拟各自创建独立 run；真实运行结果未随代码上传，报告中的旧 run 编号指原研究环境的记录。合成数据只能用于记录演示。

论文参数基准见 `configs/parameters/paper_truth.yaml`；模型与 Q/Q′ 的限制见 [复现说明](docs/science/fig10_reproduction.md) 和 [潮汐质量因子](docs/science/tidal_quality_factors.md)。

随附论文、历史代码与第三方源码保留其来源及既有版权；REBOUNDx 的许可证见 `vendor/reboundx/LICENSE`。
