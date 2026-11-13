# 第十三章实验包

当前版本：1.4.1-ch13-r3。四组仿真只使用Python标准库，要求Python 3.10及以上；不需要GPU或容器。请在run_all.py所在文件夹打开终端。

## 从这里开始

```powershell
python --version
python -m unittest discover -s tests -v
python run_all.py --config configs/base.json --output-dir results/ch13
python audit_ch13.py --run-dir results/ch13
```

成功判据：自动测试通过；results/ch13/run_manifest.json中run_status为success；核验程序显示Stage sums verified。省略--output-dir时也输出到results/ch13。比较新参数时请使用新的输出目录，并将该目录传给audit_ch13.py。

配置以configs/base.json为入口。运行清单保存当次实际配置；核验读取清单中的配置快照并核对日志哈希，因此以后修改base.json不会改变历史核验参数。哈希核对用于辨认同次材料，不证明模型本身正确。

## 单机HTTP测量

终端A：

```powershell
python edge_server.py --host 127.0.0.1 --port 18763 --log results/ch13/server_loopback.csv
```

终端B：

```powershell
python real_probe.py --url http://127.0.0.1:18763/compute --requests 30 --warmup 3 --payload-bytes 1024 --iterations 1000 --output results/ch13/probe_loopback.csv --summary-output results/ch13/probe_loopback_summary.json
```

两端仅使用同机回环。成功统计只纳入业务校验通过的正式请求。每次尝试均记录http_attempt_ms；http_rtt_ms只在完整读到响应时填写。连接失败或读取中断时，它保持空值，已观测的尝试时长与CPU时间仍保留。HTTP错误或响应校验失败不会抹去已观测字段；error_phase区分传输和响应校验。失败耗时不等于服务端计算时间。

## 结果与文件

- results/ch13：本版本重新运行的四组仿真结果、配置清单与输入。
- results/reference_ch13：原讲解版的仿真参考输出，保留用于核对；其中版本和哈希属于原运行。
- results/textbook_verified：教材修订稿表13.10（原表13.8）采用的历史单机测量；本次不以新机器计时替换这些数值。
- qlearning_training.csv：每种子每回合的完整记录；qlearning_training.svg绘出全部回合的跨种子平均奖励。
- tests/test_ch13_failures.py与tests/test_ch13_audit.py：本轮新增的异常日志与历史配置核验测试。

本包保留原有其他章节支持模块。历史变更和验证文件不作为当前运行成功的证据；当前说明以本文件为准。可选PNG绘图需要Pillow，使用scripts/plot_training.py读取已有CSV；运行核心实验与SVG输出无需安装它。详见REVISION_CH13_R3.md。
