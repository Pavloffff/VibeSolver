FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

ARG GOOSE_VERSION=v3.29.0
ARG TARGETARCH

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /srv

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && case "${TARGETARCH}" in \
        arm64) goose_arch=arm64 ;; \
        *) goose_arch=x86_64 ;; \
    esac \
    && curl -fsSL "https://github.com/pressly/goose/releases/download/${GOOSE_VERSION}/goose_linux_${goose_arch}" -o /usr/local/bin/goose \
    && chmod +x /usr/local/bin/goose \
    && goose -version

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

COPY app ./app
COPY migrations ./migrations

ENTRYPOINT ["./entrypoint.sh"]
CMD ["api"]
