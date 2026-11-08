# Install

## From source with uv (recommended)

```
uv tool install git+https://github.com/lee101/mojoanalyzer
mojoanalyzer --version
```

or `pipx install git+https://github.com/lee101/mojoanalyzer`. Python 3.12 or newer, no runtime dependencies.

## Standalone binary

Tagged releases attach `mojoanalyzer-linux-x86_64`, `mojoanalyzer-macos-arm64` and `mojoanalyzer-windows-x86_64.exe`
(built with PyInstaller by `.github/workflows/release.yml`).

```
curl -L -o mojoanalyzer https://github.com/lee101/mojoanalyzer/releases/latest/download/mojoanalyzer-linux-x86_64
chmod +x mojoanalyzer && sudo mv mojoanalyzer /usr/local/bin/
```

Build one yourself:

```
uv run --with pyinstaller pyinstaller --onefile --name mojoanalyzer scripts/entry.py --paths src --collect-submodules mojoanalyzer
./dist/mojoanalyzer --list-rules
```

## Docker

```
docker build -t mojoanalyzer .
docker run --rm -p 8080:8080 mojoanalyzer                       # HTTP API
docker run --rm -v "$PWD:/src" --entrypoint mojoanalyzer mojoanalyzer /src
```

## CI

```yaml
- uses: astral-sh/setup-uv@v5
- run: uvx --from git+https://github.com/lee101/mojoanalyzer mojoanalyzer src --select MA2,MA4 --min-confidence high
```

GitHub code scanning: `mojoanalyzer src --format sarif --fail-on never > out.sarif`, then upload with
`github/codeql-action/upload-sarif`.
