"""
Pytest configuration and fixtures for Legal-DOC-RAG tests.
"""
import sys
import importlib
import importlib.abc
import importlib.machinery
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# 重型 / 可选依赖的「惰性桩」：
#   项目在导入阶段就会拉起 chromadb / paddleocr / bs4 等重型或可选依赖。
#   为了让单元测试在「未安装这些重型依赖」的干净环境（CI / 面试官 clone）下
#   也能秒级通过，这里注册一个 MetaPathFinder：对当前环境中「未安装」的包
#   及其任意子模块，动态返回一个 MagicMock 桩。
#   已真实安装的包（如 langchain_chroma）不受影响——真实环境优先。
# ---------------------------------------------------------------------------
_HEAVY_OPTIONAL = (
    "sentence_transformers", "paddleocr", "pandas", "prometheus_client",
    "pdfplumber", "PyPDF2", "fitz", "bs4", "chromadb",
    "langchain_chroma", "langchain_community",
)


class _LazyStubLoader(importlib.abc.Loader):
    """为桩包返回一个 MagicMock 模块；子模块按需递归创建。"""

    def create_module(self, spec):
        mod = sys.modules.get(spec.name)
        if mod is None:
            mod = MagicMock()
            mod.__path__ = []            # 当作包，支持多级导入 `from X.sub import Y`
            mod.__spec__ = spec
            sys.modules[spec.name] = mod
        return mod

    def exec_module(self, module):
        return None


class _LazyStubFinder(importlib.abc.MetaPathFinder):
    def __init__(self, names):
        self.names = set(names)

    def find_spec(self, fullname, path, target=None):
        if fullname.split(".")[0] not in self.names:
            return None
        if fullname in sys.modules:
            return None  # 已存在（真实模块或已桩），交给默认机制
        return importlib.machinery.ModuleSpec(fullname, _LazyStubLoader(), is_package=True)


_stub_names = []
for _n in _HEAVY_OPTIONAL:
    try:
        importlib.import_module(_n)
    except Exception:
        _stub_names.append(_n)

if _stub_names:
    sys.meta_path.insert(0, _LazyStubFinder(set(_stub_names)))

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def project_root():
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_config():
    """Mock the configuration module."""
    with patch("app.core.config") as mock:
        mock.LLM_API_KEY = "test-key"
        mock.LLM_BASE_URL = "http://localhost:8000"
        mock.LLM_MODEL = "test-model"
        mock.EMBEDDER_TYPE = "openai"
        mock.EMBEDDING_API_KEY = "test-key"
        mock.EMBEDDING_BASE_URL = "http://localhost:8000"
        mock.EMBEDDING_MODEL = "test-model"
        mock.CHROMA_PERSIST_DIR = tempfile.mkdtemp()
        mock.UPLOAD_DIR = tempfile.mkdtemp()
        mock.REDIS_URL = "redis://localhost:6379/0"
        mock.JWT_SECRET = "test-secret"
        mock.TENANT_DB = tempfile.mktemp(suffix=".db")
        yield mock


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch("app.memory.redis_client.Redis") as mock:
        client = Mock()
        client.get.return_value = None
        client.set.return_value = True
        client.delete.return_value = True
        mock.return_value = client
        yield client


@pytest.fixture
def mock_chroma():
    """Mock ChromaDB client."""
    with patch("app.retrieval.hybrid_retriever.chromadb") as mock:
        client = Mock()
        collection = Mock()
        collection.query.return_value = {
            "documents": [["test document"]],
            "metadatas": [[{"source": "test.pdf"}]],
            "distances": [[0.5]]
        }
        client.get_or_create_collection.return_value = collection
        mock.Client.return_value = client
        yield client


@pytest.fixture
def mock_llm():
    """Mock LLM API calls."""
    with patch("httpx.AsyncClient") as mock:
        client = Mock()
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}],
            "usage": {"total_tokens": 100}
        }
        client.post.return_value = response
        mock.return_value = client
        yield client


@pytest.fixture
def sample_document():
    """Sample document for testing."""
    return {
        "content": "This is a test legal document.",
        "metadata": {
            "source": "test.pdf",
            "page": 1,
            "tenant_id": "test-tenant"
        }
    }


@pytest.fixture
def sample_query():
    """Sample query for testing."""
    return {
        "query": "What is the penalty for breach of contract?",
        "tenant_id": "test-tenant",
        "user_id": "test-user"
    }


@pytest.fixture
def sample_user():
    """Sample user for testing."""
    return {
        "username": "testuser",
        "password": "testpass123",
        "role": "user"
    }


@pytest.fixture
def authenticated_headers():
    """Headers with JWT token for authenticated requests."""
    return {
        "Authorization": "Bearer test-jwt-token"
    }