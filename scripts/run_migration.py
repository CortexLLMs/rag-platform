"""Run SQL migrations against Supabase using the Management API.

Usage:
    python scripts/run_migration.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_TOKEN = os.getenv("SUPABASE_TOKEN", "")

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS public.chat_history (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    chatbot_id  TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS chat_history_session_idx
    ON public.chat_history(session_id);
"""


def run_migration() -> None:
    if not SUPABASE_URL or not SUPABASE_TOKEN:
        print("ERROR: Set SUPABASE_URL and SUPABASE_TOKEN in your .env file.")
        sys.exit(1)

    project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")

    api_url = f"https://api.supabase.com/v1/projects/{project_ref}/database/query"

    headers = {
        "Authorization": f"Bearer {SUPABASE_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {"query": MIGRATION_SQL}

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(api_url, headers=headers, json=payload)

        if response.status_code in (200, 201):
            print("Migration applied successfully – chat_history table created.")
        else:
            print(f"Migration failed ({response.status_code}): {response.text}")
            sys.exit(1)

    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
