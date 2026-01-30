import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_CHAT_DB_PATH = "data/telebrief.db"


class ChatStorage:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("TELEBRIEF_CHAT_DB_PATH", DEFAULT_CHAT_DB_PATH)

    @contextmanager
    def _connection(self) -> Iterable[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        with self._connection() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS channels (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            try:
                conn.execute("ALTER TABLE channels ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT NOT NULL,
                    start_date TEXT,
                    end_date TEXT,
                    created_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_active ON chat_sessions(user_id, is_active)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_corpus_messages (
                    session_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    sender TEXT,
                    text TEXT NOT NULL,
                    link TEXT,
                    has_media INTEGER NOT NULL,
                    media_type TEXT,
                    PRIMARY KEY (session_id, message_id),
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_corpus_session_ts ON chat_corpus_messages(session_id, timestamp)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_turns_session_id ON chat_turns(session_id, id)"
            )

    def debug_info(self) -> Dict[str, Any]:
        return {
            "db_path": self.db_path,
        }

    def list_channels(self) -> List[Dict[str, str]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name
                FROM channels
                ORDER BY sort_order ASC, name COLLATE NOCASE
                """
            ).fetchall()

        return [{"id": str(r[0]), "name": str(r[1])} for r in rows]

    def upsert_channels(self, channels: Iterable[Tuple[str, str]]) -> int:
        inserted_or_updated = 0
        now = datetime.utcnow().isoformat()
        with self._connection() as conn:
            cur = conn.cursor()
            rows = []
            for sort_order, (channel_id, channel_name) in enumerate(channels):
                channel_id_str = str(channel_id).strip()
                channel_name_str = str(channel_name).strip()
                if not channel_id_str or not channel_name_str:
                    continue
                rows.append((channel_id_str, channel_name_str, now, sort_order))

            if not rows:
                return 0

            cur.executemany(
                """
                INSERT INTO channels (id, name, created_at, sort_order)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    sort_order = excluded.sort_order
                """,
                rows,
            )
            inserted_or_updated = cur.rowcount if cur.rowcount != -1 else 0

        return inserted_or_updated

    def add_channel(self, channel_id: str, channel_name: str) -> bool:
        channel_id_str = str(channel_id).strip()
        channel_name_str = str(channel_name).strip()
        if not channel_id_str or not channel_name_str:
            return False

        now = datetime.utcnow().isoformat()
        with self._connection() as conn:
            row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM channels").fetchone()
            sort_order = int(row[0]) if row else 0
            conn.execute(
                """
                INSERT INTO channels (id, name, created_at, sort_order)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name = excluded.name
                """,
                (channel_id_str, channel_name_str, now, sort_order),
            )
        return True

    def remove_channel(self, channel_id: str) -> bool:
        channel_id_str = str(channel_id).strip()
        if not channel_id_str:
            return False

        with self._connection() as conn:
            cur = conn.execute("DELETE FROM channels WHERE id = ?", (channel_id_str,))
            return bool(cur.rowcount and cur.rowcount > 0)

    def create_session(
        self,
        user_id: int,
        channel_id: str,
        channel_name: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> str:
        session_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        with self._connection() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                "UPDATE chat_sessions SET is_active = 0 WHERE user_id = ? AND is_active = 1",
                (user_id,),
            )
            conn.execute(
                """
                INSERT INTO chat_sessions (id, user_id, channel_id, channel_name, start_date, end_date, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    session_id,
                    user_id,
                    str(channel_id),
                    channel_name,
                    start_date.isoformat() if start_date else None,
                    end_date.isoformat() if end_date else None,
                    created_at,
                ),
            )
        return session_id

    def deactivate_active_session(self, user_id: int) -> None:
        with self._connection() as conn:
            conn.execute(
                "UPDATE chat_sessions SET is_active = 0 WHERE user_id = ? AND is_active = 1",
                (user_id,),
            )

    def get_active_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, channel_id, channel_name, start_date, end_date, created_at
                FROM chat_sessions
                WHERE user_id = ? AND is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "user_id": row[1],
            "channel_id": row[2],
            "channel_name": row[3],
            "start_date": row[4],
            "end_date": row[5],
            "created_at": row[6],
        }

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, channel_id, channel_name, start_date, end_date, created_at, is_active
                FROM chat_sessions
                WHERE id = ?
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "user_id": row[1],
            "channel_id": row[2],
            "channel_name": row[3],
            "start_date": row[4],
            "end_date": row[5],
            "created_at": row[6],
            "is_active": bool(row[7]),
        }

    def save_corpus_messages(self, session_id: str, messages: Iterable[Dict[str, Any]]) -> int:
        inserted = 0
        with self._connection() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cur = conn.cursor()
            rows: List[Tuple[Any, ...]] = []
            for msg in messages:
                rows.append(
                    (
                        session_id,
                        int(msg["message_id"]),
                        str(msg["timestamp"]),
                        msg.get("sender"),
                        msg.get("text") or "",
                        msg.get("link"),
                        1 if msg.get("has_media") else 0,
                        msg.get("media_type") or "",
                    )
                )

            cur.executemany(
                """
                INSERT OR REPLACE INTO chat_corpus_messages
                    (session_id, message_id, timestamp, sender, text, link, has_media, media_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            inserted += cur.rowcount if cur.rowcount != -1 else 0

        return inserted

    def count_corpus_messages(self, session_id: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COUNT(1) FROM chat_corpus_messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def iter_corpus_messages(
        self,
        session_id: str,
        batch_size: int = 200,
        order: str = "asc",
    ) -> Iterable[List[Dict[str, Any]]]:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")

        direction = "ASC" if str(order).strip().lower() == "asc" else "DESC"

        last_ts: Optional[str] = None
        last_id: Optional[int] = None

        with self._connection() as conn:
            while True:
                if last_ts is None or last_id is None:
                    rows = conn.execute(
                        f"""
                        SELECT message_id, timestamp, sender, text, link
                        FROM chat_corpus_messages
                        WHERE session_id = ?
                        ORDER BY timestamp {direction}, message_id {direction}
                        LIMIT ?
                        """,
                        (session_id, batch_size),
                    ).fetchall()
                else:
                    op = ">" if direction == "ASC" else "<"
                    rows = conn.execute(
                        f"""
                        SELECT message_id, timestamp, sender, text, link
                        FROM chat_corpus_messages
                        WHERE session_id = ?
                          AND (timestamp {op} ? OR (timestamp = ? AND message_id {op} ?))
                        ORDER BY timestamp {direction}, message_id {direction}
                        LIMIT ?
                        """,
                        (session_id, last_ts, last_ts, last_id, batch_size),
                    ).fetchall()

                if not rows:
                    break

                batch = [
                    {
                        "message_id": int(r[0]),
                        "timestamp": r[1],
                        "sender": r[2] or "Unknown",
                        "text": r[3] or "",
                        "link": r[4] or "#",
                    }
                    for r in rows
                ]
                last_ts = str(rows[-1][1])
                last_id = int(rows[-1][0])
                yield batch

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO chat_turns (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, datetime.utcnow().isoformat()),
            )

    def get_recent_turns(self, session_id: str, limit: int = 8) -> List[Dict[str, str]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM chat_turns
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        rows.reverse()
        return [{"role": str(r[0]), "content": str(r[1])} for r in rows]

    def _connect(self) -> sqlite3.Connection:
        db_path = self.db_path
        if db_path == ":memory:":
            db_path = "file:telebrief_memdb?mode=memory&cache=shared"
            conn = sqlite3.connect(db_path, timeout=30, uri=True)
            return conn

        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=30, uri=db_path.startswith("file:"))
        return conn
