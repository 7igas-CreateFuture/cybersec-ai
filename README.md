# CyberSec AI

本地优先的安全分析助手。**v0.1.0 是 Phase 1 工程基线版**：复用 Local AI 聊天界面与 Ollama，提供独立的 CyberSec 模型配置和可重复的合成安全评估。

已经实现模型选择、流式回复、SQLite 历史、取消生成、附件文本提取和本地性能监控。尚未实现微调、RAG 或执行型 Agent。模型回答可能误报、漏报或给出错误修复，不能视为已经验证的安全结论。

## 当前版本

| 项目 | 状态 |
| --- | --- |
| 原模型 | 保留 company-local:latest |
| 安全配置 | cybersec-base:latest，复用同一权重，独立 system/options |
| Phase 1 | 原部署工程验收通过；记录见 evidence/phase1 |
| 模型效果 | 两轮真实评测已归档，未证明整体能力提升 |
| 发布范围 | 私有仓库的早期基线；不承诺稳定公共 API |

## 安装前提

- Windows 为当前验收平台；Python 3.10+，已在 3.10 / 3.12 环境运行相关检查。
- 已安装并启动本地 Ollama，监听 127.0.0.1:11434。
- 本机已有 `company-local:latest`。本仓库不包含权重，不自动下载模型。
- 验收使用 Qwen3.5 4.2B Q4_K_M、RTX 3060 Laptop 6GB；换用其他权重需重新评估，不沿用本仓库成绩。

从仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama list
ollama show company-local:latest
```

安装依赖是用户显式执行的联网步骤；聊天推理只发送到本机 Ollama。若只使用聊天、文本和 DOCX，可以暂不安装 PDF/XLSX 依赖；对应附件类型需要 requirements.txt 中的包。未验证扫描 PDF/OCR。

如果没有原模型：先取得许可允许的本地 GGUF，参照 `examples/Modelfile.company-local.example` 填入自己的文件路径，仅在确认 `company-local` 不存在时手动创建。模板不是模型下载器；不要覆盖已有模型。

如果 `cybersec-base:latest` 尚不存在：

```powershell
.\.venv\Scripts\python.exe cybersec/create_model.py
```

创建器只从已存在的本地模型派生，拒绝源模型缺失、云模型及目标已存在的情况；不会覆盖原模型。目标已存在时报错是保护行为。运行前先检查 `ollama list`，不要反复创建。

## 启动与使用

最直接、便于查看错误的入口：

```powershell
.\.venv\Scripts\python.exe local_server.py
```

网页地址为 `http://127.0.0.1:18765/`，关闭前台进程可用 Ctrl+C。`--no-browser` 可关闭自动打开浏览器的行为。

可选 Windows 启动器：

```powershell
$env:LOCAL_AI_PYTHON = (Resolve-Path .\.venv\Scripts\pythonw.exe).Path
.\start.ps1
```

启动器在未指定解释器时查找 PATH 中的 pythonw.exe / python.exe；Ollama 默认安装路径来自 LOCALAPPDATA。若机器限制 PowerShell 脚本执行，使用上面的直接 Python 入口，不需要关闭执行策略。配置版本不匹配时拒绝复用，不会自动终止未知进程。

**已有 18765 服务时不要把“复用现有实例”误认为当前 checkout 已启动。** 健康检查只标记 profile 协议版本，不区分相同版本的所有源码。更换 checkout 时由操作者核对旧进程路径并在空闲时停止，再启动所需目录；不得随意结束所有 Python/Ollama 进程。

左上角选择 CyberSec AI；切换模型后建议新建对话。历史存于 `data/conversations.sqlite3`，不会把原始附件存入数据库。这个干净仓库不自带原部署聊天库，创建新数据目录也不意味着原历史被删除。

Python 入口支持 `LOCAL_AI_PORT` 和 `LOCAL_AI_HISTORY_DB` 覆盖；默认保持本机 18765 和仓库内 data。Windows start.ps1 固定使用 18765，不支持自定义端口。不要把服务暴露到公网。

## 验证

不调用模型的单元与合成反例检查：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s cybersec -p "test_*.py" -v
```

JDBC 案例只编译、不执行 Java；需要本机 JDK，没有则明确跳过。可用 `CYBERSEC_JAVAC` 指向已安装的 javac。完整功能检查会使用本机模型与 GPU：

```powershell
.\.venv\Scripts\python.exe cybersec/integration_test.py --out cybersec/results/integration-001
.\.venv\Scripts\python.exe cybersec/evaluate.py --out cybersec/results/baseline-001
```

输出目录必须尚不存在。集成测试用 18766 和独立 SQLite，不改用户历史；会运行短生成与取消请求。基础评估为 14 条合成题 × 两模型，完整保存失败输出，不是大规模能力基准。

`cases-v2.json` 修订了 SSRF 前提，尚无对应模型成绩。`compare_prompts.py` 复现已冻结候选对照，候选没有部署。评估细节见 [配置与评估说明](cybersec/README.md) 和 [实验结果](docs/EVALUATION.md)。

## 工程结构

```text
index.html / ui.js / ui.css   原生聊天与监控界面
local_server.py              本机 HTTP API、请求鉴权与流式事件
local_assistant.py           附件提取与 Ollama 流式调用
local_history.py             SQLite 对话、revision 检查
local_profiles.py           完整模型 ID 对应的独立配置
local_runtime.py            本机模型与 GPU 指标
cybersec/                   配置、合成样例、评估及测试
evidence/                   脱敏元数据、合成输出与验收证据
docs/                       发布记录和实验结论
```

Profile 改变的是提示词和推理参数，未改变权重。网页显式发送 system；修改本地文件不会自动更新 Ollama 内嵌配置，两者需要显式同步与重新验证。模型声明支持 tools 不代表本应用已经能执行工具。

## 发布与后续

当前代码基于已验收工程整理，移除了作者机器的固定解释器路径。没有重写正在运行的原部署，也没有迁移聊天库。干净机器从零安装尚未完整验证；初始发布保留这一限制。

- [v0.1.0 发布说明](docs/RELEASE-v0.1.0.md)
- [变更记录](CHANGELOG.md)
- [数据与许可范围](PRIVATE_REPOSITORY.md)
- [本地使用边界](SECURITY.md)

后续由项目负责人选择里程碑，不因建立仓库自动实施训练、RAG、Agent 或 v1.0。
