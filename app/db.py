import json
import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from app.config import DATABASE_URL


logger = logging.getLogger(__name__)
_db_ready = False


def is_enabled() -> bool:
    return bool(DATABASE_URL)


@contextmanager
def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    with psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=3) as conn:
        yield conn


def init_db() -> None:
    global _db_ready

    if not DATABASE_URL:
        logger.warning("DATABASE_URL is not configured; chat history will stay in memory only.")
        return

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL DEFAULT 'New chat',
                        pinned BOOLEAN NOT NULL DEFAULT FALSE,
                        ingredients JSONB NOT NULL DEFAULT '[]'::jsonb,
                        recipes JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    ALTER TABLE chat_sessions
                    ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id BIGSERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                        content TEXT NOT NULL,
                        message_type TEXT,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
                    ON chat_messages(session_id, created_at, id)
                    """
                )
        _db_ready = True
    except Exception:
        _db_ready = False
        logger.exception("Could not initialize PostgreSQL chat history.")


def ready() -> bool:
    global _db_ready

    if not _db_ready:
        return False

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        _db_ready = False
        logger.exception("Lost PostgreSQL chat history connection.")
        return False


def _disable_on_error(action: str) -> None:
    global _db_ready
    _db_ready = False
    logger.exception("PostgreSQL chat history disabled after %s failed.", action)


def _is_ready_cached() -> bool:
    return _db_ready


def upsert_session(
    session_id: str,
    title: Optional[str] = None,
    ingredients: Optional[List[str]] = None,
    recipes: Optional[List[Dict[str, Any]]] = None,
    pinned: Optional[bool] = None,
) -> None:
    if not _is_ready_cached():
        return

    has_title = title is not None
    has_ingredients = ingredients is not None
    has_recipes = recipes is not None
    has_pinned = pinned is not None

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_sessions (id, title, pinned, ingredients, recipes)
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        title = CASE WHEN %s THEN EXCLUDED.title ELSE chat_sessions.title END,
                        pinned = CASE WHEN %s THEN EXCLUDED.pinned ELSE chat_sessions.pinned END,
                        ingredients = CASE WHEN %s THEN EXCLUDED.ingredients ELSE chat_sessions.ingredients END,
                        recipes = CASE WHEN %s THEN EXCLUDED.recipes ELSE chat_sessions.recipes END,
                        updated_at = NOW()
                    """,
                    (
                        session_id,
                        title or "New chat",
                        bool(pinned) if has_pinned else False,
                        json.dumps(ingredients if has_ingredients else []),
                        json.dumps(recipes if has_recipes else []),
                        has_title,
                        has_pinned,
                        has_ingredients,
                        has_recipes,
                    ),
                )
    except Exception:
        _disable_on_error("upsert_session")


def set_session_context(session_id: str, ingredients: List[str], recipes: List[Dict[str, Any]]) -> None:
    if not _is_ready_cached():
        return

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET ingredients = %s::jsonb,
                        recipes = %s::jsonb,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (json.dumps(ingredients), json.dumps(recipes), session_id),
                )
    except Exception:
        _disable_on_error("set_session_context")


def add_message(
    session_id: str,
    role: str,
    content: str,
    message_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    if not _is_ready_cached():
        return

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_messages (session_id, role, content, message_type, metadata)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    """,
                    (session_id, role, content, message_type, json.dumps(metadata or {})),
                )
                cur.execute(
                    "UPDATE chat_sessions SET updated_at = NOW() WHERE id = %s",
                    (session_id,),
                )
    except Exception:
        _disable_on_error("add_message")


def list_sessions() -> List[Dict[str, Any]]:
    if not _is_ready_cached():
        return []

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, pinned, ingredients, created_at, updated_at
                    FROM chat_sessions
                    ORDER BY pinned DESC, updated_at DESC, created_at DESC
                    """
                )
                return list(cur.fetchall())
    except Exception:
        _disable_on_error("list_sessions")
        return []


def get_messages(session_id: str) -> List[Dict[str, Any]]:
    if not _is_ready_cached():
        return []

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, role, content, message_type, metadata, created_at
                    FROM chat_messages
                    WHERE session_id = %s
                    ORDER BY created_at ASC, id ASC
                    """,
                    (session_id,),
                )
                return list(cur.fetchall())
    except Exception:
        _disable_on_error("get_messages")
        return []


def get_session_context(session_id: str) -> Optional[Dict[str, Any]]:
    if not _is_ready_cached():
        return None

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ingredients, recipes FROM chat_sessions WHERE id = %s",
                    (session_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {"ingredients": row["ingredients"] or [], "recipes": row["recipes"] or []}
    except Exception:
        _disable_on_error("get_session_context")
        return None


def delete_session(session_id: str) -> None:
    if not _is_ready_cached():
        return

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chat_sessions WHERE id = %s", (session_id,))
    except Exception:
        _disable_on_error("delete_session")


def update_session(
    session_id: str,
    title: Optional[str] = None,
    pinned: Optional[bool] = None,
) -> bool:
    if not _is_ready_cached():
        return False

    assignments = []
    params: List[Any] = []

    if title is not None:
        assignments.append("title = %s")
        params.append(title)

    if pinned is not None:
        assignments.append("pinned = %s")
        params.append(pinned)

    if not assignments:
        return False

    assignments.append("updated_at = NOW()")
    params.append(session_id)

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE chat_sessions SET {', '.join(assignments)} WHERE id = %s",
                    params,
                )
                return cur.rowcount > 0
    except Exception:
        _disable_on_error("update_session")
        return False
