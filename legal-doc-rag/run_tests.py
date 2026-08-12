#!/usr/bin/env python
"""
run_tests.py —— Legal-DOC-RAG 项目测试用例执行入口

【作用与功能】
封装并运行项目 pytest 测试套件，并生成覆盖率报告（终端 + HTML）。
默认跳过标记为 evaluation 的测试，便于仅跑核心功能测试。

【主要组成】
- `run_tests`：以子进程方式调用 pytest，开启覆盖率统计并输出报告。
- `main`：脚本入口，将测试退出码透传给进程退出码。

【适用场景】
- 场景1：本地执行 `python run_tests.py` 跑全部核心测试
- 场景2：CI 流水线中作为测试阶段命令，依据退出码判定通过/失败

【依赖关系】
- 依赖 pytest 及 pytest-cov 插件
- 测试目录约定为项目根目录下的 `tests/`，代码覆盖范围约定为 `app`
"""
import subprocess
import sys
import os


def run_tests():
    """运行 pytest 测试套件并生成覆盖率报告。

    通过子进程调用 pytest，对 `tests/` 目录执行详细模式测试，
    统计 `app` 包的代码覆盖率，并跳过标记为 evaluation 的测试。

    参数:
        无
    返回:
        int: pytest 进程的退出码（0 表示全部通过，非 0 表示存在失败用例）
    适用场景:
        - 作为 `python run_tests.py` 的被测主体，统一测试执行方式
        - 在 CI 中依据返回码判定流水线是否继续
    """
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