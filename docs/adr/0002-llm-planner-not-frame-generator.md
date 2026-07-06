# ADR 0002: LLM Planner, Not Frame Generator

Status: Accepted

## Context

The product promise depends on editable, deterministic animation rather than opaque model-generated frames.

## Decision

LLMs may produce validated semantic plans and blueprints. They must not generate frame-by-frame animation or mutate project state directly.

## Consequences

Motion quality belongs to deterministic engine code. Ollama integration must validate structured output before later phases can construct domain objects.
