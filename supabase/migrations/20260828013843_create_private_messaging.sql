create table if not exists public.message_blocks (
  blocker_id uuid not null references public.profiles(id) on delete cascade,
  blocked_user_id uuid not null references public.profiles(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (blocker_id, blocked_user_id),
  constraint message_blocks_not_self check (blocker_id <> blocked_user_id)
);

create table if not exists public.private_messages (
  id uuid primary key default gen_random_uuid(),
  sender_id uuid not null references public.profiles(id) on delete cascade,
  recipient_id uuid not null references public.profiles(id) on delete cascade,
  reply_to_id uuid references public.private_messages(id) on delete set null,
  body text not null,
  read_at timestamptz,
  created_at timestamptz not null default now(),
  constraint private_messages_not_self check (sender_id <> recipient_id),
  constraint private_messages_body_length check (char_length(btrim(body)) between 1 and 2000)
);

create index if not exists private_messages_recipient_created_idx
  on public.private_messages(recipient_id, created_at desc);
create index if not exists private_messages_sender_created_idx
  on public.private_messages(sender_id, created_at desc);
create index if not exists private_messages_unread_idx
  on public.private_messages(recipient_id, created_at desc) where read_at is null;
create index if not exists message_blocks_blocked_idx
  on public.message_blocks(blocked_user_id, blocker_id);

alter table public.message_blocks enable row level security;
alter table public.private_messages enable row level security;

revoke all on public.message_blocks from anon, authenticated;
revoke all on public.private_messages from anon, authenticated;
grant select, insert, delete on public.message_blocks to authenticated;
grant select, insert on public.private_messages to authenticated;
grant update (read_at) on public.private_messages to authenticated;

drop policy if exists message_blocks_involved_select on public.message_blocks;
drop policy if exists message_blocks_owner_insert on public.message_blocks;
drop policy if exists message_blocks_owner_delete on public.message_blocks;
create policy message_blocks_involved_select on public.message_blocks
  for select to authenticated
  using ((select auth.uid()) = blocker_id or (select auth.uid()) = blocked_user_id);
create policy message_blocks_owner_insert on public.message_blocks
  for insert to authenticated
  with check ((select auth.uid()) = blocker_id);
create policy message_blocks_owner_delete on public.message_blocks
  for delete to authenticated
  using ((select auth.uid()) = blocker_id);

drop policy if exists private_messages_participant_select on public.private_messages;
drop policy if exists private_messages_sender_insert on public.private_messages;
drop policy if exists private_messages_recipient_read on public.private_messages;
create policy private_messages_participant_select on public.private_messages
  for select to authenticated
  using ((select auth.uid()) = sender_id or (select auth.uid()) = recipient_id);
create policy private_messages_sender_insert on public.private_messages
  for insert to authenticated
  with check (
    (select auth.uid()) = sender_id
    and sender_id <> recipient_id
    and not exists (
      select 1
      from public.message_blocks block
      where
        (block.blocker_id = sender_id and block.blocked_user_id = recipient_id)
        or (block.blocker_id = recipient_id and block.blocked_user_id = sender_id)
    )
  );
create policy private_messages_recipient_read on public.private_messages
  for update to authenticated
  using ((select auth.uid()) = recipient_id)
  with check ((select auth.uid()) = recipient_id);

comment on table public.private_messages is
  'Private FANHEAT member messages; visible only to sender and recipient.';
comment on table public.message_blocks is
  'Member-level direct-message blocks; a block prevents new messages in either direction.';
