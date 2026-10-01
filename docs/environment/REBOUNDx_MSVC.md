# REBOUNDx 本机 MSVC 适配记录

适配日期：2026-10-01。目标为本项目现有 `.venv`，Windows x64 / Python 3.12.14。

## 来源和版本

`REOUND_web.md` 提供的是 REBOUND 官网与仓库链接。REBOUND 官网的 Related projects / Additional physics 指向 REBOUNDx 官方仓库；本次据此取得 REBOUNDx 源码。

- [REBOUND 官网](https://rebound.hanno-rein.de/)
- [REBOUND 官方仓库](https://github.com/hannorein/rebound)
- [REBOUNDx 官方文档：Python 安装和使用](https://reboundx.readthedocs.io/en/latest/python_quickstart.html)
- [REBOUNDx 官方仓库](https://github.com/dtamayo/reboundx)
- [此次适配的固定源码提交](https://github.com/dtamayo/reboundx/tree/e884547a9d9790dd4779a9c129b72da8225ff67a)
- [该提交的依赖声明](https://github.com/dtamayo/reboundx/blob/e884547a9d9790dd4779a9c129b72da8225ff67a/pyproject.toml)：REBOUNDx 5.1.0，要求 `rebound>=5.0.0`。

保留已有 REBOUND 5.2.1；安装的 REBOUNDx 为 5.1.0 加本机补丁。Python 包与 C 库均保留版本号 5.1.0；这是本地适配 wheel，不能视为官方 Windows wheel。C 库 `__githash__` 记录上述上游提交，修改内容单独记录在 `artifacts/reboundx-msvc.patch`。

源码位于 `vendor/reboundx`，下载原件位于 `artifacts/reboundx-upstream.zip`，提交信息位于 `artifacts/reboundx-upstream-commit.json`。原有科学脚本未修改。

## 已确认的问题与修改

1. **C99 变长数组。** 原版在 `gr_full.c` 的 `a_const[N][3]` 和 `a_old[N][3]` 报 C2057 / C2466 / C2133。`interpolation.c` 也含 `u[n]`。改为动态分配，添加失败处理和释放；`a_old` 每次调用只分配一次，并在迭代中复用。保留原有物理公式、数组索引与循环次序。[Microsoft 数组声明说明](https://learn.microsoft.com/en-us/cpp/c-language/array-declarations?view=msvc-170)
2. **Windows 链接配置。** 上游 `setup.py` 在 Windows 仍加入 Unix `rpath` 参数，并寻找未随现有 REBOUND wheel 提供的 `.lib`。本地构建取消 Windows 的 `rpath`，用 MSVC `dumpbin /exports` 和 `lib /def` 从当前 `.venv` 的 `librebound.cp312-win_amd64.pyd` 生成导入库，链接同一份 REBOUND DLL。[Microsoft 导入库说明](https://learn.microsoft.com/en-us/cpp/build/reference/building-an-import-library-and-export-file?view=msvc-170)
3. **ctypes 库导出。** 显式导出源码中非 static 的 `rebx_*` 函数和三个版本字符串；不添加实际不存在的 Python `PyInit_libreboundx` 入口。Python 包沿用上游的 ctypes 加载方式。
4. **未导出的积分器对象。** 现有 REBOUND Windows DLL 未导出 `reb_integrator_ias15` 与 `reb_integrator_whfast` 数据对象。`steppers.c` 改用公开的 `reb_simulation_set_integrator` 取得回调与新状态；使用独立、清零的选择器结构，保持目标模拟的积分器配置不变。执行后通过对应回调释放状态。
5. **`rand_r`。** 上游随机力直接调用 POSIX `rand_r`，Windows 链接失败。改用 REBOUND 公开的 `reb_random_uniform`，保留高斯采样算法及每个模拟的 `rand_seed`，并使用 REBOUND 自身的平台随机数实现。[REBOUND 随机数实现](https://github.com/hannorein/rebound/blob/main/src/tools.c)
6. **DLL 搜索目录。** `reboundx/__init__.py` 在 Windows 先导入 REBOUND，并保持 `os.add_dll_directory` 句柄存活，确保依赖 DLL 可找到。
7. **编译参数与来源标记。** 使用 MSVC `/std:c11`、`/fp:precise`；`FFP_CONTRACT_OFF` 在 Windows 对应 `/fp:strict`。`UPSTREAM_COMMIT` 防止源码 ZIP 误记录外层项目的 Git 提交。
8. **官方测试的 Windows 文件锁。** 四个存档测试在循环中持有 `sa` 时再次删除其文件，触发 WinError 32。测试中每轮断言后 `del sa`，释放读取句柄；未跳过测试，也未调整物理、能量或逐位一致性断言。

## 本机结果

- MSVC Build Tools：Visual Studio 18，工具集 14.51.36231。
- 安装：`.venv/Lib/site-packages/reboundx` 与 `libreboundx.cp312-win_amd64.pyd`。
- wheel：`artifacts/wheels/reboundx-5.1.0-cp312-cp312-win_amd64.whl`。
- 导入 REBOUNDx、`gr_full` 实际积分与 `pip check` 通过。
- 官方测试：**134/134 通过**，耗时 29.377 秒，包含 GR、插值、随机力、参数、自定义效果、存档、恒定时间延迟潮汐、自旋潮汐和动力潮汐。最终结果见 `artifacts/reboundx-tests-final.log`。
- 本机补充验证：**4/4 通过**。IAS15 与 Kepler 包装函数和直接 IAS15 积分比较；Jacobi jump 行为、三体 interaction、目标积分器状态保持、GR 和样条插值、固定种子的随机力复现。结果见 `artifacts/reboundx-msvc-smoke.log`。
- 重装脚本已实际执行成功，完成强制编译、安装、四项补充验证和依赖检查。日志为 `artifacts/reboundx-reinstall.log`。

原版构建失败日志为 `artifacts/reboundx-upstream-build.log`，适配构建日志为 `artifacts/reboundx-msvc-build.log`。首轮官方测试日志保留了文件锁错误；存档单独复验为 `artifacts/reboundx-archive-tests.log`。

## 使用与重装

在项目目录调用现有环境：

```powershell
.\.venv\Scripts\python.exe -c "import rebound, reboundx; print(rebound.__version__, reboundx.__version__)"
.\.venv\Scripts\python.exe .\scripts\verify_reboundx_msvc.py
```

修改源码或升级 REBOUND 后，关闭使用这两个库的 Python / Jupyter 内核，再执行：

```powershell
.\scripts\install_reboundx_msvc.ps1
```

脚本针对本机 Python 3.12 x64：通过临时设置 `REBX_FORCE_BUILD=1` 强制重新编译全部 C 文件，生成 wheel，安装到现有 `.venv`，运行补充验证和 `pip check`。统一通过 pip 构建；使用 `--no-build-isolation --no-deps`，保证编译针对现有 REBOUND，并避免依赖解析替换它。构建需要 MSVC、现有 REBOUND、setuptools 和 wheel；本次已安装构建工具 setuptools 84.0.0、wheel 0.48.0。

运行官方测试：

```powershell
Push-Location .\artifacts\test-run
try {
    & ..\..\.venv\Scripts\python.exe -m unittest discover -s ..\..\vendor\reboundx\reboundx\tests -v
} finally {
    Pop-Location
}
```

本次验证范围是上述本机版本组合。REBOUND 更换版本后应重新从适配源码构建并验证，因为 C 结构布局和接口可能变化。
