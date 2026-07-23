import sqlite3

from flask import (
    Blueprint, abort, flash, g, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db
from ..security import (
    login_failed, login_locked, login_required, login_succeeded,
    valid_password, valid_username,
)

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = None
        if not valid_username(username):
            error = "아이디는 영문/숫자/밑줄 4~20자여야 합니다."
        elif not valid_password(password):
            error = "비밀번호는 8자 이상이어야 합니다."
        elif password != confirm:
            error = "비밀번호 확인이 일치하지 않습니다."

        if error is None:
            try:
                get_db().execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
            except sqlite3.IntegrityError:
                error = "이미 사용 중인 아이디입니다."
            else:
                flash("가입 완료. 로그인해 주세요.")
                return redirect(url_for("auth.login"))
        flash(error)
    return render_template("auth/register.html")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if login_locked(username):
            flash("로그인 실패가 누적되어 잠시 잠겼습니다. 5분 후 다시 시도해 주세요.")
            return render_template("auth/login.html")

        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        # 아이디 존재 여부를 구분해서 알려주지 않음 (계정 열거 방지)
        if user is None or not check_password_hash(user["password_hash"], password):
            login_failed(username)
            flash("아이디 또는 비밀번호가 올바르지 않습니다.")
        elif user["status"] != "active":
            flash("휴면 처리된 계정입니다. 관리자에게 문의해 주세요.")
        else:
            login_succeeded(username)
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("products.index"))
    return render_template("auth/login.html")


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    return redirect(url_for("home"))


@bp.route("/users/<int:user_id>")
@login_required
def profile(user_id):
    user = get_db().execute(
        "SELECT id, username, bio, status, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if user is None:
        abort(404)
    products = get_db().execute(
        "SELECT id, title, price FROM products WHERE seller_id = ? AND status = 'active' "
        "ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    return render_template("auth/profile.html", user=user, products=products)


@bp.route("/mypage", methods=("GET", "POST"))
@login_required
def mypage():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "bio":
            bio = request.form.get("bio", "").strip()
            if len(bio) > 200:
                flash("소개글은 200자 이내여야 합니다.")
            else:
                db.execute("UPDATE users SET bio = ? WHERE id = ?", (bio, g.user["id"]))
                flash("소개글을 수정했습니다.")
        elif action == "password":
            current = request.form.get("current_password", "")
            new = request.form.get("new_password", "")
            # 비밀번호 변경은 현재 비밀번호 재확인 필수 (세션 탈취 시 계정 탈취 방지)
            if not check_password_hash(g.user["password_hash"], current):
                flash("현재 비밀번호가 올바르지 않습니다.")
            elif not valid_password(new):
                flash("새 비밀번호는 8자 이상이어야 합니다.")
            else:
                db.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new), g.user["id"]),
                )
                flash("비밀번호를 변경했습니다.")
        return redirect(url_for("auth.mypage"))
    return render_template("auth/mypage.html")
