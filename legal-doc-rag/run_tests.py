#!/usr/bin/env python
"""
Run tests for Legal-DOC-RAG project.
"""
import subprocess
import sys
import os


def run_tests():
    """Run pytest with coverage."""
    print("Running tests for Legal-DOC-RAG...")
    
    # Ensure we're in the project directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Run pytest with coverage
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",
        "--tb=short",
        "--cov=app",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "-m", "not evaluation"  # Skip evaluation tests by default
    ]
    
    try:
        result = subprocess.run(cmd, check=True)
        print("\n✅ Tests passed!")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Tests failed with return code {e.returncode}")
        return e.returncode


if __name__ == "__main__":
    sys.exit(run_tests())