format: py_format js_format

py_format:
	ruff check --fix

js_format:
	npm run format --prefix gui
