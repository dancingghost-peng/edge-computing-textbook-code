> 历史记录：下文描述原版本的工作与验证。当前版本及验证结果以CH13_README.md和REVISION_CH13_R3.md为准。

# 五章共性整改运行验证

- 环境：Python 3.13.5，Linux x86-64。
- 本版基础运行：`python -m unittest discover -s tests -v`，31项测试全部通过。
- 原有四组仿真：`python run_all.py --config configs/base.json`，运行状态success。
- 新增四项跨章实验：`python run_cross_chapters.py`，输出四份CSV和跨章版本/哈希清单。
- 已归档的单机回环测量只验证本机HTTP服务，不能视为真实跨设备测量；没有执行跨设备实测。
- 自定义教学参数不是现场样本。
