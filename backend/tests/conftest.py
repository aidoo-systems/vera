import os
from pathlib import Path

TEST_DATA_DIR = Path(__file__).resolve().parent / "test_data"
TEST_DATA_DIR.mkdir(exist_ok=True)

os.environ["DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["SQLITE_PATH"] = str(TEST_DATA_DIR / "vera_test.db")
