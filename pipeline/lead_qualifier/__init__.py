"""Menu-first, pain-signal-first lead qualification system.

Standalone module that builds a ranked outreach queue by:
  Phase 1 — Menu evidence (crawl website, run evidence assessment)
  Phase 2 — Pain signals (scrape Google reviews, keyword analysis)
  Phase 3 — Contact discovery (email/contact form, only for qualified leads)

Reads from the existing pipeline (directory_discovery, evidence, contact_crawler)
but does not modify any existing modules.
"""
