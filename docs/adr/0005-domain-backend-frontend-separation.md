# ADR 0005: Domain, Backend, And Frontend Separation

Status: Accepted

## Context

The specification requires deterministic domain behavior that is independent from FastAPI, SQLModel, React, PixiJS, and Ollama.

## Decision

Domain types and algorithms will live separately from API routers, persistence models, frontend components, renderer objects, and provider adapters.

## Consequences

Phase 0 creates backend and frontend shells only. Future domain modules must avoid framework imports and be tested directly.
