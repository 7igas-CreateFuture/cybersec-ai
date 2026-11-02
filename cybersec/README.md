# CyberSec AI · Phase 1 本地配置与评估

这是现有 Local AI 的增量扩展。Python 标准库后端、原生 JavaScript 前端、SQLite 历史存储均继续复用。本阶段没有训练、RAG 或执行型 Agent。

## 使用

- 原模型：`company-local:latest`；默认选择不变。
- 新派生配置：`cybersec-base:latest`；网页显示 `CyberSec AI`。
- 两者复用相同 GGUF 权重，独立的是模型名称、System Prompt 和推理参数，不是重新训练的权重。
- 可直接运行 `ollama run cybersec-base:latest`。本项目网页请求显式设置 `think=false`；CLI 若使用服务默认值可能开启 Thinking，其结果不能直接与本轮数字比较。
- 网页后端需真正重启 Python 进程才会载入更改。刷新浏览器和再次执行会复用现有进程的启动脚本不等于后端重启。加载成功后 `/health` 应含 `cybersec_profile_version: 1`。
- 建议模型切换后新建对话，避免旧模型回答继续作为上下文；原历史不会清除。

## 配置维护

`profile.json` 管理目标 ID、来源 ID 和推理参数；`system.md` 管理独立提示词；`Modelfile` 是本次创建所用参数的可读快照。`local_profiles.py` 仅对 cybersec 命名空间读取配置，再按完整模型 ID 匹配；其他模型完全沿用旧路径。未来可把 profile 的 model 改为另一个 cybersec-* 本地模型 ID，需同步显示标签和新模型创建流程。

网页请求每次读取 profile 文件；直接调用 Ollama 使用的是创建时嵌入模型的 System Prompt。修改文件不会自动更新已存在的 Ollama 模型，两者须显式同步并再测试。

`create_model.py` 只允许从已存在的本地模型创建一个尚不存在的目标 ID，拒绝覆盖或下载。当前模型已经创建，再运行它应报“Target exists”，这是保护措施。后续版本先选择新的 cybersec-* 标签并更新 profile；不要直接覆盖 company-local。

默认参数：num_ctx=8192、num_predict=1536、temperature=0、seed=42、think=false（最后一项是请求字段）。评估为公平对照统一覆盖 num_predict=1024，不能把评估参数和网页默认值混为一谈。

## 运行检查（在工程根目录执行）

```powershell
python cybersec/test_phase1.py
python cybersec/test_gold_labels.py
python cybersec/integration_test.py --out cybersec/results/integration-001
python cybersec/evaluate.py --out cybersec/results/baseline-001
```

结果目录必须尚不存在，避免覆盖历史结果。单轮模型评估逐条执行 14 个合成样例 × 2 个模型。`--models` 可指定已安装本地模型；`--repeat` 可增加重复次数；不自动下载。集成测试在 18766 端口启动同一应用，使用独立 SQLite 文件，结束时清理自己启动的进程；不写真实聊天库。

评估保存 metadata.json（模型 show/digest、参数、数据集和脚本 hash）、cases.json、responses.jsonl（完整请求、输出、终止原因、性能统计）和 summary.json。当前严格解析拒绝重复 JSON 字段。输出额度截断和请求失败分别记录，不能当作正常完成。

本次首轮在加强重复字段检测前运行，因此保留原 summary.json，并额外生成 checks-v2.json / summary-v2.json / semantic-review.json。以 v2 严格检查为准；不是替换模型输出或重跑挑结果。复算脚本为交付包的 rescore_baseline.py。

## 评分边界

10 条主分类题（SQLi/XSS/SSRF/Authorization/PathTraversal 各正负一对）、1 条证据不足、2 条合法研究误拒答、1 条授权边界。题面、预期答案和修复判据在 cases.json。分类答案只针对指定漏洞类型与明确假设，不代表整个系统无漏洞。

