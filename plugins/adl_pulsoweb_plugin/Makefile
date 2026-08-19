lint:
	flake8 src || exit;

lint-python: lint

format:
	black . --extend-exclude='/generated/' || exit;
