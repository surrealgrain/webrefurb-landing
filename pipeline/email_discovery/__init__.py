"""
Email discovery and lead qualification system for Japanese ramen/izakaya shops.

Public API:
    discover_emails  - run the full discovery pipeline on a lead list
    load_config      - load config from YAML with defaults
    enrich_lead      - enrich an existing WebRefurb lead record
"""

__all__ = ["discover_emails", "load_config", "enrich_lead"]


def __getattr__(name):
    if name == "discover_emails":
        from .pipeline import discover_emails
        return discover_emails
    if name == "load_config":
        from .config import load_config
        return load_config
    if name == "enrich_lead":
        from .bridge import enrich_lead
        return enrich_lead
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
