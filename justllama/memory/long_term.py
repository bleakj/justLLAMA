"""Persistent long-term memory with SQLite + FTS5 full-text search."""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


class LongTermMemory(QObject):
    """SQLite-backed persistent memory with FTS5 for full-text search.

    Schema:
        memories(id, content, category, created_at, accessed_at, access_count)

    Signals:
        memory_stored(str memory_id)
        memory_forgotten(str memory_id)
    """

    memory_stored = Signal(str)
    memory_forgotten = Signal(str)

    def __init__(self, db_path: str = "", parent=None):
        super().__init__(parent)
        self._db_path = db_path or str(
            Path.home() / ".local" / "share" / "justllama" / "memory.db"
        )
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with schema."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                created_at REAL NOT NULL,
                accessed_at REAL NOT NULL,
                access_count INTEGER DEFAULT 0
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content,
                category,
                content='memories',
                content_rowid='rowid'
            );

            -- Triggers to keep FTS in sync
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, category)
                VALUES (new.rowid, new.content, new.category);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category)
                VALUES ('delete', old.rowid, old.content, old.category);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category)
                VALUES ('delete', old.rowid, old.content, old.category);
                INSERT INTO memories_fts(rowid, content, category)
                VALUES (new.rowid, new.content, new.category);
            END;
        """)
        self._conn.commit()

    def _ensure_conn(self):
        """Re-initialize connection if it was closed."""
        if self._conn is None:
            self._init_db()

    @Slot(str, str, result=str)
    def store(self, content: str, category: str = "general") -> str:
        """Store a new memory.

        Args:
            content: Memory text content.
            category: Category label (e.g., "fact", "preference", "conversation").

        Returns:
            Memory ID.
        """
        self._ensure_conn()
        memory_id = str(uuid.uuid4())
        now = time.time()
        try:
            self._conn.execute(
                "INSERT INTO memories (id, content, category, created_at, accessed_at, access_count) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (memory_id, content, category, now, now),
            )
        except sqlite3.IntegrityError:
            # Collision — extremely unlikely with full UUID, but retry once
            memory_id = str(uuid.uuid4())
            self._conn.execute(
                "INSERT INTO memories (id, content, category, created_at, accessed_at, access_count) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (memory_id, content, category, now, now),
            )
        self._conn.commit()
        self.memory_stored.emit(memory_id)
        return memory_id

    @Slot(str, int, result=str)
    def search(self, query: str, limit: int = 5) -> str:
        """Full-text search over memories using FTS5.

        Args:
            query: Search query.
            limit: Max results.

        Returns:
            JSON string — list of memory dicts.
        """
        self._ensure_conn()
        import json

        try:
            rows = self._conn.execute(
                "SELECT m.id, m.content, m.category, m.created_at, m.accessed_at, m.access_count "
                "FROM memories m "
                "JOIN memories_fts f ON m.rowid = f.rowid "
                "WHERE memories_fts MATCH ? "
                "ORDER BY rank "
                "LIMIT ?",
                (query, limit),
            ).fetchall()

            results = []
            for row in rows:
                # Update access stats
                self._conn.execute(
                    "UPDATE memories SET accessed_at = ?, access_count = access_count + 1 WHERE id = ?",
                    (time.time(), row["id"]),
                )
                results.append({
                    "id": row["id"],
                    "content": row["content"],
                    "category": row["category"],
                    "created_at": row["created_at"],
                    "accessed_at": row["accessed_at"],
                    "access_count": row["access_count"] + 1,
                })
            self._conn.commit()
            return json.dumps(results)

        except sqlite3.OperationalError:
            # FTS match syntax error — fall back to LIKE search
            rows = self._conn.execute(
                "SELECT id, content, category, created_at, accessed_at, access_count "
                "FROM memories "
                "WHERE content LIKE ? "
                "ORDER BY accessed_at DESC "
                "LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
            return json.dumps([dict(row) for row in rows])

    @Slot(str, result=bool)
    def forget(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        self._ensure_conn()
        cursor = self._conn.execute(
            "DELETE FROM memories WHERE id = ?", (memory_id,)
        )
        self._conn.commit()
        if cursor.rowcount > 0:
            self.memory_forgotten.emit(memory_id)
            return True
        return False

    @Slot(result=int)
    def count(self) -> int:
        """Total number of stored memories."""
        self._ensure_conn()
        row = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return row[0]

    @Slot(str, result=str)
    def list_by_category(self, category: str) -> str:
        """List memories in a category."""
        self._ensure_conn()
        import json
        rows = self._conn.execute(
            "SELECT id, content, category, created_at, accessed_at, access_count "
            "FROM memories WHERE category = ? "
            "ORDER BY created_at DESC",
            (category,),
        ).fetchall()
        return json.dumps([dict(row) for row in rows])

    @Slot(result=list)
    def list_all(self) -> list[dict]:
        """List all memories."""
        self._ensure_conn()
        rows = self._conn.execute(
            "SELECT id, content, category, created_at, accessed_at, access_count "
            "FROM memories ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    @Slot(int, result=str)
    def list_recent(self, limit: int = 5) -> str:
        """Return the most recently created memories as JSON.

        Unlike ``search``, this does not run a full-text MATCH — it simply
        returns the newest memories, which is what prompt augmentation wants
        for "recent interactions" context.
        """
        self._ensure_conn()
        import json
        rows = self._conn.execute(
            "SELECT id, content, category, created_at, accessed_at, access_count "
            "FROM memories ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return json.dumps([dict(row) for row in rows])

    @Slot()
    def clear(self):
        """Delete all memories."""
        self._ensure_conn()
        self._conn.execute("DELETE FROM memories")
        self._conn.commit()

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
