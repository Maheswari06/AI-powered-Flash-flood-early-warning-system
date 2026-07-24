"""
ARGUS Security — OAuth2 + JWT Authentication Middleware
Keycloak RS256 JWT validation with role-based access control.

Roles:
  VIEWER          — Read-only dashboard access
  OPERATOR        — Can acknowledge alerts
  DISTRICT_ADMIN  — Can trigger evacuations for their district
  SYSTEM_ADMIN    — Full system access
  SERVICE         — Inter-service communication (mTLS)
"""

from __future__ import annotations

import os
import time
import logging
from enum import Enum
from typing import Optional
from functools import wraps

import httpx
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, jwk
from jose.utils import base64url_decode
from pydantic import BaseModel

logger = logging.getLogger("argus.auth")

# ═══════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://auth.argus.flood.gov.in")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "argus")
JWKS_URI = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
ISSUER = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
AUDIENCE = os.getenv("JWT_AUDIENCE", "argus-api")
JWT_ALGORITHM = "RS256"

# Fallback: symmetric JWT for demo/dev mode
JWT_SECRET = os.getenv("JWT_SECRET", "argus-dev-secret-change-in-production")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"


# ═══════════════════════════════════════════════════════════════════
# Role Definitions
# ═══════════════════════════════════════════════════════════════════
class Role(str, Enum):
    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    DISTRICT_ADMIN = "DISTRICT_ADMIN"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    SERVICE = "SERVICE"


# Role hierarchy: higher roles inherit lower role permissions
ROLE_HIERARCHY = {
    Role.VIEWER: 0,
    Role.OPERATOR: 1,
    Role.DISTRICT_ADMIN: 2,
    Role.SYSTEM_ADMIN: 3,
    Role.SERVICE: 3,
}


class TokenPayload(BaseModel):
    """Decoded JWT token payload."""
    sub: str  # Subject (user ID)
    email: Optional[str] = None
    name: Optional[str] = None
    roles: list[str] = []
    district: Optional[str] = None  # For DISTRICT_ADMIN scoping
    exp: int = 0
    iat: int = 0
    iss: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# JWKS Key Cache
# ═══════════════════════════════════════════════════════════════════
class JWKSCache:
    """Caches JWKS keys with automatic refresh."""

    def __init__(self, jwks_uri: str, refresh_interval: int = 3600):
        self.jwks_uri = jwks_uri
        self.refresh_interval = refresh_interval
        self._keys: dict = {}
        self._last_refresh: float = 0

    async def get_key(self, kid: str) -> Optional[dict]:
        """Get signing key by key ID, refreshing cache if needed."""
        if time.time() - self._last_refresh > self.refresh_interval:
            await self._refresh()

        key = self._keys.get(kid)
        if key is None:
            # Key not found — force refresh in case of key rotation
            await self._refresh()
            key = self._keys.get(kid)

        return key

    async def _refresh(self):
        """Fetch JWKS from Keycloak."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.jwks_uri)
                response.raise_for_status()
                jwks = response.json()

            self._keys = {
                key["kid"]: key
                for key in jwks.get("keys", [])
                if key.get("use") == "sig"
            }
            self._last_refresh = time.time()
            logger.info(f"JWKS refreshed: {len(self._keys)} signing keys loaded")
        except Exception as e:
            logger.error(f"Failed to refresh JWKS: {e}")
            if not self._keys:
                raise HTTPException(502, "Authentication service unavailable")


_jwks_cache = JWKSCache(JWKS_URI)

# ═══════════════════════════════════════════════════════════════════
# Token Validation
# ═══════════════════════════════════════════════════════════════════
security_scheme = HTTPBearer(auto_error=False)


async def _decode_token_keycloak(token: str) -> TokenPayload:
    """Decode and validate JWT using Keycloak JWKS (RS256)."""
    try:
        # Extract kid from header without full verification
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise HTTPException(401, "Token missing key ID")

        # Get signing key
        signing_key = await _jwks_cache.get_key(kid)
        if not signing_key:
            raise HTTPException(401, "Unknown signing key")

        # Verify and decode
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[JWT_ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
        )

        # Extract roles from Keycloak realm_access
        realm_roles = payload.get("realm_access", {}).get("roles", [])
        argus_roles = [r for r in realm_roles if r in Role.__members__]

        return TokenPayload(
            sub=payload["sub"],
            email=payload.get("email"),
            name=payload.get("name", payload.get("preferred_username")),
            roles=argus_roles,
            district=payload.get("district"),
            exp=payload.get("exp", 0),
            iat=payload.get("iat", 0),
            iss=payload.get("iss"),
        )
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise HTTPException(401, f"Invalid token: {e}")


def _decode_token_demo(token: str) -> TokenPayload:
    """Decode JWT using symmetric secret (demo/dev mode only)."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False, "verify_iss": False},
        )
        return TokenPayload(
            sub=payload.get("sub", "demo-user"),
            email=payload.get("email", "demo@argus.local"),
            name=payload.get("name", "Demo User"),
            roles=payload.get("roles", ["SYSTEM_ADMIN"]),
            district=payload.get("district"),
            exp=payload.get("exp", 0),
            iat=payload.get("iat", 0),
        )
    except JWTError as e:
        raise HTTPException(401, f"Invalid demo token: {e}")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> TokenPayload:
    """FastAPI dependency: extract and validate the current user from JWT."""
    if credentials is None:
        if DEMO_MODE:
            # Auto-authenticate as SYSTEM_ADMIN in demo mode
            return TokenPayload(
                sub="demo-admin",
                email="admin@argus.local",
                name="Demo Admin",
                roles=["SYSTEM_ADMIN"],
                exp=int(time.time()) + 86400,
                iat=int(time.time()),
            )
        raise HTTPException(401, "Authentication required")

    token = credentials.credentials

    if DEMO_MODE:
        return _decode_token_demo(token)
    else:
        return await _decode_token_keycloak(token)


