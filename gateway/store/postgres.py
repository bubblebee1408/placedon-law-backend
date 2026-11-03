"""`PostgresBackend`: the store a deployment runs on, with FORCE row-level security."""
from __future__ import annotations

from contextlib import contextmanager

from gateway.store.core import (CACHE_KEYS, CACHE_STATS, DecisionExists,
    DuplicateVaultDocument, GRID_CELL_KEYS, MESSAGE_KEYS, POSTGRES, PROPOSITION_KEYS,
    REASSIGNABLE, RetryConflict, STEP_KEYS, StoreError, TurnConflict, UNOWNED_ONLY,
    _DECISION_COLS, _DOC_CHECK_COLS, _UUID, _access_event, _check_cascade,
    _check_draft_version, _check_grant, _check_grid_page, _check_message, _critic_enabled_now,
    _decision_row, _doc_check_row, _grid_summary, _insert_draft_version, _json,
    _lock_live_vault_document, _matter_scope, _shaped, failure_tag)


# ── postgres ─────────────────────────────────────────────────────────────────

class PostgresBackend:
    """The same interface over psycopg. Every connection sets app.tenant_id first."""

    kind = POSTGRES

    def __init__(self, url: str, *, tenant_id: str, actor_id: str | None = None, pool=None) -> None:
        if not _UUID.match(tenant_id or ""):
            raise StoreError(
                f"tenant_id must be a UUID, got {tenant_id!r}. The row-level security "
                f"policies compare against app.tenant_id, so a backend without one would "
                f"read nothing and write rows nobody can see.")
        if actor_id and not _UUID.match(actor_id):
            raise StoreError("actor_id must be a UUID: app.actor_id is cast to uuid by 028")
        self._url = url
        self.tenant_id = tenant_id
        self.actor_id = actor_id or tenant_id
        # 028. What app.actor_id is set to: the authenticated actor, or '' for none, which
        # sees no matter-bound or unfiled row. Never the tenant_id fallback above.
        self._session_actor = actor_id or ""
        # A1. Optional: None means open-per-operation, which is the previous behaviour.
        self._pool = pool

    @contextmanager
    def _conn(self):
        """A connection with this backend's tenant set, from the pool when one is supplied.

        A1. A context manager rather than a bare connection, so all forty-seven
        `with self._conn() as c:` call sites pool without one of them changing. The semantics
        are the same because every connection here is autocommit: psycopg's own `with` would
        close the connection on exit, and this returns it to the pool instead.

        Without a pool it opens and closes one per operation, exactly as before -- so a
        deployment that has not wired a pool is not silently changed.
        """
        if self._pool is not None:
            with self._pool.connection(tenant_id=self.tenant_id,
                                       actor_id=self._session_actor) as conn:
                yield conn
            return
        import psycopg
        from gateway.pool import set_identity
        conn = psycopg.connect(self._url, autocommit=True)
        try:
            # Before anything else. A statement issued ahead of this one is a statement the
            # policy evaluates with no tenant set, which returns nothing and looks like data
            # loss.
            set_identity(conn, self.tenant_id, self._session_actor)
            yield conn
        finally:
            conn.close()

    def write_run(self, run: dict) -> None:
        rid = run["id"]
        with self._conn() as c:
            c.execute(
                "INSERT INTO runs (run_id, tenant_id, actor_id, intent, status, "
                "refusal_code, law_versions, critic_enabled, nonconformity, "
                "nonconformity_note, matter_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (run_id) DO UPDATE SET status = EXCLUDED.status, "
                "refusal_code = EXCLUDED.refusal_code, "
                "law_versions = EXCLUDED.law_versions, "
                "critic_enabled = EXCLUDED.critic_enabled, "
                "nonconformity = EXCLUDED.nonconformity, "
                "nonconformity_note = EXCLUDED.nonconformity_note",
                (rid, self.tenant_id, self.actor_id, run.get("intent", ""),
                 run.get("status", "PLANNED"), run.get("refusal_code"),
                 _json(run.get("law_versions")), _critic_enabled_now(),
                 run.get("nonconformity"), run.get("nonconformity_note"),
                 run.get("matter_id") or None))
            c.execute("DELETE FROM run_steps WHERE run_id = %s", (rid,))
            # Shaped on the way IN, the same as MemoryBackend: one normalisation for
            # both backends, or the two disagree about what a null cost means. The shared
            # conformance suite caught this on Postgres while memory passed.
            for i, s in enumerate(_shaped(st, STEP_KEYS)
                                  for st in run.get("steps", [])):
                c.execute(
                    "INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, "
                    "engine_capability, status, model, degraded, provider, region, "
                    "cost_inr, cost_note, idempotency_key) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (rid, i, self.tenant_id, s.get("capability", ""),
                     s.get("engine_capability"), s.get("status", "PLANNED"),
                     s.get("model"), bool(s.get("degraded", False)),
                     s.get("provider"), s.get("region"), s.get("cost_inr"),
                     s.get("cost_note"), s.get("idempotency_key")))
            c.execute("DELETE FROM propositions WHERE run_id = %s", (rid,))
            for i, p in enumerate(_shaped(pr, PROPOSITION_KEYS)
                                  for pr in run.get("propositions", [])):
                import uuid as _uuid
                c.execute(
                    "INSERT INTO propositions (proposition_id, run_id, tenant_id, ordinal, "
                    "status, source_ref, span_start, span_end) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (p.get("proposition_id") or str(_uuid.uuid4()), rid, self.tenant_id, i,
                     p.get("status", "UNVERIFIED"), p.get("source_ref"),
                     p.get("span_start"), p.get("span_end")))

    def read_run(self, run_id: str) -> dict | None:
        # A malformed id is not a run. Postgres raises InvalidTextRepresentation on a
        # non-UUID for a uuid column, so without this a lookup of "no-such-run" is an
        # exception on Postgres and None in memory -- the two backends disagreeing about
        # what "unknown" means, which is exactly what the shared contract is for.
        if not _UUID.match(run_id or ""):
            return None
        with self._conn() as c:
            r = c.execute("SELECT run_id, intent, status, refusal_code, result, "
                          "law_versions, failure_category, failure_reason, "
                          "critic_enabled, nonconformity, nonconformity_note, "
                          "actor_id, matter_id "
                          "FROM runs WHERE run_id = %s", (run_id,)).fetchone()
            if r is None:
                return None
            out = {"id": str(r[0]), "intent": r[1], "status": r[2], "refusal_code": r[3],
                   "result": r[4], "law_versions": r[5],
                   # O8. Written by set_run and read back here; without these two the
                   # category existed on Postgres and was invisible to every reader, which
                   # the conformance list caught on its first live run.
                   "failure_category": r[6], "failure_reason": r[7],
                   "critic_enabled": r[8],
                   "nonconformity": float(r[9]) if r[9] is not None else None,
                   "nonconformity_note": r[10],
                   "actor_id": str(r[11]) if r[11] else None,
                   "matter_id": str(r[12]) if r[12] else None}
            out["steps"] = [
                {"capability": s[0], "engine_capability": s[1], "status": s[2],
                 "model": s[3], "degraded": s[4], "provider": s[5], "region": s[6],
                 "cost_inr": float(s[7]) if s[7] is not None else None,
                 "cost_note": s[8], "idempotency_key": s[9]}
                for s in c.execute(
                    "SELECT capability, engine_capability, status, model, degraded, "
                    "provider, region, cost_inr, cost_note, idempotency_key "
                    "FROM run_steps WHERE run_id = %s ORDER BY ordinal", (run_id,)).fetchall()]
            out["propositions"] = [
                {"status": p[0], "source_ref": p[1], "span_start": p[2], "span_end": p[3]}
                for p in c.execute(
                    "SELECT status, source_ref, span_start, span_end FROM propositions "
                    "WHERE run_id = %s ORDER BY ordinal", (run_id,)).fetchall()]
            return out

    def put_document(self, *, sha256: str, name: str, byte_count: int) -> dict:
        with self._conn() as c:
            c.execute(
                "INSERT INTO documents (sha256, tenant_id, name, byte_count) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (tenant_id, sha256) DO NOTHING",
                (sha256, self.tenant_id, name, byte_count))
        return {"sha256": sha256, "name": name, "byte_count": byte_count,
                "tenant_id": self.tenant_id}

    def get_document(self, sha256: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT sha256, name, byte_count, tenant_id FROM documents "
                          "WHERE sha256 = %s", (sha256,)).fetchone()
        return None if r is None else {"sha256": r[0], "name": r[1],
                                        "byte_count": r[2], "tenant_id": str(r[3])}

    def write_decision(self, decision: dict) -> dict:
        import psycopg
        with self._conn() as c:
            try:
                r = c.execute(
                    "INSERT INTO decisions (decision_id, run_id, tenant_id, item_ref, "
                    "decision, reason, quoted_span, quote_viewed, law_versions, actor_id, "
                    "decided_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    "COALESCE(%s::timestamptz, now())) "
                    "RETURNING " + _DECISION_COLS,
                    (decision["decision_id"], decision["run_id"], self.tenant_id,
                     decision["item_ref"], decision["decision"], decision["reason"],
                     decision["quoted_span"], bool(decision.get("quote_viewed")),
                     _json(decision.get("law_versions")), decision["actor_id"],
                     decision.get("decided_at"))).fetchone()
            except psycopg.errors.UniqueViolation:
                raise DecisionExists(
                    f"{decision['item_ref']} on run {decision['run_id']} already has a "
                    f"decision. A reviewer changing their mind writes a new one against a "
                    f"new run; overwriting would destroy the label, which is the point of "
                    f"storing it.") from None
        return _decision_row(r)

    def read_decisions(self, run_id: str) -> list[dict]:
        if not _UUID.match(run_id or ""):
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT " + _DECISION_COLS + " FROM decisions WHERE run_id = %s "
                "ORDER BY decided_at, item_ref", (run_id,)).fetchall()
        return [_decision_row(r) for r in rows]

    def append_step(self, run_id: str, step: dict, *, key: str) -> bool:
        """Append unless the key is already there. The unique index decides, not a SELECT:
        a check-then-insert is two statements a second worker can interleave with."""
        st = _shaped(step, STEP_KEYS)
        with self._conn() as c:
            n = c.execute(
                "INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, "
                "engine_capability, status, model, degraded, provider, region, cost_inr, "
                "cost_note, idempotency_key) SELECT %s, "
                "(SELECT coalesce(max(ordinal) + 1, 0) FROM run_steps WHERE run_id = %s), "
                "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s "
                "ON CONFLICT (run_id, idempotency_key) WHERE idempotency_key IS NOT NULL "
                "DO NOTHING",
                (run_id, run_id, self.tenant_id, st.get("capability", ""),
                 st.get("engine_capability"), st.get("status", "PLANNED"),
                 st.get("model"), bool(st.get("degraded", False)), st.get("provider"),
                 st.get("region"), st.get("cost_inr"), st.get("cost_note"), key)).rowcount
        return bool(n)

    def set_run(self, run_id: str, *, status: str, refusal_code=None, result=None) -> None:
        import json as _json
        with self._conn() as c:
            cat, why = failure_tag(status, refusal_code, result)
            c.execute(
                "UPDATE runs SET status = %s, refusal_code = %s, "
                "result = COALESCE(%s::jsonb, result), "
                "failure_category = %s, failure_reason = %s, "
                "finished_at = CASE WHEN %s THEN now() ELSE finished_at END "
                "WHERE run_id = %s",
                (status, refusal_code,
                 None if result is None else _json.dumps(result), cat, why,
                 status in ("ANSWERED", "PARTIAL", "REFUSED", "FAILED"), run_id))

    # 031. Only while RUNNING: a late write must not decorate a finished run. Both go
    # through the session's own RLS, like every other runs read and write here.
    def set_run_progress(self, run_id: str, progress: dict) -> None:
        import json as _json
        with self._conn() as c:
            c.execute("UPDATE runs SET progress = %s::jsonb "
                      "WHERE run_id = %s AND status = 'RUNNING'",
                      (_json.dumps(progress), run_id))

    def read_run_progress(self, run_id: str) -> dict | None:
        import psycopg
        if not _UUID.match(run_id or ""):
            return None
        try:
            with self._conn() as c:
                r = c.execute("SELECT progress FROM runs WHERE run_id = %s",
                              (run_id,)).fetchone()
        except psycopg.errors.UndefinedColumn:
            return None   # 031 not applied yet: no progress, the turn still shows waiting
        return r[0] if r and r[0] else None

    # ── 8a: users, roles and invites ─────────────────────────────────────────
    def write_actor(self, actor: dict) -> dict:
        import psycopg
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO actors (actor_id, tenant_id, label, role, email, "
                    "password_hash, disabled_at) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (actor_id) DO UPDATE SET label = EXCLUDED.label, "
                    "role = EXCLUDED.role, email = EXCLUDED.email, "
                    "password_hash = EXCLUDED.password_hash, "
                    "disabled_at = EXCLUDED.disabled_at",
                    (actor["actor_id"], self.tenant_id, actor.get("label") or "",
                     actor.get("role") or "viewer",
                     (str(actor.get("email") or "").strip() or None),
                     actor.get("password_hash"), actor.get("disabled_at")))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this actor: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return self.read_actor(actor["actor_id"]) or {}

    def read_actor(self, actor_id: str) -> dict | None:
        if not _UUID.match(actor_id or ""):
            return None
        with self._conn() as c:
            r = c.execute("SELECT actor_id, label, role, email, password_hash, "
                          "disabled_at FROM actors WHERE actor_id = %s",
                          (actor_id,)).fetchone()
        return None if r is None else {
            "actor_id": str(r[0]), "label": r[1], "role": r[2], "email": r[3],
            "password_hash": r[4], "disabled_at": r[5].isoformat() if r[5] else None}

    def create_invite(self, invite: dict) -> dict:
        import psycopg
        try:
            with self._conn() as c, c.transaction():
                # An EXPIRED unused invite still holds this email's slot in
                # invites_live_per_email_idx (a partial index cannot say "not expired"),
                # so re-inviting after the 7 days would be refused forever. Retire it.
                c.execute("UPDATE invites SET cancelled_at = now(), cancelled_by = %s "
                          "WHERE lower(email) = lower(%s) AND accepted_at IS NULL "
                          "AND cancelled_at IS NULL AND expires_at <= now()",
                          (invite["invited_by"], invite["email"]))
                r = c.execute(
                    "INSERT INTO invites (invite_id, tenant_id, email, role, token_hash, "
                    "invited_by, expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING invite_id, email, role, token_hash, invited_by, "
                    "expires_at, accepted_at, accepted_by",
                    (invite["invite_id"], self.tenant_id, invite["email"],
                     invite["role"], invite["token_hash"], invite["invited_by"],
                     invite["expires_at"])).fetchone()
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this invite: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return {"invite_id": str(r[0]), "email": r[1], "role": r[2], "token_hash": r[3],
                "invited_by": str(r[4]), "expires_at": r[5].isoformat(),
                "accepted_at": None, "accepted_by": None}

    def accept_invite(self, token_hash: str, *, actor_id: str, now: str,
                      actor: dict | None = None) -> dict | None:
        """One UPDATE, so two simultaneous accepts cannot both win.

        The `accepted_at IS NULL` in the WHERE clause is the single-use guarantee: the
        second statement matches no row. Checking first and updating after would be a race
        with a window exactly as wide as the round trip.

        `actor` is the account the invite creates, inserted in the SAME transaction and
        before the UPDATE, because invites.accepted_by is a foreign key to actors: stamping
        the invite first failed on every real database. A lost race rolls both back.
        """
        import psycopg

        class _Spent(Exception):
            pass
        try:
            with self._conn() as c, c.transaction():
                # Lock the invite while it is still usable, BEFORE creating anything: an
                # unknown, used or expired token creates no account and gets the same None
                # the memory backend gives. The row lock keeps two accepts from both passing.
                if c.execute("SELECT 1 FROM invites WHERE token_hash = %s AND accepted_at IS NULL "
                             "AND cancelled_at IS NULL AND expires_at > now() FOR UPDATE",
                             (str(token_hash or ""),)).fetchone() is None:
                    raise _Spent()
                if actor is not None:
                    c.execute(
                        "INSERT INTO actors (actor_id, tenant_id, label, role, email, "
                        "password_hash) VALUES (%s,%s,%s,%s,%s,%s)",
                        (actor_id, self.tenant_id, actor.get("label") or "",
                         actor.get("role") or "viewer",
                         (str(actor.get("email") or "").strip() or None),
                         actor.get("password_hash")))
                r = c.execute(
                    "UPDATE invites SET accepted_at = now(), accepted_by = %s "
                    "WHERE token_hash = %s AND accepted_at IS NULL AND cancelled_at IS NULL "
                    "AND expires_at > now() "
                    "RETURNING invite_id, email, role, token_hash, invited_by, expires_at, "
                    "accepted_at, accepted_by",
                    (actor_id, str(token_hash or ""))).fetchone()
                if r is None:
                    raise _Spent()        # roll the account back with the refused accept
        except _Spent:
            return None
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this account: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return None if r is None else {
            "invite_id": str(r[0]), "email": r[1], "role": r[2], "token_hash": r[3],
            "invited_by": str(r[4]), "expires_at": r[5].isoformat(),
            "accepted_at": r[6].isoformat(), "accepted_by": str(r[7])}

    def create_session(self, session: dict) -> dict:
        import psycopg
        try:
            with self._conn() as c:
                r = c.execute(
                    "INSERT INTO sessions (session_id, tenant_id, actor_id, token_hash, "
                    "expires_at) VALUES (%s,%s,%s,%s,%s) "
                    "RETURNING session_id, actor_id, token_hash, expires_at, revoked_at",
                    (session["session_id"], self.tenant_id, session["actor_id"],
                     session["token_hash"], session["expires_at"])).fetchone()
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this session: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return {"session_id": str(r[0]), "actor_id": str(r[1]), "token_hash": r[2],
                "expires_at": r[3].isoformat(), "revoked_at": None}

    def revoke_session(self, token_hash: str) -> bool:
        """Scoped to THIS tenant by the connection's app.tenant_id, like every write here."""
        with self._conn() as c:
            r = c.execute(
                "UPDATE sessions SET revoked_at = now() "
                "WHERE token_hash = %s AND revoked_at IS NULL RETURNING session_id",
                (str(token_hash or ""),)).fetchone()
        return r is not None

    def find_actor_by_email(self, email: str) -> dict | None:
        want = str(email or "").strip()
        if not want:
            return None
        with self._conn() as c:
            r = c.execute("SELECT actor_id FROM actors WHERE lower(email) = lower(%s)",
                          (want,)).fetchone()
        return None if r is None else self.read_actor(str(r[0]))

    def read_invite(self, token_hash: str) -> dict | None:
        with self._conn() as c:
            r = c.execute(
                "SELECT invite_id, email, role, token_hash, invited_by, expires_at, "
                "accepted_at, accepted_by FROM invites WHERE token_hash = %s",
                (str(token_hash or ""),)).fetchone()
        return None if r is None else {
            "invite_id": str(r[0]), "email": r[1], "role": r[2], "token_hash": r[3],
            "invited_by": str(r[4]), "expires_at": r[5].isoformat(),
            "accepted_at": r[6].isoformat() if r[6] else None,
            "accepted_by": str(r[7]) if r[7] else None}

    def list_actors(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT actor_id, label, role, email, disabled_at, created_at "
                             "FROM actors WHERE email IS NOT NULL "
                             "ORDER BY lower(email)").fetchall()
        return [{"actor_id": str(r[0]), "label": r[1], "role": r[2], "email": r[3],
                 "disabled_at": r[4].isoformat() if r[4] else None,
                 "created_at": r[5].isoformat()} for r in rows]

    def list_pending_invites(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT invite_id, email, role, invited_by, created_at, expires_at "
                "FROM invites WHERE accepted_at IS NULL AND cancelled_at IS NULL "
                "AND expires_at > now() ORDER BY created_at DESC").fetchall()
        return [{"invite_id": str(r[0]), "email": r[1], "role": r[2],
                 "invited_by": str(r[3]), "created_at": r[4].isoformat(),
                 "expires_at": r[5].isoformat()} for r in rows]

    def cancel_invite(self, invite_id: str, *, cancelled_by: str) -> bool:
        """Scoped to THIS tenant by RLS: another firm's invite id matches no row."""
        if not _UUID.match(str(invite_id or "")):
            return False
        with self._conn() as c:
            r = c.execute(
                "UPDATE invites SET cancelled_at = now(), cancelled_by = %s "
                "WHERE invite_id = %s AND accepted_at IS NULL AND cancelled_at IS NULL "
                "RETURNING invite_id", (cancelled_by, invite_id)).fetchone()
        return r is not None

    def read_labels(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT COALESCE(r.intent, ''), "
                "       COALESCE(r.result #>> '{bodies,0,body}', ''), d.decision "
                "FROM decisions d LEFT JOIN runs r ON r.run_id = d.run_id").fetchall()
        return [{"task": r[0], "body": r[1], "decision": r[2]} for r in rows]

    def read_failure_counts(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT to_char(date_trunc('week', COALESCE(finished_at, created_at)), "
                "       'IYYY-\"W\"IW') AS week, failure_category, count(*) "
                "FROM runs WHERE status <> 'ANSWERED' "
                "GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
        return [{"week": r[0], "category": r[1], "count": int(r[2])} for r in rows]

    def write_cascade(self, record: dict, *, run_id: str | None = None) -> dict:
        import json as _json
        import uuid as _uuid
        row = {
            "cascade_id": record.get("cascade_id") or str(_uuid.uuid4()),
            "run_id": run_id,
            "status": record.get("status", ""),
            "error": record.get("error"),
            "attempts": [dict(a) for a in record.get("attempts", [])],
            "body_ids": list(record.get("body_ids", [])),
            "claim_count": len(record.get("claims", [])),
            "refusal_count": len(record.get("refusals", [])),
            "total_cost_inr": record.get("total_cost_inr"),
        }
        _check_cascade(row)
        with self._conn() as c:
            c.execute(
                "INSERT INTO cascade_runs (cascade_id, run_id, tenant_id, status, error, "
                "attempts, body_ids, claim_count, refusal_count, total_cost_inr) "
                "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)",
                (row["cascade_id"], row["run_id"], self.tenant_id, row["status"],
                 row["error"], _json.dumps(row["attempts"]), row["body_ids"],
                 row["claim_count"], row["refusal_count"], row["total_cost_inr"]))
        return dict(row)

    def read_cascades(self, *, run_id: str | None = None, limit: int = 1000) -> list[dict]:
        if run_id is not None and not _UUID.match(run_id or ""):
            return []
        where = "WHERE run_id = %s " if run_id is not None else ""
        args = (run_id, limit) if run_id is not None else (limit,)
        with self._conn() as c:
            rows = c.execute(
                "SELECT cascade_id, run_id, status, error, attempts, body_ids, "
                "claim_count, refusal_count, total_cost_inr FROM cascade_runs "
                + where + "ORDER BY created_at LIMIT %s", args).fetchall()
        return [{"cascade_id": str(r[0]),
                 "run_id": str(r[1]) if r[1] is not None else None,
                 "status": r[2], "error": r[3], "attempts": r[4] or [],
                 "body_ids": list(r[5] or []), "claim_count": r[6],
                 "refusal_count": r[7],
                 "total_cost_inr": float(r[8]) if r[8] is not None else None}
                for r in rows]

    # ── C2: the chat layer (010_conversations.sql) ───────────────────────────
    def write_conversation(self, conversation: dict) -> dict:
        import psycopg
        cid = conversation["conversation_id"]
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO conversations (conversation_id, tenant_id, title, "
                    "matter_id, actor_id) VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (conversation_id) DO UPDATE SET "
                    "title = EXCLUDED.title, matter_id = EXCLUDED.matter_id, "
                    "updated_at = now()",
                    (cid, self.tenant_id, conversation.get("title") or "",
                     (str(conversation.get("matter_id") or "").strip() or None),
                     self._session_actor or None))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this conversation: "
                             f"{type(exc).__name__}") from None
        return self.read_conversation(cid) or {"conversation_id": cid}

    def read_conversation(self, conversation_id: str) -> dict | None:
        if not _UUID.match(conversation_id or ""):
            return None
        with self._conn() as c:
            r = c.execute("SELECT conversation_id, title, created_at, updated_at, "
                          "matter_id, actor_id FROM "
                          "conversations WHERE conversation_id = %s",
                          (conversation_id,)).fetchone()
        if r is None:
            return None
        return {"matter_id": str(r[4]) if r[4] else None,
                "actor_id": str(r[5]) if r[5] else None,
                "conversation_id": str(r[0]), "title": r[1],
                "created_at": r[2].isoformat() if r[2] else None,
                "updated_at": r[3].isoformat() if r[3] else None}

    def list_conversations(self, *, matter_id: str, limit: int = 50) -> list[dict]:
        want = _matter_scope(matter_id)
        with self._conn() as c:
            rows = c.execute("SELECT conversation_id, title, created_at, updated_at FROM "
                             "conversations WHERE matter_id = %s "
                             "ORDER BY updated_at DESC LIMIT %s",
                             (want, limit)).fetchall()
        return [{"conversation_id": str(r[0]), "title": r[1],
                 "created_at": r[2].isoformat() if r[2] else None,
                 "updated_at": r[3].isoformat() if r[3] else None} for r in rows]

    def write_matter(self, matter: dict, *, owner: str | None = None) -> dict:
        """Create or update one matter. A NEW matter gets its creator's owner grant in the
        same transaction, so no matter ever exists that nobody can reach (028)."""
        import psycopg
        import uuid as _uuid
        mid = matter["matter_id"]
        values = (str(matter.get("name") or "").strip(), matter.get("client_ref") or "",
                  matter.get("closed_at"))
        try:
            with self._conn() as c, c.transaction():
                updated = c.execute(
                    "UPDATE matters SET name = %s, client_ref = %s, closed_at = %s "
                    "WHERE matter_id = %s", values + (mid,)).rowcount
                if not updated:
                    # No RETURNING: the new row is not readable until the grant exists.
                    c.execute("INSERT INTO matters (matter_id, tenant_id, name, client_ref, "
                              "closed_at) VALUES (%s,%s,%s,%s,%s)",
                              (mid, self.tenant_id) + values)
                    if owner:
                        # 028 grant_bootstrap, transaction-local: the creator's OWN owner
                        # grant on the matter just inserted. The policy admits nothing else
                        # under this scope -- not another actor, not another role.
                        c.execute("SELECT set_config('app.actor_scope', 'grant_bootstrap', true)")
                        c.execute("INSERT INTO matter_memberships (membership_id, tenant_id, "
                                  "matter_id, actor_id, role, granted_by, grant_reason) "
                                  "VALUES (%s,%s,%s,%s,'owner',%s,'created the matter')",
                                  (str(_uuid.uuid4()), self.tenant_id, mid, owner, owner))
                        c.execute("SELECT set_config('app.actor_scope', '', true)")
                r = c.execute("SELECT matter_id, name, client_ref, closed_at FROM matters "
                              "WHERE matter_id = %s", (mid,)).fetchone()
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this matter: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        if r is None:
            # Committed, but this actor holds no grant (no owner was given): report what
            # was written rather than raise about a change that already happened.
            return {"matter_id": mid, "name": values[0], "client_ref": values[1],
                    "closed_at": values[2]}
        return {"matter_id": str(r[0]), "name": r[1], "client_ref": r[2],
                "closed_at": r[3].isoformat() if r[3] else None}

    def list_matters(self) -> list[dict]:
        """The matters this actor's policy shows: its own grants, or all for an admin."""
        with self._conn() as c:
            rows = c.execute("SELECT matter_id, name, client_ref, closed_at FROM matters "
                             "ORDER BY lower(name)").fetchall()
        return [{"matter_id": str(r[0]), "name": r[1], "client_ref": r[2],
                 "closed_at": r[3].isoformat() if r[3] else None} for r in rows]

    # ── 028: matter grants ────────────────────────────────────────────────────
    _MEMBERSHIP_COLS = ("membership_id, matter_id, actor_id, role, granted_by, granted_at, "
                        "grant_reason, revoked_at, revoked_by, revoke_reason")

    @staticmethod
    def _membership_row(r) -> dict:
        return {"membership_id": str(r[0]), "matter_id": str(r[1]), "actor_id": str(r[2]),
                "role": r[3], "granted_by": str(r[4]), "granted_at": r[5].isoformat(),
                "grant_reason": r[6], "revoked_at": r[7].isoformat() if r[7] else None,
                "revoked_by": str(r[8]) if r[8] else None, "revoke_reason": r[9]}

    def matter_role(self, matter_id: str, actor_id: str) -> str | None:
        if not (_UUID.match(matter_id or "") and _UUID.match(actor_id or "")):
            return None
        with self._conn() as c:
            r = c.execute("SELECT mm.role FROM matter_memberships mm JOIN actors a "
                          "ON a.actor_id = mm.actor_id AND a.disabled_at IS NULL "
                          "WHERE mm.matter_id = %s AND mm.actor_id = %s "
                          "AND mm.revoked_at IS NULL", (matter_id, actor_id)).fetchone()
        return r[0] if r else None

    def matter_roles(self, actor_id: str) -> dict:
        if not _UUID.match(actor_id or ""):
            return {}
        with self._conn() as c:
            rows = c.execute("SELECT matter_id, role FROM matter_memberships "
                             "WHERE actor_id = %s AND revoked_at IS NULL",
                             (actor_id,)).fetchall()
        return {str(r[0]): r[1] for r in rows}

    def grant_matter_access(self, *, matter_id: str, actor_id: str, role: str,
                            granted_by: str, reason: str) -> dict:
        """Admin-only by POLICY (028 membership_insert), whatever the caller checked."""
        import psycopg
        import uuid as _uuid
        _check_grant(role, reason)
        try:
            with self._conn() as c, c.transaction():
                prior = c.execute(f"SELECT {self._MEMBERSHIP_COLS} FROM matter_memberships "
                                  "WHERE matter_id = %s AND actor_id = %s AND revoked_at IS "
                                  "NULL FOR UPDATE", (matter_id, actor_id)).fetchone()
                if prior is not None and prior[3] == role:
                    return self._membership_row(prior)
                if prior is not None:
                    c.execute("UPDATE matter_memberships SET revoked_at = now(), "
                              "revoked_by = %s, revoke_reason = %s WHERE membership_id = %s",
                              (granted_by, f"role changed to {role}: {reason}", prior[0]))
                r = c.execute("INSERT INTO matter_memberships (membership_id, tenant_id, "
                              "matter_id, actor_id, role, granted_by, grant_reason) "
                              "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                              f"RETURNING {self._MEMBERSHIP_COLS}",
                              (str(_uuid.uuid4()), self.tenant_id, matter_id, actor_id, role,
                               granted_by, reason)).fetchone()
        except psycopg.errors.InsufficientPrivilege:
            raise StoreError("only an administrator may grant matter access") from None
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this grant: {type(exc).__name__}") from None
        return self._membership_row(r)

    def revoke_matter_access(self, *, matter_id: str, actor_id: str, revoked_by: str,
                             reason: str) -> bool:
        if not str(reason or "").strip():
            raise StoreError("a revocation needs a reason (028 matter_memberships)")
        with self._conn() as c:
            n = c.execute("UPDATE matter_memberships SET revoked_at = now(), revoked_by = %s, "
                          "revoke_reason = %s WHERE matter_id = %s AND actor_id = %s "
                          "AND revoked_at IS NULL",
                          (revoked_by, reason, matter_id, actor_id)).rowcount
        return bool(n)

    def list_matter_memberships(self, matter_id: str, *, include_revoked: bool = False) -> list[dict]:
        if not _UUID.match(matter_id or ""):
            return []
        with self._conn() as c:
            rows = c.execute(f"SELECT {self._MEMBERSHIP_COLS} FROM matter_memberships "
                             "WHERE matter_id = %s AND (%s OR revoked_at IS NULL) "
                             "ORDER BY granted_at", (matter_id, include_revoked)).fetchall()
        return [self._membership_row(r) for r in rows]

    def _record_access_event(self, c, event: dict) -> None:
        import uuid as _uuid
        c.execute("INSERT INTO access_events (event_id, tenant_id, resource_kind, resource_id, "
                  "action, by_actor, from_actor, to_actor, from_matter, to_matter, reason) "
                  "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                  (str(_uuid.uuid4()), self.tenant_id, event["resource_kind"],
                   event["resource_id"], event["action"], event["by_actor"],
                   event["from_actor"], event["to_actor"], event["from_matter"],
                   event["to_matter"], event["reason"]))

    def share_vault_document(self, document_id: str, *, by_actor: str, reason: str,
                             shared: bool = True) -> dict:
        """The uploader's own act, under the ordinary policy: no scope."""
        import psycopg
        row = self.read_vault_document(document_id)
        if row is None or row.get("matter_id") or row.get("uploaded_by") != str(by_actor):
            raise StoreError("only the uploader shares an unfiled document")
        event = _access_event("vault_document", document_id, "share" if shared else "unshare",
                              by_actor, reason, from_actor=row.get("uploaded_by"))
        try:
            with self._conn() as c, c.transaction():
                n = c.execute("UPDATE vault_documents SET shared_with_firm_at = "
                              "CASE WHEN %s THEN now() END, shared_by = CASE WHEN %s THEN "
                              "%s::uuid END WHERE document_id = %s",
                              (shared, shared, by_actor, document_id)).rowcount
                if not n:
                    raise StoreError("this vault document cannot be changed by this actor")
                self._record_access_event(c, event)
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this change: {type(exc).__name__}") from None
        return self.read_vault_document(document_id) or {}

    _PROFILE_COLS = ("fact_id, field, value, basis, source_label, quoted_span, uploaded_on, "
                     "confirmed_by, confirmed_at, reason")

    def _profile_rows(self, c) -> list[dict]:
        cols = [k.strip() for k in self._PROFILE_COLS.split(",")]
        rows = c.execute(f"SELECT {self._PROFILE_COLS} FROM company_profile_facts "
                         f"WHERE superseded_at IS NULL ORDER BY field").fetchall()
        return [{k: (str(v) if k in ("fact_id", "confirmed_by") else v)
                 for k, v in zip(cols, r)} for r in rows]

    def read_company_profile(self) -> list[dict]:
        with self._conn() as c:
            return self._profile_rows(c)

    def set_company_profile(self, rows: list[dict], *, by_actor: str, reason: str) -> list[dict]:
        """One transaction: supersede what changed, insert what is new, keep the rest."""
        import uuid
        import psycopg
        from gateway.company_profile import same_fact
        if not str(reason or "").strip():
            raise StoreError("a company profile change needs a reason (032)")
        try:
            with self._conn() as c, c.transaction():
                # Serialise concurrent saves within this firm; another firm is untouched.
                c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                          (f"company_profile:{self.tenant_id}",))
                current = self._profile_rows(c)
                keep = [r for r in current if any(same_fact(r, n) for n in rows)]
                gone = [r["fact_id"] for r in current if r not in keep]
                if gone:
                    c.execute("UPDATE company_profile_facts SET superseded_at = now(), "
                              "superseded_by = %s WHERE fact_id = ANY(%s::uuid[])",
                              (by_actor, gone))
                for n in rows:
                    if any(same_fact(k, n) for k in keep):
                        continue
                    c.execute("INSERT INTO company_profile_facts (fact_id, tenant_id, field, "
                              "value, basis, source_label, quoted_span, uploaded_on, "
                              "confirmed_by, reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                              (str(uuid.uuid4()), self.tenant_id, n["field"], n["value"],
                               n["basis"], n["source_label"], n.get("quoted_span") or "",
                               n.get("uploaded_on"), by_actor, reason))
                return self._profile_rows(c)
        except psycopg.Error as exc:
            raise StoreError(f"the database refused this change: {type(exc).__name__}") from None

    @contextmanager
    def _reassigning(self):
        """A transaction under 028's `reassign` scope, local to it. Used ONLY by list_unowned
        and reassign_work, both behind admin-only verbs: work with no owner is visible to no
        person's policy. The scope reaches the metadata row of UNFILED work and nothing else
        -- no filed row, no chunk, message, version or cell."""
        with self._conn() as c, c.transaction():
            c.execute("SELECT set_config('app.actor_scope', 'reassign', true)")
            yield c

    def list_unowned(self) -> dict:
        out = {}
        with self._reassigning() as c:
            for kind, (_a, table, idc, owner, name) in REASSIGNABLE.items():
                gone = " AND deleted_at IS NULL" if kind == "vault_document" else ""
                rows = c.execute(f"SELECT {idc}, {name} FROM {table} WHERE matter_id IS NULL "
                                 f"AND {owner} IS NULL{gone} ORDER BY {idc} LIMIT 1000").fetchall()
                out[kind] = [{"id": str(r[0]), "name": r[1] or ""} for r in rows]
        return out

    def reassign_work(self, kind: str, resource_id: str, *, by_actor: str, reason: str,
                      to_actor: str | None = None, to_matter: str | None = None) -> dict:
        import psycopg
        if kind not in REASSIGNABLE:
            raise StoreError(f"{kind!r} is not reassignable")
        if not (to_actor or to_matter):
            raise StoreError("a reassignment names a new owner, a matter, or both")
        _a, table, idc, owner, _name = REASSIGNABLE[kind]
        if not _UUID.match(resource_id or ""):
            raise StoreError("no such item")
        try:
            with self._reassigning() as c:
                r = c.execute(f"SELECT {owner} FROM {table} WHERE {idc} = %s "
                              f"AND matter_id IS NULL AND {owner} IS NULL FOR UPDATE",
                              (resource_id,)).fetchone()
                if r is None:
                    raise StoreError(UNOWNED_ONLY)
                event = _access_event(kind, resource_id, "reassign", by_actor, reason,
                                      from_actor=str(r[0]) if r[0] else None,
                                      to_actor=to_actor, to_matter=to_matter)
                unshare = (", shared_with_firm_at = NULL, shared_by = NULL"
                           if kind == "vault_document" and to_matter else "")
                # The event FIRST: 028's placedon_reassigning admits the changed row only
                # where this transaction has already recorded why it changed.
                self._record_access_event(c, event)
                c.execute(f"UPDATE {table} SET {owner} = coalesce(%s::uuid, {owner}), "
                          f"matter_id = coalesce(%s::uuid, matter_id){unshare} "
                          f"WHERE {idc} = %s", (to_actor, to_matter, resource_id))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this reassignment: {type(exc).__name__}") from None
        return {"kind": kind, "id": resource_id, "owner": to_actor or event["from_actor"],
                "matter_id": to_matter}

    # ── V1: the vault ────────────────────────────────────────────────────────
    def write_vault_document(self, doc: dict, *, run: dict | None = None,
                             queue=None, queued: dict | None = None) -> dict:
        """Insert or update one vault document.

        With `run` and `queue`/`queued`, the document row, its run row and its ingest job
        commit in ONE transaction (the `reserve_turn` pattern). A full queue or a crash
        between the writes leaves nothing, so no PENDING document can exist without a job.
        """
        import psycopg
        job = None
        try:
            with self._conn() as c, c.transaction():
                c.execute(
                    "INSERT INTO vault_documents (document_id, tenant_id, matter_id, "
                    "sha256, name, byte_count, state, doc_class, class_reason, "
                    "text_chars, ocr_state, uploaded_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (document_id) DO UPDATE SET state = EXCLUDED.state, "
                    "doc_class = EXCLUDED.doc_class, "
                    "class_reason = EXCLUDED.class_reason, "
                    "text_chars = EXCLUDED.text_chars, ocr_state = EXCLUDED.ocr_state, "
                    "matter_id = EXCLUDED.matter_id, "
                    # 030: a reason only while FAILED. A late ingest that finishes after
                    # the document was marked FAILED clears it rather than break the CHECK.
                    "failure_reason = CASE WHEN EXCLUDED.state = 'FAILED' "
                    "THEN vault_documents.failure_reason ELSE NULL END, "
                    "ingested_at = CASE WHEN EXCLUDED.state IN ('INGESTED', 'PARTIAL') THEN now() "
                    "ELSE vault_documents.ingested_at END "
                    # A document deleted while its ingest ran stays deleted: the conflict
                    # row is locked and this re-checked on its latest version, so the
                    # ingest's final write cannot flip it back to INGESTED.
                    "WHERE vault_documents.deleted_at IS NULL",
                    (doc["document_id"], self.tenant_id,
                     (str(doc.get("matter_id") or "").strip() or None), doc["sha256"],
                     doc.get("name") or "", int(doc.get("byte_count") or 0),
                     doc.get("state") or "PENDING", doc.get("doc_class"),
                     doc.get("class_reason"), doc.get("text_chars"),
                     doc.get("ocr_state") or "NOT_NEEDED",
                     # 028. The SESSION's actor, never a field the caller supplied.
                     self._session_actor or None))
                if run is not None:
                    c.execute("INSERT INTO runs (run_id, tenant_id, actor_id, intent, status, "
                              "critic_enabled, matter_id) VALUES (%s,%s,%s,%s,'PLANNED',%s,%s)",
                              (run["id"], self.tenant_id, self.actor_id,
                               run["intent"], _critic_enabled_now(), run.get("matter_id")))
                if queue is not None and queued is not None:
                    # Same transaction: no worker sees a job without its document and run.
                    job = queue.enqueue(**queued, connection=c)
        except psycopg.errors.IntegrityError as exc:
            constraint = getattr(getattr(exc, "diag", None), "constraint_name", None)
            if constraint in ("vault_documents_matter_sha", "vault_documents_owner_sha"):
                # The failed INSERT aborted its transaction, so look the holder up on a
                # fresh connection, in the same scope as the unique index that fired.
                matter = (str(doc.get("matter_id") or "").strip() or None)
                existing = None
                try:
                    with self._conn() as c:
                        r = c.execute("SELECT document_id FROM vault_documents "
                                      "WHERE sha256 = %s AND matter_id IS NOT DISTINCT FROM "
                                      "%s::uuid AND (matter_id IS NOT NULL OR uploaded_by = "
                                      "%s::uuid)", (doc["sha256"], matter,
                                                    self._session_actor or None)).fetchone()
                    existing = str(r[0]) if r else None
                except Exception:                                # noqa: BLE001
                    existing = None
                raise DuplicateVaultDocument(
                    "these bytes are already in this tenant's vault",
                    document_id=existing) from None
            raise StoreError("the database refused this vault document") from None
        out = self.read_vault_document(doc["document_id"]) or {}
        return {**out, "job_id": job.job_id} if job is not None else out

    def read_vault_document(self, document_id: str) -> dict | None:
        if not _UUID.match(document_id or ""):
            return None
        with self._conn() as c:
            r = c.execute(
                "SELECT document_id, matter_id, sha256, name, byte_count, state, "
                "doc_class, class_reason, text_chars, ocr_state, deleted_at, uploaded_by, "
                "shared_with_firm_at, shared_by, failure_reason "
                "FROM vault_documents WHERE document_id = %s", (document_id,)).fetchone()
        return None if r is None else {
            "document_id": str(r[0]), "matter_id": str(r[1]) if r[1] else None,
            "sha256": r[2], "name": r[3], "byte_count": int(r[4]), "state": r[5],
            "doc_class": r[6], "class_reason": r[7],
            "text_chars": int(r[8]) if r[8] is not None else None, "ocr_state": r[9],
            "deleted_at": r[10].isoformat() if r[10] else None,
            "uploaded_by": str(r[11]) if r[11] else None,
            "shared_with_firm_at": r[12].isoformat() if r[12] else None,
            "shared_by": str(r[13]) if r[13] else None, "failure_reason": r[14]}

    def vault_documents_by_sha256(self, sha256: str) -> list[dict]:
        """The live documents with these bytes that this actor's policy shows."""
        with self._conn() as c:
            rows = c.execute("SELECT document_id FROM vault_documents WHERE sha256 = %s "
                             "AND deleted_at IS NULL", (sha256,)).fetchall()
        return [d for d in (self.read_vault_document(str(r[0])) for r in rows) if d]

    def list_vault_documents(self, *, matter_id: str) -> list[dict]:
        want = _matter_scope(matter_id)
        with self._conn() as c:
            rows = c.execute(
                "SELECT document_id FROM vault_documents WHERE matter_id = %s "
                "AND deleted_at IS NULL ORDER BY lower(name)", (want,)).fetchall()
        return [self.read_vault_document(str(r[0])) or {} for r in rows]

    def browse_vault_documents(self, *, matter_id: str | None, query: str, limit: int, offset: int) -> list[dict]:
        """One bounded metadata query under tenant RLS, without N+1 reads."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT document_id, sha256, name, state, matter_id, byte_count, doc_class, "
                "uploaded_by, shared_with_firm_at "
                "FROM vault_documents WHERE matter_id IS NOT DISTINCT FROM %s::uuid "
                "AND deleted_at IS NULL AND state <> 'DELETED' "
                "AND position(%s in lower(name)) > 0 "
                "ORDER BY lower(name), document_id LIMIT %s OFFSET %s",
                (matter_id, query.lower(), limit, offset)).fetchall()
        return [{"document_id": str(r[0]), "sha256": r[1], "name": r[2], "state": r[3],
                 "matter_id": str(r[4]) if r[4] else None, "byte_count": int(r[5]),
                 "doc_class": r[6], "uploaded_by": str(r[7]) if r[7] else None,
                 "shared_with_firm_at": r[8].isoformat() if r[8] else None} for r in rows]

    def write_vault_chunks(self, document_id: str, chunks: list) -> int:
        import psycopg
        try:
            with self._conn() as c, c.transaction():
                if not _lock_live_vault_document(c, document_id):
                    return 0
                c.execute("DELETE FROM vault_chunks WHERE document_id = %s",
                          (document_id,))
                for i, text in enumerate(chunks or ()):
                    c.execute("INSERT INTO vault_chunks (document_id, tenant_id, ordinal, "
                              "text) VALUES (%s,%s,%s,%s)",
                              (document_id, self.tenant_id, i, str(text)))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused a chunk: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return len(chunks or ())

    def read_vault_chunks(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT c.document_id, c.ordinal, c.text, d.name, d.doc_class, "
                "       d.matter_id, d.uploaded_by, d.shared_with_firm_at "
                "FROM vault_chunks c JOIN vault_documents d "
                "  ON d.document_id = c.document_id "
                "WHERE d.deleted_at IS NULL ORDER BY c.document_id, c.ordinal").fetchall()
        return [{"document_id": str(r[0]), "ordinal": int(r[1]), "text": r[2],
                 "name": r[3], "doc_class": r[4] or "",
                 "matter_id": str(r[5]) if r[5] else None,
                 "uploaded_by": str(r[6]) if r[6] else None,
                 "shared_with_firm_at": r[7].isoformat() if r[7] else None} for r in rows]

    def write_vault_tags(self, document_id: str, tags: list) -> int:
        import psycopg
        try:
            with self._conn() as c, c.transaction():
                if not _lock_live_vault_document(c, document_id):
                    return 0
                c.execute("DELETE FROM vault_tags WHERE document_id = %s", (document_id,))
                for t in tags or ():
                    c.execute(
                        "INSERT INTO vault_tags (document_id, tenant_id, tag, quote, "
                        "span_start, span_end) VALUES (%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT DO NOTHING",
                        (document_id, self.tenant_id, (t or {}).get("tag"),
                         (t or {}).get("quote"), (t or {}).get("span_start"),
                         (t or {}).get("span_end")))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused a tag: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return len(tags or ())

    def read_vault_tags(self, document_id: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT tag, quote, span_start, span_end FROM vault_tags "
                "WHERE document_id = %s ORDER BY tag, quote", (document_id,)).fetchall()
        return [{"document_id": str(document_id), "tag": r[0], "quote": r[1],
                 "span_start": r[2], "span_end": r[3]} for r in rows]

    def delete_vault_document(self, document_id: str, *, now: str) -> bool:
        """One statement, so a second delete cannot also claim to be the first."""
        with self._conn() as c:
            n = c.execute(
                "UPDATE vault_documents SET state = 'DELETED', deleted_at = now(), "
                "text_chars = NULL, failure_reason = NULL "
                "WHERE document_id = %s AND deleted_at IS NULL",
                (document_id,)).rowcount
            if n:
                c.execute("DELETE FROM vault_chunks WHERE document_id = %s",
                          (document_id,))
                c.execute("DELETE FROM vault_tags WHERE document_id = %s",
                          (document_id,))
        return bool(n)

    def fail_vault_document(self, document_id: str, reason: str) -> bool:
        """PENDING -> FAILED with the reason (030). One guarded statement."""
        if not str(reason or "").strip():
            raise StoreError("a FAILED document says why (030 vault_documents_failed_has_reason)")
        with self._conn() as c:
            n = c.execute("UPDATE vault_documents SET state = 'FAILED', failure_reason = %s "
                          "WHERE document_id = %s AND state = 'PENDING'",
                          (str(reason), document_id)).rowcount
        return bool(n)

    def retry_vault_document(self, document_id: str, *, queue) -> bool:
        """FAILED -> PENDING, its run back to PLANNED and its DEAD job requeued, in ONE
        transaction. The guard on the document (`state = 'FAILED'`) and on the job
        (`status = 'DEAD'`) means a second, racing retry changes nothing."""
        with self._conn() as c, c.transaction():
            n = c.execute("UPDATE vault_documents SET state = 'PENDING', failure_reason = NULL "
                          "WHERE document_id = %s AND state = 'FAILED'",
                          (document_id,)).rowcount
            if not n:
                return False
            reset = c.execute("UPDATE runs SET status = 'PLANNED', refusal_code = NULL, "
                              "result = NULL, failure_category = NULL, failure_reason = NULL, "
                              "finished_at = NULL WHERE run_id = %s AND status = 'FAILED'",
                              (document_id,)).rowcount
            if not reset:
                # A run that is not FAILED (cancelled, say) is not this retry's to restart.
                # Raising rolls the document back to FAILED too.
                raise RetryConflict("this document's run is not FAILED, so it was not retried")
            # The failed attempt's steps go, as `write_run` replaces a run's steps: they are
            # keyed by capability, so a FAILED step left here would make the retry's own
            # step a "replay" and the finished run would still show FAILED.
            c.execute("DELETE FROM run_steps WHERE run_id = %s", (document_id,))
            queue.requeue_dead(document_id, connection=c)
        return True

    # ── T3 move 10: document_checks (023) ───────────────────────────────────
    def write_document_check(self, check: dict) -> dict:
        """One row per check. No ON CONFLICT clause, deliberately: there is nothing to
        update, and an UPSERT here would be the overwrite 023's architect record rejected."""
        import uuid as _uuid
        cid = str(check.get("check_id") or _uuid.uuid4())
        with self._conn() as c:
            c.execute(
                "INSERT INTO document_checks (check_id, tenant_id, document_id, as_of, "
                "verification_status, validity_status, action, action_reason, expires_on, "
                "renew_by, law_versions) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (cid, self.tenant_id, check["document_id"], check["as_of"],
                 check["verification_status"], check["validity_status"], check["action"],
                 check["action_reason"], check.get("expires_on"), check.get("renew_by"),
                 _json(check.get("law_versions"))))
            row = c.execute(
                "SELECT " + ", ".join(_DOC_CHECK_COLS) + " FROM document_checks "
                "WHERE check_id = %s", (cid,)).fetchone()
        return _doc_check_row(row)

    def read_document_checks(self, *, document_id: str = "",
                             limit: int = 100) -> list[dict]:
        sql = ("SELECT " + ", ".join(_DOC_CHECK_COLS) + " FROM document_checks ")
        args: tuple = ()
        if document_id:
            sql += "WHERE document_id = %s "
            args = (document_id,)
        sql += "ORDER BY checked_at DESC LIMIT %s"
        with self._conn() as c:
            rows = c.execute(sql, args + (int(limit),)).fetchall()
        return [_doc_check_row(r) for r in rows]

    def read_renewals(self, *, on_or_before: str = "") -> list[dict]:
        """Outstanding RENEW_BY rows, soonest first, LATEST CHECK PER DOCUMENT only.

        `DISTINCT ON (document_id) ... ORDER BY document_id, checked_at DESC` is the whole
        point: a document checked in March (RENEW_BY) and again in April (KEEP, because it
        was renewed) must not still show a deadline. A bare `WHERE renew_by IS NOT NULL`
        would show every renewal ever raised, which is the cost of the append-only shape.
        """
        sql = ("SELECT " + ", ".join(_DOC_CHECK_COLS) + " FROM ("
               "SELECT DISTINCT ON (document_id) " + ", ".join(_DOC_CHECK_COLS) + " "
               "FROM document_checks ORDER BY document_id, checked_at DESC) latest "
               "WHERE renew_by IS NOT NULL ")
        args: tuple = ()
        if on_or_before:
            sql += "AND renew_by <= %s "
            args = (on_or_before,)
        sql += "ORDER BY renew_by"
        with self._conn() as c:
            rows = c.execute(sql, args).fetchall()
        return [_doc_check_row(r) for r in rows]

    def vault_counts(self) -> dict:
        with self._conn() as c:
            rows = c.execute("SELECT state, count(*) FROM vault_documents "
                             "WHERE deleted_at IS NULL GROUP BY state").fetchall()
            gone = c.execute("SELECT count(*) FROM vault_documents "
                             "WHERE deleted_at IS NOT NULL").fetchone()[0]
        by_state = {r[0]: int(r[1]) for r in rows}
        return {"documents": sum(by_state.values()), "by_state": by_state,
                "deleted": int(gone),
                "unsearchable": by_state.get("PENDING", 0)
                + by_state.get("CANNOT_READ", 0) + by_state.get("FAILED", 0)}

    @staticmethod
    def _turn_row(row) -> dict:
        return {"message_id": str(row[0]), "conversation_id": str(row[1]),
                "ordinal": row[2], "role": row[3], "text": row[4],
                "file_ids": list(row[5] or []), "task": row[6],
                "run_id": str(row[7]) if row[7] else None,
                "envelope": row[8], "metadata": row[9]}

    def _find_turn(self, c, request_id: str, payload_digest: str) -> dict | None:
        row = c.execute(
            "SELECT message_id, conversation_id, ordinal, role, text, file_ids, task, "
            "run_id, envelope, metadata, payload_digest FROM messages WHERE request_id = %s",
            (request_id,)).fetchone()
        if row is None:
            return None
        if row[10] != payload_digest:
            raise TurnConflict("request_id was already used with different input")
        return self._turn_row(row)

    def find_turn(self, request_id: str, payload_digest: str) -> dict | None:
        with self._conn() as c:
            return self._find_turn(c, request_id, payload_digest)

    def reserve_turn(self, conversation: dict, user: dict, assistant: dict, *,
                     request_id: str, payload_digest: str, queue=None, queued=None) -> tuple[dict, bool]:
        """Retry reservation and both ordinal slots commit in a single transaction.

        The request lock also works when the first caller had no conversation_id. The
        conversation row lock serializes different requests in the same thread. Neither
        lock is held during model work. RLS applies to every statement below.
        """
        cid = conversation["conversation_id"]
        with self._conn() as c, c.transaction():
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                      (self.tenant_id + ":turn:" + request_id,))
            prior = self._find_turn(c, request_id, payload_digest)
            if prior is not None:
                return prior, False
            c.execute("INSERT INTO conversations (conversation_id, tenant_id, actor_id, "
                      "title, matter_id) VALUES (%s,%s,%s,%s,%s) "
                      "ON CONFLICT (conversation_id) DO NOTHING",
                      (cid, self.tenant_id, self.actor_id, conversation.get("title") or "",
                       conversation.get("matter_id")))
            existing = c.execute("SELECT matter_id FROM conversations "
                                 "WHERE conversation_id = %s FOR UPDATE", (cid,)).fetchone()
            if existing is None:
                raise StoreError("conversation is unavailable")
            if (str(existing[0]) if existing[0] else None) != conversation.get("matter_id"):
                raise TurnConflict("a conversation's matter cannot change during a turn")
            ordinal = c.execute("SELECT COALESCE(max(ordinal), -1) + 1 FROM messages "
                                "WHERE conversation_id = %s", (cid,)).fetchone()[0]
            if queued is not None:
                c.execute("INSERT INTO runs (run_id, tenant_id, actor_id, intent, status, "
                          "matter_id) VALUES (%s,%s,%s,%s,'PLANNED',%s)",
                          (queued["run_id"], self.tenant_id, self.actor_id, queued["intent"],
                           conversation.get("matter_id")))
            for offset, message in enumerate((user, assistant)):
                message = dict(message, conversation_id=cid, ordinal=ordinal + offset)
                _check_message(message)
                c.execute("INSERT INTO messages (message_id, conversation_id, tenant_id, "
                          "ordinal, role, text, file_ids, task, run_id, envelope, metadata, "
                          "request_id, payload_digest) VALUES "
                          "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                          (message["message_id"], cid, self.tenant_id, message["ordinal"],
                           message["role"], message.get("text") or "",
                           _json(message.get("file_ids") or []), message.get("task"),
                           message.get("run_id"), _json(message.get("envelope")),
                           _json(message.get("metadata")), request_id if offset else None,
                           payload_digest if offset else None))
            if queued is not None:
                # Same transaction: no worker can see a job without its run and message.
                queue.enqueue(**queued, connection=c)
            c.execute("UPDATE conversations SET updated_at = now() "
                      "WHERE conversation_id = %s", (cid,))
            return _shaped(message, MESSAGE_KEYS), True

    def expire_pending_message(self, message_id: str, envelope: dict) -> bool:
        if not _UUID.match(message_id or ""):
            return False
        with self._conn() as c:
            n = c.execute("UPDATE messages SET envelope = %s WHERE message_id = %s "
                          "AND role = 'assistant' AND envelope IS NULL AND run_id IS NULL",
                          (_json(envelope), message_id)).rowcount
        return bool(n)

    def update_message(self, message_id: str, *, task, run_id, envelope, metadata) -> bool:
        if not _UUID.match(message_id or ""):
            return False
        with self._conn() as c:
            n = c.execute("UPDATE messages SET task = %s, run_id = %s, envelope = %s, "
                          "metadata = %s WHERE message_id = %s AND role = 'assistant'",
                          (task, run_id, _json(envelope), _json(metadata), message_id)).rowcount
        return bool(n)

    def append_message(self, message: dict) -> dict:
        """Append one message, translating the database's refusals into StoreError.

        The translation is not cosmetic. `conformance()` asserts that both backends refuse
        the same rows, and it caught this: the dict raised `StoreError` on a duplicate
        ordinal while Postgres raised `psycopg.errors.UniqueViolation`, so a caller with
        one `except StoreError` handled the memory backend and crashed on the real one --
        the divergence that only shows up on the backend the gate does not run, which is
        the whole reason that list is shared.
        """
        import psycopg
        _check_message(message)
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO messages (message_id, conversation_id, tenant_id, "
                    "ordinal, role, text, file_ids, task, run_id, envelope, metadata) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (message["message_id"], message["conversation_id"], self.tenant_id,
                     message["ordinal"], message["role"], message.get("text") or "",
                     _json(list(message.get("file_ids") or [])), message.get("task"),
                     message.get("run_id"), _json(message.get("envelope")),
                     _json(message.get("metadata"))))
                c.execute("UPDATE conversations SET updated_at = now() WHERE "
                          "conversation_id = %s", (message["conversation_id"],))
        except psycopg.errors.IntegrityError as exc:
            # UniqueViolation (the ordinal), CheckViolation (010's role/envelope/file_ids
            # rules), ForeignKeyViolation (no such conversation) all land here.
            raise StoreError(
                f"the database refused this message: {type(exc).__name__} "
                f"{str(exc).splitlines()[0][:160]}") from None
        return _shaped(message, MESSAGE_KEYS)

    def read_messages(self, conversation_id: str) -> list[dict]:
        if not _UUID.match(conversation_id or ""):
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT message_id, conversation_id, ordinal, role, text, file_ids, task, "
                "run_id, envelope, metadata FROM messages WHERE conversation_id = %s "
                "ORDER BY ordinal", (conversation_id,)).fetchall()
        return [{"message_id": str(r[0]), "conversation_id": str(r[1]), "ordinal": r[2],
                 "role": r[3], "text": r[4], "file_ids": list(r[5] or []),
                 "task": r[6], "run_id": str(r[7]) if r[7] is not None else None,
                 "envelope": r[8], "metadata": r[9]} for r in rows]

    def set_message_envelope(self, message_id: str, envelope: dict) -> bool:
        if not _UUID.match(message_id or ""):
            return False
        with self._conn() as c:
            # role = 'assistant' in the WHERE, not asserted in Python: a user message must
            # not gain an envelope even if a caller asks, and 010's CHECK says so too.
            n = c.execute("UPDATE messages SET envelope = %s WHERE message_id = %s AND "
                          "role = 'assistant'",
                          (_json(envelope), message_id)).rowcount
        return bool(n)

    # ── H4: review grids ─────────────────────────────────────────────────────
    def write_grid(self, grid: dict) -> dict:
        import psycopg
        gid = grid["grid_id"]
        try:
            with self._conn() as c:
                c.execute("INSERT INTO review_grids (grid_id, tenant_id, name, actor_id, "
                          "document_names) VALUES (%s,%s,%s,%s,%s) "
                          "ON CONFLICT (grid_id) DO UPDATE SET name = EXCLUDED.name, "
                          "document_names = review_grids.document_names || "
                          "EXCLUDED.document_names",
                          (gid, self.tenant_id, grid.get("name") or "",
                           self._session_actor or None,
                           _json(dict(grid.get("document_names") or {}))))
                for i, col in enumerate(grid.get("columns") or ()):
                    c.execute(
                        "INSERT INTO review_grid_columns (grid_id, tenant_id, name, kind, "
                        "question, ordinal) VALUES (%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (grid_id, name) DO NOTHING",
                        (gid, self.tenant_id, col["name"], col["kind"], col["question"], i))
                for d in grid.get("document_ids") or ():
                    for col in grid.get("columns") or ():
                        c.execute(
                            "INSERT INTO review_grid_cells (grid_id, tenant_id, "
                            "document_id, column_name, state, reason) VALUES "
                            "(%s,%s,%s,%s,'PENDING',%s) ON CONFLICT DO NOTHING",
                            (gid, self.tenant_id, d, col["name"],
                             "queued; this cell has not been run yet"))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this grid: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return self.read_grid(gid) or {"grid_id": gid}

    def read_grid(self, grid_id: str) -> dict | None:
        if not _UUID.match(grid_id or ""):
            return None
        with self._conn() as c:
            g = c.execute("SELECT grid_id, name, cancelled_at, paused_budget, "
                          "pause_reason, cells_not_dispatched, actor_id, matter_id, "
                          "document_names FROM review_grids "
                          "WHERE grid_id = %s", (grid_id,)).fetchone()
            if g is None:
                return None
            cols = c.execute("SELECT name, kind, question FROM review_grid_columns "
                             "WHERE grid_id = %s ORDER BY ordinal", (grid_id,)).fetchall()
            docs = c.execute("SELECT DISTINCT document_id FROM review_grid_cells "
                             "WHERE grid_id = %s ORDER BY document_id",
                             (grid_id,)).fetchall()
        return {"grid_id": str(g[0]), "name": g[1],
                "cancelled_at": g[2].isoformat() if g[2] else None,
                # 022. Selected explicitly: a default standing in for a column the query
                # forgot is a lie with a safety net, which is how A1's `jobs.get()` came
                # to report a DEAD job with no reason.
                "paused_budget": bool(g[3]),
                "pause_reason": g[4] or "",
                "cells_not_dispatched": int(g[5] or 0),
                "actor_id": str(g[6]) if g[6] else None,
                "matter_id": str(g[7]) if g[7] else None,
                "document_names": dict(g[8] or {}),
                "columns": [{"name": r[0], "kind": r[1], "question": r[2]} for r in cols],
                "document_ids": [r[0] for r in docs]}

    def read_grid_cells(self, grid_id: str) -> list[dict]:
        if not _UUID.match(grid_id or ""):
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT grid_id, document_id, column_name, state, value, quote, reason, "
                "provider, cost_inr, cost_note "
                "FROM review_grid_cells WHERE grid_id = %s "
                "ORDER BY document_id, column_name", (grid_id,)).fetchall()
        # Through `_shaped`, like every other row: it floats the numeric (Postgres returns
        # Decimal, the dict returns float, and a caller summing a grid would hit a
        # TypeError on exactly one backend) and it fills NO_CALL_NOTE for a null cost with
        # no note -- which is how a PENDING cell reads the same on both. The conformance
        # list caught that divergence the first time it ran these columns.
        return [_shaped({"grid_id": str(r[0]), "document_id": r[1], "column_name": r[2],
                         "state": r[3], "value": r[4], "quote": r[5], "reason": r[6],
                         "provider": r[7],
                         "cost_inr": float(r[8]) if r[8] is not None else None,
                         "cost_note": r[9]}, GRID_CELL_KEYS)
                for r in rows]

    def list_grids(self, *, limit: int, before_created_at: str | None = None,
                   before_grid_id: str | None = None) -> list[dict]:
        _check_grid_page(limit, before_created_at, before_grid_id)
        with self._conn() as c:
            rows = c.execute(
                "SELECT g.grid_id, g.name, g.created_at, g.cancelled_at, g.paused_budget, "
                "g.actor_id, g.matter_id, "
                "(SELECT count(*) FROM review_grid_columns k WHERE k.grid_id = g.grid_id), "
                "x.documents, x.cells, x.pending "
                "FROM review_grids g CROSS JOIN LATERAL ("
                "  SELECT count(DISTINCT document_id) AS documents, count(*) AS cells, "
                "  count(*) FILTER (WHERE state = 'PENDING') AS pending "
                "  FROM review_grid_cells c WHERE c.grid_id = g.grid_id) x "
                "WHERE (%s::timestamptz IS NULL OR (g.created_at, g.grid_id) < "
                "(%s::timestamptz, %s::uuid)) "
                "ORDER BY g.created_at DESC, g.grid_id DESC LIMIT %s",
                (before_created_at, before_created_at, before_grid_id, limit)).fetchall()
        return [_grid_summary(
                    {"grid_id": str(r[0]), "name": r[1], "created_at": r[2].isoformat(),
                     "cancelled_at": r[3].isoformat() if r[3] else None,
                     "paused_budget": bool(r[4]),
                     "actor_id": str(r[5]) if r[5] else None,
                     "matter_id": str(r[6]) if r[6] else None},
                    columns=int(r[7]), documents=int(r[8]), cells=int(r[9]),
                    pending=int(r[10]))
                for r in rows]

    def pause_grid(self, grid_id: str, *, reason: str, not_dispatched: int) -> bool:
        """Record that the budget paused this table. False when there is no such grid.

        022's CHECKs do the refusing on this path; the guards below are the same rules
        restated so the dict cannot accept a row Postgres would reject.
        """
        import psycopg
        if not str(reason or "").strip():
            raise StoreError(
                "a paused table needs a reason (022 review_grids_pause_reason_iff_paused)")
        if int(not_dispatched) < 0:
            raise StoreError("cells_not_dispatched cannot be negative")
        if not _UUID.match(grid_id or ""):
            return False
        try:
            with self._conn() as c:
                n = c.execute(
                    "UPDATE review_grids SET paused_budget = true, pause_reason = %s, "
                    "cells_not_dispatched = %s WHERE grid_id = %s",
                    (str(reason)[:2000], int(not_dispatched), grid_id)).rowcount
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this pause: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return bool(n)

    def write_grid_cell(self, cell: dict, *, if_pending: bool = True) -> bool:
        import psycopg
        where = " AND review_grid_cells.state = 'PENDING'" if if_pending else ""
        try:
            with self._conn() as c:
                n = c.execute(
                    "INSERT INTO review_grid_cells (grid_id, tenant_id, document_id, "
                    "column_name, state, value, quote, reason, provider, cost_inr, "
                    "cost_note, answered_at) VALUES "
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) "
                    "ON CONFLICT (grid_id, document_id, column_name) DO UPDATE SET "
                    "state = EXCLUDED.state, value = EXCLUDED.value, "
                    "quote = EXCLUDED.quote, reason = EXCLUDED.reason, "
                    "provider = EXCLUDED.provider, cost_inr = EXCLUDED.cost_inr, "
                    "cost_note = EXCLUDED.cost_note, "
                    "answered_at = now() WHERE TRUE" + where,
                    (cell["grid_id"], self.tenant_id, cell["document_id"],
                     cell["column_name"], cell["state"], cell.get("value") or "",
                     cell.get("quote") or "", cell.get("reason") or "",
                     cell.get("provider"), cell.get("cost_inr"),
                     cell.get("cost_note"))).rowcount
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this cell: {type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return bool(n)

    def cancel_grid(self, grid_id: str) -> bool:
        if not _UUID.match(grid_id or ""):
            return False
        with self._conn() as c:
            n = c.execute("UPDATE review_grids SET cancelled_at = now() "
                          "WHERE grid_id = %s AND cancelled_at IS NULL",
                          (grid_id,)).rowcount
        return bool(n)

    # ── O9: the answer cache ─────────────────────────────────────────────────
    def write_cache_entry(self, entry: dict) -> bool:
        import json as _json
        import psycopg
        if not (entry.get("citations") or []):
            raise StoreError(
                "a cache entry with NO citations is refused (014 answer_cache.citations): "
                "an answer that cites nothing can never be shown to be still true")
        try:
            with self._conn() as c:
                n = c.execute(
                    "INSERT INTO answer_cache (tenant_id, lookup_key, content_key, "
                    "question, task, as_of, sources, citations, payload, actor_id, "
                    "matter_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (tenant_id, lookup_key) DO UPDATE SET "
                    "content_key = EXCLUDED.content_key, citations = EXCLUDED.citations, "
                    "payload = EXCLUDED.payload, created_at = now()",
                    (self.tenant_id, entry["lookup_key"], entry["content_key"],
                     entry.get("question") or "", entry.get("task") or "",
                     entry.get("as_of") or "",
                     _json.dumps(list(entry.get("sources") or [])),
                     _json.dumps(list(entry.get("citations") or [])),
                     _json.dumps(dict(entry.get("payload") or {})),
                     # 028. Owned by the session's actor, filed to the matter it was asked in.
                     self._session_actor or None,
                     str(entry.get("matter_id") or "").strip() or None)).rowcount
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this cache entry: "
                             f"{type(exc).__name__} "
                             f"{str(exc).splitlines()[0][:150]}") from None
        return bool(n)

    def read_cache_entry(self, lookup_key: str) -> dict | None:
        with self._conn() as c:
            r = c.execute(
                "SELECT lookup_key, content_key, question, task, as_of, sources, "
                "citations, payload, created_at, served FROM answer_cache "
                "WHERE lookup_key = %s", (str(lookup_key or ""),)).fetchone()
        if not r:
            return None
        row = _shaped({"lookup_key": r[0], "content_key": r[1], "question": r[2],
                       "task": r[3], "as_of": r[4], "sources": list(r[5] or []),
                       "citations": list(r[6] or []), "payload": dict(r[7] or {}),
                       "created_at": r[8].isoformat() if r[8] else ""}, CACHE_KEYS)
        row["served"] = int(r[9] or 0)
        return row

    def bump_cache_stat(self, kind: str, *, day: str) -> None:
        if kind not in CACHE_STATS:
            raise StoreError(f"{kind!r} is not a cache statistic; one of {CACHE_STATS}")
        # The column name is interpolated and that is safe ONLY because `kind` has just
        # been checked against a fixed tuple. Never widen this without that check.
        with self._conn() as c:
            c.execute(
                f"INSERT INTO answer_cache_stats (tenant_id, day, {kind}) "
                f"VALUES (%s, %s, 1) ON CONFLICT (tenant_id, day) DO UPDATE SET "
                f"{kind} = answer_cache_stats.{kind} + 1",
                (self.tenant_id, str(day)))

    def read_cache_stats(self) -> dict:
        with self._conn() as c:
            r = c.execute("SELECT COALESCE(SUM(hits),0), COALESCE(SUM(misses),0), "
                          "COALESCE(SUM(stale),0) FROM answer_cache_stats").fetchone()
        return {"hits": int(r[0]), "misses": int(r[1]), "stale": int(r[2])}

    # ── H3: drafts ───────────────────────────────────────────────────────────
    def write_draft(self, draft: dict, *, create_only: bool = False) -> dict:
        import psycopg
        did = draft["draft_id"]
        try:
            with self._conn() as c:
                c.execute("INSERT INTO drafts (draft_id, tenant_id, kind, title, actor_id) "
                          "VALUES (%s,%s,%s,%s,%s) " + ("" if create_only else
                          "ON CONFLICT (draft_id) DO UPDATE SET "
                          "title = EXCLUDED.title, updated_at = now()"),
                          (did, self.tenant_id, draft.get("kind") or "unknown",
                           draft.get("title") or "", self._session_actor or None))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused this draft: {type(exc).__name__}") from None
        return self.read_draft(did) or {"draft_id": did}

    def create_draft(self, draft: dict, first_version: dict) -> int:
        """Insert metadata and version 1 in the same transaction, or neither."""
        import psycopg
        version = dict(first_version, draft_id=draft["draft_id"], version=1)
        _check_draft_version(version)
        try:
            with self._conn() as c:
                with c.transaction():
                    c.execute("INSERT INTO drafts (draft_id, tenant_id, kind, title, "
                              "actor_id) VALUES (%s,%s,%s,%s,%s)",
                              (draft["draft_id"], self.tenant_id,
                               draft.get("kind") or "unknown", draft.get("title") or "",
                               self._session_actor or None))
                    _insert_draft_version(c, self.tenant_id, version, 1)
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(f"the database refused draft creation: {type(exc).__name__}") from None
        return 1

    def read_draft(self, draft_id: str) -> dict | None:
        if not _UUID.match(draft_id or ""):
            return None
        with self._conn() as c:
            r = c.execute("SELECT draft_id, kind, title, actor_id, matter_id FROM drafts "
                          "WHERE draft_id = %s", (draft_id,)).fetchone()
        return None if r is None else {"draft_id": str(r[0]), "kind": r[1], "title": r[2],
                                       "actor_id": str(r[3]) if r[3] else None,
                                       "matter_id": str(r[4]) if r[4] else None}

    def list_drafts(self, *, limit: int, before_updated_at: str | None = None,
                    before_draft_id: str | None = None) -> list[dict]:
        if limit < 1 or limit > 51:
            raise StoreError("draft list page size must be from 1 to 51")
        if before_updated_at is not None and not before_draft_id:
            raise StoreError("a draft cursor needs both updated_at and draft_id")
        if before_draft_id is not None and not _UUID.match(before_draft_id):
            raise StoreError("a draft cursor has an invalid draft_id")
        with self._conn() as c:
            rows = c.execute(
                "SELECT d.draft_id, d.kind, v.title, d.updated_at, v.version, "
                "v.blocking_count, (v.approved_at IS NOT NULL) AS approved, v.body, v.slots, "
                "d.actor_id, d.matter_id "
                "FROM drafts d JOIN LATERAL ("
                "  SELECT version, title, blocking_count, approved_at, body, slots FROM draft_versions "
                "  WHERE draft_id = d.draft_id ORDER BY version DESC LIMIT 1"
                ") v ON true "
                "WHERE (%s::timestamptz IS NULL OR (d.updated_at, d.draft_id) < "
                "(%s::timestamptz, %s::uuid)) "
                "ORDER BY d.updated_at DESC, d.draft_id DESC LIMIT %s",
                (before_updated_at, before_updated_at, before_draft_id, limit),
            ).fetchall()
        from checker.draft_versions import stored_review_count
        result = []
        for r in rows:
            count = stored_review_count(r[7] or "", r[8] or [], int(r[5]))
            result.append({"draft_id": str(r[0]), "kind": r[1], "title": r[2],
                           "updated_at": r[3].isoformat(), "version": int(r[4]),
                           "blocking_count": count, "approved": bool(r[6]) and count == 0,
                           "actor_id": str(r[9]) if r[9] else None,
                           "matter_id": str(r[10]) if r[10] else None})
        return result

    def append_draft_version(self, version: dict) -> int:
        import psycopg
        _check_draft_version(version)
        did = version["draft_id"]
        try:
            with self._conn() as c:
                n = version.get("version")
                if n is None:
                    row = c.execute("SELECT coalesce(max(version), 0) + 1 FROM "
                                    "draft_versions WHERE draft_id = %s",
                                    (did,)).fetchone()
                    n = int(row[0]) if row else 1
                _insert_draft_version(c, self.tenant_id, version, int(n))
                c.execute("UPDATE drafts SET updated_at = now() WHERE draft_id = %s",
                          (did,))
        except psycopg.errors.IntegrityError as exc:
            raise StoreError(
                f"the database refused this draft version: {type(exc).__name__} "
                f"{str(exc).splitlines()[0][:150]}") from None
        return int(n)

    def read_draft_versions(self, draft_id: str) -> list[dict]:
        if not _UUID.match(draft_id or ""):
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT draft_id, version, title, body, slots, citations, "
                "blocking_count, approved_by, approved_at, created_at FROM draft_versions "
                "WHERE draft_id = %s ORDER BY version", (draft_id,)).fetchall()
        # created_at was not selected, so every version read back undated and
        # verbs._draft_history stamped it 2026-01-01.
        return [{"draft_id": str(r[0]), "version": r[1], "title": r[2], "body": r[3],
                 "slots": list(r[4] or []), "citations": list(r[5] or []),
                 "blocking_count": r[6], "approved_by": r[7],
                 "approved_at": r[8].isoformat() if r[8] else None,
                 "created_at": r[9].isoformat() if r[9] else None} for r in rows]

    def next_ordinal(self, conversation_id: str) -> int:
        if not _UUID.match(conversation_id or ""):
            return 0
        with self._conn() as c:
            r = c.execute("SELECT count(*) FROM messages WHERE conversation_id = %s",
                          (conversation_id,)).fetchone()
        return int(r[0]) if r else 0

    def read(self, run_id: str) -> dict | None:
        return self.read_run(run_id)

    def write(self, run: dict) -> None:
        self.write_run(run)
