import functools
import re
import secrets
import time

from flask import abort, flash, g, redirect, request, session, url_for

from .db import get_db

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{4,20}$")
PASSWORD_MIN = 8

# 로그인 브루트포스 방어: username 기준 실패 횟수 추적 (데모용 인메모리, 운영은 Redis 등)
LOGIN_MAX_FAIL = 5
LOGIN_LOCK_SECONDS = 300
_login_fails = {}


def load_logged_in_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id is None:
        return
    user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user and user["status"] == "active":
        g.user = user
    else:
        # 휴면 전환·삭제된 계정은 기존 세션도 즉시 무효화
        session.clear()


def generate_csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def csrf_protect():
    if request.method == "POST":
        token = session.get("_csrf")
        sent = request.form.get("_csrf")
        if not token or not sent or not secrets.compare_digest(token, sent):
            abort(400)


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            flash("로그인이 필요합니다.")
            return redirect(url_for("auth.login"))
        return view(**kwargs)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None or g.user["role"] != "admin":
            abort(403)
        return view(**kwargs)
    return wrapped


def valid_username(username):
    return bool(USERNAME_RE.match(username or ""))


def valid_password(password):
    return password is not None and len(password) >= PASSWORD_MIN


def login_locked(username):
    rec = _login_fails.get(username)
    if not rec:
        return False
    fails, locked_until = rec
    if locked_until and time.time() < locked_until:
        return True
    if locked_until and time.time() >= locked_until:
        _login_fails.pop(username, None)
    return False


def login_failed(username):
    fails, _ = _login_fails.get(username, (0, None))
    fails += 1
    locked_until = time.time() + LOGIN_LOCK_SECONDS if fails >= LOGIN_MAX_FAIL else None
    _login_fails[username] = (fails, locked_until)


def login_succeeded(username):
    _login_fails.pop(username, None)
