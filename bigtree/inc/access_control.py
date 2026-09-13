from __future__ import annotations

"""BigTree Identity & Access foundation.

This module is deliberately provider/client neutral. Discord roles, web tokens,
Forest clients and game/session credentials are authentication inputs; the
permission vocabulary lives here.

Phase 1 keeps the existing Discord/web behaviour through compatibility bridges
while giving new code one capability evaluator and PostgreSQL-backed role
assignments. No access state is written to local container storage.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


# Canonical capabilities use dots. Existing colon-delimited web scopes remain
# accepted and are normalized here so old tokens/routes continue to work.
LEGACY_SCOPE_ALIASES: Dict[str, str] = {
    "admin:web": "admin.web",
    "admin:*": "admin.*",
    "event:host": "event.host",
    "conclave:admin": "game.conclave.host",
    "bingo:admin": "game.bingo.host",
    "tarot:admin": "game.tarot.manage",
    "cardgames:admin": "game.cardgames.manage",
    "dice:admin": "game.dice.manage",
    "slots:admin": "game.slots.manage",
    "hunt:admin": "hunt.manage",
}

CAPABILITY_DESCRIPTIONS: Dict[str, str] = {
    "*": "All BigTree capabilities.",
    "admin.*": "All Elfministration administrative capabilities.",
    "admin.web": "Open and use Elfministration administrative surfaces.",
    "system.permissions": "Manage identities, roles, bindings and access policy.",
    "system.tokens": "Issue, inspect and revoke administrative credentials.",
    "tree.address": "Address TheBigTree and hear its generated response.",
    "tree.commune": "Speak as TheBigTree through the operator Commune function.",
    "language.view": "Inspect Language Services state and diagnostics.",
    "language.manage": "Configure Language Services providers, memory and ritual policy.",
    "discord.announce": "Publish operator-managed Discord announcements.",
    "content.manage": "Create and review managed community content.",
    "gallery.moderate": "Moderate gallery content and metadata.",
    "event.view": "View event administration data.",
    "event.host": "Host assigned events.",
    "event.manage": "Create and administer events.",
    "venue.view": "View assigned venue administration data.",
    "venue.manage": "Administer an assigned venue.",
    "game.play": "Play a joined game/session.",
    "game.host": "Host an assigned game/session.",
    "game.manage": "Administer games globally or for an assigned resource.",
    "game.bingo.host": "Host Bingo.",
    "game.conclave.host": "Host Verdant Conclave.",
    "game.gpose.host": "Host GPose activities.",
    "game.tarot.manage": "Administer Tarot content and sessions.",
    "game.cardgames.manage": "Administer card games.",
    "game.dice.manage": "Administer dice sets.",
    "game.slots.manage": "Administer slot machines.",
    "hunt.manage": "Administer Hunt staffing/state.",
    "review.manage": "Review managed requests/content.",
    # Compatibility capabilities exist only so untouched decorators preserve
    # their historical meaning while callers are migrated one by one.
    "legacy.operator": "Compatibility bridge for the historical BigTree operator check.",
    "legacy.elfministrator": "Compatibility bridge for the historical Elfministrator check.",
}

# Roles are capability bundles, not authorization checks in themselves. A role
# may be global or assigned to a resource (venue/event/game) in PostgreSQL.
BUILTIN_ROLES: Dict[str, Dict[str, Any]] = {
    "root": {
        "name": "Root",
        "description": "Unrestricted BigTree authority.",
        "capabilities": ["*"],
    },
    "elfministrator": {
        "name": "Elfministrator",
        "description": "Compatibility full-administration role during IAM migration.",
        "capabilities": ["*", "legacy.elfministrator"],
    },
    "operator": {
        "name": "BigTree Operator",
        "description": "Operational Discord/game authority without IAM/security administration.",
        "capabilities": [
            "legacy.operator",
            "tree.commune",
            "discord.announce",
            "content.manage",
            "gallery.moderate",
            "event.host",
            "game.host",
            "game.bingo.host",
            "game.conclave.host",
            "game.gpose.host",
            "review.manage",
        ],
    },
    "priest": {
        "name": "Priest",
        "description": "May address TheBigTree; does not gain operator authority.",
        "capabilities": ["tree.address"],
    },
    "venue_admin": {
        "name": "Venue Administrator",
        "description": "Manages an assigned venue and its events/games.",
        "capabilities": ["venue.view", "venue.manage", "event.view", "event.host", "event.manage", "game.host"],
    },
    "event_host": {
        "name": "Event Host",
        "description": "Hosts an assigned event and its games.",
        "capabilities": ["event.view", "event.host", "game.host"],
    },
    "game_host": {
        "name": "Game Host",
        "description": "Hosts an assigned game/session.",
        "capabilities": ["game.host"],
    },
    "conclave_host": {
        "name": "Verdant Conclave Host",
        "description": "Hosts an assigned Verdant Conclave session.",
        "capabilities": ["game.host", "game.conclave.host"],
    },
    "player": {
        "name": "Player",
        "description": "Plays a joined game/session.",
        "capabilities": ["game.play"],
    },
}

# Some permissions are identity/ritual entitlements rather than administrative
# authority. They must be granted explicitly and are intentionally not covered
# by global wildcards. This preserves the historical Priest-only Tree audience.
EXPLICIT_ONLY_CAPABILITIES: Set[str] = {"tree.address"}

_CATALOG_LOCK = threading.RLock()
_CATALOG_READY = False


@dataclass(frozen=True)
class ResourceRef:
    type: str = ""
    id: str = ""

    @classmethod
    def coerce(cls, value: Any) -> "ResourceRef":
        if isinstance(value, cls):
            return value
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            return cls(str(value[0] or "").strip(), str(value[1] or "").strip())
        if isinstance(value, dict):
            return cls(str(value.get("type") or "").strip(), str(value.get("id") or "").strip())
        return cls()


@dataclass
class AccessDecision:
    allowed: bool
    capability: str
    principal_id: Optional[int] = None
    principal_label: str = ""
    resource: ResourceRef = field(default_factory=ResourceRef)
    roles: List[str] = field(default_factory=list)
    grants: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    compatibility: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": bool(self.allowed),
            "capability": self.capability,
            "principal_id": self.principal_id,
            "principal_label": self.principal_label,
            "resource": {"type": self.resource.type, "id": self.resource.id},
            "roles": sorted(set(self.roles)),
            "grants": sorted(set(self.grants)),
            "reasons": list(self.reasons),
            "compatibility": bool(self.compatibility),
        }


def normalize_capability(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if raw in LEGACY_SCOPE_ALIASES:
        return LEGACY_SCOPE_ALIASES[raw]
    # Preserve wildcard meaning while making old scope syntax compatible with
    # the canonical capability namespace.
    return raw.replace(":", ".")


def capability_grants(granted: Any, required: Any) -> bool:
    grant = normalize_capability(granted)
    need = normalize_capability(required)
    if not grant or not need:
        return False
    if grant == need:
        return True
    if need in EXPLICIT_ONLY_CAPABILITIES:
        return False
    if grant == "*":
        return True
    if grant.endswith(".*"):
        prefix = grant[:-2]
        return need == prefix or need.startswith(prefix + ".")
    return False


def any_capability_granted(required: Iterable[Any], granted: Iterable[Any]) -> bool:
    required_set = [normalize_capability(item) for item in required if normalize_capability(item)]
    if not required_set:
        return True
    grants = [normalize_capability(item) for item in granted if normalize_capability(item)]
    return any(capability_grants(grant, need) for need in required_set for grant in grants)


def all_capabilities_granted(required: Iterable[Any], granted: Iterable[Any]) -> bool:
    required_set = [normalize_capability(item) for item in required if normalize_capability(item)]
    grants = [normalize_capability(item) for item in granted if normalize_capability(item)]
    return all(any(capability_grants(grant, need) for grant in grants) for need in required_set)


def _get_db():
    from bigtree.inc.database import get_database
    return get_database()


def seed_builtin_catalog(db=None) -> None:
    """Upsert the small built-in role/capability catalogue into PostgreSQL."""
    global _CATALOG_READY
    with _CATALOG_LOCK:
        if _CATALOG_READY and db is None:
            return
        db = db or _get_db()
        with db.transaction() as cur:
            for capability, description in CAPABILITY_DESCRIPTIONS.items():
                cur.execute(
                    """
                    INSERT INTO access_capabilities (capability, description, system)
                    VALUES (%s, %s, TRUE)
                    ON CONFLICT (capability) DO UPDATE
                    SET description = EXCLUDED.description, system = TRUE
                    """,
                    (normalize_capability(capability), description),
                )
            for role_key, spec in BUILTIN_ROLES.items():
                cur.execute(
                    """
                    INSERT INTO access_roles (role_key, name, description, system)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (role_key) DO UPDATE
                    SET name = EXCLUDED.name, description = EXCLUDED.description, system = TRUE
                    """,
                    (role_key, spec["name"], spec["description"]),
                )
                for capability in spec["capabilities"]:
                    normalized = normalize_capability(capability)
                    cur.execute(
                        """
                        INSERT INTO access_role_capabilities (role_key, capability, source)
                        VALUES (%s, %s, 'builtin')
                        ON CONFLICT (role_key, capability) DO UPDATE SET source = EXCLUDED.source
                        """,
                        (role_key, normalized),
                    )
        _CATALOG_READY = True


def _ensure_catalog(db=None) -> None:
    global _CATALOG_READY
    if _CATALOG_READY:
        return
    seed_builtin_catalog(db)


def _member_identity(member: Any) -> Tuple[str, str, str]:
    user_id = str(getattr(member, "id", "") or "").strip()
    display = str(
        getattr(member, "display_name", None)
        or getattr(member, "global_name", None)
        or getattr(member, "name", None)
        or user_id
    ).strip()
    guild = getattr(member, "guild", None)
    guild_id = str(getattr(guild, "id", "") or "").strip()
    return user_id, display, guild_id


def ensure_discord_principal(member: Any, db=None) -> Tuple[Optional[int], str]:
    """Resolve/create the durable BigTree principal for a Discord member.

    Creation is one-time; ordinary checks do not continuously rewrite member
    metadata. If PostgreSQL is unavailable, callers can still use the legacy
    compatibility grants and receive a principal_id of None.
    """
    user_id, display, guild_id = _member_identity(member)
    if not user_id:
        return None, display
    try:
        db = db or _get_db()
        _ensure_catalog(db)
        with db.transaction() as cur:
            cur.execute(
                """
                SELECT p.id, p.display_name
                FROM access_identities i
                JOIN access_principals p ON p.id = i.principal_id
                WHERE i.provider = 'discord' AND i.external_id = %s
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row:
                return int(row[0]), str(row[1] or display)

            from psycopg2.extras import Json
            cur.execute(
                """
                INSERT INTO access_principals (principal_type, display_name, metadata)
                VALUES ('human', %s, %s)
                RETURNING id
                """,
                (display or user_id, Json({"created_from": "discord"})),
            )
            principal_id = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO access_identities (principal_id, provider, external_id, metadata)
                VALUES (%s, 'discord', %s, %s)
                ON CONFLICT (provider, external_id) DO NOTHING
                RETURNING principal_id
                """,
                (principal_id, user_id, Json({"guild_id": guild_id} if guild_id else {})),
            )
            linked = cur.fetchone()
            if linked:
                return principal_id, display or user_id

            # Another worker won a first-seen race. Reuse the winner and remove
            # the unreferenced principal created by this transaction.
            cur.execute(
                "SELECT principal_id FROM access_identities WHERE provider = 'discord' AND external_id = %s",
                (user_id,),
            )
            winner = cur.fetchone()
            cur.execute("DELETE FROM access_principals WHERE id = %s", (principal_id,))
            return (int(winner[0]) if winner else None), display or user_id
    except Exception:
        return None, display or user_id


def _resource_chain(resource: ResourceRef, ancestors: Optional[Sequence[Any]]) -> Set[Tuple[str, str]]:
    chain: Set[Tuple[str, str]] = set()
    if resource.type and resource.id:
        chain.add((resource.type, resource.id))
    for item in ancestors or []:
        ref = ResourceRef.coerce(item)
        if ref.type and ref.id:
            chain.add((ref.type, ref.id))
    return chain


def _assignment_applies(resource_type: str, resource_id: str, chain: Set[Tuple[str, str]]) -> bool:
    resource_type = str(resource_type or "").strip()
    resource_id = str(resource_id or "").strip()
    if not resource_type and not resource_id:
        return True
    return (resource_type, resource_id) in chain


def _db_principal_grants(
    principal_id: Optional[int],
    resource: ResourceRef,
    ancestors: Optional[Sequence[Any]],
    db=None,
) -> Tuple[Set[str], Set[str], List[str]]:
    if not principal_id:
        return set(), set(), []
    db = db or _get_db()
    chain = _resource_chain(resource, ancestors)
    rows = db._execute(
        """
        SELECT pr.role_key, pr.resource_type, pr.resource_id, pr.source, rc.capability
        FROM access_principal_roles pr
        JOIN access_role_capabilities rc ON rc.role_key = pr.role_key
        WHERE pr.principal_id = %s
          AND (pr.expires_at IS NULL OR pr.expires_at > CURRENT_TIMESTAMP)
        """,
        (int(principal_id),),
        fetch=True,
    ) or []
    roles: Set[str] = set()
    grants: Set[str] = set()
    reasons: List[str] = []
    for row in rows:
        if not _assignment_applies(row.get("resource_type"), row.get("resource_id"), chain):
            continue
        role_key = str(row.get("role_key") or "").strip()
        capability = normalize_capability(row.get("capability"))
        if role_key:
            roles.add(role_key)
        if capability:
            grants.add(capability)
        source = str(row.get("source") or "assignment")
        if role_key:
            reasons.append(f"role {role_key} assigned via {source}")
    return roles, grants, reasons


def _external_discord_grants(member: Any, db=None) -> Tuple[Set[str], Set[str], List[str]]:
    role_ids = [str(getattr(role, "id", "") or "").strip() for role in getattr(member, "roles", [])]
    role_ids = [role_id for role_id in role_ids if role_id]
    if not role_ids:
        return set(), set(), []
    _, _, guild_id = _member_identity(member)
    try:
        db = db or _get_db()
        rows = db._execute(
            """
            SELECT b.external_role_id, b.role_key, rc.capability
            FROM access_external_role_bindings b
            JOIN access_role_capabilities rc ON rc.role_key = b.role_key
            WHERE b.provider = 'discord'
              AND b.enabled = TRUE
              AND b.external_role_id = ANY(%s)
              AND (b.guild_id = '' OR b.guild_id = %s)
            """,
            (role_ids, guild_id),
            fetch=True,
        ) or []
    except Exception:
        rows = []
    roles: Set[str] = set()
    grants: Set[str] = set()
    reasons: List[str] = []
    for row in rows:
        role_key = str(row.get("role_key") or "").strip()
        capability = normalize_capability(row.get("capability"))
        if role_key:
            roles.add(role_key)
        if capability:
            grants.add(capability)
        reasons.append(f"Discord role {row.get('external_role_id')} bound to {role_key}")
    return roles, grants, reasons


def _legacy_role_scope_grants(member: Any, db=None) -> Tuple[Set[str], List[str]]:
    try:
        db = db or _get_db()
        mapping = db.get_auth_roles() or {}
    except Exception:
        mapping = {}
    grants: Set[str] = set()
    reasons: List[str] = []
    for role in getattr(member, "roles", []) or []:
        role_id = str(getattr(role, "id", "") or "")
        raw = mapping.get(role_id) or mapping.get(getattr(role, "id", None)) or []
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.split(",") if part.strip()]
        for item in raw or []:
            capability = normalize_capability(item)
            if capability:
                grants.add(capability)
                reasons.append(f"legacy Discord scope {item} from role {role_id}")
    return grants, reasons


def _legacy_discord_roles(member: Any) -> Tuple[Set[str], Set[str], List[str]]:
    """Preserve historical Discord semantics while migration is in progress."""
    roles: Set[str] = set()
    grants: Set[str] = set()
    reasons: List[str] = []
    member_id = getattr(member, "id", None)
    member_roles = list(getattr(member, "roles", []) or [])
    role_ids = {getattr(role, "id", None) for role in member_roles}
    role_names = {str(getattr(role, "name", "") or "").strip().casefold() for role in member_roles}
    perms = getattr(member, "guild_permissions", None)

    # Preserve current Elfministrator semantics during transition: Discord
    # Administrator, configured role/user IDs, and the historical role-name
    # fallback are full administration. This becomes configurable in the IAM UI.
    elfministrator = bool(perms and getattr(perms, "administrator", False))
    try:
        import bigtree
        configured_roles = set()
        configured_users = set()
        for value in getattr(bigtree, "elfministrator_role_ids", []) or []:
            try:
                configured_roles.add(int(value))
            except Exception:
                pass
        for value in getattr(bigtree, "elfministrator_user_ids", []) or []:
            try:
                configured_users.add(int(value))
            except Exception:
                pass
        settings = getattr(bigtree, "settings", None)
        if settings:
            raw = settings.get("BOT.elfministrator_role_ids", [], cast="json") or []
            if isinstance(raw, (str, int)):
                raw = [raw]
            for value in raw:
                try:
                    configured_roles.add(int(value))
                except Exception:
                    pass
        elfministrator = elfministrator or bool(configured_roles & role_ids) or member_id in configured_users
    except Exception:
        pass
    if "elfministrator" in role_names:
        elfministrator = True
    if elfministrator:
        roles.add("elfministrator")
        grants.update(normalize_capability(c) for c in BUILTIN_ROLES["elfministrator"]["capabilities"])
        reasons.append("historical Elfministrator/Discord Administrator compatibility")

    # Preserve current BigTree operator semantics independently of full admin.
    operator = bool(perms and (getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)))
    try:
        import bigtree
        configured_roles = set()
        configured_users = set()
        for value in getattr(bigtree, "operator_role_ids", []) or []:
            try:
                configured_roles.add(int(value))
            except Exception:
                pass
        for value in getattr(bigtree, "operator_user_ids", []) or []:
            try:
                configured_users.add(int(value))
            except Exception:
                pass
        operator = operator or bool(configured_roles & role_ids) or member_id in configured_users
    except Exception:
        pass
    if operator:
        roles.add("operator")
        grants.update(normalize_capability(c) for c in BUILTIN_ROLES["operator"]["capabilities"])
        reasons.append("historical BigTree operator compatibility")

    # The Priest role is intentionally narrow. It allows addressing/hearing
    # TheBigTree and never implies tree.commune or operator authority.
    if "priest/ess" in role_names:
        roles.add("priest")
        grants.add("tree.address")
        reasons.append("historical Priest/ess Discord role compatibility")

    return roles, grants, reasons


def evaluate_discord_member(
    member: Any,
    capability: str,
    *,
    resource_type: str = "",
    resource_id: Any = "",
    ancestors: Optional[Sequence[Any]] = None,
    db=None,
) -> AccessDecision:
    required = normalize_capability(capability)
    resource = ResourceRef(str(resource_type or "").strip(), str(resource_id or "").strip())
    principal_id, label = ensure_discord_principal(member, db=db)

    roles: Set[str] = set()
    grants: Set[str] = set()
    reasons: List[str] = []

    try:
        db_roles, db_grants, db_reasons = _db_principal_grants(principal_id, resource, ancestors, db=db)
        roles.update(db_roles)
        grants.update(db_grants)
        reasons.extend(db_reasons)
    except Exception:
        pass

    ext_roles, ext_grants, ext_reasons = _external_discord_grants(member, db=db)
    roles.update(ext_roles)
    grants.update(ext_grants)
    reasons.extend(ext_reasons)

    legacy_scope_grants, scope_reasons = _legacy_role_scope_grants(member, db=db)
    grants.update(legacy_scope_grants)
    reasons.extend(scope_reasons)

    compat_roles, compat_grants, compat_reasons = _legacy_discord_roles(member)
    roles.update(compat_roles)
    grants.update(compat_grants)
    reasons.extend(compat_reasons)

    allowed = any(capability_grants(grant, required) for grant in grants)
    if allowed:
        matching = sorted(grant for grant in grants if capability_grants(grant, required))
        reasons.append(f"{required} granted by {', '.join(matching)}")
    else:
        reasons.append(f"no effective role/capability grants {required}")

    return AccessDecision(
        allowed=allowed,
        capability=required,
        principal_id=principal_id,
        principal_label=label,
        resource=resource,
        roles=sorted(roles),
        grants=sorted(grants),
        reasons=reasons,
        compatibility=bool(compat_reasons or scope_reasons),
    )


def assign_role(
    principal_id: int,
    role_key: str,
    *,
    resource_type: str = "",
    resource_id: Any = "",
    source: str = "operator",
    expires_at: Optional[datetime] = None,
    db=None,
) -> None:
    db = db or _get_db()
    _ensure_catalog(db)
    role_key = str(role_key or "").strip().lower()
    if not role_key:
        raise ValueError("role_key is required")
    db._execute(
        """
        INSERT INTO access_principal_roles
            (principal_id, role_key, resource_type, resource_id, source, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (principal_id, role_key, resource_type, resource_id)
        DO UPDATE SET source = EXCLUDED.source, expires_at = EXCLUDED.expires_at
        """,
        (
            int(principal_id), role_key, str(resource_type or "").strip(),
            str(resource_id or "").strip(), str(source or "operator")[:80], expires_at,
        ),
    )


def bind_external_role(
    provider: str,
    external_role_id: Any,
    role_key: str,
    *,
    guild_id: Any = "",
    db=None,
) -> None:
    db = db or _get_db()
    _ensure_catalog(db)
    provider = str(provider or "").strip().lower()
    external_role_id = str(external_role_id or "").strip()
    role_key = str(role_key or "").strip().lower()
    if not provider or not external_role_id or not role_key:
        raise ValueError("provider, external_role_id and role_key are required")
    db._execute(
        """
        INSERT INTO access_external_role_bindings
            (provider, guild_id, external_role_id, role_key, enabled)
        VALUES (%s, %s, %s, %s, TRUE)
        ON CONFLICT (provider, guild_id, external_role_id, role_key)
        DO UPDATE SET enabled = TRUE, updated_at = CURRENT_TIMESTAMP
        """,
        (provider, str(guild_id or "").strip(), external_role_id, role_key),
    )


def catalog_snapshot(db=None) -> Dict[str, Any]:
    db = db or _get_db()
    _ensure_catalog(db)
    roles = db._execute(
        "SELECT role_key, name, description, system FROM access_roles ORDER BY role_key",
        fetch=True,
    ) or []
    role_caps = db._execute(
        "SELECT role_key, capability, source FROM access_role_capabilities ORDER BY role_key, capability",
        fetch=True,
    ) or []
    bindings = db._execute(
        """
        SELECT provider, guild_id, external_role_id, role_key, enabled, updated_at
        FROM access_external_role_bindings
        ORDER BY provider, guild_id, external_role_id, role_key
        LIMIT 500
        """,
        fetch=True,
    ) or []
    by_role: Dict[str, List[str]] = {}
    for row in role_caps:
        by_role.setdefault(str(row.get("role_key") or ""), []).append(str(row.get("capability") or ""))
    role_docs = []
    for row in roles:
        doc = dict(row)
        doc["capabilities"] = by_role.get(str(row.get("role_key") or ""), [])
        role_docs.append(doc)
    for row in bindings:
        value = row.get("updated_at")
        if isinstance(value, datetime):
            row["updated_at"] = value.astimezone(timezone.utc).isoformat()
    return {
        "mode": "compatibility-first",
        "canonical_separator": ".",
        "persistent_backend": "PostgreSQL",
        "roles": role_docs,
        "capabilities": [
            {"capability": key, "description": value}
            for key, value in sorted(CAPABILITY_DESCRIPTIONS.items())
        ],
        "external_bindings": bindings,
        "legacy_scope_aliases": dict(sorted(LEGACY_SCOPE_ALIASES.items())),
    }
