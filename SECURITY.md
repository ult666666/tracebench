# Security

TraceBench reads local files and writes local reports; it has no network client,
credential loader, provider execution, plugin loading, or evaluation via `eval`.
Treat imported prompts and outputs as untrusted. JSONL lines are bounded,
schemas reject ambiguity, and Markdown content is escaped before rendering.

Reports contain full recorded outputs in JSON and previews in Markdown. Keep
sensitive data out of shared reports. The tool does not redact or encrypt data.
It is an educational local CLI, not a hardened multi-tenant sandbox. File-system
access permissions, concurrent file mutations, and input provenance belong to
the caller's environment. Do not run it against attacker-controlled paths with
elevated privileges.

If reporting a bug publicly, use a minimal synthetic reproduction without
credentials or personal information. For a sensitive issue, use the repository's
private vulnerability reporting channel if enabled; do not post exploitable
private data to an issue. No dedicated response-time guarantee is offered.
