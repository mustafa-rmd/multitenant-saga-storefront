-- scripts/init-db.sql
--
-- Runs once on first Postgres startup (mounted into docker-entrypoint-initdb.d).
-- Creates the two roles that drive our RLS strategy:
--
--   app_user    -- normal app code; RLS policies apply
--   app_admin   -- Celery, Django admin, migrations; BYPASSRLS
--
-- Note: Django migrations themselves must run as a superuser (`postgres`)
-- because they need DDL privileges that GRANT ALL doesn't cover (e.g.
-- creating sequences, altering tables to enable RLS). The compose `web`
-- service uses `app_user` for normal traffic and we run migrations
-- as `postgres` via `make migrate`.

CREATE ROLE app_user LOGIN PASSWORD 'app_user_pass';
CREATE ROLE app_admin LOGIN PASSWORD 'app_admin_pass' BYPASSRLS;

GRANT CONNECT ON DATABASE acme_cart TO app_user, app_admin;
GRANT USAGE ON SCHEMA public TO app_user, app_admin;

-- app_admin needs CREATE on schema public so the platform-admin tenant
-- create endpoint can `CREATE SEQUENCE order_number_seq_<uuid>` on demand.
-- app_user remains restricted to USAGE.
GRANT CREATE ON SCHEMA public TO app_admin;

GRANT ALL ON ALL TABLES IN SCHEMA public TO app_user, app_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO app_user, app_admin;

-- Future tables created by migrations should also be accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON TABLES TO app_user, app_admin;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON SEQUENCES TO app_user, app_admin;
