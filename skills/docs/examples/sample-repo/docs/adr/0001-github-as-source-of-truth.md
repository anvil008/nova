# 1. GitHub as the source of truth

## Status
Accepted

## Context
Plans decompose into tasks that many builders work in parallel; the state must survive crashes and be resumable.

## Decision
Use GitHub issues under a milestone as the durable task board.

## Consequences
Work is observable and resumable; a future Kanban can pull from it.
