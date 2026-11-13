> 历史记录：下文描述原版本的工作与验证。当前版本及验证结果以CH13_README.md和REVISION_CH13_R3.md为准。

# 运行验证记录（单机服务测量修订版）

- 资源包版本：1.3.0
- 参考运行日期：2026-10-23
- 参考环境：Python 3.13.5、Linux x86-64
- 核心仿真和单机 HTTP/CPU 测量均使用 Python 标准库；可选 psutil 只用于补充内存元数据，不是运行必需依赖。
- 自动测试：`python -m unittest discover -s tests -v`，21 项测试全部通过，包含事件与容量边界、配置读取、统一计分器、五任务手算验算、测量统计和回环范围检查。
- 四组仿真实验：`python run_all.py --config configs/base.json`，`run_status=success`；卸载、资源分配、迁移和 Q-learning 汇总行数分别为 9、3、3、4。
- 单机服务测量：在同一台电脑上启动 `edge_server.py`，执行 3 次预热和 30 次正式请求；正式请求成功 30/30，预热成功 3/3，服务端日志记录 33 条请求。
- HTTP RTT（ms）：均值 1.794、中位数 1.713、最近秩 p95 2.222、样本标准差 0.266。
- 客户端本地计算时间（ms）：中位数 0.384、p95 0.587；服务端计算墙钟时间（ms）：中位数 0.381、p95 0.535；服务端线程 CPU 时间中位数 0.379 ms。
- 输出文件：`results/real_probe_loopback.csv`、`results/real_probe_loopback_summary.json`、`results/server_requests_loopback.csv`。汇总 JSON 记录客户端 CSV 的 SHA-256。
- 范围限制：以上数据是本次主机、软件版本和负载设置下的单机回环结果，用于验证服务启动、请求处理、摘要校验、日志和统计流程；不代表跨设备网络或真实边缘网络性能。任务卸载、资源分配、服务迁移和 Q-learning 的结果仍为仿真输出，须分别解释。
- 复现命令：详见 `docs/SINGLE_MACHINE_SERVICE_TEST_GUIDE.md` 和 `README.md`。跨设备测量不是本版本基础验收条件。
