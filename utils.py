import sqlite3
from datetime import datetime
from typing import List, Dict, Optional

import requests

from config import BITRIX_URL, BITRIX_WEBHOOK_KEY


class HistoryManager:
    """
    Управление историей диалога через SQLite.
    """

    def __init__(self, db_path: str = "database.sqlt", max_history_length: int = 10):
        self.db_path = db_path
        self.max_history = max_history_length

        self.conn: sqlite3.Connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor: sqlite3.Cursor = self.conn.cursor()

    def get_history(self, peer_id: int) -> List[Dict[str, str]]:
        """
        Возвращает список реплик для данного диалога (peer_id):
          [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."},
            ...
          ]
        Возвращает не более max_history последних записей (в порядке вставки).
        """
        self.cursor.execute("""
            SELECT role, content
            FROM dialog_history
            WHERE peer_id = ?
            ORDER BY id ASC
            LIMIT ?
        """, (peer_id, self.max_history))
        rows = self.cursor.fetchall()

        history = [{"role": row[0], "content": row[1]} for row in rows]
        return history

    def add_message(self, peer_id: int, message: Dict[str, str]):
        role = message["role"]
        content = message["content"]

        # Обёртка in-transaction: автоматически BEGIN/COMMIT
        with self.conn:
            # Вставляем новую запись
            self.conn.execute(
                "INSERT INTO dialog_history(peer_id, role, content) VALUES (?, ?, ?)",
                (peer_id, role, content)
            )

            # Считаем, сколько записей стало
            total_count = self.conn.execute(
                "SELECT COUNT(*) FROM dialog_history WHERE peer_id = ?",
                (peer_id,)
            ).fetchone()[0]

            if total_count > self.max_history:
                overflow = total_count - self.max_history
                # Удаляем старые записи в одной транзакции
                self.conn.execute("""
                    DELETE FROM dialog_history
                    WHERE id IN (
                        SELECT id FROM dialog_history
                        WHERE peer_id = ?
                        ORDER BY id ASC
                        LIMIT ?
                    )
                """, (peer_id, overflow))

    def get_last_user_timestamp(self, peer_id: int) -> Optional[datetime]:
        self.cursor.execute("""
            SELECT timestamp
            FROM dialog_history
            WHERE peer_id = ? AND role = 'user'
            ORDER BY id DESC
            LIMIT 1
        """, (peer_id,))
        row = self.cursor.fetchone()
        if row:
            return datetime.fromisoformat(row[0])
        return None

    def get_stage(self, peer_id: int) -> int:
        self.cursor.execute("""
            SELECT stage
            FROM reminder_status
            WHERE peer_id = ?
        """, (peer_id,))
        row = self.cursor.fetchone()
        return row[0] if row else 0

    def set_stage(self, peer_id: int, stage: int):
        """
        Устанавливает этап напоминаний для peer_id. stage ∈ {0, 1, 2}.
        """
        self.cursor.execute(
            "SELECT 1 FROM reminder_status WHERE peer_id = ?",
            (peer_id,)
        )
        exists = self.cursor.fetchone() is not None

        if not exists:
            self.cursor.execute(
                "INSERT INTO reminder_status (peer_id, stage) VALUES (?, ?)",
                (peer_id, stage)
            )
        else:
            self.cursor.execute(
                "UPDATE reminder_status SET stage = ? WHERE peer_id = ?",
                (stage, peer_id)
            )

        self.conn.commit()

    def reset_stage(self, peer_id: int):
        self.cursor.execute("""
            DELETE FROM reminder_status
            WHERE peer_id = ?
        """, (peer_id,))
        self.conn.commit()

    def close(self):
        self.conn.close()

    def in_blacklist(self, peer_id: int) -> bool:
        self.cursor.execute("""
        SELECT * FROM blacklist WHERE peer_id = ?""", (peer_id,))
        exists = self.cursor.fetchone() is not None
        return exists

    def put_in_blacklist(self, peer_id: int, reason: str):
        self.cursor.execute("""
        INSERT INTO blacklist (peer_id, reason) VALUES (?, ?)""", (peer_id, reason))

        self.cursor.execute("""
                DELETE FROM dialog_history WHERE peer_id = ?""", (peer_id,))

        self.cursor.execute("""
        DELETE FROM reminder_status WHERE peer_id = ?""", (peer_id,))

        self.conn.commit()


def create_bitrix_request(name: str):
    import requests

    url = f'https://{BITRIX_URL}/rest/1/{BITRIX_WEBHOOK_KEY}/crm.deal.add.json'

    params = {
        'fields[TITLE]': name,
        'fields[STAGE_ID]': 'NEW'
    }

    response = requests.post(url, params=params)

    # data = response.json()
    # print(data)
