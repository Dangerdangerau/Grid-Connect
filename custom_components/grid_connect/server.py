"""HTTP server endpoints for Grid Connect provisioning workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
import logging
from typing import Any
from uuid import uuid4

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback

from .const import (
    DATA_SERVER,
    DEFAULT_PROVISIONING_SESSION_TTL,
    DOMAIN,
    PROVISIONING_API_BASE,
)

_LOGGER = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


@dataclass(slots=True)
class ProvisioningSession:
    """Provisioning state tracked by the Grid Connect onboarding server."""

    session_id: str
    created_at: datetime
    expires_at: datetime
    status: str = "created"
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialize the session for the API response."""
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["expires_at"] = self.expires_at.isoformat()
        return payload


class GridConnectProvisioningServer:
    """Small in-memory session server for Grid Connect onboarding."""

    def __init__(
        self,
        hass: HomeAssistant,
        session_ttl: int = DEFAULT_PROVISIONING_SESSION_TTL,
    ) -> None:
        """Initialize the provisioning server."""
        self.hass = hass
        self._session_ttl = timedelta(seconds=session_ttl)
        self._sessions: dict[str, ProvisioningSession] = {}

    @callback
    def create_session(
        self,
        *,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProvisioningSession:
        """Create and store a new provisioning session."""
        self.purge_expired_sessions()
        now = _utcnow()
        session = ProvisioningSession(
            session_id=uuid4().hex,
            created_at=now,
            expires_at=now + self._session_ttl,
            model=model,
            metadata=metadata or {},
        )
        self._sessions[session.session_id] = session
        _LOGGER.debug("Created provisioning session %s", session.session_id)
        return session

    @callback
    def get_session(self, session_id: str) -> ProvisioningSession | None:
        """Return a session when it exists and has not expired."""
        self.purge_expired_sessions()
        return self._sessions.get(session_id)

    @callback
    def delete_session(self, session_id: str) -> bool:
        """Delete a session if present."""
        deleted = self._sessions.pop(session_id, None) is not None
        if deleted:
            _LOGGER.debug("Deleted provisioning session %s", session_id)
        return deleted

    @callback
    def update_session(
        self,
        session_id: str,
        *,
        status: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProvisioningSession | None:
        """Update a provisioning session in-place."""
        session = self.get_session(session_id)
        if session is None:
            return None

        if status is not None:
            session.status = status
        if model is not None:
            session.model = model
        if metadata:
            session.metadata.update(metadata)
        return session

    @callback
    def purge_expired_sessions(self) -> None:
        """Drop sessions that have exceeded the configured TTL."""
        now = _utcnow()
        expired_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for session_id in expired_ids:
            self._sessions.pop(session_id, None)
        if expired_ids:
            _LOGGER.debug("Purged %d expired provisioning sessions", len(expired_ids))

    @callback
    def health(self) -> dict[str, Any]:
        """Return a lightweight summary of the provisioning server state."""
        self.purge_expired_sessions()
        return {
            "status": "ok",
            "active_sessions": len(self._sessions),
            "session_ttl_seconds": int(self._session_ttl.total_seconds()),
        }


def _server_from_request(request: web.Request) -> GridConnectProvisioningServer:
    """Return the provisioning server from a request context."""
    hass: HomeAssistant = request.app["hass"]
    return hass.data[DOMAIN][DATA_SERVER]


class GridConnectProvisioningHealthView(HomeAssistantView):
    """Health endpoint for the Grid Connect provisioning server."""

    url = PROVISIONING_API_BASE
    name = "api:grid_connect:provisioning"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return provisioning server health details."""
        return self.json(_server_from_request(request).health())


class GridConnectProvisioningSessionCollectionView(HomeAssistantView):
    """Collection endpoint for provisioning sessions."""

    url = f"{PROVISIONING_API_BASE}/sessions"
    name = "api:grid_connect:provisioning:sessions"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Create a new provisioning session."""
        try:
            payload = await request.json() if request.can_read_body else {}
        except ValueError:
            return self.json_message(
                "Invalid JSON body.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        if not isinstance(payload, dict):
            return self.json_message(
                "Expected a JSON object body.",
                status_code=HTTPStatus.BAD_REQUEST,
            )

        session = _server_from_request(request).create_session(
            model=payload.get("model"),
            metadata=payload.get("metadata")
            if isinstance(payload.get("metadata"), dict)
            else None,
        )
        return self.json(session.as_dict(), status_code=HTTPStatus.CREATED)


class GridConnectProvisioningSessionResourceView(HomeAssistantView):
    """Resource endpoint for a single provisioning session."""

    url = f"{PROVISIONING_API_BASE}/sessions/{{session_id}}"
    name = "api:grid_connect:provisioning:session"
    requires_auth = True

    async def get(self, request: web.Request, session_id: str) -> web.Response:
        """Return the current state of a provisioning session."""
        session = _server_from_request(request).get_session(session_id)
        if session is None:
            return self.json_message(
                "Provisioning session not found.",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return self.json(session.as_dict())

    async def patch(self, request: web.Request, session_id: str) -> web.Response:
        """Update mutable fields on a provisioning session."""
        try:
            payload = await request.json()
        except ValueError:
            return self.json_message(
                "Invalid JSON body.",
                status_code=HTTPStatus.BAD_REQUEST,
            )

        if not isinstance(payload, dict):
            return self.json_message(
                "Expected a JSON object body.",
                status_code=HTTPStatus.BAD_REQUEST,
            )

        session = _server_from_request(request).update_session(
            session_id,
            status=payload.get("status")
            if isinstance(payload.get("status"), str)
            else None,
            model=payload.get("model")
            if isinstance(payload.get("model"), str)
            else None,
            metadata=payload.get("metadata")
            if isinstance(payload.get("metadata"), dict)
            else None,
        )
        if session is None:
            return self.json_message(
                "Provisioning session not found.",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return self.json(session.as_dict())

    async def delete(self, request: web.Request, session_id: str) -> web.Response:
        """Delete a provisioning session."""
        if not _server_from_request(request).delete_session(session_id):
            return self.json_message(
                "Provisioning session not found.",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return self.json({"deleted": True, "session_id": session_id})


@callback
def async_setup_provisioning_server(hass: HomeAssistant) -> GridConnectProvisioningServer:
    """Create and register the Grid Connect provisioning server."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    server = domain_data.get(DATA_SERVER)
    if server is not None:
        return server

    server = GridConnectProvisioningServer(hass)
    domain_data[DATA_SERVER] = server

    hass.http.register_view(GridConnectProvisioningHealthView)
    hass.http.register_view(GridConnectProvisioningSessionCollectionView)
    hass.http.register_view(GridConnectProvisioningSessionResourceView)
    _LOGGER.info("Registered Grid Connect provisioning server endpoints")
    return server
