"""CLI Script for Safe Online SQLite Backup (uses sqlite3 .backup API)."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.ops_utils import backup_sqlite_database  # noqa: E402


if __name__ == "__main__":
    db_file = ROOT / "data" / "rental_intelligence.db"
    backup_dir = ROOT / "data" / "backups"
    result = backup_sqlite_database(db_file, backup_dir)
    print(json.dumps(result, indent=2))
