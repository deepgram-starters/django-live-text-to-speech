.PHONY: help init dev build

init:
	@echo "Initializing..."
	git submodule update --init --recursive
	python3 -m venv venv
	./venv/bin/pip install -r requirements.txt
	cd frontend && pnpm install
	@echo "Setup complete! Run 'make dev'"

dev:
	@echo "Starting development server..."
	./venv/bin/daphne -b 0.0.0.0 -p 8080 config.asgi:application

build:
	@echo "Building frontend..."
	cd frontend && pnpm build
	@echo "Build complete!"
