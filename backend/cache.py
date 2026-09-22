# backend/cache.py
#
# Redis cache client for the support system.
#
# Responsibility:
#   Provides a centralised interface for all Redis operations in the system.
#   Redis is used as an ephemeral layer — nothing stored here is a system of
#   record; Postgres is always the source of truth.
#
# Use cases this module covers:
#
#   1. Session memory hot cache
#      - Store recent conversation turns for low-latency reads during a live
#        session (Orchestrator reads this first before hitting Postgres).
#      - TTL-based expiry so stale sessions are cleaned up automatically.
#
#   2. Rate limiting
#      - Sliding-window counters per customer / per IP to enforce request
#        rate limits at the Gateway before hitting the agent runtime.
#
#   3. Session-level locking
#      - A short-lived distributed lock per session_id to serialise concurrent
#        messages in the same session. Prevents racing writes to the LangGraph
#        checkpointer when a customer sends messages in rapid succession.
#
#   4. HITL resume pub/sub
#      - The approval HTTP endpoint publishes a "resume" signal to a Redis
#        channel keyed by session_id. The Agent Runtime Worker subscribes and
#        calls graph.resume() to continue the paused LangGraph execution.
#
#   5. Background job queue
#      - Jobs for the Notification Worker (approval alerts, SLA expiry sweeps)
#        are enqueued here and consumed by the worker process asynchronously,
#        so a flaky notification channel never blocks the main request path.
