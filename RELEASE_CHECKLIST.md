# WebRefurbMenu Release Checklist

Use this before pushing a public-site or send/publish workflow change.

## Local Gate

- [ ] `git status --short` contains only intentional files.
- [ ] `.venv/bin/python scripts/release_gate.py`
- [ ] `.venv/bin/python scripts/deployment_health_check.py --mode static --root docs`
- [ ] `.venv/bin/python scripts/deployment_health_check.py --mode static --root .`
- [ ] `.venv/bin/python scripts/secret_scan.py --root .`

## Public Site

- [ ] Root and `docs/` public files are mirrored if GitHub Pages is still serving the repository root.
- [ ] All 7 public URLs return `200`.
- [ ] EN pages serve `lang="en"` and JA/demo menu pages serve the intended language.
- [ ] Canonical and Open Graph tags are present.
- [ ] No banned customer-facing terms are visible.
- [ ] Ramen and sushi demos still use the coral/white visual system.

## Send And Publish Safety

- [ ] Test sends go only to `chris@webrefurb.com`.
- [ ] Real sends have explicit manual approval.
- [ ] Opt-out, bounced, and do-not-contact records are blocked.
- [ ] Publish blocks unconfirmed prices, descriptions, ingredients, and allergy notes.
- [ ] Draft/review/trial/paid/archived state is clear before publishing.

## Live Gate

- [ ] `.venv/bin/python scripts/deployment_health_check.py --mode live --base-url https://webrefurb.com`
- [ ] If the live check fails after a push, revert the last public-site commit or switch Pages back to the last known-good branch.
- [ ] If a wrong menu is live, archive that menu first, then publish a corrected version after owner confirmation.
