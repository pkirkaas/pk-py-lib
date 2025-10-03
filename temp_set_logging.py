import sqlite3
from pathlib import Path
from src.pk_py_lib.core import get_data_dir

# Path to settings DB
data_dir = get_data_dir()
settings_db = data_dir / "settings.db"

# Connect and update
conn = sqlite3.connect(settings_db)
try:
    conn.execute("UPDATE app_settings SET logging_to_user_dir = 0")
    conn.commit()
    print("Updated logging_to_user_dir to False")
finally:
    conn.close()