#!/usr/bin/env python3
"""
Legal-DOC-RAG Backup & Recovery Script

Usage:
    python scripts/backup.py backup              # Create a full backup
    python scripts/backup.py backup --target <dir>  # Backup to specific directory
    python scripts/backup.py restore <backup_dir>   # Restore from backup
    python scripts/backup.py list                  # List available backups
    python scripts/backup.py cleanup --keep 5       # Keep only last N backups

Environment variables:
    BACKUP_DIR       - Where to store backups (default: ./backups)
    CHROMA_PERSIST_DIR - ChromaDB data directory (default: ./chroma_db)
    UPLOAD_DIR       - Uploaded files directory (default: ./uploads)
    MEMORY_DB_DIR    - Memory database directory (default: ./memory_db)
    TENANT_DB        - Tenant database path (default: ./tenant_data/users.db)
"""
import os
import sys
import shutil
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load config
from dotenv import load_dotenv
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(str(env_path))


# ============================================================
# Configuration
# ============================================================

BACKUP_DIR = os.getenv("BACKUP_DIR", str(PROJECT_ROOT / "backups"))
CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", str(PROJECT_ROOT / "chroma_db"))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(PROJECT_ROOT / "uploads"))
MEMORY_DB_DIR = os.getenv("MEMORY_DB_DIR", str(PROJECT_ROOT / "memory_db"))
TENANT_DB = os.getenv("TENANT_DB", str(PROJECT_ROOT / "tenant_data" / "users.db"))

# Directories/files to backup
BACKUP_TARGETS = {
    "chroma_db": CHROMA_DIR,
    "uploads": UPLOAD_DIR,
    "memory_db": MEMORY_DB_DIR,
    "tenant_data": os.path.dirname(TENANT_DB),
}


# ============================================================
# Backup
# ============================================================

def calculate_checksum(directory: str) -> str:
    """Calculate a quick checksum of a directory (file count + total size)."""
    total_size = 0
    file_count = 0
    for root, dirs, files in os.walk(directory):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total_size += os.path.getsize(fp)
                file_count += 1
            except OSError:
                pass
    return f"{file_count}_{total_size}"


def create_backup(target_dir: str = None) -> str:
    """Create a full backup of all data directories.

    Returns:
        Path to the created backup directory.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_base = target_dir or BACKUP_DIR
    backup_path = os.path.join(backup_base, f"backup_{timestamp}")
    os.makedirs(backup_path, exist_ok=True)

    manifest = {
        "timestamp": timestamp,
        "created_at": datetime.now().isoformat(),
        "sources": {},
    }

    for name, source_dir in BACKUP_TARGETS.items():
        if not os.path.exists(source_dir):
            logger.warning("Source not found, skipping: {} ({})", name, source_dir)
            continue

        dest = os.path.join(backup_path, name)
        logger.info("Backing up {} from {} ...", name, source_dir)

        try:
            shutil.copytree(source_dir, dest, dirs_exist_ok=True)
            checksum = calculate_checksum(source_dir)
            manifest["sources"][name] = {
                "source": source_dir,
                "checksum": checksum,
                "success": True,
            }
            logger.info("  ✓ {} backed up successfully", name)
        except Exception as e:
            logger.error("  ✗ {} backup failed: {}", name, e)
            manifest["sources"][name] = {
                "source": source_dir,
                "error": str(e),
                "success": False,
            }

    # Save manifest
    manifest_path = os.path.join(backup_path, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    logger.info("Backup completed: {}", backup_path)
    return backup_path


# ============================================================
# Restore
# ============================================================

def restore_backup(backup_dir: str) -> bool:
    """Restore data from a backup.

    Args:
        backup_dir: Path to the backup directory.

    Returns:
        True if successful.
    """
    backup_path = Path(backup_dir)
    if not backup_path.exists():
        logger.error("Backup directory not found: {}", backup_dir)
        return False

    manifest_path = backup_path / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        logger.info("Restoring backup from {}", manifest.get("created_at", "unknown"))
    else:
        logger.warning("No manifest found, attempting blind restore")

    for name, source_dir in BACKUP_TARGETS.items():
        src = backup_path / name
        if not src.exists():
            logger.warning("Backup source not found, skipping: {}", name)
            continue

        # Create target directory
        os.makedirs(source_dir, exist_ok=True)

        logger.info("Restoring {} to {} ...", name, source_dir)
        try:
            # For tenant_data, we only restore the DB file
            if name == "tenant_data":
                db_file = src / "users.db"
                if db_file.exists():
                    target_db = os.path.join(source_dir, "users.db")
                    shutil.copy2(str(db_file), target_db)
                    logger.info("  ✓ {} DB restored", name)
                else:
                    logger.warning("  ✗ users.db not found in backup")
            else:
                shutil.copytree(str(src), source_dir, dirs_exist_ok=True)
                logger.info("  ✓ {} restored successfully", name)
        except Exception as e:
            logger.error("  ✗ {} restore failed: {}", name, e)

    logger.info("Restore completed from: {}", backup_dir)
    return True


# ============================================================
# List & Cleanup
# ============================================================

def list_backups() -> list:
    """List all available backups."""
    if not os.path.exists(BACKUP_DIR):
        return []

    backups = []
    for name in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if name.startswith("backup_"):
            bp = os.path.join(BACKUP_DIR, name)
            manifest_path = os.path.join(bp, "manifest.json")
            info = {"name": name, "path": bp}

            if os.path.exists(manifest_path):
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                info["created_at"] = manifest.get("created_at", "unknown")
                info["sources"] = len(manifest.get("sources", {}))
            else:
                info["created_at"] = "unknown"

            backups.append(info)

    return backups


def cleanup_backups(keep: int = 5):
    """Remove old backups, keeping only the most recent N."""
    backups = list_backups()
    if len(backups) <= keep:
        logger.info("No cleanup needed ({} backups, keeping {})", len(backups), keep)
        return

    to_remove = backups[keep:]
    for b in to_remove:
        logger.info("Removing old backup: {}", b["name"])
        shutil.rmtree(b["path"], ignore_errors=True)

    logger.info("Cleanup done. Removed {} backups, kept {}", len(to_remove), keep)


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Legal-DOC-RAG Backup & Recovery")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # backup
    backup_parser = subparsers.add_parser("backup", help="Create a backup")
    backup_parser.add_argument("--target", help="Target directory for backup")

    # restore
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("backup_dir", help="Path to backup directory")

    # list
    subparsers.add_parser("list", help="List available backups")

    # cleanup
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old backups")
    cleanup_parser.add_argument("--keep", type=int, default=5, help="Number of backups to keep (default: 5)")

    args = parser.parse_args()

    if args.command == "backup":
        create_backup(target_dir=args.target)
    elif args.command == "restore":
        restore_backup(args.backup_dir)
    elif args.command == "list":
        backups = list_backups()
        if not backups:
            print("No backups found.")
        else:
            print(f"\n{'Name':<35} {'Created At':<25} {'Sources':<10}")
            print("-" * 70)
            for b in backups:
                print(f"{b['name']:<35} {b.get('created_at', 'N/A'):<25} {b.get('sources', 'N/A'):<10}")
            print(f"\nTotal: {len(backups)} backup(s)")
    elif args.command == "cleanup":
        cleanup_backups(keep=args.keep)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()