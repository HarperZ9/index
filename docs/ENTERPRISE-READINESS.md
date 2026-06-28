# Index Enterprise Readiness

Index is the enterprise codebase atlas: it compresses large workspaces into evidence-backed maps, source refs, dependency edges, freshness checks, and context packs for agent workflows.

This guide aligns the flagship with Project Telos context envelopes and action receipts. The goal is unattended agent work that can be left running and later inspected: what context the agent saw, what exact material it relied on, what it changed, what verified, and what remained unverifiable.

## Enterprise Role

- Map repositories, manifests, imports, docs, internals, and architecture rules before an agent edits.
- Emit compact context packs with exact file-line evidence and expansion commands.
- Measure token economy, architecture drift, freshness, cycles, and claim grounding without a model.

## Host Commands

- `index status --json` and `index doctor --json` for host readiness.
- `index map --root ROOT --json` before assignment or routing.
- `index context --root ROOT --focus NAME --json --audit` for source-ref packets.
- `index verify --root ROOT --depends "A -> B" --json` for claim grounding.
- `index freshness --cert CERT --root ROOT --json` before trusting an old packet.

## Context Envelope Contribution

- Context envelopes should start from an index map and include root hash, git head, dirty state, source refs, and expansion commands.
- Summaries must point to evidence like `pyproject.toml:12` or a symbol/file range, not memory of the repo.
- A large codebase should be routed through focused packs and on-demand expansion instead of raw full-tree dumps.

## Action Receipt Contribution

- Input/material digests come from workspace fingerprints, map outputs, freshness certificates, and source-ref content hashes.
- Side-effect class is usually `read`; generated routers or artifacts are `write` and need output refs.
- A stale freshness certificate maps to an UNVERIFIABLE receipt until the map is refreshed.

## Readability Gate

Enterprise agent output should be easier for the next agent and a human reviewer to continue:

- Keep patches small enough to review and tied to one bounded work item.
- Prefer named helpers and domain terms over dense inline logic.
- Preserve public interfaces unless the receipt explains why they moved.
- Leave tests, command output, changed files, and next action in the handoff.
- Mark missing source refs, stale packets, failed tests, and verifier abstentions as UNVERIFIABLE instead of guessing.

## Platform Boundary

The flagship remains usable alone through CLI JSON and as part of a larger surface through MCP. OpenAI, Anthropic, IDE, CLI, TUI, and application hosts should consume the same tool outputs and receipt fields rather than reimplementing flagship behavior.

See Project Telos `project-telos.context-envelope/v1` and `project-telos.action-receipt/v1` for the shared cross-tool contract.
