# Figure 10 第一阶段数值复现记录

日期：2026-10-01；对象：EPIC 201498078 / K2-261 b。正式版源文件：`references/papers/brahm2018/published.pdf`，§4.2 与 Figure 10（PDF 第 7、8 页）。

**结论：已完成 REBOUND BS 对 Jackson (2009) 方程的中心曲线重建，并通过指定区间的初步图像比较和数值检查。完整 Figure 10 的联合后验 ensemble、恒星轨迹来源及物理 Q 解释仍未验证，不能称为全部物理复现完成。REBOUNDx CTL 已做实际短程积分，结果证实本次校准条件下与 Jackson 方程不等价。**

## 实现与版本

- `src/k2_261b/tides.py`：Jackson (2009) 公式 (1)、(2)，恒星项 de/dt 系数为 225/16，不使用 Jackson (2008) 的旧系数 171/16。REBOUND 5.2.1 的自定义 ODE + BS；没有虚构 N-body 粒子。
- `src/k2_261b/physics.py`：独立 SciPy DOP853、历史 Euler 对照与显式物理执行入口；所有真实实验调用原记录模块。
- `src/k2_261b/ctl.py`：REBOUNDx 5.1.0 本机 MSVC 版本的 `tides_constant_time_lag` 实际双体积分，以及按本机 C 源码导出的耗散加速度轨道平均积分。
- 官方 API 已核对：[REBOUND ODE](https://rebound.hanno-rein.de/ipython_examples/IntegratingArbitraryODEs/)、[REBOUNDx effects](https://reboundx.readthedocs.io/en/latest/effects.html)。实现同时核对本机 Python API 和 `vendor/reboundx/src/tides_constant_time_lag.c`；未更新或重装科学库。

采用 au、Msun、365 日年。常数均显式保存在配置中：G=6.67430e-11 SI、au=149597870700 m、Rsun=695700000 m、Rjup=71492000 m，以及显式太阳/木星质量。历史 Astropy 版本未知，不能据此声称恢复旧常数的所有有效位。年长度沿用历史 365 日约定。

## 中心曲线与数值结果

历史候选使用 Ms=1.101 Msun、Mp=0.179 Mjup、Rp=0.840 Rjup、a=0.10376 au、e=0.42、年龄 8.51 Gyr，以及 Jackson 有效分母 Q'_star=1e6、Q'_planet=32000。另运行 Ms=1.104 Msun、Q'_planet=30000 的正式版表格/正文操作性对照；这两种设置不覆盖 `paper_truth.yaml`。

| 量 | 历史候选中心曲线结果 |
|---|---:|
| 年龄 1 Gyr 时 a | 0.1737905 au |
| 年龄 1 Gyr 时 e | 0.8315607 |
| 年龄 1 Gyr 时近日点 | 0.02927315 au |
| Roche 极限（系数 2.7） | 0.02016881 au |
| 年龄 1 Gyr 时 q/Roche | 1.45141 |
| 吞没恒星年龄 | 9.7004321 Gyr |
| 距观测时刻到吞没 | 1.1904321 Gyr |
| 正式版操作性对照吞没年龄 | 9.7005895 Gyr |

上述有效位描述数值模型，不代表测量或物理预测精度。正文的 a≈0.175 au、e≈0.85、q/Roche≈1.4 和约 1 Gyr 后吞没是近似叙述；历史候选 e 与正文数值有差异，但更接近图中的中心线。

中心解 `run_000005`（过去）与 `run_000011`（未来）有独立 DOP853 和更细 BS/DOP853 对照。基础 tolerance=1e-10、max_step=1 Myr；细化 tolerance=1e-12、max_step=0.25 Myr。吞没附近输出与试算步长另限于当前 a/|da/dt| 的 1%，避免试算跨越 a=0 奇点。吞没用 q=Rstar，BS 二分时间括区宽度小于 10 年。

- 过去的 BS/DOP853 最大差：a 约 9.4e-13 au，e 约 4.2e-12。
- 未来比较包含输出线性插值误差：a 小于 5.4e-6 au，e 小于 8.7e-6；吞没时间差小于 7 年。恒星半径曲线在轨迹折点的插值误差不属于 ODE 求解误差。
- 100 kyr Euler 的未来吞没时间偏差约 0.268 Myr；其结果用于历史算法对照。
- `run_000003` 为步长限制修复前的失败记录，保持原状；没有改写成成功运行。

独立测试验证 SI 方程与年转换、正/反向求解、仅行星潮汐的积分不变量 ln(a)-e²、圆轨道极限、轨迹边界和吞没事件。ln(a)-e² 是本截断方程的不变量；它不意味着高 e 时精确的轨道角动量守恒。

## 正式版图像比较

`scripts/digitize_fig10.py` 使用文档运行时只读渲染正式版第 8 页，不改变科研 `.venv`。在已目视核对的轴坐标上，对黄色中心线、红色 Roche 线和绿色恒星半径线做颜色阈值提取；每点保留年龄、量值、像素 y 和 x 窗口。CSV、校准和源 PDF SHA256 保存于 `data/processed/fig10/`，并快照到 suite 的每个 run。

以 0.2–9.2 Gyr 的 46 个年龄点/每个曲线量作初步验收。容差在新曲线比较前写入配置；是图像分辨率级别的初步标准，不是原作者的数值误差。

| 量 | 最大绝对偏差 | 初步容差 | 结果 |
|---|---:|---:|---|
| e | 0.002665 | 0.006 | 通过 |
| a | 0.001119 au | 0.0015 au | 通过 |
| 近日点 | 0.000550 au | 0.0015 au | 通过 |
| Roche | 0.000250 au | 0.0015 au | 通过 |
| 恒星半径 | 0.000399 au | 0.0015 au | 通过 |

提取不使用模拟值选择目标曲线。颜色遮挡、虚线缺口和后期曲线并合限制图像可靠性；9.2 Gyr 以后只作目视检查，不把临近吞没的快速变化宣称为全区间定量通过。原始图片并非原作者的数值表，轴定位、线宽和窗口造成额外误差。

## REBOUNDx 对应检查

诊断 run：`run_000081`、`run_000082`。固定现时 a、恒星半径和质量，在 e=0.01、0.42、0.85 分别做加速度平均；高 e 点是模型比较，不是演化到该年代的预测。

明确的诊断假设：共面、自转轴沿 z、恒星自转 0、行星采用 Hut 伪同步初始自转并在短程积分内固定、k2_star=0.028、k2_planet=0.37。Love number 是测试假设，不是 K2-261 的观测值。令 n=sqrt(G(Ms+Mp)/a³)，选择：

- 恒星：k2*n*tau=3/(4Q')，仅校准 e→0 时 da/dt。
- 行星：k2*n*tau=3/(2Q')，仅校准 e→0、伪同步时 de/dt。

这两条是局部导数校准，不是已经确立的 Q→时间延迟物理转换。小 e 时行星导数匹配，而恒星 de/dt 仍约为 Jackson 的 1.44 倍；同时匹配两个导数的条件已经不满足。

| e=0.42 时，CTL/Jackson | da/dt 比值 | de/dt 比值 |
|---|---:|---:|
| 恒星潮汐 | 5.844 | 8.747 |
| 行星潮汐 | 5.101 | 4.201 |
| 合计 | 5.105 | 4.210 |

实际 IAS15 积分分别开启恒星、行星和两者潮汐，各运行 64 周期。时间延迟放大 1e4 和 1e5 来分辨非常微弱的轨道漂移；扣除 tau=0 的保守潮汐对照后再除放大倍数。所有放大曲线标为诊断，不能用作 Figure 10 的物理演化曲线。

N-body 测得导数与本机 C 源码轨道平均的最大相对偏差约 3.13e-4。更小的放大倍数更接近线性响应。IAS15 tolerance 从 1e-10 收紧到 1e-12，并把平均积分网格从 16384 加密到 65536，结果另存 `ctl_comparison.json`。Newtonian 和 tau=0 保守潮汐检查的最大能量误差约 1.09e-14（包含潮汐势能时才检查保守潮汐总能量）。有耗散时机械能降低；固定自转是角动量库，不能要求轨道角动量自身守恒。

## 半径轨迹与 ensemble 限制

半径直接读取历史 YY 轨迹，分段线性插值，在 1–9.8 Gyr 外按端点钳制。没有将曲线在观测时刻缩放到 1.669 Rsun：轨迹给出约 1.67923 Rsun，这一差异已保留。轨迹的原始 YY 参数与生成方法未核实；过去 1 Gyr 以前的恒星半径是边界假设。

Roche 穿越只记录，继续理想化点行星模型；没有实现流体瓦解。名义中心曲线未穿越 Roche。q≤Rstar 为几何吞没，不模拟恒星包层内的演化。该独立 a/e 模型没有外部扰动或抛射通道；离开有限椭圆域按数值失败处理。

灰线为 32 组固定种子、独立历史高斯边缘分布的近似样本，每组过去/未来分别分配 run。质量、半径、a、e 和年龄的采样、截断和实际值全部记录；每个样本共用同一条未缩放恒星半径轨迹。恒星半径的观测误差不作为额外的半径轨迹误差采样，因为旧脚本也会用轨迹覆盖该值。年龄先验截断为 1<age<9.5 Gyr，属于明确的本轮假设。

不存在真实联合后验时，不能验收原图灰线的精确分布或将它称为完整不确定性传播。高 e 的 Jackson 方程属于截断模型外推；CTL 的明显不同也不能直接证明哪种模型更接近真实系统。物理解释还退化于 Love number、自转、频率依赖、半径演化和行星内部结构。

## 运行、证据与后续验收

suite 在 180 秒预算内完成，实际约 79 秒，76 个独立 run；另有 pilot、早期中心验证、失败记录和两次 CTL 诊断。总计 82 个科研记录全部通过记录工具完整性检查，其中 81 completed、1 failed。completed 只表示执行结束；不可改写终态 summary 中的 pending 接受状态，后续接受结论单独写分析文件。

```powershell
.\.venv\Scripts\python.exe scripts/experiment.py simulate --config configs/reproductions/fig10_pilot.yaml
.\.venv\Scripts\python.exe scripts/experiment.py simulate --config configs/reproductions/fig10_bs_backward.yaml
.\.venv\Scripts\python.exe scripts/experiment.py simulate --config configs/reproductions/fig10_bs_forward.yaml
.\.venv\Scripts\python.exe scripts/experiment.py ctl-check --config configs/reproductions/fig10_ctl_diagnostic.yaml
# 新 suite 必须使用新的 label；不会覆盖已有 run
.\.venv\Scripts\python.exe scripts/reproduce_fig10.py --ensemble 32 --budget-seconds 180 --label fig10_stage2
# 仅重做派生分析，不改 run
.\.venv\Scripts\python.exe scripts/reproduce_fig10.py --analyze results/reproductions/fig10_stage1
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

PDF 提取需另用 安装了 pdfplumber、Pillow 和 NumPy 的独立 Python 环境 执行 `scripts/digitize_fig10.py`；模拟入口始终用当前 `.venv/Scripts/python.exe`。先提取目标 CSV，再执行 suite。分析从 run 的不可变输入快照读取目标点与半径轨迹，保存分析脚本 hash。

- 可视化：`results/reproductions/fig10_stage1/fig10_comparison.png` 与 SVG。
- 详细指标与 run 清单：同目录 `comparison.json`、`ctl_comparison.json`、`runs.json`。
- 小型可追踪摘要：`artifacts/fig10-stage1-summary.json`。
- 工具检查：`artifacts/fig10-stage1-tests.txt`，**22 项测试通过**；`artifacts/fig10-stage1-integrity.json`，26 个原件 hash 和半径副本均通过。

下一步物理验收应优先确认恒星轨迹生成来源、严格处理原图端点数字化误差，并设法获取真实联合后验。正式版 Q 的物理含义及高 e 潮汐模型应独立讨论；在这些问题未澄清前，不将 CTL 时间延迟自动解释为原论文 Q 的唯一转换，也不启动大规模敏感性扫描。
