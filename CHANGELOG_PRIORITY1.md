> 历史记录：下文描述原版本的工作与验证。当前版本及验证结果以CH13_README.md和REVISION_CH13_R3.md为准。

# 第一优先级修订记录

本版本对应《逐章整改意见》第十三章的第一优先级：补齐复现基础。

## 本次修改
1. `configs/base.json` 现在是实际生效的实验参数入口；`run_all.py --config <路径>` 会读取并传递配置。
2. 新增 `src/config.py`，检查必需字段、种子数量、数值范围和 Python 版本下限。
3. 新增统一计分器 `src/metrics.py`，固定完成率、超时率、拒绝率、按时完成率、平均时延、最近秩 p95、队列等待、决策耗时、能耗字段及容量违例计数的口径。
4. 任务级 CSV 使用稳定的基础字段；未建模的能耗或决策字段留空，不用零伪造数据。
5. `results/ch13/run_manifest.json` 记录包版本、运行状态、实际配置及哈希、Python/操作系统/CPU 信息、源文件哈希、输入 CSV 哈希和输出文件哈希；运行失败时记录异常。
6. 新增 `data/hand_check_5_tasks.csv`、`results/hand_check_5_tasks_reference.csv` 和 `results/hand_check_5_tasks_expected.json`，正文同步增加五任务手算表。
7. 新增计分器手算验收表及测试；测试覆盖平均时延、最近秩 p95、完成率、超时率、拒绝率、按时率和容量违例次数。

## 验证结果
- Python 3.13.5、Linux x86-64。
- `python -m unittest discover -s tests -v`：12 项测试通过。
- `python run_all.py --config configs/base.json`：四组实验成功运行，manifest 的 `run_status` 为 `success`。
- 临时自定义配置测试确认任务数、到达间隔、Q-learning 训练回合数和资源任务数会影响实际输出。
- 本机测试不代表两台独立物理设备之间的实测；跨设备验证仍属于第二优先级。

## 复现命令
```bash
python -m unittest discover -s tests -v
python run_all.py --config configs/base.json --output-dir results/ch13
```
