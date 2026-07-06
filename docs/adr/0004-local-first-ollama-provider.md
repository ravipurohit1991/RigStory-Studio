# ADR 0004: Local-First Ollama Provider

Status: Accepted

## Context

The first release targets local privacy and Ollama running on the user's computer.

## Decision

Ollama is accessed through an `LLMProvider` boundary using configurable HTTP base URLs. Phase 0 implements only reachability health.

## Consequences

The app remains useful when Ollama is offline. Future model listing and structured generation must stay behind the provider boundary.
