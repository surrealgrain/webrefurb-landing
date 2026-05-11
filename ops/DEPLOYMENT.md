# Deployment Source Of Truth

GitHub Pages is currently serving the repository root for the custom domain.

The canonical editable public site remains under `docs/`, and the deployed root files mirror the public `docs/` files. This duplication is intentional until Pages is explicitly moved to serve from `docs/`.

## Mirrored Paths

- `index.html`
- `pricing.html`
- `ja/`
- `demo/`
- `assets/previews/`
- `logo.svg`
- `email-logo.svg`
- `robots.txt`
- `sitemap.xml`
- `CNAME`

## Guardrail

`tests/test_website.py::test_root_public_files_mirror_docs_pages_source` blocks drift for the main mirrored files.

## Health Check

- Static docs: `.venv/bin/python scripts/deployment_health_check.py --mode static --root docs`
- Static root: `.venv/bin/python scripts/deployment_health_check.py --mode static --root .`
- Live: `.venv/bin/python scripts/deployment_health_check.py --mode live --base-url https://webrefurb.com`
