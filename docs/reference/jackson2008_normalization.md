# Jackson 方法的 Love number 归一化

来源：Jackson, Greenberg & Barnes (2008), *Tidal Evolution of Close-in Extrasolar Planets*, ApJ 678, 1396–1406，§2.1，PDF 第 2 页（期刊第 1397 页）。[作者托管 PDF](https://faculty.washington.edu/rkb9/publications/jgb08a.pdf)，DOI `10.1086/529221`。2026-10-01 核对在线原文；本文件是来源核对笔记，不是论文原件。

原文说明轨道平均方程的系数按 Love number 为 3/2 写出，实际 Love number 的修正吸收到其称为 Q 的参数中。因此与普通质量因子 Q 比较时，Jackson 分母采用的归一化为 `Q_prime_J = 3*Q/(2*k2)`。Jackson (2009) §2 改用带撇号记法，并修正恒星潮汐系数；实现必须使用 2009 的公式 (1)、(2)。

这只核对归一化，不证明不同耗散模型、激励频率或自转状态可以用同一个 Q 相互映射。Penev (2018) 本地 PDF 第 1 页定义 `Q_prime_P = Q/k2`；只有普通 Q、k2 及其物理条件相同，才有 `Q_prime_J = 1.5*Q_prime_P`。
