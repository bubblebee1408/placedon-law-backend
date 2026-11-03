# One-command local development. Needs Docker (with compose) and nothing else.
# See docs/START_HERE.md §6.
.PHONY: dev down reset migrate test test-db smoke logs shell

dev: .env            ## build, start db + migrations + gateway + worker, then prove it is wired
	docker compose up --build -d
	$(MAKE) smoke

down:                ## stop the stack (keeps the database)
	docker compose down

reset:               ## stop the stack AND delete the local database, vault and backups
	docker compose down -v

migrate: .env        ## apply pending migrations (backup first) and the local bootstrap
	docker compose run --rm migrate

test: .env           ## the repository gate, exactly as CI runs it (keyless, no database)
	docker compose run --rm --no-deps gateway bash scripts/run_tests.sh

test-db: .env        ## the live-database regressions and the RLS proof, as CI runs them
	docker compose up -d --wait db
	docker compose run --rm --no-deps gateway bash scripts/db_regressions.sh

smoke:               ## /v1/health reports postgres, a queue and a vault
	docker compose exec -T gateway python ops/dev/smoke.py

logs:
	docker compose logs -f gateway worker

shell: .env          ## a shell in the dev image, repo mounted at /app
	docker compose run --rm --no-deps gateway bash

# First run: .env from the template, with a fresh random service key (never a shared one).
.env:
	sed "s|^PLACEDON_GATEWAY_SERVICE_KEY=.*|PLACEDON_GATEWAY_SERVICE_KEY=$$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')|" .env.example > .env
	@echo "wrote .env (gitignored); add model keys there only if you need live answers"
