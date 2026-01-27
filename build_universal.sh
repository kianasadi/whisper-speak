#!/bin/bash
# Build Viska as a Universal2 macOS app (Intel + Apple Silicon)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_VERSION="3.11.9"
PYTHON_FRAMEWORK="/Library/Frameworks/Python.framework/Versions/3.11"
VENV_DIR="$SCRIPT_DIR/.venv-universal"

echo "=== Viska Universal2 Build Script ==="
echo ""

# Check if universal2 Python is installed
check_universal_python() {
    if [ -f "$PYTHON_FRAMEWORK/bin/python3" ]; then
        ARCH=$(file "$PYTHON_FRAMEWORK/bin/python3" | grep -o "universal")
        if [ -n "$ARCH" ]; then
            echo "✓ Universal2 Python found at $PYTHON_FRAMEWORK"
            return 0
        fi
    fi
    return 1
}

# Install universal2 Python from python.org
install_universal_python() {
    echo "Downloading Python $PYTHON_VERSION universal2 installer..."
    PKG_URL="https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-macos11.pkg"
    PKG_FILE="/tmp/python-$PYTHON_VERSION-universal.pkg"

    curl -L -o "$PKG_FILE" "$PKG_URL"

    echo ""
    echo "Installing Python $PYTHON_VERSION (requires sudo)..."
    sudo installer -pkg "$PKG_FILE" -target /

    rm "$PKG_FILE"
    echo "✓ Python $PYTHON_VERSION universal2 installed"
}

# Create virtual environment with universal2 Python
create_venv() {
    echo ""
    echo "Creating virtual environment..."

    # Remove old venv if exists
    rm -rf "$VENV_DIR"

    # Create new venv with universal2 Python
    "$PYTHON_FRAMEWORK/bin/python3" -m venv "$VENV_DIR"

    echo "✓ Virtual environment created at $VENV_DIR"
}

# Install dependencies
install_deps() {
    echo ""
    echo "Installing dependencies..."

    source "$VENV_DIR/bin/activate"

    # Upgrade pip
    pip install --upgrade pip

    # Install dependencies with universal2 preference
    # numpy, scipy have universal2 wheels on PyPI
    pip install \
        "numpy>=1.24.0" \
        "scipy>=1.10.0" \
        "PyQt6>=6.4.0" \
        "sounddevice>=0.4.6" \
        "pynput>=1.7.6" \
        "openai>=1.0.0" \
        "python-dotenv>=1.0.0" \
        "pyinstaller>=6.0.0"

    echo "✓ Dependencies installed"
}

# Verify universal2 binaries
verify_universal() {
    echo ""
    echo "Verifying universal2 binaries..."

    source "$VENV_DIR/bin/activate"

    # Check key native libraries
    SITE_PACKAGES="$VENV_DIR/lib/python3.11/site-packages"

    echo "Checking numpy..."
    NUMPY_LIB=$(find "$SITE_PACKAGES/numpy" -name "*.so" | head -1)
    if [ -n "$NUMPY_LIB" ]; then
        file "$NUMPY_LIB" | grep -q "universal" && echo "  ✓ numpy: universal2" || echo "  ⚠ numpy: single arch (may still work)"
    fi

    echo "Checking scipy..."
    SCIPY_LIB=$(find "$SITE_PACKAGES/scipy" -name "*.so" | head -1)
    if [ -n "$SCIPY_LIB" ]; then
        file "$SCIPY_LIB" | grep -q "universal" && echo "  ✓ scipy: universal2" || echo "  ⚠ scipy: single arch (may still work)"
    fi
}

# Build the app
build_app() {
    echo ""
    echo "Building Viska.app..."

    source "$VENV_DIR/bin/activate"

    # Clean previous build
    rm -rf build dist

    # Build with PyInstaller
    pyinstaller viska.spec --clean

    echo ""
    echo "✓ Build complete!"

    # Verify the built binary
    echo ""
    echo "Verifying built binary architecture..."
    BINARY="dist/Viska.app/Contents/MacOS/Viska"
    if [ -f "$BINARY" ]; then
        file "$BINARY"

        # Check if it's actually universal
        if file "$BINARY" | grep -q "universal"; then
            echo ""
            echo "✓ SUCCESS: Viska.app is a universal2 binary!"
        else
            echo ""
            echo "⚠ WARNING: Binary may not be universal2. Check dependencies."
        fi
    fi
}

# Create distributable zip
create_zip() {
    echo ""
    echo "Creating distributable zip..."

    cd dist
    ZIP_NAME="Viska-$(grep CFBundleVersion ../viska.spec | grep -o '[0-9.]*')-macOS-universal.zip"
    rm -f "$ZIP_NAME"
    ditto -c -k --keepParent Viska.app "$ZIP_NAME"

    echo "✓ Created: dist/$ZIP_NAME"
    cd ..
}

# Main
main() {
    echo "Step 1: Checking for universal2 Python..."
    if ! check_universal_python; then
        echo ""
        echo "Universal2 Python not found."
        echo "This script will install Python $PYTHON_VERSION from python.org"
        echo ""
        read -p "Continue? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            install_universal_python
        else
            echo "Aborted. Install universal2 Python manually from:"
            echo "https://www.python.org/downloads/macos/"
            exit 1
        fi
    fi

    echo ""
    echo "Step 2: Creating virtual environment..."
    create_venv

    echo ""
    echo "Step 3: Installing dependencies..."
    install_deps

    echo ""
    echo "Step 4: Verifying universal2 support..."
    verify_universal

    echo ""
    echo "Step 5: Building app..."
    build_app

    echo ""
    echo "Step 6: Creating zip..."
    create_zip

    echo ""
    echo "=== Build Complete ==="
    echo "Output: dist/Viska.app"
    echo ""
    echo "To test on Intel Mac:"
    echo "  arch -x86_64 dist/Viska.app/Contents/MacOS/Viska"
}

main "$@"
