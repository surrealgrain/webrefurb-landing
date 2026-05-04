# No-Neon Deployment

This project does not need Neon or another managed Postgres service for its current dashboard and pipeline.

Runtime persistence is local-first:

- `state/leads/*.json` for lead queue records.
- `state/orders/*.json` for quote, payment, intake, and delivery state.
- `state/sent/*.json` and `state/incoming_replies/*.json` for outreach history.
- `state/launch_batches/*.json` for launch tracking.
- `state/email_discovery.db` for the email discovery SQLite cache when the discovery pipeline is used.
- `docs/menus/**` for static QR menu pages and public menu artifacts.

## Run Locally Without Neon

From the repo root:

```bash
mkdir -p state docs
docker compose -f compose.no-neon.yml up --build
```

Then open:

```text
http://localhost:8000
```

The container stores operational data on the host through these mounted folders:

- `./state` -> `/app/state`
- `./docs` -> `/app/docs`

That means deleting the container does not delete the dashboard data.

## Environment Variables

The app still uses optional service keys for specific workflows, but none of these are a database:

- `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_FROM_NAME`, `RESEND_REPLY_TO_EMAIL`, `RESEND_WEBHOOK_SECRET`
- `OPENROUTER_API_KEY`
- `SERPER_API_KEY`, only when the Serper provider is selected
- `GOOGLE_PLACES_API_KEY`
- `WEBREFURB_SEARCH_PROVIDER`, defaults to `webserper`

Docker Compose reads variables from your shell or a repo-root `.env` file.

## Backups

Before running real outreach or moving the app between machines:

```bash
.venv/bin/python -m pipeline.cli backup-state
```

Inside the container:

```bash
docker compose -f compose.no-neon.yml exec dashboard python -m pipeline.cli backup-state
```

Backups are written under `state/backups/`.

## Check For Accidental Neon/Postgres Wiring

```bash
.venv/bin/python scripts/no_neon_audit.py
```

The script scans project files for Neon/Postgres database wiring and summarizes the local persistence directories.
