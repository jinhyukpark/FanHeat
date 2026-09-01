-- Public content remains readable, but member profile records require a session.
drop policy if exists profiles_public_read on public.profiles;

create policy profiles_authenticated_read
on public.profiles
for select
to authenticated
using (true);
