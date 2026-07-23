import sqlite3

from flask import (
    Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for,
)

from ..db import get_db
from ..security import login_required

bp = Blueprint("reports", __name__, url_prefix="/report")


def load_target(target_type, target_id):
    db = get_db()
    if target_type == "product":
        row = db.execute(
            "SELECT p.id, p.title AS label, p.seller_id FROM products p WHERE p.id = ?",
            (target_id,),
        ).fetchone()
    elif target_type == "user":
        row = db.execute(
            "SELECT id, username AS label, role FROM users WHERE id = ?", (target_id,)
        ).fetchone()
    else:
        row = None
    if row is None:
        abort(404)
    return row


@bp.route("/new", methods=("GET", "POST"))
@login_required
def new():
    target_type = request.values.get("type", "")
    target_id = request.values.get("id", "")
    if target_type not in ("user", "product") or not target_id.isdigit():
        abort(400)
    target_id = int(target_id)
    target = load_target(target_type, target_id)

    # 자기 자신·본인 상품 신고 방지
    if target_type == "user" and target_id == g.user["id"]:
        abort(400)
    if target_type == "product" and target["seller_id"] == g.user["id"]:
        abort(400)

    if request.method == "POST":
        reason = request.form.get("reason", "").strip()
        if not (10 <= len(reason) <= 500):
            flash("신고 사유는 10~500자로 작성해 주세요.")
        else:
            db = get_db()
            try:
                # UNIQUE(reporter, target)로 동일 대상 중복 신고 차단 (신고 남용 방지)
                db.execute(
                    "INSERT INTO reports (reporter_id, target_type, target_id, reason) "
                    "VALUES (?, ?, ?, ?)",
                    (g.user["id"], target_type, target_id, reason),
                )
            except sqlite3.IntegrityError:
                flash("이미 신고한 대상입니다.")
                return redirect(url_for("products.index"))
            apply_threshold(target_type, target_id)
            flash("신고가 접수되었습니다.")
            return redirect(url_for("products.index"))
    return render_template("reports/new.html", target_type=target_type, target=target)


def apply_threshold(target_type, target_id):
    """누적 신고가 기준치를 넘으면 상품은 차단, 유저는 휴면 전환."""
    db = get_db()
    count = db.execute(
        "SELECT COUNT(*) AS c FROM reports WHERE target_type = ? AND target_id = ?",
        (target_type, target_id),
    ).fetchone()["c"]
    if count < current_app.config["REPORT_THRESHOLD"]:
        return
    if target_type == "product":
        db.execute("UPDATE products SET status = 'blocked' WHERE id = ?", (target_id,))
    else:
        # 관리자 계정은 신고 누적으로 휴면 전환되지 않음 (운영 계정 잠금 공격 방지)
        db.execute(
            "UPDATE users SET status = 'dormant' WHERE id = ? AND role != 'admin'",
            (target_id,),
        )
