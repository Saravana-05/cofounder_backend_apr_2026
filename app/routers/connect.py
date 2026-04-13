# app/routers/connect.py
"""
Handles:
  POST /connect/{receiver_id}        — send a connection request
  GET  /connect/                     — list all connections for current user
  POST /connect/{connection_id}/accept  — accept a pending request
  POST /connect/{connection_id}/reject  — reject a pending request
  GET  /connect/{connection_id}/messages — fetch chat history
  POST /connect/{connection_id}/messages — send a message (REST fallback)
  WS   /connect/{connection_id}/ws   — real-time chat WebSocket
"""

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.auth_utils import get_current_user
import app.models as models
from app.email_utils import (
    send_connect_request_email,
    send_connection_accepted_email,
    send_new_message_email,
)
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/connect", tags=["connect"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ConnectionOut(BaseModel):
    id:          int
    sender_id:   int
    receiver_id: int
    status:      str
    created_at:  datetime
    sender_name:   str = ""
    receiver_name: str = ""
    other_user_id: int = 0
    other_name:    str = ""
    unread_count:  int = 0

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id:            int
    connection_id: int
    sender_id:     int
    content:       str
    is_read:       bool
    created_at:    datetime
    sender_name:   str = ""

    class Config:
        from_attributes = True


class SendMessageIn(BaseModel):
    content: str


# ── WebSocket connection manager ──────────────────────────────────────────────

