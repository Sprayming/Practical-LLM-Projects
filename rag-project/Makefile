.PHONY: setup dev lint test clean

setup:                   ## 初始化开发环境
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1

dev:                     ## 启动后端开发服务器
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1

lint:                    ## 运行代码检查
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/lint.ps1

test:                    ## 运行测试
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1

clean:                   ## 清理运行时文件
	rm -rf backend/uploads/*
	rm -rf backend/chroma_db/*
	rm -rf backend/**/__pycache__
	rm -rf backend/.venv
	rm -rf frontend/node_modules
