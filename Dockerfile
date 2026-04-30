ARG PYTHON_VERSION=3.10

FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm AS build

# Copy from the cache instead of linking since it's a mounted volume
# Don't download isolated python builds
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=${PYTHON_VERSION} \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Install usb-dependencies
RUN apt -y update && apt -y install libusb-1.0-0

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Then, add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
ADD pyproject.toml uv.lock README.md /app/
ADD src /app/src
WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

CMD [ "connector", "start", "--app", "unitelabs.opentrons_ot2:create_app", "-vvv" ]
