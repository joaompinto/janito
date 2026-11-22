# Janito Web UI — Docker image
#
# Builds a minimal image that runs the browser chat (`janito --web`)
# listening on port 9090.
#
#   docker build -t janito:local .
#   docker run --rm -p 9090:9090 \
#     -e JANITO_WEB_TOKEN=secret \
#     -v janito-config:/home/appuser/.janito \
#     janito:local
#
# Then open http://localhost:9090
#
# Set JANITO_WEB_PORT to listen on a different port (remember to publish the
# same port, e.g. -e JANITO_WEB_PORT=8080 -p 8080:8080).
#
# Config, auth and chat history live under /home/appuser/.janito (a VOLUME).
# JANITO_SESSIONS_DIR points the session store there so history survives
# container recreation instead of being written to the read-only /app.
#
# The container binds 0.0.0.0 (the CLI default 127.0.0.1 is unreachable
# from outside a container) and never tries to open a browser.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    JANITO_WEB_PORT=9090 \
    JANITO_SESSIONS_DIR=/home/appuser/.janito/sessions

WORKDIR /app

# Version stamp for setuptools_scm (the build has no .git directory,
# so the version cannot be inferred from tags). The release workflow
# passes --build-arg VERSION=<tag without leading v>.
ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}

# Install dependencies first (better layer caching): project metadata
# plus the package itself, with the [web] extra (fastapi/uvicorn).
COPY pyproject.toml README.md ./
COPY janito ./janito
RUN pip install --upgrade pip && \
    pip install ".[web]"

# Run as non-root; config/auth/sessions live in ~/.janito (/home/appuser/.janito).
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /home/appuser/.janito && \
    chown -R appuser:appuser /home/appuser/.janito
USER appuser

VOLUME ["/home/appuser/.janito"]

EXPOSE 9090

# /health is deliberately outside /api so it stays reachable without the
# bearer token when JANITO_WEB_TOKEN is set.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/health' % os.environ.get('JANITO_WEB_PORT', '9090'))"

LABEL org.opencontainers.image.source="https://github.com/joaompinto/janito" \
      org.opencontainers.image.description="Janito Web UI (janito --web) on port 9090" \
      org.opencontainers.image.licenses="MIT"

# 0.0.0.0 is required inside containers; --no-web-open avoids a browser
# launch attempt. The port comes from JANITO_WEB_PORT (default 9090 here,
# 8080 outside the image).
CMD ["janito", "--web", "--web-host", "0.0.0.0", "--no-web-open"]
