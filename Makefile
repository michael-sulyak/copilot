format: py_format js_format

py_format:
	ruff check --fix

js_format:
	npm run format --prefix gui

build_gui:
	npm run build --prefix gui

run_gui:
	npm run start --prefix gui

install_deps:
	npm install --prefix gui
	poetry install

run_server:
	poetry run python main.py

prepare: install_deps build_gui
	cp -r demo_configs configs

create_desktop_icon:
	@echo "Generating run.sh..."
	@printf "#!/bin/bash\n\ncd \"%s\" && make run_server\n" "$(CURDIR)" > run.sh
	@chmod +x ./run.sh

	@echo "Generating copilot_m.desktop..."
	@printf "[Desktop Entry]\nType=Application\nName=Copilot\nTerminal=false\nExec=\"%s/run.sh\"\nIcon=%s/gui/public/icon.png\n" "$(CURDIR)" "$(CURDIR)" > copilot_m.desktop

	@echo "Copying copilot_m.desktop to ~/.local/share/applications/..."
	@cp copilot_m.desktop ~/.local/share/applications/
	@chmod +x ~/.local/share/applications/copilot_m.desktop
	@echo "Desktop icon has been installed."

install: prepare create_desktop_icon
