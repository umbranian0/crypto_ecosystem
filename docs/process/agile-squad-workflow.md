# Agile squad workflow — custom, built on Claude Code subagents

> Decision (2026-08-05): custom-built on native Claude Code agents rather than installing BMAD-METHOD or another external framework — no upstream dependency to reconcile with the conventions already in `implementation-plan.md`. If this stops fitting the project's needs, revisit as an ADR (`docs/adr/`), don't silently drift from it.

## Pipeline

```
Product Owner agent  →  backlog (docs/product/backlog-<module>.md)
        ↓ [human approval]
PM agent              →  sprint plan (docs/sprints/sprint-NN.md) + handoff to Tech Lead
        ↓ [human approval]
Tech Lead agent       →  tickets (docs/tickets/<ID>.md) → raises dev squad
        ↓
Dev agent(s)          →  code + tests, one ticket each, reported back to Tech Lead
```

Two human approval gates, by design (per your instruction): after the backlog, and after the sprint plan. Once the sprint plan is approved, the Tech Lead and dev squad run without further pauses and report back on completion.

**Every ticket carries the full SDLC, not just "write code"** (per your instruction 2026-08-05): Analysis → Design → Implementation → Test → Review → Documentation, each with its own acceptance criteria in the ticket file. The Tech Lead writes tickets this way and does the Review phase itself (reads the actual diff, doesn't just trust a dev agent's report); each `dev` agent does its own Design note and Self-review pass before handing a ticket back. See `.claude/agents/tech-lead.md` and `.claude/agents/dev.md` for exactly what each phase requires.

## Agents (`.claude/agents/`)

| Agent | Produces | Reads | Never does |
|---|---|---|---|
| `product-owner` | `docs/product/backlog-<module>.md` — prioritized (MoSCoW) INVEST user stories with acceptance criteria | business case, solution design, implementation plan, target module README | write sprint plans, tickets, or code; propose stories for modules whose trigger hasn't fired without flagging it |
| `pm` | `docs/sprints/sprint-NN.md` — sequenced, dependency-aware sprint plan + handoff summary | an *approved* backlog file, implementation-plan.md's build-order/module map | invent new stories, re-prioritize the backlog, make technical design calls, invoke other agents |
| `tech-lead` | `docs/tickets/<ID>.md` per ticket + `docs/tickets/README.md` index; raises `dev` subagents | an *approved* sprint plan, implementation-plan.md in full, module READMEs, CLAUDE.md | write most code itself; skip verifying a dev agent's reported results |
| `dev` | code + tests for exactly one ticket | its ticket file, target module README, relevant implementation-plan.md sections | expand scope beyond the ticket; touch another module's files; report success without having actually run tests |

## Artifact locations (repo-tracked, per module boundary rules)

```
docs/
├── product/
│   └── backlog-<module>.md       # one per module/scope, e.g. backlog-naive-first-engine.md
├── sprints/
│   └── sprint-<NN>.md            # one per sprint, sequential numbering
├── tickets/
│   ├── README.md                 # index: ticket ID, story, status, owner sprint
│   └── <ID>.md                   # one file per ticket, e.g. NFE-001-01.md
└── process/
    └── agile-squad-workflow.md   # this file
```

Ticket/story IDs use a per-module prefix matching the module's package name (e.g. `NFE-` for `naive_first_engine`). Never reuse an ID once assigned, even if a story/ticket is dropped — the gap is informative (something was scoped and deliberately cut), not a bug to fix.

## How to run this

1. `Product Owner, produce a backlog for <module>` → review `docs/product/backlog-<module>.md` → approve or request changes.
2. `PM, plan a sprint from <approved backlog file>, scope: <what you want in this sprint>` → review `docs/sprints/sprint-NN.md` → approve.
3. `Tech Lead, execute sprint <NN>` → tickets get created and a dev squad runs; you get a final report with files changed and test results.

Each stage is a separate `Agent` invocation with `subagent_type` set to the role name above — start a fresh one per stage rather than trying to keep one agent playing multiple roles, so each role only ever sees the context relevant to its job (this also keeps the "who decided what" trail clean in the artifacts themselves, not just in conversation history).
