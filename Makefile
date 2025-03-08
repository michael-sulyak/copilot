format: py_format js_format

py_format:
	ruff check --fix

js_format:
	npm run format --prefix gui

build_gui:
	npm run build --prefix gui

run_gui:
	npm run start --prefix gui