class _ConnectionManager:
    """Holds active WebSocket connections keyed by connection_id → {user_id: ws}."""

    def __init__(self) -> None:
        # { connection_id: { user_id: WebSocket } }
        self._rooms: dict[int, dict[int, WebSocket]] = {}

    async def join(self, connection_id: int, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._rooms.setdefault(connection_id, {})[user_id] = ws
        logger.info("WS joined room=%s user=%s", connection_id, user_id)

    def leave(self, connection_id: int, user_id: int) -> None:
        room = self._rooms.get(connection_id, {})
        room.pop(user_id, None)
        if not room:
            self._rooms.pop(connection_id, None)
        logger.info("WS left  room=%s user=%s", connection_id, user_id)

    async def broadcast(self, connection_id: int, payload: dict[str, Any]) -> None:
        """Send JSON payload to every socket in the room."""
        room = self._rooms.get(connection_id, {})
        dead: list[int] = []
        for uid, ws in room.items():
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(uid)
        for uid in dead:
            room.pop(uid, None)

    def online_users(self, connection_id: int) -> list[int]:
        return list(self._rooms.get(connection_id, {}).keys())


manager = _ConnectionManager()


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_profile_name(user_id: int, db: Session) -> str:
    p = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
    return p.full_name if p else f"User {user_id}"


def _get_connection_or_404(connection_id: int, db: Session) -> models.Connection:
    conn = db.query(models.Connection).filter(models.Connection.id == connection_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


def _assert_participant(conn: models.Connection, user_id: int) -> None:
    if conn.sender_id != user_id and conn.receiver_id != user_id:
        raise HTTPException(status_code=403, detail="Not a participant in this connection")


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{receiver_id}", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
def send_connect_request(
    receiver_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if receiver_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot connect with yourself")

    # Prevent duplicate requests
    existing = (
        db.query(models.Connection)
        .filter(
            models.Connection.sender_id == current_user.id,
            models.Connection.receiver_id == receiver_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Connection already exists (status: {existing.status})")

    receiver = db.query(models.User).filter(models.User.id == receiver_id).first()
    if not receiver:
        raise HTTPException(status_code=404, detail="User not found")

    conn = models.Connection(sender_id=current_user.id, receiver_id=receiver_id, status="pending")
    db.add(conn)
    db.commit()
    db.refresh(conn)

    # Look up match score for the email
    match_row = (
        db.query(models.Match)
        .filter(models.Match.user_id == current_user.id, models.Match.matched_user_id == receiver_id)
        .first()
    )
    score = match_row.final_score if match_row else 0.0

    sender_name   = _get_profile_name(current_user.id, db)
    receiver_name = _get_profile_name(receiver_id, db)

    # Send email in background so the request returns immediately
    background_tasks.add_task(
        send_connect_request_email,
        to_email=receiver.email,
        to_name=receiver_name,
        from_name=sender_name,
        match_score=score,
        app_url=settings.APP_URL,
    )

    return _enrich(conn, current_user.id, db)


@router.get("/", response_model=list[ConnectionOut])
def list_connections(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    conns = (
        db.query(models.Connection)
        .filter(
            (models.Connection.sender_id == current_user.id) |
            (models.Connection.receiver_id == current_user.id)
        )
        .order_by(models.Connection.created_at.desc())
        .all()
    )
    return [_enrich(c, current_user.id, db) for c in conns]


@router.post("/{connection_id}/accept", response_model=ConnectionOut)
def accept_connection(
    connection_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    conn = _get_connection_or_404(connection_id, db)
    if conn.receiver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the receiver can accept")
    if conn.status != "pending":
        raise HTTPException(status_code=400, detail=f"Connection is already {conn.status}")

    conn.status = "accepted"
    db.commit()
    db.refresh(conn)

    acceptor_name = _get_profile_name(current_user.id, db)
    sender        = db.query(models.User).filter(models.User.id == conn.sender_id).first()
    sender_name   = _get_profile_name(conn.sender_id, db)

    background_tasks.add_task(
        send_connection_accepted_email,
        to_email=sender.email,
        to_name=sender_name,
        accepted_by=acceptor_name,
        app_url=settings.APP_URL,
    )

    return _enrich(conn, current_user.id, db)


@router.post("/{connection_id}/reject", response_model=ConnectionOut)
def reject_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    conn = _get_connection_or_404(connection_id, db)
    if conn.receiver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the receiver can reject")
    conn.status = "rejected"
    db.commit()
    db.refresh(conn)
    return _enrich(conn, current_user.id, db)


# ── messaging ─────────────────────────────────────────────────────────────────

@router.get("/{connection_id}/messages", response_model=list[MessageOut])
def get_messages(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    conn = _get_connection_or_404(connection_id, db)
    _assert_participant(conn, current_user.id)
    if conn.status != "accepted":
        raise HTTPException(status_code=403, detail="Connection not accepted yet")

    messages = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.connection_id == connection_id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )

    # Mark unread messages as read
    for m in messages:
        if m.sender_id != current_user.id and not m.is_read:
            m.is_read = True
    db.commit()

    return [_enrich_msg(m, db) for m in messages]


@router.post("/{connection_id}/messages", response_model=MessageOut, status_code=201)
async def send_message_rest(
    connection_id: int,
    body: SendMessageIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """REST fallback — use WebSocket when possible for real-time delivery."""
    return await _persist_and_broadcast(
        connection_id=connection_id,
        content=body.content,
        sender=current_user,
        background_tasks=background_tasks,
        db=db,
    )


# ── WebSocket ─────────────────────────────────────────────────────────────────

@router.websocket("/{connection_id}/ws")
async def chat_websocket(
    connection_id: int,
    websocket: WebSocket,
    token: str,                       # passed as ?token=<jwt> query param
    db: Session = Depends(get_db),
):
    # Authenticate via token query param (browsers can't set WS headers)
    from app.auth_utils import get_current_user as _auth
    from fastapi.security import OAuth2PasswordBearer
    from jose import jwt, JWTError

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        email: str = payload.get("sub")
        current_user = db.query(models.User).filter(models.User.email == email).first()
        if not current_user:
            await websocket.close(code=4001)
            return
    except JWTError:
        await websocket.close(code=4001)
        return

    conn = db.query(models.Connection).filter(models.Connection.id == connection_id).first()
    if not conn or conn.status != "accepted":
        await websocket.close(code=4003)
        return
    if conn.sender_id != current_user.id and conn.receiver_id != current_user.id:
        await websocket.close(code=4003)
        return

    await manager.join(connection_id, current_user.id, websocket)

    # Notify the room that this user is online
    await manager.broadcast(connection_id, {
        "type": "presence",
        "user_id": current_user.id,
        "online": True,
    })

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            if data.get("type") == "message":
                content = (data.get("content") or "").strip()
                if not content:
                    continue

                msg = models.ChatMessage(
                    connection_id=connection_id,
                    sender_id=current_user.id,
                    content=content,
                )
                db.add(msg)
                db.commit()
                db.refresh(msg)

                sender_name = _get_profile_name(current_user.id, db)

                payload_out = {
                    "type":          "message",
                    "id":            msg.id,
                    "connection_id": connection_id,
                    "sender_id":     current_user.id,
                    "sender_name":   sender_name,
                    "content":       msg.content,
                    "is_read":       False,
                    "created_at":    msg.created_at.isoformat(),
                }
                await manager.broadcast(connection_id, payload_out)

                # Email notification only if the other user is NOT in the room
                other_id = conn.receiver_id if conn.sender_id == current_user.id else conn.sender_id
                if other_id not in manager.online_users(connection_id):
                    other_user = db.query(models.User).filter(models.User.id == other_id).first()
                    other_name = _get_profile_name(other_id, db)
                    if other_user:
                        from fastapi import BackgroundTasks as BT
                        # Fire-and-forget in the same event loop
                        import asyncio
                        asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: send_new_message_email(
                                to_email=other_user.email,
                                to_name=other_name,
                                from_name=sender_name,
                                preview=content,
                                app_url=settings.APP_URL,
                            ),
                        )

            elif data.get("type") == "read":
                # Mark messages as read
                db.query(models.ChatMessage).filter(
                    models.ChatMessage.connection_id == connection_id,
                    models.ChatMessage.sender_id != current_user.id,
                    models.ChatMessage.is_read == False,
                ).update({"is_read": True})
                db.commit()
                await manager.broadcast(connection_id, {"type": "read", "reader_id": current_user.id})

    except WebSocketDisconnect:
        manager.leave(connection_id, current_user.id)
        await manager.broadcast(connection_id, {
            "type": "presence",
            "user_id": current_user.id,
            "online": False,
        })


# ── internal helpers ──────────────────────────────────────────────────────────

async def _persist_and_broadcast(
    *,
    connection_id: int,
    content: str,
    sender: models.User,
    background_tasks: BackgroundTasks,
    db: Session,
) -> models.ChatMessage:
    conn = _get_connection_or_404(connection_id, db)
    _assert_participant(conn, sender.id)
    if conn.status != "accepted":
        raise HTTPException(status_code=403, detail="Connection not accepted yet")

    msg = models.ChatMessage(connection_id=connection_id, sender_id=sender.id, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)

    sender_name = _get_profile_name(sender.id, db)
    payload_out = {
        "type":          "message",
        "id":            msg.id,
        "connection_id": connection_id,
        "sender_id":     sender.id,
        "sender_name":   sender_name,
        "content":       msg.content,
        "is_read":       False,
        "created_at":    msg.created_at.isoformat(),
    }
    await manager.broadcast(connection_id, payload_out)

    other_id = conn.receiver_id if conn.sender_id == sender.id else conn.sender_id
    if other_id not in manager.online_users(connection_id):
        other_user = db.query(models.User).filter(models.User.id == other_id).first()
        other_name = _get_profile_name(other_id, db)
        if other_user:
            background_tasks.add_task(
                send_new_message_email,
                to_email=other_user.email,
                to_name=other_name,
                from_name=sender_name,
                preview=content,
                app_url=settings.APP_URL,
            )

    return _enrich_msg(msg, db)


def _enrich(conn: models.Connection, current_user_id: int, db: Session) -> dict:
    sender_name   = _get_profile_name(conn.sender_id, db)
    receiver_name = _get_profile_name(conn.receiver_id, db)
    other_id   = conn.receiver_id if conn.sender_id == current_user_id else conn.sender_id
    other_name = receiver_name    if conn.sender_id == current_user_id else sender_name
    unread = (
        db.query(models.ChatMessage)
        .filter(
            models.ChatMessage.connection_id == conn.id,
            models.ChatMessage.sender_id != current_user_id,
            models.ChatMessage.is_read == False,
        )
        .count()
    )
    return {
        "id":            conn.id,
        "sender_id":     conn.sender_id,
        "receiver_id":   conn.receiver_id,
        "status":        conn.status,
        "created_at":    conn.created_at,
        "sender_name":   sender_name,
        "receiver_name": receiver_name,
        "other_user_id": other_id,
        "other_name":    other_name,
        "unread_count":  unread,
    }


def _enrich_msg(msg: models.ChatMessage, db: Session) -> dict:
    return {
        "id":            msg.id,
        "connection_id": msg.connection_id,
        "sender_id":     msg.sender_id,
        "content":       msg.content,
        "is_read":       msg.is_read,
        "created_at":    msg.created_at,
        "sender_name":   _get_profile_name(msg.sender_id, db),
    }