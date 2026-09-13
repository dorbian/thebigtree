# Validation snapshot — 2026-09-11

This file records the validation state of the source tree packaged after the
Raspberry Pi/runtime, Verdant Conclave, Forest, cardgame and Elfministration
improvement passes.

## Passed locally

- `python -m compileall -q bigtree tests tools dev_frontend.py`
- `python -m unittest discover -s tests -v` — **39 tests passed**
- `node --check bigtree/web/static/overlay/overlay.js`
- `node --check bigtree/web/static/gallery/gallery.js`
- `node --check bigtree/web/static/user_area/user_area.js`
- `node --check bigtree/web/static/bingo/bingo_owner.js`
- `node --check bigtree/web/static/bingo/bingo_card.js`
- All `.github/workflows/*.yml` parsed as YAML.
- `tools/precompress_static.py` generated 10 gzip sidecars and each decompressed
  byte-for-byte to its source. The measured compressible payload changed from
  628,825 bytes to 122,528 bytes (80.5% smaller). Sidecars were removed again
  because the Containerfile generates them during the image build.

The tests include Verdant Conclave phase/role secrecy/readiness behavior,
intentional passes and last wills, Boughwatcher/Wayfinder behavior, the
production `EBADF` rotating-log recovery, Blackjack split-hand progression,
Craps duplicate-round protection, cardgame event polling/cleanup, reverse
proxy trust, HTTP gzip negotiation, and web asset/UI contracts.

## Validation requiring the normal CI/deployment environment

- **Forest/Dalamud:** the current execution environment does not contain the
  .NET SDK/Dalamud build environment. The `forest-client.yml` workflow remains
  the authoritative compile/package test.
- **Go overlay:** `go test ./...` and `go vet ./...` were attempted, but this
  environment cannot resolve/download `github.com/webview/webview` from
  `proxy.golang.org`. The workflow now runs both checks where dependencies are
  available.
- **Container:** Docker/Podman is not installed in this execution environment,
  so the multi-stage Containerfile was source/contract tested but not built
  here. The main GitHub Buildx workflow performs the real multi-architecture
  image build for amd64, arm64 and arm/v7.

## First deployment checks

1. Let GitHub Actions build the source and confirm the Forest workflow compiles.
2. Confirm the Pi's `/healthz` reports the expected `build.sha`.
3. Wait for `/readyz` to return HTTP 200 before considering the new container
   fully ready for player traffic.
4. If Traefik's address is outside loopback/private networks, configure
   `BIGTREE__WEB__trusted_proxy_cidrs` with the exact Traefik IP/CIDR.
5. Confirm a static JS/CSS request with `Accept-Encoding: gzip` receives
   `Content-Encoding: gzip` and a versioned immutable cache policy.
6. Run a short Discord Verdant Conclave with at least five players and confirm
   all actions are rejected outside its bound channel.
7. Run a wallet-backed cardgame and retry an identical action nonce to confirm
   it cannot charge/pay twice.

## Deliberately remaining larger work

- Continue decomposing the very large Forest `MainWindow.cs` and web
  `overlay.js` by feature without changing their public behavior.
- Continue moving older games onto the shared transactional/session patterns.
- Expand Verdant Conclave with additional original roles/rules after live
  playtesting the current information/disruption balance.
- Retire remaining legacy cardgame host-token URLs after a compatible
  cookie/bootstrap migration is in place.
- Add PostgreSQL-backed integration tests in CI for wallet/session transaction
  behavior in addition to the current pure regression tests.
