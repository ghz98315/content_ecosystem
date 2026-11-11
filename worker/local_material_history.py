"""Keep recent source order and cover choices beside the local library."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

FILENAME = '素材组合记录.sqlite3'


def _connect(root: Path):
    connection = sqlite3.connect(root / FILENAME, timeout=5)
    connection.execute('''CREATE TABLE IF NOT EXISTS combinations (
        revision TEXT PRIMARY KEY, category TEXT NOT NULL, task_id TEXT NOT NULL,
        clips TEXT NOT NULL, cover_source TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    return connection


def recent(root: Path, category: str) -> list[dict]:
    try:
        with closing(_connect(root)) as connection:
            rows = connection.execute('''SELECT clips, cover_source FROM combinations
                WHERE category = ? ORDER BY rowid DESC LIMIT 12''', (category,))
            return [{'clips': json.loads(clips), 'cover_source': cover} for clips, cover in rows]
    except (sqlite3.Error, ValueError) as exc:
        print(f'  [local-materials] 无法读取本地组合表：{exc}', flush=True)
        return []


def record(root: Path, category: str, task_id: str, revision: str, entries: list[dict], cover_source: str) -> None:
    clips = [{'id': item['asset']['id'], 'path': item['asset']['relative_path'],
              'start': round(item['source_start'], 2), 'end': round(item['source_end'], 2),
              'rate': item['playback_rate']} for item in entries]
    try:
        with closing(_connect(root)) as connection, connection:
            connection.execute('''INSERT OR IGNORE INTO combinations
                (revision, category, task_id, clips, cover_source) VALUES (?, ?, ?, ?, ?)''',
                (revision, category, task_id, json.dumps(clips, ensure_ascii=False), cover_source))
    except sqlite3.Error as exc:
        print(f'  [local-materials] 无法保存本地组合表：{exc}', flush=True)