机械格式和 verdict 匹配与 Codex 的 AI 语义复核分开。语义复核不是人工，也不是与实现者独立的评审。标签正确并不证明修复正确。小样本、单 seed、顺序执行、无专门预热和混合长短输出不能证明稳定速度或统计显著的能力提升。False Refusal 仅两个合法请求，报告观察而不作泛化结论。

## What / Why / How / Validation

What：模型 Profile 是“同一权重 + 独立提示词/参数”的可维护配置，不是微调。
Why：在 6GB 显存环境先用已有 4.2B Q4_K_M 权重建立基准，避免重复下载及混入训练变量。
How：浏览器发送完整 Ollama ID → 后端验证本地模型 → 按 ID 选择 system/options → 本机 Ollama NDJSON → 原页面流式渲染/最终统计 → SQLite。模型工具能力声明不会自动变成可执行工具；Phase 1 不提供 tools 或执行器。
Validation：单元测试观察请求结构，HTTP 测试捕获实际发往 Ollama 的 system/options，验证双模型流式、历史保存及取消不落库；快照对比原模型 show、权重 digest 和原聊天库 hash。安全能力另用真实模型输出评价。

## 当前限制

模型在 textContent 和对象级授权负例上误报；给出了将订单 ID 与用户 ID 比较的错误修复。原模型也有错误修复。不能把输出直接当作可执行修复或生产安全结论。长附件沿用原有逐段分析，跨文件数据流不受支持。262144 是模型声明上限，本轮实际使用8192，没有长上下文或6GB训练可行性结论。

## 参考依据

模型创建与参数语义参见 [Ollama Modelfile](https://docs.ollama.com/modelfile)；流式与纳秒统计参见 [Ollama Chat API](https://docs.ollama.com/api/chat)。
XSS 标签依据 [MDN textContent](https://developer.mozilla.org/en-US/docs/Web/API/Node/textContent) 和 [innerHTML](https://developer.mozilla.org/en-US/docs/Web/API/Element/innerHTML)。SSRF 负例明确禁用 [Requests 默认跟随重定向](https://requests.readthedocs.io/en/latest/user/quickstart/#redirection-and-history)。SQL 参数绑定参见 [Python sqlite3](https://docs.python.org/3/library/sqlite3.html)。

合成样例标注 CC0-1.0，仅适用于本轮自编样例；本轮没有为原工程或模型上游权重重新指定许可证，也未推送任何远程仓库。


## Phase 1 收尾补充（2026-11-02）

`cases-v2.json` 只拆分了 SSRF 正负例的威胁前提。原 cases.json 与旧实验不变；v2尚未模型复测。显式选择：

```powershell
python cybersec/evaluate.py --cases cybersec/cases-v2.json --out cybersec/results/baseline-v2-001
```

这是供后续执行的命令，本轮没有运行。默认仍选择v1，metadata记录数据文件名、版本和hash。评估器现在只将明确stop且有内容的响应视为完整，未知终止保留输出但计为未完成。

```powershell
python -m unittest discover -s cybersec -p "test_*.py" -v
```

新test_quality.py包含协议、数据版本与人工编写的修复反例测试，不运行模型输出，不联网扫描。JDBC仅编译；未安装JDK则明确skip。若Windows系统javapath入口不可用，可将CYBERSEC_JAVAC环境变量设为实际已安装JDK的javac.exe绝对路径；本轮该入口超时，改用本机JDK23后25项全部通过，失败记录仍保存。

合成修复测试不是自动安全判定器：订单测试证明特定ID相等逻辑导致越权与误拒；文档与纯路径测试证明指定语义下的误拒；SSRF桩只验证目的地选择；Java编译仅验证声明类型。它们不证明生产修复已实现或模型能力提高。原18765已于2026-11-02完成实际流式和历史保存验收，参见 ../evidence/phase1/production-acceptance.json。隔离测试另有出站配置捕获证据；候选未替换。
