# TraceBench evaluation

Offline deterministic checks of recorded outputs.

Passed: 4 / 6 · Failed: 2 / 6

Suite fingerprint: `a99313d2d77360598bd69ac001f84a4562ac4dafd79ef199930fbe72a8f94733`

Latency observations: 6 / 6 (milliseconds; nearest-rank percentiles).
Mean: 150 ms · p50: 140 ms · p95: 210 ms.
Known token cost: 0.0000327 USD · priced cases: 6 / 6.
Cases missing token observations: 0 / 6.

Regressions: 2 · Improvements: 0 · Unchanged: 4.
Regression IDs: en&#x2D;greeting, zh&#x2D;location.

| Case ID | Status | Check results | Recorded output preview |
| --- | --- | --- | --- |
| en&#x2D;greeting | FAIL | exact&#x3A; FAIL &#x2014; exact string differs &#x28;case and whitespace are significant&#x29; | &#x22;hello&#x2C; world&#x21;&#x22; |
| zh&#x2D;greeting | PASS | exact&#x3A; PASS &#x2014; exact match | &#x22;你好&#xFF0C;世界&#x3002;&#x22; |
| en&#x2D;summary | PASS | contains&#x3A; PASS &#x2014; substring found | &#x22;A community can invest in renewable energy&#x2E;&#x22; |
| zh&#x2D;location | FAIL | contains&#x3A; FAIL &#x2014; required literal substring not found in string output | &#x22;上海今天晴朗&#x3002;&#x22; |
| en&#x2D;structured | PASS | json&#x5F;subset&#x3A; PASS &#x2014; JSON subset matches | &#x7B;&#xA;  &#x22;status&#x22;&#x3A; &#x22;ready&#x22;&#x2C;&#xA;  &#x22;count&#x22;&#x3A; 2&#xA;&#x7D; |
| zh&#x2D;structured | PASS | json&#x5F;subset&#x3A; PASS &#x2014; JSON subset matches | &#x7B;&#xA;  &#x22;城市&#x22;&#x3A; &#x22;上海&#x22;&#x2C;&#xA;  &#x22;项目&#x22;&#x3A; &#x5B;&#xA;    &#x22;教育&#x22;&#x2C;&#xA;    &#x22;社区&#x22;&#xA;  &#x5D;&#x2C;&#xA;  &#x22;已验证&#x22;&#x3A; true&#xA;&#x7D; |

Costs use only supplied prices and token observations. Partial coverage is not a total bill.
Recorded latency is supplied by the caller; TraceBench does not time a provider or verify provenance.
