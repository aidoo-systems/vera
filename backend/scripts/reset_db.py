from __future__ import annotations

import os
import shutil


def main() -> None:
    sqlite_path = os.getenv("SQLITE_PATH", "./data/vera.db")
    data_dir = os.path.dirname(sqlite_path) or "./data"

    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)

    os.makedirs(data_dir, exist_ok=True)
    print(f"Reset database directory at {data_dir}")


if __name__ == "__main__":
    main()
