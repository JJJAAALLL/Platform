"""Permission helpers for organization assets and event visibility."""
from config import READABLE_EVENT_VISIBILITY


def can_edit_org(user, org_id):
    return bool(user) and int(user["organization_id"]) == int(org_id)


def can_view_org_assets(user, org_id):
    return bool(user)


def can_view_event(user, event_org_id, visibility):
    if not user:
        return False
    return visibility in READABLE_EVENT_VISIBILITY or can_edit_org(user, event_org_id)


def event_access_params(user, org_id=None):
    params = list(READABLE_EVENT_VISIBILITY)
    params.append(int(user["organization_id"]))
    if org_id is not None:
        params.append(int(org_id))
    return tuple(params)
