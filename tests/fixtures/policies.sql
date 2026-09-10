create table public.employees (id uuid primary key, home_branch_id uuid);

create or replace function app.is_admin() returns boolean
  language sql stable as $$ select true $$;

create policy employees_select on public.employees
  for select to authenticated
  using (app.is_admin());

create policy employees_update on public.employees
  for update to authenticated
  using (app.is_admin()) with check (app.is_admin());
