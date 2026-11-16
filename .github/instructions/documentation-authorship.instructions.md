---
description: Repository rule for who authors prose and documentation
applyTo: "**"
---

# Documentation authorship

In this repository, a Claude Opus 5.5 subagent must write all prose and
documentation, including Markdown docs, templates, changelog entries, and
user-facing summaries. The primary agent writes code only. When the user needs
a message, the primary agent passes on the Opus-written text unchanged. In a
task that mixes code and documentation, still delegate the prose. If Opus 5.5
is unavailable, say so instead of using another model.

- Right: the primary agent changes the code, and an Opus 5.5 subagent updates
  `README.md`.
- Wrong: the primary agent edits `README.md` itself or writes its own summary.
