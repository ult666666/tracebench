# TraceBench 中文指南

TraceBench 用于离线检查已记录的 AI 输出。它按案例 ID 对齐数据，执行确定性检查，
汇总用户提供的延迟与 token 数，并与基线比较。Python 3.11 以上即可运行，无第三方
依赖，不调用模型、不需要密钥。

所有示例、延迟、token 数和价格均为合成演示数据，不代表真实模型表现或当前价格。
这是 AI 辅助开发的学习项目，尚未用于生产。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --no-index .
mkdir -p reports
.venv/bin/tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/baseline.jsonl --pricing fixtures/pricing.json --report reports/baseline.json
.venv/bin/tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/clean.jsonl --pricing fixtures/pricing.json --baseline reports/baseline.json --report reports/clean.json
.venv/bin/tracebench evaluate --cases fixtures/cases.jsonl --outputs fixtures/regression.jsonl --pricing fixtures/pricing.json --baseline reports/baseline.json --format markdown --report reports/regression.md
```

三条评估命令依次返回 **0、0、3**。最后一条故意把英文大小写改错，并将“北京”改为
“上海”，从而触发两个回归。可直接阅读[示例报告](sample-regression.md)。

- `exact`：字符串完全一致，区分大小写、空格与 Unicode 码点。
- `contains`：输出字符串包含指定的非空子串。
- `json_subset`：递归匹配对象子集；数组长度和顺序必须一致；布尔值不等于数字。

案例和输出均使用 UTF-8 JSONL，每行一个对象。重复 ID、重复 JSON 键、缺失或多余
输出、未知字段、非法 Unicode、NaN/Infinity 与负数指标都会被拒绝。

延迟单位为毫秒，必须由调用方测量并提供；缺失值不会被当作零。p50/p95 使用最近秩
方法。价格单位为每百万 token，使用十进制字符串与 Decimal 计算。没有价格或 token
观测时，成本为 null；只覆盖部分案例的成本和不代表完整账单。

退出码：0 全部通过；1 有检查失败；2 输入、基线兼容性或文件错误；3 基线通过的案例
现在失败。基线必须是相同案例集的 JSON 报告，修改提示、描述或检查条件后需重新建立。

## 离线 HTML 报告

添加 `--format html --report reports/regression.html` 即可生成自包含报告，
省略 `--report` 则输出到标准输出。退出码仍为 0/1/2/3，文件写入仍为原子替换，
不能覆盖输入文件。HTML 不能作为比较基线，基线仍使用 JSON。

可在浏览器中打开[合成数据示例](sample-report.html)。报告显示套件指纹、通过与失败数、
回归与改善数、最近秩延迟统计及观测覆盖率、精确十进制成本与币种，并保留数据来源限制。
每个案例可展开查看完整输出及各项检查的状态和原因。输出以完整 JSON 值显示，原因以
JSON 字符串显示，不截断，保留 Unicode、换行、控制字符和精确小数。当前报告结构
没有保留输入及预期值，因此不会重建或编造这些内容。

搜索框支持案例 ID 与输出文本，状态筛选包括全部、通过、失败、回归及改善。
控件有标签，可用键盘操作，并显示实时可见数。禁用 JavaScript 时，所有案例仍可查看；
打印会隐藏控件，并展开全部案例的输出与检查原因。

报告没有外部资源、网络请求或运行时依赖。所有记录内容均被转义为惰性文本，严格 CSP
仅允许固定脚本及样式的精确哈希。示例可通过 `python3 scripts/verify_html.py --write-sample`
从已提交夹具确定性重建；不带该选项运行时会检查提交文件的精确字节。可选浏览器验证
使用已有 Playwright，不安装 Node 依赖。详见 [HTML 报告](HTML.md)。

运行测试：`python3 -m unittest discover -v`。详细设计见
[架构](ARCHITECTURE.md)、[方法与限制](METHODOLOGY.md)、[数据契约](SCHEMAS.md)
与[验证记录](VERIFICATION.md)。这些机械检查无法判断事实正确性或语义质量。

## 0.4.0：显式观测预算

预算是独立的规则文件与判定结果，不改变原有 schema 1 评估报告或 evaluate
命令的 0/1/2/3 退出码。在前面的 clean.json 生成后运行：

```sh
.venv/bin/tracebench policy --evaluation reports/clean.json --rules fixtures/budget-pass.json --report reports/policy.json
.venv/bin/tracebench policy --evaluation reports/clean.json --rules fixtures/budget-fail.json --format markdown --report reports/policy-fail.md
```

两条命令分别退出 **0**、**1**。合成规则均要求通过率 1、总成本不超过
0.0000327 USD，p95 延迟上限分别为 210 与 209.999 毫秒。所有选中规则必须满足；
通过率按整数通过数/案例数精确比较，延迟和成本不转为二进制浮点数。

延迟预算要求全部案例都有用户提供的延迟。成本预算要求全部案例都有 token
观测与已定价成本，且币种完全相同。缺失、部分覆盖或币种不符显示 unavailable，
并拒绝预算；完整覆盖下的实际零值可以参与比较。policy 的 **2** 表示规则、报告、
文件、用法错误。规则文件上限 64 KiB，评估输入上限 64 MiB，原有基线输入仍为
16 MiB。详见 [规则与结果契约](SCHEMAS.md)。

预算接受只针对选中的阈值；结果保留失败案例数、回归数、suite 指纹及序列化评估
指纹。所有观测仍由调用者提供，工具不测量、不认证、不查询价格、不换算币种，
也不代表模型质量、安全性或支出授权。

可复用 CI 的可选 `rules` 参数生成 policy.json、policy.md 与 rules.json 快照，
先上传再应用组合门禁。普通门禁优先保留评估的 1/3 失败；只有评估 0 时才由预算
拒绝增加退出 1。`expectation: policy-failure` 仅用于合成验证，必须观察到评估 0
与预算 1；不能替代真实发布门禁。默认不传规则时，原有五个文件和门禁契约保持。
参见 [CI 文档](CI.md)。托管运行、独立审查及发布证据由集成阶段另行记录。
