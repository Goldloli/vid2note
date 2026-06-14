.PHONY: help dev test test-unit test-integ test-e2e test-watch coverage lint typecheck golden package clean

help:
	@echo "vid2note 开发命令"
	@echo "  make dev          启动开发服务（hot reload）"
	@echo "  make test         跑所有测试"
	@echo "  make test-unit    只跑单元测试"
	@echo "  make test-integ   只跑集成测试"
	@echo "  make test-e2e     E2E（需先构建客户端）"
	@echo "  make coverage     生成覆盖率报告"
	@echo "  make lint         Lint"
	@echo "  make typecheck    类型检查"
	@echo "  make golden       跑 Golden 评估"
	@echo "  make package      打包客户端（mac arm64）"
	@echo "  make clean        清理产物"

dev:
	uv run uvicorn vid2note_server.main:app --reload --port 8765

test:
	uv run pytest core/tests/ server/tests/

test-unit:
	uv run pytest core/tests/unit/ -v

test-integ:
	uv run pytest server/tests/integration/ -v

test-e2e:
	cd desktop && npx playwright test

test-watch:
	uv run pytest-watch core/tests/

coverage:
	uv run pytest --cov=vid2note_core --cov=vid2note_server --cov-report=html
	open htmlcov/index.html

lint:
	uv run ruff check . && uv run ruff format --check .

typecheck:
	uv run mypy core/src/ server/src/

golden:
	uv run python scripts/eval_golden.py

package:
	./scripts/build_desktop.sh

clean:
	rm -rf htmlcov .coverage coverage.xml .pytest_cache .mypy_cache .ruff_cache
	rm -rf desktop/dist desktop/build
	find . -type d -name __pycache__ -exec rm -rf {} +
