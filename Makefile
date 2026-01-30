.PHONY: help install-hooks test lint clean

help:
	@echo "Available targets:"
	@echo "  make install-hooks  - Install git pre-commit hook to prevent token commits"
	@echo "  make test           - Run tests"
	@echo "  make lint           - Run linting"
	@echo "  make clean          - Clean build artifacts"

install-hooks:
	@echo "Installing pre-commit hook..."
	@mkdir -p .git/hooks
	@cp githooks/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "✓ Pre-commit hook installed successfully"
	@echo ""
	@echo "The hook will now scan staged files for tokens before each commit."
	@echo "To bypass: git commit --no-verify"

test:
	@echo "Running tests..."
	@python -m pytest tests/ -v

lint:
	@echo "Running linting..."
	@python -m pylint bridge.py --disable=C0111,C0103,R0913

clean:
	@echo "Cleaning build artifacts..."
	@rm -rf __pycache__/
	@rm -rf *.egg-info/
	@rm -rf .pytest_cache/
	@rm -rf .venv/
	@echo "✓ Clean complete"
