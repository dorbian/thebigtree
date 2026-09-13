# TheBigTree

Welcome to the source of TheBigTree, Here you can find a collection of the Lore of the Forest, TheBigTree, and Elf.
Also, the source of the individual components are stored here as well.

If you would like to read the lore, please click [Here](LOREFORGE.MD)

## Discord Bot

The Discord bot uses the following modules:

uses discordpy, tinydb, pillow

Sources:
https://discordpy.readthedocs.io/en/stable/
https://tinydb.readthedocs.io/en/latest/usage.html

partake.gg module:  
pip install "gql[all]"

## Service setup

To run the bot as a service, use the included install.sh and configure the settings file with your own token and required information.
This will automatically install a timer for the update service and setup the service itself.

## Raspberry Pi / container deployment

The current production-oriented layout supports BigTree and PostgreSQL in the same Podman pod. Keeping PostgreSQL on `127.0.0.1:5432` is intentional for that topology. BigTree exposes `/healthz` for process liveness and `/readyz` for cutover/readiness checks; the latter only becomes healthy when the Discord client and PostgreSQL are ready. Normal diagnostic logging is designed for container stdout, while persistent file logging is optional.

Uploaded media keeps its original file and gets two local WebP derivatives: a small grid thumbnail and a screen-sized preview. Web views use those derivatives by default so large artwork does not need to be transferred/decoded for every tile. Existing media generates derivatives lazily the first time it is viewed; newly uploaded media generates both once at upload time.

## Verdant Conclave

Verdant Conclave is an original Elezen-inspired elf social-deduction game for Discord. Create it with `/conclave-create`; by default BigTree creates and binds a dedicated Discord text channel, and player interactions are rejected outside that channel. Private roles, night actions, nominations and judgements remain Discord-only. The Elfministration web UI and Forest/Dalamud client expose host-safe session state and controls without revealing living secret roles.

The host flow is Lobby → Night → Day council → Nominations → Trial → Judgement, repeating until a faction wins or the host ends the session. Players can deliberately pass/abstain where appropriate and maintain a private last will that can be revealed on death.


## Reverse proxy and rollout notes

BigTree is intended to sit behind the external Traefik instance rather than terminate public TLS itself. Forwarded protocol/client-IP headers are accepted only when the immediate peer is a trusted proxy network. By default loopback, RFC1918 and IPv6 private/link-local ranges are trusted; deployments using a public or otherwise unusual Traefik address should set `BIGTREE__WEB__trusted_proxy_cidrs` to the exact Traefik IP/CIDR (comma-separated).

The main container workflow cancels superseded builds on the same branch so an older build cannot finish late and overwrite a newer `latest` image. The workflow passes the Git commit as `BIGTREE_BUILD_SHA`; `/healthz`, `/readyz` and `/bot` expose that non-secret revision for rollout troubleshooting.

Static CSS/JavaScript is gzip-precompressed once during image creation by `tools/precompress_static.py`. The runtime server negotiates those sidecars and keeps versioned assets immutable, reducing both transfer size and Pi CPU. Generated `.gz` files are build artifacts and are not kept in source.

Cardgame state mutations are serialized in-process and protected by PostgreSQL row locks/transactions. Event publication is committed with the state update, wallet actions use idempotency keys, and finished-session maintenance is throttled instead of running a cleanup query for every page refresh.
