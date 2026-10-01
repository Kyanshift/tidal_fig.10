# Windows 科学环境

初始化核对日期：2026-10-01。使用已有 `.venv`，Python 3.12.14、REBOUND 5.2.1、REBOUNDx 5.1.0、PyYAML 6.0.3。实际分发包版本保存于 `requirements/environment-observed.txt`。

REBOUNDx 是已有 MSVC 本机适配版。包版本号本身不能唯一标识 DLL：`artifacts/reboundx-msvc.patch`、`artifacts/reboundx-upstream-commit.json`、`vendor/reboundx` 和本机 wheel 一起构成来源。记录工具保存补丁/来源文件 SHA256，基准配置还复制这些证据到每个 run。

详细历史说明见 `REBOUNDx_MSVC.md`；该文件从根目录移动到此，内容保持原件。其中 `REOUND_web.md` 原件现位于 `docs/reference/REOUND_web.md`，文中的 PowerShell 命令均以项目根目录为运行目录。

构建脚本仍在 `scripts/install_reboundx_msvc.ps1`，验证脚本仍在 `scripts/verify_reboundx_msvc.py`，vendor/artifacts 的相对路径未变化。本次没有重新构建、升级或重新安装科学包。

```powershell
.\.venv\Scripts\python.exe .\scripts\experiment.py doctor
.\.venv\Scripts\python.exe .\scripts\verify_reboundx_msvc.py
```

`requirements/recording.txt` 只用于缺失 PyYAML 的记录环境；`environment-observed.txt` 是实际版本快照，不是可替代本机补丁来源的安装锁文件。不要根据普通 `pip install reboundx==5.1.0` 就认定重建了当前环境。以后需要重建时按 MSVC 说明使用固定源码、补丁、既有 REBOUND 和验证脚本。
