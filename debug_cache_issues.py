#!/usr/bin/env python3
"""
Debug script to examine flat_cache issues.
This script will help identify the root causes of the cache problems.
"""

import sqlite3
import os
from pathlib import Path
from pk_py_lib.core.flat_cache import FlatCacheManager
from pk_py_lib.core.logging.logger import get_logger

logger = get_logger(__name__)

def examine_cache_database(db_path: str = None):
    """Examine the cache database to identify issues."""
    if db_path is None:
        from src.pk_py_lib.core.utils import get_data_dir
        db_path = get_data_dir() / "flat_cache.db"

    print(f"=== Examining Cache Database: {db_path} ===")

    if not os.path.exists(db_path):
        print(f"Database file {db_path} does not exist!")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get total count
        cursor.execute("SELECT COUNT(*) FROM flat_cache_entries")
        total_count = cursor.fetchone()[0]
        print(f"Total entries in cache: {total_count}")

        # Check for directories/drives in cache
        cursor.execute("""
            SELECT path, size, mtime, xxh3, phash, whash, width, height
            FROM flat_cache_entries
            WHERE path LIKE '%/' OR path LIKE '%\\' OR path LIKE '%:%' OR size = 0
            ORDER BY path
            LIMIT 20
        """)
        suspicious_entries = cursor.fetchall()

        print(f"\n=== Suspicious Entries (directories/drives/empty files) ===")
        for entry in suspicious_entries:
            path, size, mtime, xxh3, phash, whash, width, height = entry
            print(f"Path: {path}")
            print(f"  Size: {size}, Mtime: {mtime}")
            print(f"  XXH3: {xxh3}, pHash: {phash}, wHash: {whash}")
            print(f"  Width: {width}, Height: {height}")
            print()

        # Check for files missing xxh3
        cursor.execute("""
            SELECT COUNT(*) FROM flat_cache_entries
            WHERE xxh3 IS NULL OR xxh3 = ''
        """)
        missing_xxh3_count = cursor.fetchone()[0]
        print(f"Entries missing XXH3: {missing_xxh3_count}")

        # Check for image files missing metadata
        cursor.execute("""
            SELECT COUNT(*) FROM flat_cache_entries
            WHERE (path LIKE '%.jpg' OR path LIKE '%.jpeg' OR path LIKE '%.png' OR path LIKE '%.gif' OR path LIKE '%.bmp' OR path LIKE '%.tiff' OR path LIKE '%.webp')
            AND (width IS NULL OR height IS NULL OR phash IS NULL OR whash IS NULL)
        """)
        missing_metadata_count = cursor.fetchone()[0]
        print(f"Image files missing metadata: {missing_metadata_count}")

        # Show sample of image files with missing metadata
        cursor.execute("""
            SELECT path, size, xxh3, phash, whash, width, height
            FROM flat_cache_entries
            WHERE (path LIKE '%.jpg' OR path LIKE '%.jpeg' OR path LIKE '%.png' OR path LIKE '%.gif' OR path LIKE '%.bmp' OR path LIKE '%.tiff' OR path LIKE '%.webp')
            AND (width IS NULL OR height IS NULL OR phash IS NULL OR whash IS NULL)
            ORDER BY path
            LIMIT 10
        """)
        missing_metadata_samples = cursor.fetchall()

        print(f"\n=== Sample Image Files Missing Metadata ===")
        for entry in missing_metadata_samples:
            path, size, xxh3, phash, whash, width, height = entry
            print(f"Path: {path}")
            print(f"  Size: {size}")
            print(f"  XXH3: {xxh3}, pHash: {phash}, wHash: {whash}")
            print(f"  Width: {width}, Height: {height}")
            print()

        # Show sample of regular files
        cursor.execute("""
            SELECT path, size, xxh3, phash, whash, width, height
            FROM flat_cache_entries
            WHERE path NOT LIKE '%/' AND path NOT LIKE '%\\' AND size > 0
            ORDER BY path
            LIMIT 10
        """)
        regular_entries = cursor.fetchall()

        print(f"\n=== Sample Regular File Entries ===")
        for entry in regular_entries:
            path, size, xxh3, phash, whash, width, height = entry
            print(f"Path: {path}")
            print(f"  Size: {size}")
            print(f"  XXH3: {xxh3}, pHash: {phash}, wHash: {whash}")
            print(f"  Width: {width}, Height: {height}")
            print()

        conn.close()

    except Exception as e:
        print(f"Error examining database: {e}")

def test_cache_manager():
    """Test the FlatCacheManager directly."""
    print("\n=== Testing FlatCacheManager ===")

    try:
        from src.pk_py_lib.core.utils import get_data_dir
        db_path = get_data_dir() / "flat_cache.db"
        cache_manager = FlatCacheManager(db_path=db_path)
        info = cache_manager.get_cache_info()
        print(f"Cache info: {info}")

        # Test getting an entry
        cursor = sqlite3.connect(str(db_path)).cursor()
        cursor.execute("SELECT path FROM flat_cache_entries LIMIT 1")
        result = cursor.fetchone()
        if result:
            test_path = result[0]
            entry = cache_manager.get_entry(test_path)
            if entry:
                print(f"\nSample entry for {test_path}:")
                print(f"  Path: {entry.path}")
                print(f"  Size: {entry.size}")
                print(f"  Mtime: {entry.mtime}")
                print(f"  XXH3: {entry.xxh3}")
                print(f"  pHash: {entry.phash}")
                print(f"  wHash: {entry.whash}")
                print(f"  Width: {entry.width}")
                print(f"  Height: {entry.height}")
                print(f"  Is Valid: {entry.is_valid}")
            else:
                print(f"No entry found for {test_path}")

    except Exception as e:
        print(f"Error testing cache manager: {e}")

if __name__ == "__main__":
    examine_cache_database()
    test_cache_manager()
