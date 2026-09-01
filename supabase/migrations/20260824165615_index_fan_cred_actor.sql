create index fan_cred_events_actor_idx
  on public.fan_cred_events (actor_id)
  where actor_id is not null;
