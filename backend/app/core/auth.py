from collections.abc import Callable
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.data import repository
from app.models.schemas import UserPublic


READ_ROLES = {
    "admin",
    "maintenance_engineer",
    "maintenance_technician",
    "maintenance_supervisor",
    "reliability_engineer",
    "planner",
    "operator",
}
DECISION_ROLES = {"admin", "maintenance_engineer", "reliability_engineer", "planner"}
WORK_ORDER_ACTION_ROLES = {
    "admin",
    "maintenance_engineer",
    "maintenance_technician",
    "maintenance_supervisor",
    "reliability_engineer",
    "planner",
}
WORK_ORDER_ASSIGNMENT_ROLES = {"admin", "maintenance_supervisor"}
TECHNICIAN_ASSISTANT_ROLES = {"maintenance_technician"}
SUPERVISOR_ASSISTANT_ROLES = {"maintenance_supervisor"}
FEEDBACK_ROLES = {"admin", "maintenance_engineer", "reliability_engineer"}
INGESTION_ROLES = {"admin", "reliability_engineer", "iot_service"}
STREAMING_STATUS_ROLES = {"admin", "reliability_engineer"}
ADMIN_ROLES = {"admin"}

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer_scheme)],
) -> UserPublic:
    settings = get_settings()
    if not settings.auth_enabled:
        return UserPublic(
            id="AUTH-DISABLED",
            email="auth-disabled@local",
            display_name="Auth Disabled",
            role="admin",
            is_active=True,
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = repository.get_user_by_id(user_id)
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive or not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return UserPublic(**user)


def require_roles(*roles: str) -> Callable[[UserPublic], UserPublic]:
    allowed = set(roles)

    def dependency(current_user: Annotated[UserPublic, Depends(get_current_user)]) -> UserPublic:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions",
            )
        return current_user

    return dependency
