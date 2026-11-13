# 边缘计算教材第1章与第13章配套 Python 代码

本仓库提供教材第1章的时延计算程序，以及第13章的实验代码、教学数据、配置文件和参考结果，供读者查看与复现。第1章程序对应“习题—4. 时延计算程序实验”；第13章代码版本为 **1.4.1-ch13-r3**，来源于“最终修订版”的第13章配套代码包。

第1章程序在 `chapter01/` 子目录；第13章程序保留在仓库根目录，运行命令与教材一致。

## 环境要求

- Python 3.10 或以上，建议使用 Python 3.12。
- 四组核心仿真及 SVG 输出只使用 Python 标准库，无需安装第三方依赖。
- 基础实验不需要 GPU、容器或云平台。
- 可选的 PNG 绘图另需依赖，见 `requirements-figures.txt` 和对应脚本说明。

## 第1章时延计算

下载解压后，在仓库根目录打开终端：

```console
python chapter01/chapter1_latency.py
python chapter01/chapter1_latency.py --scan
```

程序只使用 Python 标准库，在 `chapter01/` 生成 `latency_results.csv`、`calculation_record.json`；加上 `--scan` 后另生成 `sensitivity_results.csv`。

基准本地、边缘、远端云时延依次为 400、231、542 ms；边缘上行降为 20 Mbit/s 后为 331 ms；最小上行速率约为 23.669 Mbit/s。它们是例题参数下的理论计算。详情见 [第1章说明](chapter01/README.md)。

## 第13章下载与运行

点击仓库页面的 **Code → Download ZIP**，解压后，在 `run_all.py` 所在文件夹打开终端。也可以使用 Git 克隆仓库。

先检查版本并运行自动测试：

```console
python --version
python -m unittest discover -s tests -v
```

按教材命令运行全部四组仿真，再核验时延各阶段之和：

```console
python run_all.py --config configs/base.json --output-dir results/ch13
python audit_ch13.py --run-dir results/ch13
```

`results/ch13` 含随包参考结果，上述命令会更新其中的同名文件。希望保留参考结果时，请使用新目录：

```console
python run_all.py --config configs/base.json --output-dir results/my_run
python audit_ch13.py --run-dir results/my_run
```

成功判据：自动测试通过；本次输出目录的 `run_manifest.json` 中 `run_status` 为 `success`；核验程序显示 `Stage sums verified`。运行前已有的参考文件不能代替本次运行成功的证据。

部分系统的 Python 命令为 `python3`，请相应替换。

## 实验内容与程序入口

| 内容 | 主要代码 |
|---|---|
| 任务卸载 | `src/experiment_offloading.py` |
| 资源分配 | `src/experiment_resources.py` |
| 服务迁移 | `src/experiment_migration.py` |
| 表格型 Q-learning | `src/experiment_qlearning.py` |
| 四组实验统一入口 | `run_all.py` |
| 结果核验 | `audit_ch13.py` |
| 单机 HTTP 服务与请求测量 | `edge_server.py`、`real_probe.py` |

## 文件说明

| 路径 | 用途 |
|---|---|
| `configs/base.json` | 第13章默认实验参数 |
| `src/` | 实验实现、配置校验与指标计算 |
| `data/` | 教学输入与记录模板 |
| `tests/` | 原配套包自动测试 |
| `results/ch13/` | 当前版本随包仿真结果 |
| `results/reference_ch13/` | 原讲解版参考输出 |
| `results/textbook_verified/` | 教材历史单机测量日志 |
| `CH13_README.md` | 原第13章详细说明 |
| `docs/SINGLE_MACHINE_SERVICE_TEST_GUIDE.md` | 单机服务测量说明 |
| `docs/REPOSITORY_SCOPE.md` | 收录范围、来源和版本说明 |
| `source_manifest.json` | 原始来源与文件哈希 |

原包还包含第4、5、11、12章的辅助算例模块和跨章运行入口，保留其依赖关系；本仓库本次发布范围为第1章和第13章，不表示全书各章代码均已整理。

## 单机 HTTP 测量

在两个终端分别运行以下命令。它们通过本机回环地址通信。

终端 A：

```console
python edge_server.py --host 127.0.0.1 --port 18763 --log results/my_run/server_loopback.csv
```

终端 B：

```console
python real_probe.py --url http://127.0.0.1:18763/compute --requests 30 --warmup 3 --payload-bytes 1024 --iterations 1000 --output results/my_run/probe_loopback.csv --summary-output results/my_run/probe_loopback_summary.json
```

结束后在终端 A 按 `Ctrl+C` 停止服务。单机回环测量与仿真结果分别解释；实际运行耗时会随机器变化。教材历史测量值应以原日志为依据。

## 数据与授权说明

仿真 CSV 使用教学假设数据；本仓库不包含教材 Word 正文。公开查看代码与采用开源许可证是两件独立事项。本次整理保留原包的授权说明，未新增 MIT、Apache 等许可证；使用及再分发范围以权利人的明确授权为准。详见 `资源许可待确认.md`。
