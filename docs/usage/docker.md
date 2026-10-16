# Janito Web UI with Docker

The Janito repository ships a `Dockerfile` that runs the browser chat
(`janito --web`) on port **9090**, and every release publishes the image to
the GitHub Container Registry (GHCR) as `ghcr.io/joaompinto/janito`.

## Run a released image

```bash
docker run --rm -p 9090:9090 ghcr.io/joaompinto/janito:latest
# then open http://localhost:9090
```

Available tags per release: full version (`4.49.1`), `major.minor`
(`4.49`), and `latest`.

## Configuration

Config, auth and web sessions live in `~/.janito` inside the container
(`/home/appuser/.janito`). Persist them with a named volume:

```bash
docker run --rm -p 9090:9090 \
  -v janito-config:/home/appuser/.janito \
  ghcr.io/joaompinto/janito:latest
```

### First run: configure a provider

A fresh container has no provider configured, so the server refuses to
start (`Error: No provider is configured`). Initialize the named volume
once by overriding the container command (no TTY needed):

```bash
# Equivalent of `janito --config`, but headless: writes into the volume's
# /home/appuser/.janito (config.json + auth.json).
docker run --rm -v janito-config:/home/appuser/.janito \
  ghcr.io/joaompinto/janito:latest \
  janito --set provider=openai --set model=gpt-6.1-sol
docker run --rm -v janito-config:/home/appuser/.janito \
  ghcr.io/joaompinto/janito:latest \
  janito --set-api-key="sk-your-key" --provider openai
```

Alternatively, mount your existing host config instead of a named volume:

```bash
docker run --rm -p 9090:9090 \
  -v ~/.janito:/home/appuser/.janito \
  ghcr.io/joaompinto/janito:latest
```

You can also pass `--provider` / `--model` on the server command line
(the API key itself always comes from the auth store above):

```bash
docker run --rm -p 9090:9090 -v janito-config:/home/appuser/.janito \
  ghcr.io/joaompinto/janito:latest \
  janito --web --web-host 0.0.0.0 --web-port 9090 --no-web-open \
    --provider openai --model gpt-6.1-sol
```

Protect the UI with a bearer token (see [Web UI](web-ui.md)):

```bash
docker run --rm -p 9090:9090 \
  -e JANITO_WEB_TOKEN=secret \
  -v janito-config:/home/appuser/.janito \
  ghcr.io/joaompinto/janito:latest
```

All normal `janito --web` flags still apply by overriding the command:

```bash
docker run --rm -p 9090:9090 ghcr.io/joaompinto/janito:latest \
  janito --web --web-host 0.0.0.0 --web-port 9090 --no-web-open -r -w
```

## Build locally

```bash
docker build -t janito:local .
docker run --rm -p 9090:9090 janito:local
```

The build accepts an optional version stamp (used by the release workflow
to tag the Python package version via `setuptools_scm`):

```bash
docker build --build-arg VERSION=4.49.1 -t janito:local .
```

## Publishing

`.github/workflows/docker-publish.yml` builds and pushes the image to GHCR
on every `v*` tag push and on published GitHub releases, using the release
tag (without the leading `v`) as the `VERSION` build-arg. The job only
runs in the official `joaompinto/janito` repository, so forks never
publish from this workflow.
