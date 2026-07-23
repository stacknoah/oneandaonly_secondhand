import time

from flask import Blueprint, abort, g, render_template, session
from flask_socketio import emit, join_room

from .. import socketio
from ..db import get_db
from ..security import login_required

bp = Blueprint("chat", __name__, url_prefix="/chat")

MESSAGE_MAX = 500

# 채팅 도배 방지: 유저별 최근 전송 시각 (3초에 5건 허용)
_rate = {}


def rate_ok(user_id):
    now = time.time()
    recent = [t for t in _rate.get(user_id, []) if now - t < 3]
    if len(recent) >= 5:
        _rate[user_id] = recent
        return False
    recent.append(now)
    _rate[user_id] = recent
    return True


def socket_user():
    """소켓 이벤트마다 세션 기준으로 인증·상태 재확인. 클라이언트가 준 값은 신뢰하지 않음."""
    user_id = session.get("user_id")
    if user_id is None:
        return None
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None or user["status"] != "active":
        return None
    return user


def dm_room(a, b):
    lo, hi = sorted((a, b))
    return f"dm:{lo}:{hi}"


@bp.route("/dm")
@login_required
def inbox():
    # 대화 상대 목록: 내가 보냈거나 받은 DM의 상대방들
    rows = get_db().execute(
        "SELECT DISTINCT u.id, u.username FROM messages m "
        "JOIN users u ON u.id = CASE WHEN m.sender_id = ? THEN m.receiver_id ELSE m.sender_id END "
        "WHERE ? IN (m.sender_id, m.receiver_id) AND m.receiver_id IS NOT NULL",
        (g.user["id"], g.user["id"]),
    ).fetchall()
    return render_template("chat/inbox.html", partners=rows)


@bp.route("/dm/<int:peer_id>")
@login_required
def dm(peer_id):
    if peer_id == g.user["id"]:
        abort(400)
    peer = get_db().execute(
        "SELECT id, username FROM users WHERE id = ?", (peer_id,)
    ).fetchone()
    if peer is None:
        abort(404)
    history = get_db().execute(
        "SELECT m.content, m.created_at, m.sender_id, u.username FROM messages m "
        "JOIN users u ON u.id = m.sender_id "
        "WHERE (m.sender_id = ? AND m.receiver_id = ?) OR (m.sender_id = ? AND m.receiver_id = ?) "
        "ORDER BY m.id LIMIT 200",
        (g.user["id"], peer_id, peer_id, g.user["id"]),
    ).fetchall()
    return render_template("chat/dm.html", peer=peer, history=history)


@socketio.on("join_lobby")
def join_lobby():
    if socket_user() is None:
        return
    join_room("lobby")


@socketio.on("lobby_message")
def lobby_message(data):
    user = socket_user()
    if user is None:
        return
    content = ((data or {}).get("content") or "").strip()
    if not content or len(content) > MESSAGE_MAX or not rate_ok(user["id"]):
        return
    get_db().execute(
        "INSERT INTO messages (sender_id, receiver_id, content) VALUES (?, NULL, ?)",
        (user["id"], content),
    )
    emit("lobby_message", {"username": user["username"], "content": content}, to="lobby")


@socketio.on("join_dm")
def join_dm(data):
    user = socket_user()
    if user is None:
        return
    peer_id = (data or {}).get("peer_id")
    if not isinstance(peer_id, int) or peer_id == user["id"]:
        return
    # 방 이름은 서버가 세션 신원으로 계산. 클라이언트가 임의 방에 조인하는 것 차단
    join_room(dm_room(user["id"], peer_id))


@socketio.on("dm_message")
def dm_message(data):
    user = socket_user()
    if user is None:
        return
    peer_id = (data or {}).get("peer_id")
    content = ((data or {}).get("content") or "").strip()
    if not isinstance(peer_id, int) or peer_id == user["id"]:
        return
    if not content or len(content) > MESSAGE_MAX or not rate_ok(user["id"]):
        return
    peer = get_db().execute("SELECT id FROM users WHERE id = ?", (peer_id,)).fetchone()
    if peer is None:
        return
    get_db().execute(
        "INSERT INTO messages (sender_id, receiver_id, content) VALUES (?, ?, ?)",
        (user["id"], peer_id, content),
    )
    emit(
        "dm_message",
        {"username": user["username"], "sender_id": user["id"], "content": content},
        to=dm_room(user["id"], peer_id),
    )
