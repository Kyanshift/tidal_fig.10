# 实验记录系统

每次运行分配新目录；run 数字在各类别内递增，完整身份是类别+run_id。创建通过原子 mkdir 防止 ID 覆盖。

```text
results/sweeps/run_000123/
├── config.yaml          创建时解析后的 YAML 快照
├── metadata.json        来源、环境、代码/输入 SHA256 和随机种子
├── evolution.csv        长表格式演化输出
├── summary.json         状态、终止原因和指标
└── inputs/
    ├── code.zip         当前 src/scripts/requirements/pyproject 的代码快照
    └── files/           config.inputs 中逐项复制的输入
```

## 核心文件契约

`config.yaml`：schema_version=1、experiment.name/kind/dataset_type、seed、单位、模型、初态、积分方向和输入列表。保存 resolved 配置；当前示例本身没有变量继承/插值。以后 sweep 生成器须把每组实际数值写成单次配置后再创建 run。搜索设计 YAML 不能直接传入 create。

`metadata.json`：创建时间 UTC、项目时区 Europe/Berlin、Python/平台/依赖、Git commit/dirty/状态摘要、配置 hash、输入和代码快照。未提交代码也存入 code.zip；Git commit 为 null 时不能假称提交已存在。本机 REBOUNDx 记录补丁与上游来源文件 hash；基准配置同时复制它们。环境版本快照不等于跨机器逐位可重复承诺。

`evolution.csv` 列：

| 字段 | 含义 |
|---|---|
| t_year | 配置时间零点后的年数，可为负；按积分方向严格单调（每个 body 各自检查） |
| body | 行星/其他轨道体标识；多个 body 可交错输出 |
| a_au, e | 瞬时/轨道平均量的含义须由 model 说明 |
| pericentre_au | a×(1-e)，记录工具核验一致性 |
| stellar_radius_au, roche_limit_au | 可空；有值时必须非负并以 au 表示 |
| event | 事件或空串；双曲逃逸允许 a<0、e>1，但必须写 ejection |

NaN/Infinity 不允许作为普通演化值；数值失败写入 summary。抛物轨道等没有有限 a 的状态用事件/终止摘要表达，不强行塞入当前表。每个随机实现单独 run，避免多条样本轨迹共用同一个 body 时间序列。

`summary.json`：planned → running → completed/failed/aborted。row_count 与 CSV 对应。必须填写终止原因；completed 必须有演化数据，但不等同于科学通过。将 Fig.10 接受与收敛结果另写 metrics，并标单位；工具不自动推算这些物理指标。

## 使用

```powershell
# 只创建记录。示例路径以 create 实际返回值为准。
.\.venv\Scripts\python.exe scripts/experiment.py create --config configs/reproductions/fig10_baseline.yaml --category reproductions
# 未来模拟器输出具有上述完整表头的 CSV，再追加。
.\.venv\Scripts\python.exe scripts/experiment.py append --run results/reproductions/run_000001 --csv path/to/output.csv
.\.venv\Scripts\python.exe scripts/experiment.py finish --run results/reproductions/run_000001 --status completed --reason integration_end
.\.venv\Scripts\python.exe scripts/experiment.py validate --run results/reproductions/run_000001
.\.venv\Scripts\python.exe scripts/experiment.py list
```

Python 接口为 `k2_261b.records.create_run/append_rows/finish_run/validate_run`。不安装项目时，入口脚本自动添加 src 路径。

物理求解器与记录模块分开：`scripts/experiment.py simulate --config configs/reproductions/fig10_bs_forward.yaml` 分配新科研 run 并执行明确配置的 Jackson 求解器；`ctl-check --config configs/reproductions/fig10_ctl_diagnostic.yaml` 执行 REBOUNDx 短程诊断。求解器使用 run 中的配置/输入快照。完整中心曲线、收敛与近似 ensemble 的有预算运行入口见 `scripts/reproduce_fig10.py` 与 `docs/science/fig10_stage1_results.md`。新的接受结论写派生分析文件，不改写已完成 run。

`configs/examples/recording_demo.yaml` 和 demo 命令提供 synthetic 记录演示，构造数值明确没有物理意义；已有本机示例结果未随代码分发。科研统计必须筛选 dataset_type=scientific。

## 完整性与存储边界

配置/输入快照由 SHA256 检查；终态通过工具不再可追加。同一 run 的写入使用独占锁。写 CSV 与 summary 分别使用原子替换，但两文件不是跨文件事务：进程在中间被终止可能出现 row_count 不一致，validate 会报错。遇到这种情况保留现场、先核对 CSV/状态和日志，再明确记录恢复操作。不要自动删除陈旧锁或默默改写原实验。

输入/代码快照创建失败时，保留四个核心文件与 failed 状态，metadata 的 initialization_status 标为 failed。该目录用于审计失败，不作为完整实验使用；validate 拒绝继续写入，重新尝试时分配新编号。磁盘完全不可写等底层故障仍需保留现有现场后恢复。

Git 保留契约、配置、输入来源与小型 examples；真实 reproductions/sweeps/architectures 输出被忽略，仍保存在本机。忽略不等于备份，长期结果需要另选归档位置。无需中心数据库，list 从各 run 的 summary 发现记录。
