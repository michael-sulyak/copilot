#!/bin/bash
set -e  # Exit on any error

##############################
# Configuration variables
##############################

APP_NAME="Copilot"
MAIN_SCRIPT="main.py"
EXTRA_DIRS=("app" "demo_configs" "gui/build" "scripts")
ICON_SRC="./gui/build/icon.png"
APPIMAGE_TOOL="./appimagetool-x86_64.AppImage"

# For PyInstaller, the data separator is ":" on Linux
SEP=":"

##############################
# Cleanup previous builds
##############################
echo "Cleaning previous builds..."
rm -rf build dist ${APP_NAME}.AppDir *.AppImage

##############################
# Install dependencies
##############################
echo "Installing dependencies..."
make install_deps

##############################
# Building frontend part
##############################
echo "Installing dependencies..."
make build_gui

##############################
# Build the executable using PyInstaller via Poetry
##############################
echo "Building executable with PyInstaller..."

# Construct --add-data parameters for each extra directory (if they exist)
ADD_DATA_PARAMS=""
for DIR in "${EXTRA_DIRS[@]}"; do
    if [ -d "${DIR}" ]; then
        # The format for --add-data is "source${SEP}destination"
        ADD_DATA_PARAMS+=" --add-data ${DIR}${SEP}${DIR}"
    else
        echo "Warning: Directory '${DIR}' not found; skipping."
    fi
done

# Run PyInstaller using poetry so it picks up the Poetry virtual environment
# The output executable will be named after the main script, so we strip the '.py'
poetry run pyinstaller --onedir ${MAIN_SCRIPT} ${ADD_DATA_PARAMS}

# Expected executable name (without .py extension)
EXECUTABLE_NAME="$(basename ${MAIN_SCRIPT} .py)"
EXECUTABLE_PATH="dist/${EXECUTABLE_NAME}/${EXECUTABLE_NAME}"

if [ ! -f "${EXECUTABLE_PATH}" ]; then
    echo "Error: Expected executable '${EXECUTABLE_PATH}' not found."
    exit 1
fi

##############################
# Create the AppDir structure
##############################
echo "Creating AppDir structure..."
APPDIR="${APP_NAME}.AppDir"
mkdir -p ${APPDIR}/usr/bin

##############################
# Copy the executable into AppDir
##############################
echo "Copying executable..."
# We rename the executable to a user-friendly name (here: myapp)
cp -r "dist/${EXECUTABLE_NAME}" ${APPDIR}/usr/bin/myapp

##############################
# Create the AppRun launcher script
##############################
echo "Creating AppRun script..."
cat <<'EOF' > ${APPDIR}/AppRun
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
cd "$HERE/usr/bin/myapp"
export USE_WEBVIEW=${USE_WEBVIEW:-1}
export LIBGL_ALWAYS_SOFTWARE=${LIBGL_ALWAYS_SOFTWARE:-1}
export INIT_CONFIGS_DIR=${INIT_CONFIGS_DIR:-./_internal/demo_configs}
export CONFIGS_DIR=${CONFIGS_DIR:-"$HOME/.config/copilot_m/"}
export STATICS_DIR=${STATICS_DIR:-./_internal/gui/build}
export TIKTOKEN_CACHE_DIR=${TIKTOKEN_CACHE_DIR:-"$HOME/.cache/copilot_m/tiktoken_cache"}
export LOG_FILE=${LOG_FILE:-}
exec "./main" "$@"
EOF
chmod +x ${APPDIR}/AppRun

##############################
# Create the desktop entry file
##############################
echo "Creating desktop entry..."
# The file name is the lowercase version of the application name
DESKTOP_FILE="${APPDIR}/${APP_NAME,,}.desktop"
cat <<EOF > ${DESKTOP_FILE}
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Exec=myapp
Icon=myapp
Categories=Utility;
EOF

##############################
# Copy the application icon
##############################
echo "Copying icon..."
if [ ! -f "${ICON_SRC}" ]; then
    echo "Error: Icon file '${ICON_SRC}' not found!"
    exit 1
fi
cp "${ICON_SRC}" ${APPDIR}/myapp.png

##############################
# Package the AppImage
##############################
echo "Building AppImage..."
wget https://github.com/AppImage/AppImageKit/releases/download/13/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
if [ ! -x "${APPIMAGE_TOOL}" ]; then
    echo "Error: appimagetool not found or not executable at '${APPIMAGE_TOOL}'"
    exit 1
fi

APPDIR_ABS="$(readlink -f ${APPDIR})"
echo "Building AppImage with AppDir at ${APPDIR_ABS}..."
${APPIMAGE_TOOL} "${APPDIR_ABS}"

##############################
# Cleanup temp files
##############################
echo "Cleaning previous builds..."
rm -rf build dist ${APP_NAME}.AppDir

echo "AppImage has been successfully created!"
