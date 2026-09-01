-- Public read policies call is_admin() to include hidden rows for an
-- authenticated administrator. Anonymous requests must be able to evaluate
-- the predicate as false instead of failing the whole Data API query.
grant execute on function public.is_admin() to anon;
