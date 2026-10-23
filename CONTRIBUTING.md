# Contributing

Use Python 3.11+ and synthetic inputs. No third-party runtime or test dependency
is needed. Run `python3 -m unittest discover -v` from the repository root.

For behavior changes, first add a failing boundary test with a hand-derived
expected result. Test actual parsing, evaluation, or CLI behavior rather than
source text. Preserve stable exit codes, strict schemas, exact costs, and honest
metric coverage. Document schema or compatibility changes explicitly.

Check installation with `python3 -m venv .venv` followed by
`.venv/bin/python -m pip install --no-index .`. Run the README demo and expect
exits 0, 0, 3. Never commit real prompts, credentials, private outputs, generated
`reports/`, or virtual environments. AI-assisted contributions are welcome;
describe what was generated and what you actually reviewed and executed.

For the dedicated HTML browser checks, use Node 24 and the exact locked
Playwright tooling in `browser/`; see [HTML verification](docs/HTML.md).
The [CI integration guide](docs/CI.md) describes report handoff, deliberate
regression verification and caller trust. Node tooling is development-only.
