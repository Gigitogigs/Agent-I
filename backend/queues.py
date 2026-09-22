# backend/queues.py
#
# Background job queue definitions for the support system.
#
# Responsibility:
#   Defines the job/task types that are enqueued in Redis and consumed by
#   the Notification Worker process. This separates slow or potentially
#   flaky side-effects (sending emails, calling webhooks) from the critical
#   request path, so a downstream notification failure never blocks a live
#   chat turn.
#
# Job types this module will define:
#
#   1. ApprovalNotificationJob
#      - Triggered when: escalation_agent creates a new HITL checkpoint
#      - Payload: checkpoint_id, operator_role, action_summary, risk_level,
#                 expires_at, channel preference (webhook primary / email fallback)
#      - Worker behaviour: attempt webhook → on failure, fall back to email;
#                          log both attempt and outcome to audit_log
#
#   2. SlaExpiryJob
#      - Triggered when: an approval checkpoint reaches its expiry timestamp
#                        without a decision (scheduled by the escalation_agent
#                        at checkpoint creation time)
#      - Payload: checkpoint_id, session_id, expiry_policy
#      - Worker behaviour: set checkpoint status=expired, publish a Redis
#                          resume signal so the Orchestrator applies the
#                          configured auto-escalation outcome
#
#   3. SessionCleanupJob (optional / future)
#      - Triggered when: a conversation ends or times out
#      - Payload: session_id
#      - Worker behaviour: flush the session hot cache from Redis, trigger
#                          end-of-conversation long-term memory write
#
# Queue backend:
#   Redis-backed (via the cache client in backend/cache.py). Worker process
#   is a separate container/process so queue congestion never starves the
#   API or Agent Runtime tier.
