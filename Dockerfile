# The LinkGraph image for the homelab cluster. The laptop does not need it: start.sh runs on the
# host. No export, notes or logo cache goes in here; they live on the /data volume.
#
# Two stages on the same base. The builder makes the venv with uv; the runtime stage gets the venv
# and the source only, so uv and the build cache stay out of a public image. Tag and digest are
# both pinned; Dependabot moves them together.

FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS base

FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv

FROM base AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM base AS runtime

LABEL org.opencontainers.image.title="linkgraph" \
      org.opencontainers.image.description="Explore your LinkedIn export: who you know where, and warm paths in" \
      org.opencontainers.image.source="https://github.com/mortennordbye/linkgraph" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV=/opt/venv \
    LINKGRAPH_HOST=0.0.0.0 \
    LINKGRAPH_DATA_DIR=/data \
    LINKGRAPH_DOWNLOADS=/data/exports

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY linkgraph/ linkgraph/
COPY static/ static/

# Non-root. uid 1000 owns the files on the NFS volume, so it must match the pod's runAsUser.
# pip goes too: nothing installs at runtime, and its vendored packages only add scanner findings.
RUN useradd --create-home --uid 1000 linkgraph \
 && mkdir -p /data/exports \
 && chown -R linkgraph:linkgraph /data \
 && rm -rf /usr/local/lib/python3.*/site-packages/pip* /usr/local/bin/pip*
USER 1000

EXPOSE 8765

CMD ["python", "-m", "linkgraph.server", "--no-browser"]
