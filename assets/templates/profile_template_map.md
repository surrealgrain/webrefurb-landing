# Profile Template Routing Map

Locked menu template assets for Codex routing. GLM-owned; Codex wires code routing separately.

## Active Outreach Contract

- Scope is Japan-only ramen and izakaya.
- Active first-contact menu samples are limited to two HTML templates:
  - Ramen: `assets/templates/ramen_food_menu.html`
  - Izakaya: `assets/templates/izakaya_food_drinks_menu.html`
- The only optional inline add-on is `assets/templates/ticket_machine_guide.html`.
- The template seal is generic `見本`; first-contact samples do not use a restaurant-name seal.
- First contact uses inline previews or hosted sample links, not PDF attachments.
- No template routing change promotes live records or makes a record send-ready by itself.

## Routing

| Lead condition | Menu Template | Optional Guide |
| --- | --- | --- |
| Ramen, no proven ticket-machine evidence | `assets/templates/ramen_food_menu.html` | none |
| Ramen, ticket machine proven by Google review/photo evidence or Tabelog/directory evidence | `assets/templates/ramen_food_menu.html` | `assets/templates/ticket_machine_guide.html` |
| Izakaya | `assets/templates/izakaya_food_drinks_menu.html` | none |

## Profile Normalization

Legacy profile IDs are collapsed before active routing:

| Legacy/current profile | Active route |
| --- | --- |
| `ramen_only`, `ramen_with_sides_add_ons`, `ramen_with_drinks`, `ramen_ticket_machine`, `ramen_menu_plus_ticket_machine` | Ramen template |
| Any `izakaya_*` profile | Izakaya template |
| Plain `soba_only` / `soba` | Out of active scope; must not become send-ready |

Ramen variants such as `abura_soba`, `mazesoba`, and `chuka_soba` remain ramen. Plain soba/蕎麦 shops are out of scope.

## Template Design Contract

Every active HTML template listed above meets these criteria:

- Exactly one `<html>`, `<body>`, `</body>`, `</html>` per file.
- `<body data-profile="ramen_only">`, `<body data-profile="izakaya_food_and_drinks">`, or `<body data-profile="ticket_machine_guide">` matches the route.
- Generic sample seal: `data-slot="seal-text"` contains `見本`.
- Customer-facing footer note confirms the sample is illustrative and owner-confirmed content/photos are used in production.
- No prices, no fake restaurant claims, no real-shop claims.
- No mentions of AI, automation, scraping, internal tools, outreach, lead sourcing, or Codex.
