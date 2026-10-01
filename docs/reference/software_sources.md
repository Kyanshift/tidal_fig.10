# 软件与官方资料入口

原始 `REOUND_web.md` 保存在同目录，拼写保持原件。以下补充 REBOUNDx 官方来源。

| 软件 | 文档 | 源码 |
|---|---|---|
| REBOUND | https://rebound.hanno-rein.de/ | https://github.com/hannorein/rebound |
| REBOUNDx | https://reboundx.readthedocs.io/en/latest/ | https://github.com/dtamayo/reboundx |
| REBOUNDx 效果目录 | https://reboundx.readthedocs.io/en/latest/effects.html | 当前项目 `vendor/reboundx/src/` |

实现时核对安装版本与 API，而非默认网页 latest 等于本机版本。当前是 REBOUND 5.2.1 + REBOUNDx 5.1.0，本机 REBOUNDx 有 MSVC 补丁。

官方效果目录说明 `tides_constant_time_lag` 使用半径、Love number、时间延迟和自转参数；它不是接收 Q′ 数值后自动复现 Jackson (2009) 方程的工具。模型对应、单位和参数转换需单独验证。此初始化只验证效果可以加载，没有用它生成科研曲线。
