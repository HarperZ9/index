# Product

## Register

product

## Users

Engineers and agents handed a codebase or workspace they did not write: new
maintainers, reviewers, and operators who need to know what an AI agent's
context actually contains. They arrive mid-task, often skeptical, and need to
verify rather than trust. The generated HTML surfaces (wiki, atlas, lens) are
opened locally, offline, frequently on a second monitor next to a terminal.

## Product Purpose

index maps large workspaces so people and agents can find the right context.
It derives verified wikis, dependency atlases, and budget-bounded context
envelopes from file:line evidence — never from a model's guess. The Context
Lens makes the envelope visible: what a token budget retains, what it drops,
and why, replayed live with the exact algorithm the CLI runs. Success is a
stranger re-deriving every claim on the page and getting the same bytes.

## Brand Personality

Calm, evidentiary, precise. Rigor reads calm: the interface never shouts,
never decorates, never rounds up. The receipt is part of the UI, not a
footnote. Confidence comes from re-derivability, not from visual assertion.

## Anti-references

- DeepWiki-class generated wikis: fluent, confident, unverifiable.
- SaaS dashboard grammar: hero metrics, gradient text, glassmorphism, card
  grids, eyebrow kickers. None of it carries evidence.
- Obsidian's graph view: nodes for the sake of nodes; pretty, unverified,
  silent about staleness.

## Design Principles

- **The receipt is the interface.** Hashes, verdicts, failure codes, and
  re-check commands are first-class visual elements, not fine print.
- **Never render what cannot be re-derived.** Every visual state must be a
  replay of the real algorithm over the real numbers; a slider that lies is
  worse than no slider.
- **Zero-dependency craft.** Self-contained, offline, deterministic HTML.
  Fluidity is earned with hand-rolled CSS/JS, never bought with a CDN.
- **UNVERIFIABLE is first-class.** Verdicts are never softened or rounded up;
  the UI gives failure the same typographic dignity as success.
- **Invent the category when the category is crowded.** The graph view market
  is saturated; the context lens, the budget-frontier replay, and the spine
  view exist nowhere else. Compose organs into surfaces with no incumbent
  rather than chasing parity in someone else's frame.
- **Motion shows state change.** Things move when the data moves (a repo
  crossing the budget frontier); nothing animates for decoration.

## Accessibility & Inclusion

WCAG AA contrast (4.5:1 body text), keyboard-reachable controls, visible
focus states, and a `prefers-reduced-motion` alternative for every animation.
Verdict states never rely on color alone; the word is always printed.
