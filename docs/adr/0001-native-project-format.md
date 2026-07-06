# ADR 0001: Native Project Format

Status: Accepted

## Context

The specification requires RigStory Studio to own a versioned project format and avoid making Spine or any proprietary runtime the source of truth.

## Decision

RigStory Studio will store projects in a native `rigstory-project` format with explicit schema versions, migrations, stable IDs, and portable assets.

## Consequences

Spine-like import/export can be added later through isolated adapters, but core editing and persistence will target the native format first.
