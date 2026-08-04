"""
Document Category Management for Legal-DOC-RAG.

Provides:
- Category CRUD operations
- Document classification
- Category-based search
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from loguru import logger


def _db_path() -> str:
    """返回 users.db 的路径"""
    base = Path(__file__).resolve().parent.parent.parent
    db_dir = base / "tenant_data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "users.db")


def create_category(tenant_id: str, name: str, description: str = None) -> Tuple[bool, str]:
    """
    Create a new document category.

    Args:
        tenant_id: Tenant ID
        name: Category name
        description: Optional description

    Returns:
        Tuple of (success, message)
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
    """
    List all categories for a tenant.

    Args:
        tenant_id: Tenant ID

    Returns:
        List of category dictionaries
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
    """
    Delete a category.

    Args:
        tenant_id: Tenant ID
        category_id: Category ID

    Returns:
        Tuple of (success, message)
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
    """
    Set category for a document.

    Args:
        tenant_id: Tenant ID
        filename: Document filename
        category_id: Category ID (None to unset)

    Returns:
        Tuple of (success, message)
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
    """
    Get category for a document.

    Args:
        tenant_id: Tenant ID
        filename: Document filename

    Returns:
        Category dictionary or None
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
    """
    List documents, optionally filtered by category.

    Args:
        tenant_id: Tenant ID
        category_id: Optional category ID to filter by

    Returns:
        List of document dictionaries
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