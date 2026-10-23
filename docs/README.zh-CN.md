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
