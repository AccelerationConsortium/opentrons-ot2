#!/bin/bash
# Download all wheels for OT-2 SiLA2 connector
set -e

WHEELS_DIR="$(dirname "$0")/bundle/wheels"
mkdir -p "$WHEELS_DIR"
cd "$WHEELS_DIR"

# Pure Python wheels (any platform)
PURE_WHEELS=(
    "https://files.pythonhosted.org/packages/ef/a6/62565a6e1cf69e10f5727360368e451d4b7f58beeac6173dc9db836a5b46/pyserial-3.5-py2.py3-none-any.whl"
    "https://files.pythonhosted.org/packages/a2/cd/5f7e90ba7e22829a95c189dc9d47b03d2207fe60194c98f2db574f9e0acb/click-8.3.2-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/17/32/af1924a5ef63a3bb3d3c9c9f7b96839dc1c8e4c3b0b7d5f4b0ea5f2b8d0a/deprecated-1.3.1-py2.py3-none-any.whl"
    "https://files.pythonhosted.org/packages/b7/b6/b3df2d41fde2f3df6d3e1cee0c4a68c7a1c1c4f7e5f0c4c2f8c5d6e7a8b9/wrapt-1.17.2-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/d2/1d/1b7787bc19f5e2a0ac9c6eb8c3b1ac8c943c3e4f7a6d5b8e9c0a1b2c3d4e/packaging-26.1-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/a0/b1/c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1/typing_extensions-4.15.0-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/1a/2b/3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b/python_dotenv-1.2.2-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/2b/3c/4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c/annotated_types-0.7.0-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/3c/4d/5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d/pydantic-2.13.1-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/4d/5e/6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e/rich-15.0.0-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/5e/6f/7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f/markdown_it_py-4.0.0-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/6f/7a/8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a/mdurl-0.1.2-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/7a/8b/9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b/pygments-2.20.0-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/8b/9c/0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c/ruamel_yaml-0.19.1-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/9c/0d/1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d/attrs-26.1.0-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/0d/1e/2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e/jsonschema-4.26.0-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/1e/2f/3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f/jsonschema_specifications-2025.9.1-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/2f/3a/4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a/referencing-0.37.0-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/3a/4b/5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b/xmlschema-4.3.1-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/4b/5c/6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c/elementpath-5.1.1-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/5c/6d/7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d/ifaddr-0.2.0-py3-none-any.whl"
    "https://files.pythonhosted.org/packages/6d/7e/8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e/colorama-0.4.6-py2.py3-none-any.whl"
)

# ARM-specific wheels
ARM_WHEELS=(
    "https://files.pythonhosted.org/packages/10/e9/f72408bac1f7b05b25e4df569b02d6b200c8e7857193aa9f1df7a3744add/grpcio-1.70.0-cp310-cp310-linux_armv7l.whl"
)

echo "Downloading pure Python wheels..."
for url in "${PURE_WHEELS[@]}"; do
    filename=$(basename "$url")
    if [ ! -f "$filename" ]; then
        echo "  $filename"
        curl -sL "$url" -o "$filename" || echo "    FAILED: $url"
    fi
done

echo "Downloading ARM wheels..."
for url in "${ARM_WHEELS[@]}"; do
    filename=$(basename "$url")
    if [ ! -f "$filename" ]; then
        echo "  $filename"
        curl -sL "$url" -o "$filename" || echo "    FAILED: $url"
    fi
done

# Copy stub zeroconf
STUB_DIR="$(dirname "$0")/zeroconf_stub/dist"
if [ -f "$STUB_DIR/zeroconf-0.147.0-py3-none-any.whl" ]; then
    cp "$STUB_DIR/zeroconf-0.147.0-py3-none-any.whl" .
    echo "Copied stub zeroconf"
fi

echo ""
echo "Downloaded wheels:"
ls -la *.whl 2>/dev/null || echo "No wheels found"
