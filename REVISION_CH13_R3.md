# 第十三章配套修订记录

版本1.4.1-ch13-r3，修订日期2026年11月12日。

1. real_probe.py以结构化结果返回已观测的传输信息；先写入观测，再解析和校验响应。新增http_attempt_ms、http_response_complete和error_phase。完整响应的往返时长与未完成尝试的耗时分别标明，失败仍不进入成功时延汇总。
2. audit_ch13.py读取目标运行清单中的配置快照，并核对卸载日志哈希，避免当前配置修改后误检历史结果。
3. run_all.py默认输出目录与教材、README统一为results/ch13；自定义目录通过--output-dir和--run-dir对应。
4. 保留全部训练回合绘制SVG。可选scripts/plot_training.py从CSV生成单模型与跨种子平均的两幅训练曲线，不重新训练。
5. 新增6项请求异常与成功路径测试、5项运行核验测试。加上原32项，共43项自动测试。

复核命令：

```powershell
python -m unittest discover -s tests -v
python run_all.py --config configs/base.json --output-dir results/ch13
python audit_ch13.py --run-dir results/ch13
```

本轮已运行全部43项测试、四组仿真和4500条卸载日志核验。与原参考运行相比，五个主要汇总CSV的非墙钟指标逐字段一致；实际决策耗时与训练耗时会随运行变化。

教材单机测量表沿用原始日志重算值（修订稿表13.10，原表13.8），不以本轮短测替换。单机短测只用于检查修复后的服务调用成功与失败路径，输出位于单独的验证目录。
