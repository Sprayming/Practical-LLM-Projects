"""
Pytest configuration and fixtures for Legal-DOC-RAG tests.
"""
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