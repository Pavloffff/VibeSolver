# VibeSolver — Project Context

> Source of truth for AI agents. Read this before proposing or implementing changes.

## Purpose

VibeSolver automates IT support ticket handling end-to-end: a customer's unstructured ticket goes in; a Merge Request with a fix (after human approval) or an escalation dossier for the on-call developer comes out. The system grounds all agent reasoning in product context — source code, documentation, user flows, and ticket history — provided by an internal knowledge layer.

## Problem Statement

1. Ticket resolution time grows with load.
2. Product knowledge is scattered across support lines and not accumulated.
3. General-purpose LLMs do not know the specific product (code, docs, scenarios).
4. No standardized multi-agent solutions connect development and support processes.

## Architecture (C4 summary)

- **C1 Context:** support L1 staff (tickets, MR approval), support engineer (import, user-flow approval), on-call developer (escalations). External: GitLab (repos, MR API), Confluence/GitWiki, LLM APIs.
- **C2 Containers:** web UI (React) → API gateway (FastAPI) → PostgreSQL+pgvector; Celery workers (ingest, agents) over Redis; SeaweedFS (S3 artifacts); Langfuse (traces); Sandbox Executor.
- **C3 Agent graph (LangGraph):** Triage → Log/Screen Analyzer → Code Investigator → Fix Writer ↔ (sandbox tests, max 3 iterations) → Human Approval → MR Builder | Escalation Builder.

Key ideas (also the research hypotheses):
- User Flow matching scopes retrieval before the LLM is invoked (narrower search → fewer tokens, higher auto-resolution).
- Ticket history is a fourth source type (kind=ticket) for similar-case retrieval.
- LLM-generated documentation from docstrings (kind=doc_generated, provenance-flagged, human-validated) improves retrieval vs. code-only index.
- Ablation ("with context / without") quantifies the knowledge layer's contribution.

## Data Model (core tables)

- `sources` — registered content sources (connector config, JSONB).
- `chunks` — universal index: kind (code|doc|doc_generated|ticket), repo, path, symbol, content, tsv (tsvector), embedding (vector), content_hash, commit.
- `user_flows` + `user_flow_versions` + `flow_embeddings` — user scenarios as first-class retrieval context.
- `tickets`, `ticket_artifacts`, `agent_runs`, `patches`, `sandbox_runs`, `escalations`, `audit_log` — ticket lifecycle and full traceability.

## Non-Goals (for now)

- No model training/fine-tuning — existing models only, via LLM gateway.
- No multi-host k8s — single host docker-compose MVP.
- No Jira/Telegram sinks yet — OutcomeSink SPI keeps the door open.

## Quality Standards

- Retrieval quality: recall@10 ≥ 0.8 on golden set localization labels.
- Pipeline: auto-resolution ≥ 50% of golden set, MR acceptance ≥ 70% by reviewers.
- Eval protocol: ablation of context sources (flow scope on/off, ticket history on/off, local vs cloud models).

## References

- Architecture diagrams: `docs/` (C4: SystemContext, Containers, AgentGraph, TicketFlow, ImportFlow).
- Comparison with analogs (Glean, Copilot Enterprise, Cody, SWE-agent, AutoCodeRover, RAGFlow, Dify, etc.): thesis review chapter.