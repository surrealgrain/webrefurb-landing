"""SQLite persistence for email discovery results.

Stores enriched leads, discovered emails, and contact forms.
Supports deduplication by (shop_name, prefecture).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import EnrichedLead, DiscoveredEmail, OperatorCompany


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    lead_id TEXT PRIMARY KEY,
    shop_name TEXT NOT NULL,
    normalized_shop_name TEXT,
    genre TEXT,
    genre_confidence REAL DEFAULT 0,
    address TEXT,
    prefecture TEXT,
    city TEXT,
    phone TEXT,
    official_site_url TEXT,
    operator_company_name TEXT,
    operator_company_url TEXT,
    best_email TEXT,
    best_email_type TEXT,
    contact_form_url TEXT,
    email_source_url TEXT,
    email_source_snippet TEXT,
    no_sales_warning INTEGER DEFAULT 0,
    menu_url TEXT,
    menu_detected INTEGER DEFAULT 0,
    tourist_area_signal INTEGER DEFAULT 0,
    online_shop_detected INTEGER DEFAULT 0,
    tokushoho_page_url TEXT,
    recruitment_page_url TEXT,
    pr_page_url TEXT,
    launch_ready INTEGER DEFAULT 0,
    confidence_score REAL DEFAULT 0,
    reason_codes TEXT,
    next_best_action TEXT,
    operator_company_json TEXT,
    crawl_timestamp TEXT,
    all_emails_json TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_leads_shop ON leads(shop_name);
CREATE INDEX IF NOT EXISTS idx_leads_prefecture ON leads(prefecture);
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(confidence_score DESC);
CREATE INDEX IF NOT EXISTS idx_leads_launch ON leads(launch_ready);

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL,
    email TEXT NOT NULL,
    email_type TEXT,
    source_url TEXT,
    source_snippet TEXT,
    source_page_type TEXT,
    confidence REAL DEFAULT 0,
    mx_valid INTEGER,
    discovered_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
);

CREATE INDEX IF NOT EXISTS idx_emails_lead ON emails(lead_id);
CREATE INDEX IF NOT EXISTS idx_emails_type ON emails(email_type);
"""


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class DiscoveryDB:
    """SQLite database for email discovery results."""

    def __init__(self, path: str = "state/email_discovery.db"):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # -----------------------------------------------------------------------
    # Lead operations
    # -----------------------------------------------------------------------

    def upsert_lead(self, lead: EnrichedLead) -> None:
        """Insert or update a lead."""
        all_emails_json = json.dumps([e.to_dict() for e in lead.all_emails])
        operator_json = json.dumps(lead.operator_company.to_dict()) if lead.operator_company else None
        reason_codes_json = json.dumps(lead.reason_codes)

        self.conn.execute("""
            INSERT INTO leads (
                lead_id, shop_name, normalized_shop_name, genre, genre_confidence,
                address, prefecture, city, phone, official_site_url,
                operator_company_name, operator_company_url, best_email, best_email_type,
                contact_form_url, email_source_url, email_source_snippet,
                no_sales_warning, menu_url, menu_detected, tourist_area_signal,
                online_shop_detected, tokushoho_page_url, recruitment_page_url,
                pr_page_url, launch_ready, confidence_score, reason_codes,
                next_best_action, operator_company_json, crawl_timestamp,
                all_emails_json
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(lead_id) DO UPDATE SET
                shop_name=excluded.shop_name,
                normalized_shop_name=excluded.normalized_shop_name,
                genre=excluded.genre,
                genre_confidence=excluded.genre_confidence,
                address=excluded.address,
                prefecture=excluded.prefecture,
                city=excluded.city,
                phone=excluded.phone,
                official_site_url=excluded.official_site_url,
                operator_company_name=excluded.operator_company_name,
                operator_company_url=excluded.operator_company_url,
                best_email=excluded.best_email,
                best_email_type=excluded.best_email_type,
                contact_form_url=excluded.contact_form_url,
                email_source_url=excluded.email_source_url,
                email_source_snippet=excluded.email_source_snippet,
                no_sales_warning=excluded.no_sales_warning,
                menu_url=excluded.menu_url,
                menu_detected=excluded.menu_detected,
                tourist_area_signal=excluded.tourist_area_signal,
                online_shop_detected=excluded.online_shop_detected,
                tokushoho_page_url=excluded.tokushoho_page_url,
                recruitment_page_url=excluded.recruitment_page_url,
                pr_page_url=excluded.pr_page_url,
                launch_ready=excluded.launch_ready,
                confidence_score=excluded.confidence_score,
                reason_codes=excluded.reason_codes,
                next_best_action=excluded.next_best_action,
                operator_company_json=excluded.operator_company_json,
                crawl_timestamp=excluded.crawl_timestamp,
                all_emails_json=excluded.all_emails_json,
                updated_at=datetime('now')
        """, (
            lead.lead_id, lead.shop_name, lead.normalized_shop_name,
            lead.genre, lead.genre_confidence, lead.address, lead.prefecture,
            lead.city, lead.phone, lead.official_site_url,
            lead.operator_company_name, lead.operator_company_url,
            lead.best_email, lead.best_email_type, lead.contact_form_url,
            lead.email_source_url, lead.email_source_snippet,
            int(lead.no_sales_warning), lead.menu_url, int(lead.menu_detected),
            int(lead.tourist_area_signal), int(lead.online_shop_detected),
            lead.tokushoho_page_url, lead.recruitment_page_url, lead.pr_page_url,
            int(lead.launch_ready), lead.confidence_score, reason_codes_json,
            lead.next_best_action, operator_json, lead.crawl_timestamp,
            all_emails_json,
        ))
        self.conn.commit()

    def get_lead(self, lead_id: str) -> Optional[dict]:
        """Get a lead by ID."""
        row = self.conn.execute(
            "SELECT * FROM leads WHERE lead_id = ?", (lead_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_leads(self, launch_ready_only: bool = False) -> list[dict]:
        """Get all leads, optionally filtered by launch readiness."""
        if launch_ready_only:
            rows = self.conn.execute(
                "SELECT * FROM leads WHERE launch_ready = 1 ORDER BY confidence_score DESC"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM leads ORDER BY confidence_score DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def lead_exists(self, shop_name: str, prefecture: str) -> bool:
        """Check if a lead already exists."""
        row = self.conn.execute(
            "SELECT 1 FROM leads WHERE shop_name = ? AND prefecture = ?",
            (shop_name, prefecture),
        ).fetchone()
        return row is not None

    # -----------------------------------------------------------------------
    # Email operations
    # -----------------------------------------------------------------------

    def insert_email(self, lead_id: str, email: DiscoveredEmail) -> None:
        """Insert a discovered email."""
        self.conn.execute("""
            INSERT INTO emails (lead_id, email, email_type, source_url,
                                source_snippet, source_page_type, confidence, mx_valid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            lead_id, email.email, email.email_type.value,
            email.source_url, email.source_snippet, email.source_page_type,
            email.confidence, email.mx_valid,
        ))
        self.conn.commit()

    def get_emails_for_lead(self, lead_id: str) -> list[dict]:
        """Get all emails for a lead."""
        rows = self.conn.execute(
            "SELECT * FROM emails WHERE lead_id = ?", (lead_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # -----------------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------------

    def stats(self) -> dict:
        """Return summary statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        launch_ready = self.conn.execute(
            "SELECT COUNT(*) FROM leads WHERE launch_ready = 1"
        ).fetchone()[0]
        with_email = self.conn.execute(
            "SELECT COUNT(*) FROM leads WHERE best_email != ''"
        ).fetchone()[0]
        with_form = self.conn.execute(
            "SELECT COUNT(*) FROM leads WHERE contact_form_url != ''"
        ).fetchone()[0]
        avg_score = self.conn.execute(
            "SELECT AVG(confidence_score) FROM leads"
        ).fetchone()[0] or 0

        return {
            "total_leads": total,
            "launch_ready": launch_ready,
            "with_email": with_email,
            "with_contact_form": with_form,
            "avg_score": round(avg_score, 1),
        }
