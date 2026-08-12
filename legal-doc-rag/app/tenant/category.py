"""
category.py —— Legal-DOC-RAG 文档分类管理

【作用与功能】
本模块提供文档分类（Category）的增删查，以及文档与分类的关联管理。分类
以 (tenant_id, name) 唯一约束实现租户隔离，文档（documents 表）通过
category_id 归属到某个分类，从而支撑按分类组织与检索文档。底层使用
users.db 的 document_categories / documents 两张表。

【主要组成】
- `_db_path`：users.db 路径
- `create_category` / `list_categories` / `delete_category`：分类 CRUD
- `set_document_category`：为文档设置/取消分类（不存在则插入文档记录）
- `get_document_category` / `list_documents_by_category`：分类与文档的查询

【适用场景】
- 场景1：用户在前台创建/管理文档分类体系
- 场景2：上传或整理文档时归类，便于后续按分类检索

【依赖关系】
- 上游调用方：分类管理路由、文档上传/检索接口
- 下游依赖：sqlite3、users.db（document_categories/documents 表）
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from loguru import logger


def _db_path() -> str:
    """返回 users.db 的磁盘路径（位于项目根的 tenant_data 目录）。

    参数:
        无

    返回:
        str: users.db 的绝对路径

    异常:
        无
    适用场景:
        - 所有分类/文档数据库操作前获取统一存储路径
    """
    base = Path(__file__).resolve().parent.parent.parent
    db_dir = base / "tenant_data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "users.db")


def create_category(tenant_id: str, name: str, description: str = None) -> Tuple[bool, str]:
    """创建新的文档分类。

    先查重 (tenant_id, name) 是否已存在，避免重复；通过则写入
    document_categories 表并返回成功。

    参数:
        tenant_id (str): 租户标识（隔离分类）
        name (str): 分类名称
        description (str, 可选): 分类描述

    返回:
        Tuple[bool, str]: (是否成功, 消息)

    异常:
        无（数据库错误被捕获并回滚）
    适用场景:
        - 用户新建文档分类
    """
    conn = sqlite3.connect(_db_path())
    try:
        # Check if category already exists
        cur = conn.execute(
            "SELECT id FROM document_categories WHERE tenant_id=? AND name=?",
            (tenant_id, name)
        )
        if cur.fetchone():
            return False, "分类已存在"

        conn.execute(
            "INSERT INTO document_categories (tenant_id, name, description) VALUES (?, ?, ?)",
            (tenant_id, name, description)
        )
        conn.commit()
        return True, "分类创建成功"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def list_categories(tenant_id: str) -> List[Dict]:
    """列出某租户下的全部文档分类。

    参数:
        tenant_id (str): 租户标识

    返回:
        List[Dict]: 含 id、name、description、created_at 的分类字典列表

    异常:
        无
    适用场景:
        - 前台展示分类树供选择
    """
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute(
            "SELECT id, name, description, created_at FROM document_categories WHERE tenant_id=?",
            (tenant_id,)
        )
        rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "created_at": row[3],
            }
            for row in rows
        ]
    finally:
        conn.close()


def delete_category(tenant_id: str, category_id: int) -> Tuple[bool, str]:
    """删除指定分类。

    先确认分类存在且属于该租户；删除前将归属该分类的文档 category_id 置空
    （解除归类但不删文档），随后删除分类记录。

    参数:
        tenant_id (str): 租户标识（权限校验）
        category_id (int): 待删除的分类 id

    返回:
        Tuple[bool, str]: (是否成功, 消息)

    异常:
        无（数据库错误被捕获并回滚）
    适用场景:
        - 用户删除不再需要的分类
    """
    conn = sqlite3.connect(_db_path())
    try:
        # Check if category exists
        cur = conn.execute(
            "SELECT id FROM document_categories WHERE tenant_id=? AND id=?",
            (tenant_id, category_id)
        )
        if not cur.fetchone():
            return False, "分类不存在"

        # Unset category for documents in this category
        conn.execute(
            "UPDATE documents SET category_id=NULL WHERE tenant_id=? AND category_id=?",
            (tenant_id, category_id)
        )

        # Delete category
        conn.execute(
            "DELETE FROM document_categories WHERE tenant_id=? AND id=?",
            (tenant_id, category_id)
        )
        conn.commit()
        return True, "分类删除成功"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def set_document_category(tenant_id: str, filename: str, category_id: int = None) -> Tuple[bool, str]:
    """为文档设置（或取消）分类。

    若提供了 category_id 先校验其存在；再查找文档记录——存在则更新其
    category_id，不存在则以 (tenant_id, filename, category_id) 插入一条文档
    记录。category_id 为 None 时表示取消归类。

    参数:
        tenant_id (str): 租户标识
        filename (str): 文档文件名
        category_id (int, 可选): 目标分类 id，None 表示取消归类

    返回:
        Tuple[bool, str]: (是否成功, 消息)

    异常:
        无（数据库错误被捕获并回滚）
    适用场景:
        - 上传/整理文档时归类到分类
    """
    conn = sqlite3.connect(_db_path())
    try:
        # Check if category exists (if provided)
        if category_id is not None:
            cur = conn.execute(
                "SELECT id FROM document_categories WHERE tenant_id=? AND id=?",
                (tenant_id, category_id)
            )
            if not cur.fetchone():
                return False, "分类不存在"

        # Check if document exists
        cur = conn.execute(
            "SELECT id FROM documents WHERE tenant_id=? AND filename=?",
            (tenant_id, filename)
        )
        row = cur.fetchone()

        if row:
            # Update existing document
            conn.execute(
                "UPDATE documents SET category_id=? WHERE tenant_id=? AND filename=?",
                (category_id, tenant_id, filename)
            )
        else:
            # Insert new document
            conn.execute(
                "INSERT INTO documents (tenant_id, filename, category_id) VALUES (?, ?, ?)",
                (tenant_id, filename, category_id)
            )

        conn.commit()
        return True, "文档分类设置成功"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def get_document_category(tenant_id: str, filename: str) -> Optional[Dict]:
    """获取某文档所属的分类。

    通过 LEFT JOIN 关联 documents 与 document_categories，按 (tenant_id, filename)
    查询；文档未归类时返回 None。

    参数:
        tenant_id (str): 租户标识
        filename (str): 文档文件名

    返回:
        Optional[Dict]: 含 id/name/description 的分类字典，或 None

    异常:
        无
    适用场景:
        - 展示文档当前所属分类
    """
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute(
            """SELECT c.id, c.name, c.description
               FROM documents d
               LEFT JOIN document_categories c ON d.category_id = c.id
               WHERE d.tenant_id=? AND d.filename=?""",
            (tenant_id, filename)
        )
        row = cur.fetchone()
        if row and row[0]:
            return {
                "id": row[0],
                "name": row[1],
                "description": row[2],
            }
        return None
    finally:
        conn.close()


def list_documents_by_category(tenant_id: str, category_id: int = None) -> List[Dict]:
    """列出文档，可按要求按分类过滤。

    返回该租户下（或指定分类下）的文档列表，每条含文件名、分类名称与分类
    id；未归类的文档其分类名显示为「未分类」。

    参数:
        tenant_id (str): 租户标识
        category_id (int, 可选): 仅返回该分类下的文档；省略则返回全部

    返回:
        List[Dict]: 含 filename、category_name、category_id 的字典列表

    异常:
        无
    适用场景:
        - 按分类浏览/检索文档
    """
    conn = sqlite3.connect(_db_path())
    try:
        if category_id is not None:
            cur = conn.execute(
                """SELECT d.filename, c.name, c.id
                   FROM documents d
                   LEFT JOIN document_categories c ON d.category_id = c.id
                   WHERE d.tenant_id=? AND d.category_id=?""",
                (tenant_id, category_id)
            )
        else:
            cur = conn.execute(
                """SELECT d.filename, c.name, c.id
                   FROM documents d
                   LEFT JOIN document_categories c ON d.category_id = c.id
                   WHERE d.tenant_id=?""",
                (tenant_id,)
            )

        rows = cur.fetchall()
        return [
            {
                "filename": row[0],
                "category_name": row[1] if row[1] else "未分类",
                "category_id": row[2],
            }
            for row in rows
        ]
    finally:
        conn.close()