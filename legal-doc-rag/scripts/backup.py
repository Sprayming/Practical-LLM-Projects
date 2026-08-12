#!/usr/bin/env python3
"""
backup.py —— Legal-DOC-RAG 数据备份与恢复命令行工具。

【作用与功能】
本脚本负责项目"有状态数据"的整体备份与还原，是运维/交付环节的安全网。
它把系统运行期间产生、且无法通过重新部署恢复的四类数据目录整体复制到
带时间戳的备份目录中，并生成 manifest.json 清单记录本次备份的来源路径、
校验值与成功状态；恢复时按清单反向拷回原位置。

需要保护的四类数据:
- chroma_db    :ChromaDB 向量库(文档切片的向量索引，重建代价高、要重新跑 embedding)
- uploads      :用户上传的原始法律文档
- memory_db    :对话记忆数据库
- tenant_data  :多租户用户库 users.db(账号、密码哈希等)

【主要组成】
- `calculate_checksum`:快速计算目录指纹(文件数 + 总字节数)，用于粗粒度完整性比对
- `create_backup`:创建一次全量备份，逐目录拷贝并写出 manifest.json
- `restore_backup`:从指定备份目录恢复数据(tenant_data 只恢复 users.db 单文件)
- `list_backups`:列出备份根目录下所有 `backup_*` 备份及其创建时间
- `cleanup_backups`:按"保留最近 N 份"的策略删除过期备份，防止磁盘被占满
- `main`:argparse 子命令入口，提供 backup / restore / list / cleanup 四个命令

【适用场景】
- 场景1:上线或重大变更前做全量快照 —— `python scripts/backup.py backup`
- 场景2:备份到指定盘位/挂载目录 —— `python scripts/backup.py backup --target /mnt/nas/ldr`
- 场景3:数据损坏或误删后回滚 —— `python scripts/backup.py restore backups/backup_20260812_101500`
- 场景4:查看现有备份 —— `python scripts/backup.py list`
- 场景5:定时任务(cron / 计划任务)中做滚动清理 —— `python scripts/backup.py cleanup --keep 5`

【依赖关系】
- 标准库:os / sys / shutil / json / hashlib / argparse / pathlib / datetime
- 第三方库:loguru(日志输出)、python-dotenv(读取项目根目录 .env)
- 环境变量:BACKUP_DIR、CHROMA_PERSIST_DIR、UPLOAD_DIR、MEMORY_DB_DIR、TENANT_DB
  (均有默认值，未配置时回落到项目根目录下的同名子目录)
- 前置要求:执行账号需对源目录有读权限、对备份目录有写权限；
  恢复操作会覆盖现有数据，建议在服务停止状态下执行

--------------------------------------------------------------------
以下为原有英文用法说明(保留):

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
# 计算项目根目录(scripts/ 的上一级)，并插入 sys.path 首位，
# 保证脚本以 `python scripts/backup.py` 方式直接运行时也能 import 到 app 包。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load config
# 加载项目根目录的 .env，使下面的 os.getenv 能读到用户自定义的数据目录配置；
# .env 不存在时不报错，直接使用各配置项的默认值。
from dotenv import load_dotenv
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(str(env_path))


# ============================================================
# Configuration
# ============================================================

# 各路径均"环境变量优先、否则回落到项目根目录下的默认子目录"
BACKUP_DIR = os.getenv("BACKUP_DIR", str(PROJECT_ROOT / "backups"))            # 备份归档根目录
CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", str(PROJECT_ROOT / "chroma_db"))  # 向量库持久化目录
UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(PROJECT_ROOT / "uploads"))            # 用户上传原文件目录
MEMORY_DB_DIR = os.getenv("MEMORY_DB_DIR", str(PROJECT_ROOT / "memory_db"))    # 对话记忆库目录
TENANT_DB = os.getenv("TENANT_DB", str(PROJECT_ROOT / "tenant_data" / "users.db"))  # 租户/用户 DB 文件

# Directories/files to backup
# 备份清单:键为备份目录内的子目录名(也是恢复时的定位标识)，值为源目录绝对路径。
# 注意 tenant_data 配置的是 DB 文件路径，故这里取其所在目录(dirname)整体备份。
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
    """快速计算一个目录的轻量级校验指纹(文件总数 + 字节总大小)。

    Calculate a quick checksum of a directory (file count + total size).

    参数:
        directory (str): 待计算的目录绝对路径
    返回:
        str: 形如 "文件数_总字节数" 的指纹字符串，例如 "128_10485760"
    适用场景:
        - 备份时写入 manifest.json，事后可再次计算源目录指纹做粗粒度比对，
          快速判断数据规模是否发生明显变化
    说明:
        - 有意不做逐文件哈希:向量库动辄上 GB，全量哈希耗时过长；
          这里只需要"低成本、可比较"的指纹，而非密码学意义上的完整性校验
    """
    total_size = 0
    file_count = 0
    # 递归遍历目录下所有层级的文件
    for root, dirs, files in os.walk(directory):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total_size += os.path.getsize(fp)
                file_count += 1
            except OSError:
                # 文件可能在遍历过程中被删除、或存在权限/软链接失效问题，
                # 单个文件取大小失败不应中断整体统计，直接跳过
                pass
    return f"{file_count}_{total_size}"


def create_backup(target_dir: str = None) -> str:
    """对 BACKUP_TARGETS 中登记的全部数据目录做一次全量备份。

    Create a full backup of all data directories.

    参数:
        target_dir (str | None): 备份归档的父目录；传 None 时使用全局 BACKUP_DIR
    返回:
        str: 本次创建的备份目录绝对路径(形如 `<base>/backup_20260812_101500`)
    适用场景:
        - 上线、升级、批量导入文档等高风险操作前做快照
        - 由定时任务周期性调用，配合 `cleanup_backups` 实现滚动备份
    说明:
        - 单个目录备份失败不会中断整体流程，失败信息会记入 manifest["sources"]，
          便于事后判断该备份是否可用("部分成功"也会留下痕迹而非静默丢失)

    返回:
        Path to the created backup directory.
    """
    # 用秒级时间戳命名备份目录，保证多次备份互不覆盖且天然按时间排序
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_base = target_dir or BACKUP_DIR
    backup_path = os.path.join(backup_base, f"backup_{timestamp}")
    os.makedirs(backup_path, exist_ok=True)

    # 备份清单:记录本次备份的时间与每个数据源的来源路径、指纹、成功标志
    manifest = {
        "timestamp": timestamp,
        "created_at": datetime.now().isoformat(),
        "sources": {},
    }

    for name, source_dir in BACKUP_TARGETS.items():
        # 源目录不存在通常意味着该功能尚未使用过(如还没有人上传文档)，属正常情况，
        # 记一条 warning 后跳过，不视为备份失败
        if not os.path.exists(source_dir):
            logger.warning("Source not found, skipping: {} ({})", name, source_dir)
            continue

        dest = os.path.join(backup_path, name)
        logger.info("Backing up {} from {} ...", name, source_dir)

        try:
            # dirs_exist_ok=True:目标已存在时允许合并写入(Python 3.8+ 支持)，
            # 使同一备份目录可被重复写入而不抛 FileExistsError
            shutil.copytree(source_dir, dest, dirs_exist_ok=True)
            checksum = calculate_checksum(source_dir)
            manifest["sources"][name] = {
                "source": source_dir,
                "checksum": checksum,
                "success": True,
            }
            logger.info("  ✓ {} backed up successfully", name)
        except Exception as e:
            # 捕获全部异常(磁盘满、权限不足、文件被占用等)，
            # 把错误写进清单并继续备份剩余目录，避免"一个失败全部白做"
            logger.error("  ✗ {} backup failed: {}", name, e)
            manifest["sources"][name] = {
                "source": source_dir,
                "error": str(e),
                "success": False,
            }

    # Save manifest
    # 最后写出清单文件；ensure_ascii=False 保证中文路径可读，indent=2 便于人工查看
    manifest_path = os.path.join(backup_path, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    logger.info("Backup completed: {}", backup_path)
    return backup_path


# ============================================================
# Restore
# ============================================================

def restore_backup(backup_dir: str) -> bool:
    """从指定备份目录把数据恢复回各自的原始位置。

    Restore data from a backup.

    参数:
        backup_dir (str): 备份目录路径，例如 `backups/backup_20260812_101500`
    返回:
        bool: 备份目录存在并完成恢复流程返回 True；备份目录不存在返回 False
    适用场景:
        - 误删文档、向量库损坏、迁移到新机器后需要还原历史数据
    风险提示:
        - 恢复是**覆盖式**操作，会用备份内容覆盖当前同名文件，建议先停服再执行；
        - 返回 True 仅代表流程跑完，个别子目录恢复失败只会记 error 日志，
          需结合控制台输出确认每一项是否都打了 "✓"

    参数:
        backup_dir: Path to the backup directory.

    返回:
        True if successful.
    """
    backup_path = Path(backup_dir)
    # 前置校验:备份目录不存在直接返回 False，避免后续无意义的空操作
    if not backup_path.exists():
        logger.error("Backup directory not found: {}", backup_dir)
        return False

    manifest_path = backup_path / "manifest.json"
    if manifest_path.exists():
        # 有清单:读出来只为打印备份创建时间，让操作者确认恢复的是哪一份快照
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        logger.info("Restoring backup from {}", manifest.get("created_at", "unknown"))
    else:
        # 无清单(如手工拷贝的备份):降级为"盲恢复"，仅按固定子目录名尝试匹配
        logger.warning("No manifest found, attempting blind restore")

    # 以 BACKUP_TARGETS 为准反向遍历:备份目录内的子目录名 -> 恢复到对应的源路径
    for name, source_dir in BACKUP_TARGETS.items():
        src = backup_path / name
        # 该项在备份中不存在(备份时就跳过了)，恢复时同样跳过
        if not src.exists():
            logger.warning("Backup source not found, skipping: {}", name)
            continue

        # Create target directory
        # 目标目录可能已被整体删除，先补建出来再拷贝
        os.makedirs(source_dir, exist_ok=True)

        logger.info("Restoring {} to {} ...", name, source_dir)
        try:
            # For tenant_data, we only restore the DB file
            # 租户数据特殊处理:该目录里可能含运行期临时文件，只精确恢复 users.db 一个文件，
            # 避免把无关文件一并覆盖回去
            if name == "tenant_data":
                db_file = src / "users.db"
                if db_file.exists():
                    target_db = os.path.join(source_dir, "users.db")
                    shutil.copy2(str(db_file), target_db)
                    logger.info("  ✓ {} DB restored", name)
                else:
                    logger.warning("  ✗ users.db not found in backup")
            else:
                # 其余目录整体覆盖式回拷(同名文件被备份内容替换，多余的新文件保留)
                shutil.copytree(str(src), source_dir, dirs_exist_ok=True)
                logger.info("  ✓ {} restored successfully", name)
        except Exception as e:
            # 单项恢复失败不中断其他项，保证能尽量多恢复数据
            logger.error("  ✗ {} restore failed: {}", name, e)

    logger.info("Restore completed from: {}", backup_dir)
    return True


# ============================================================
# List & Cleanup
# ============================================================

def list_backups() -> list:
    """列出 BACKUP_DIR 下所有可用备份，按时间从新到旧排序。

    List all available backups.

    参数:
        无(读取全局 BACKUP_DIR)
    返回:
        list[dict]: 每个元素形如
            {"name": "backup_20260812_101500", "path": "<绝对路径>",
             "created_at": "ISO 时间或 unknown", "sources": 成功记录的数据源个数}
            备份根目录不存在时返回空列表
    适用场景:
        - `list` 子命令展示备份清单，供人工挑选恢复目标
        - 被 `cleanup_backups` 复用，作为"哪些备份该删"的判断依据
    """
    # 备份根目录还没建立(从未备份过)时直接返回空列表，交由调用方提示
    if not os.path.exists(BACKUP_DIR):
        return []

    backups = []
    # 目录名带秒级时间戳，字典序即时间序；reverse=True 让最新备份排在最前面，
    # 这也是 cleanup_backups 里能用切片 [keep:] 取"较旧备份"的前提
    for name in sorted(os.listdir(BACKUP_DIR), reverse=True):
        # 只认 backup_ 前缀的目录，忽略同目录下的其他无关文件
        if name.startswith("backup_"):
            bp = os.path.join(BACKUP_DIR, name)
            manifest_path = os.path.join(bp, "manifest.json")
            info = {"name": name, "path": bp}

            if os.path.exists(manifest_path):
                # 有清单:补充精确创建时间和数据源数量
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                info["created_at"] = manifest.get("created_at", "unknown")
                info["sources"] = len(manifest.get("sources", {}))
            else:
                # 无清单:仍然纳入列表(目录名本身含时间戳)，时间标记为 unknown
                info["created_at"] = "unknown"

            backups.append(info)

    return backups


def cleanup_backups(keep: int = 5):
    """删除过期备份，仅保留最近的 N 份。

    Remove old backups, keeping only the most recent N.

    参数:
        keep (int): 需要保留的最新备份份数，默认 5
    返回:
        None: 结果通过日志输出，无返回值
    适用场景:
        - 定时任务里紧跟 `backup` 之后执行，实现"滚动备份 + 自动回收磁盘"
    风险提示:
        - 这是**不可逆的删除**操作；keep 传得过小会丢掉历史快照，请谨慎设置
    """
    backups = list_backups()
    # 总数未超过保留额度，无需清理
    if len(backups) <= keep:
        logger.info("No cleanup needed ({} backups, keeping {})", len(backups), keep)
        return

    # list_backups 已按时间倒序，因此下标 >= keep 的都是较旧的、应被删除的备份
    to_remove = backups[keep:]
    for b in to_remove:
        logger.info("Removing old backup: {}", b["name"])
        # ignore_errors=True:个别文件被占用/权限不足时不抛异常，继续清理其余备份
        shutil.rmtree(b["path"], ignore_errors=True)

    logger.info("Cleanup done. Removed {} backups, kept {}", len(to_remove), keep)


# ============================================================
# CLI
# ============================================================

def main():
    """命令行入口:解析子命令并分派到对应的备份/恢复/查询/清理函数。

    参数:
        无(从 sys.argv 读取命令行参数)
    返回:
        None
    适用场景:
        - `python scripts/backup.py backup [--target DIR]`:创建全量备份
        - `python scripts/backup.py restore <backup_dir>`:从指定备份恢复
        - `python scripts/backup.py list`:表格化列出所有备份
        - `python scripts/backup.py cleanup [--keep N]`:仅保留最近 N 份备份
        - 不带任何子命令时打印帮助信息
    """
    parser = argparse.ArgumentParser(description="Legal-DOC-RAG Backup & Recovery")
    # dest="command" 把选中的子命令名存进 args.command，供下方分派使用
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # backup —— 创建备份，--target 为可选的自定义归档父目录
    backup_parser = subparsers.add_parser("backup", help="Create a backup")
    backup_parser.add_argument("--target", help="Target directory for backup")

    # restore —— 从备份恢复，backup_dir 为必填位置参数
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("backup_dir", help="Path to backup directory")

    # list —— 无额外参数，直接列出全部备份
    subparsers.add_parser("list", help="List available backups")

    # cleanup —— 清理旧备份，--keep 指定保留份数(默认 5)
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old backups")
    cleanup_parser.add_argument("--keep", type=int, default=5, help="Number of backups to keep (default: 5)")

    args = parser.parse_args()

    # 按子命令分派到具体处理函数
    if args.command == "backup":
        create_backup(target_dir=args.target)
    elif args.command == "restore":
        restore_backup(args.backup_dir)
    elif args.command == "list":
        backups = list_backups()
        if not backups:
            print("No backups found.")
        else:
            # 用固定列宽拼出对齐的表头与数据行，便于终端阅读
            print(f"\n{'Name':<35} {'Created At':<25} {'Sources':<10}")
            print("-" * 70)
            for b in backups:
                print(f"{b['name']:<35} {b.get('created_at', 'N/A'):<25} {b.get('sources', 'N/A'):<10}")
            print(f"\nTotal: {len(backups)} backup(s)")
    elif args.command == "cleanup":
        cleanup_backups(keep=args.keep)
    else:
        # 未提供子命令(args.command 为 None)时输出帮助，而不是静默退出
        parser.print_help()


if __name__ == "__main__":
    main()