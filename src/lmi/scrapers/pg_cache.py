"""Cache scrapera w PostgreSQL (schemat scrape)."""
from __future__ import annotations

import json


class PgCache:
    def __init__(self, conn, source: str = "otodom"):
        self.conn = conn
        self.source = source

    def get_detail(self, ad_id: str) -> dict | None:
        if self.source == "otodom":
            row = self.conn.execute("SELECT detail FROM scrape.otodom_details WHERE ad_id = %s", (ad_id,)).fetchone()
        else:
            row = self.conn.execute("SELECT detail FROM scrape.portal_details WHERE source_id = %s AND ad_id = %s",
                                    (self.source, ad_id)).fetchone()
        return row[0] if row else None

    def put_detail(self, ad_id: str, slug: str, detail: dict) -> None:
        if self.source == "otodom":
            self.conn.execute(
                """INSERT INTO scrape.otodom_details (ad_id, slug, detail) VALUES (%s, %s, %s)
                   ON CONFLICT (ad_id) DO UPDATE SET detail = EXCLUDED.detail, slug = EXCLUDED.slug,
                                                     fetched_at = now()""",
                (ad_id, slug, json.dumps(detail)),
            )
        else:
            self.conn.execute(
                """INSERT INTO scrape.portal_details (source_id, ad_id, url, detail) VALUES (%s, %s, %s, %s)
                   ON CONFLICT (source_id, ad_id) DO UPDATE SET detail = EXCLUDED.detail, url = EXCLUDED.url,
                                                               fetched_at = now()""",
                (self.source, ad_id, slug, json.dumps(detail)),
            )
        self.conn.commit()  # zapis od razu: przerwany przebieg nie traci pobranych szczegółów

    def get_commune(self, key: str) -> tuple[str, str | None] | None:
        row = self.conn.execute("SELECT teryt, name FROM scrape.uldk_communes WHERE coord_key = %s", (key,)).fetchone()
        return (row[0], row[1]) if row else None

    def put_commune(self, key: str, teryt: str, name: str | None) -> None:
        self.conn.execute(
            """INSERT INTO scrape.uldk_communes (coord_key, teryt, name) VALUES (%s, %s, %s)
               ON CONFLICT (coord_key) DO NOTHING""",
            (key, teryt, name),
        )
        self.conn.commit()