# ═══════════════════════════════════════════════════════════════════
# Role-Based Access Control Decorators
# ═══════════════════════════════════════════════════════════════════
def require_role(minimum_role: Role):
    """
    Dependency factory: require the user to have at least the specified role.

    Usage:
        @app.get("/admin/config")
        async def get_config(user = Depends(require_role(Role.SYSTEM_ADMIN))):
            ...
    """
    async def _check(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        user_max_level = max(
            (ROLE_HIERARCHY.get(Role(r), -1) for r in user.roles),
            default=-1,
        )
        required_level = ROLE_HIERARCHY[minimum_role]

        if user_max_level < required_level:
            logger.warning(
                f"Access denied: user={user.sub} roles={user.roles} "
                f"required={minimum_role.value}"
            )
            raise HTTPException(
                403,
                f"Insufficient permissions. Required: {minimum_role.value}",
            )
        return user

    return _check


def require_district(district_id: str):
    """
    Dependency factory: require DISTRICT_ADMIN scoped to a specific district.

    SYSTEM_ADMIN bypasses district check.
    """
    async def _check(user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        if Role.SYSTEM_ADMIN.value in user.roles or Role.SERVICE.value in user.roles:
            return user

        if Role.DISTRICT_ADMIN.value not in user.roles:
            raise HTTPException(403, "District admin role required")

        if user.district != district_id:
            raise HTTPException(
                403,
                f"Not authorized for district {district_id}",
            )
        return user

    return _check


# ═══════════════════════════════════════════════════════════════════
# Endpoint-Level RBAC Map
# ═══════════════════════════════════════════════════════════════════
ENDPOINT_PERMISSIONS: dict[str, Role] = {
    # Phase 1
    "GET /api/v1/predictions": Role.VIEWER,
    "GET /api/v1/alerts": Role.VIEWER,
    "POST /api/v1/alerts/acknowledge": Role.OPERATOR,
    "GET /api/v1/gauges": Role.VIEWER,

    # Phase 2
    "GET /api/v1/causal/dag": Role.VIEWER,
    "POST /api/v1/causal/validate": Role.SYSTEM_ADMIN,
    "GET /api/v1/ledger/records": Role.VIEWER,

    # Phase 3
    "GET /api/v1/chorus/trust": Role.VIEWER,
    "POST /api/v1/federated/round": Role.SYSTEM_ADMIN,

    # Phase 4
    "POST /api/v1/evacuation/trigger": Role.DISTRICT_ADMIN,
    "GET /api/v1/evacuation/routes": Role.VIEWER,
    "GET /api/v1/mirror/simulation": Role.OPERATOR,
    "POST /api/v1/mirror/scenario": Role.OPERATOR,
    "GET /api/v1/scarnet/assessment": Role.VIEWER,
    "GET /api/v1/model-monitor/drift": Role.OPERATOR,

    # Admin
    "GET /api/v1/admin/config": Role.SYSTEM_ADMIN,
    "PUT /api/v1/admin/config": Role.SYSTEM_ADMIN,
    "GET /api/v1/admin/audit-log": Role.SYSTEM_ADMIN,
    "POST /api/v1/admin/storm-mode": Role.SYSTEM_ADMIN,
}


# ═══════════════════════════════════════════════════════════════════
# JWT Token Generation (for inter-service and demo)
# ═══════════════════════════════════════════════════════════════════
def create_service_token(service_name: str, ttl: int = 3600) -> str:
    """Generate a service-to-service JWT for internal communication."""
    now = int(time.time())
    payload = {
        "sub": f"service:{service_name}",
        "name": service_name,
        "roles": [Role.SERVICE.value],
        "iat": now,
        "exp": now + ttl,
        "iss": "argus-internal",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def create_demo_token(
    username: str = "demo_admin",
    roles: list[str] = None,
    district: Optional[str] = None,
    ttl: int = 86400,
) -> str:
    """Generate a demo JWT for development/testing."""
    if roles is None:
        roles = [Role.SYSTEM_ADMIN.value]
    now = int(time.time())
    payload = {
        "sub": username,
        "email": f"{username}@argus.local",
        "name": username.replace("_", " ").title(),
        "roles": roles,
        "district": district,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")
