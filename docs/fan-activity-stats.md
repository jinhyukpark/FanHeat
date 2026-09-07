# FANHEAT activity statistics

## Implementation

Migration: `20260907052226_complete_fan_activity_stats.sql`.
Applied to hosted project `yuiemljibxeoifupvluc` on 2026-09-07 with explicit
user approval. The authenticated RPC returned zero initial statistics for
JH Park; anonymous execution and direct member ledger writes are denied.
Frontend hosting deployment is separate from this database migration.

Security Advisor: no new WARN-level finding for this migration. The private
ledger has an intentional deny-all RLS configuration (no client policies),
reported as INFO. Existing warnings remain for the public friends definer RPC
and disabled leaked-password protection; these were not changed here.

- HEAT weights: published post 18; accepted friendship 12 per member;
  comment/reply 6; profile gallery image 4; bookmark 3; post vote 2;
  daily artist vote 2 per day (changing artist is not another event).
- A private ledger receives changes from database triggers. Clients have no
  write access. Editing profile metadata does not change any score.
- Cancellation/deletion deactivates the corresponding contribution. Recreating
  the same bookmark/vote/gallery object/friend pair reuses its first timestamp.
  A newly created post/comment is a distinct activity.
- Replay active activities chronologically: round the previous HEAT after
  linear decay over 30 days, add the weight, cap at 100. MAX counts transitions
  from below 100 to 100. Cancelling an activity recalculates MAX too.
- After the last valid activity, HEAT decays over 30 days. TTL is the remaining
  days rounded up; no activity or zero displayed HEAT means TTL 0.
- Existing FAN CREDIT triggers remain: a recommendation from another member
  earns the post author 3 FC; a comment like earns its author 1 FC. Cancelling
  the recommendation removes its FC. Self-recommendations earn no FC.
  Existing moderation adjustment events remain part of the balance.
- Level = floor(sqrt(max(FC,0)/100)) + 1. Level thresholds are 0, 100, 400,
  900, …; progress is floored within the current interval, avoiding premature
  100% at the previous level.
- Rank uses positive FC balances (including AI profiles). Equal balances share
  competition rank (1, 1, 3). The denominator is members with positive FC,
  not all registered accounts. Zero-FC profiles are unranked.
- The RPC exposes only aggregate statistics of an existing profile to signed-in
  users. It does not disclose activity identities, actors, or private content.
- The profile refreshes on entry, focus, gallery changes and every 30 seconds
  while visible. Loading/failure is explicit and is not mistaken for zero.

## Verification

`node --test web/scripts/fan-stats.test.mjs` tests decay, MAX, initial state,
level thresholds and rank presentation.

The SQL fixture is **only for a disposable local PostgreSQL database**:
1. `supabase/tests/fan_stats_fixture.sql`
2. `supabase/migrations/20260824165310_create_fan_cred_system.sql`
3. `supabase/migrations/20260907052226_complete_fan_activity_stats.sql`
4. `supabase/tests/fan_stats_assertions.sql`

The assertions exercise real triggers, publication, duplicate edits,
recommendation withdrawal, self-recommendations, daily vote changes, friendship
acceptance/removal, comment deletion, FC ties, expiration and database grants.
Test data is rolled back. This minimal fixture verifies this migration in
isolation, not all existing production RLS policies.

Before hosted rollout, verify current table/RLS compatibility and aggregate RPC
responses with ordinary and administrator accounts, then run Security Advisor.
No application/DB deployment is included in the local verification.
