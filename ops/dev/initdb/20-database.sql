-- The local database, owned by the app role as in production (RUNBOOK: placedon_app owns the
-- database and its public schema, and runs the migrations). pgcrypto is a trusted extension
-- on PG 13+, so the owner can create it from 001_core.sql without a superuser.
CREATE DATABASE placedon OWNER placedon_app;
\connect placedon
ALTER SCHEMA public OWNER TO placedon_app;
