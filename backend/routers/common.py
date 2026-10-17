from fastapi import HTTPException

from db import store


def load_session(sid: str) -> dict:
    st = store.get("sessions", sid)
    if not st:
        raise HTTPException(404, "session not found")
    return st
