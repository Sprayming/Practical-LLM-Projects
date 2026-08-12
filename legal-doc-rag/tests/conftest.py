"""
conftest.py —— legal-doc-rag 项目的 pytest 全局配置与共享固定装置 (fixtures)。

【测试覆盖范围】
- 重型/可选依赖惰性桩:注册 MetaPathFinder，对当前环境「未安装」的 chromadb、
  paddleocr、bs4、sentence_transformers 等重型/可选包动态返回 MagicMock 桩，
  保证单元测试在干净环境(CI / 未安装重型依赖)下也能秒级通过；已真实安装的
  包不受影响(真实环境优先)。
- 共享 fixture:project_root(项目根目录)、temp_dir(临时目录)、mock_config
  (模拟配置模块)、mock_redis(模拟 Redis)、mock_chroma(模拟 ChromaDB)、
  mock_llm(模拟 LLM HTTP 调用)、sample_document / sample_query / sample_user
  (示例数据)、authenticated_headers(带 JWT 的认证头)，供各 unit 测试复用。

【适用场景】
- 由 pytest 自动加载，为 app.* 各模块的单元/接口测试提供运行环境与依赖模拟。

【依赖】
- 依赖 pytest、unittest.mock；并对 app.core.config、app.memory.redis_client、
  app.retrieval.hybrid_retriever、httpx 等模块做 patch。
"""
import sys
import importlib
import importlib.abc
import importlib.machinery
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# 重型 / 可选依赖的「惰性桩」:
#   项目在导入阶段就会拉起 chromadb / paddleocr / bs4 等重型或可选依赖。
#   为了让单元测试在「未安装这些重型依赖」的干净环境(CI / 面试官 clone)下
#   也能秒级通过，这里注册一个 MetaPathFinder:对当前环境中「未安装」的包
#   及其任意子模块，动态返回一个 MagicMock 桩。
#   已真实安装的包(如 langchain_chroma)不受影响——真实环境优先。
# ---------------------------------------------------------------------------
_HEAVY_OPTIONAL = (
    "sentence_transformers", "paddleocr", "pandas", "prometheus_client",
    "pdfplumber", "PyPDF2", "fitz", "bs4", "chromadb",
    "langchain_chroma", "langchain_community",
)


class _LazyStubLoader(importlib.abc.Loader):
    """
    为桩包返回一个 MagicMock 模块；子模块按需递归创建。
    
    这个加载器的作用是:
    1. 当导入未安装的包时，返回一个 MagicMock
    2. 支持 多级导入(from X.sub import Y)
    3. 保持模块的包特性
    """

    def create_module(self, spec):
        """创建模块"""
        mod = sys.modules.get(spec.name)
        if mod is None:
            mod = MagicMock()
            mod.__path__ = []            # 当作包，支持多级导入
            mod.__spec__ = spec
            sys.modules[spec.name] = mod
        return mod

    def exec_module(self, module):
        """执行模块(空实现)"""
        return None


class _LazyStubFinder(importlib.abc.MetaPathFinder):
    """
    惰性桩查找器
    
    作用:
    1. 拦截未安装包的导入
    2. 返回桩加载器
    3. 不影响已安装的包
    """
    def __init__(self, names):
        self.names = set(names)

    def find_spec(self, fullname, path, target=None):
        """查找模块规范"""
        # 检查是否是我们要桩化的包
        if fullname.split(".")[0] not in self.names:
            return None
        # 如果模块已存在(真实模块或已桩)，交给默认机制
        if fullname in sys.modules:
            return None
        # 返回桩加载器的规范
        return importlib.machinery.ModuleSpec(fullname, _LazyStubLoader(), is_package=True)


# 收集需要桩化的包名
_stub_names = []
for _n in _HEAVY_OPTIONAL:
    try:
        importlib.import_module(_n)
    except Exception:
        _stub_names.append(_n)

# 如果有需要桩化的包，注册查找器
if _stub_names:
    sys.meta_path.insert(0, _LazyStubFinder(set(_stub_names)))

# 导入 pytest 和其他测试工具
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

# 添加项目根目录到 Python 路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def project_root():
    """
    返回项目根目录
    
    返回:
        Path: 项目根目录的 Path 对象
    """
    return Path(__file__).parent.parent


@pytest.fixture
def temp_dir():
    """
    创建临时目录用于测试文件
    
    返回:
        str: 临时目录路径
    """
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_config():
    """
    模拟配置模块
    
    返回:
        Mock: 模拟的配置模块
    """
    with patch("app.core.config") as mock:
        # 设置各种配置项的默认值
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
    """
    模拟 Redis 客户端
    
    返回:
        Mock: 模拟的 Redis 客户端
    """
    with patch("app.memory.redis_client.Redis") as mock:
        client = Mock()
        client.get.return_value = None
        client.set.return_value = True
        client.delete.return_value = True
        mock.return_value = client
        yield client


@pytest.fixture
def mock_chroma():
    """
    模拟 ChromaDB 客户端
    
    返回:
        Mock: 模拟的 ChromaDB 客户端
    """
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
    """
    模拟 LLM API 调用
    
    返回:
        Mock: 模拟的 LLM 客户端
    """
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
    """
    测试用示例文档
    
    返回:
        dict: 示例文档数据
    """
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
    """
    测试用示例查询
    
    返回:
        dict: 示例查询数据
    """
    return {
        "query": "What is the penalty for breach of contract?",
        "tenant_id": "test-tenant",
        "user_id": "test-user"
    }


@pytest.fixture
def sample_user():
    """
    测试用示例用户
    
    返回:
        dict: 示例用户数据
    """
    return {
        "username": "testuser",
        "password": "testpass123",
        "role": "user"
    }


@pytest.fixture
def authenticated_headers():
    """
    带认证头的请求头
    
    返回:
        dict: 包含 JWT token 的请求头
    """
    return {
        "Authorization": "Bearer test-jwt-token"
    }
