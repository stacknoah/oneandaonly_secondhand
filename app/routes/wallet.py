from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..db import get_db
from ..security import login_required

bp = Blueprint("wallet", __name__, url_prefix="/wallet")

TRANSFER_MAX = 10_000_000


@bp.route("/")
@login_required
def index():
    history = get_db().execute(
        "SELECT t.amount, t.created_at, t.sender_id, s.username AS sender, r.username AS receiver "
        "FROM transfers t "
        "JOIN users s ON s.id = t.sender_id JOIN users r ON r.id = t.receiver_id "
        "WHERE ? IN (t.sender_id, t.receiver_id) ORDER BY t.id DESC LIMIT 50",
        (g.user["id"],),
    ).fetchall()
    balance = get_db().execute(
        "SELECT balance FROM users WHERE id = ?", (g.user["id"],)
    ).fetchone()["balance"]
    return render_template("wallet/index.html", history=history, balance=balance)


@bp.route("/transfer", methods=("POST",))
@login_required
def transfer():
    receiver_name = request.form.get("receiver", "").strip()
    amount_raw = request.form.get("amount", "").strip()

    # 금액은 서버에서 정수·범위 검증. 음수/0/문자열 조작 차단
    if not amount_raw.isdigit() or int(amount_raw) == 0 or int(amount_raw) > TRANSFER_MAX:
        flash("송금액은 1 ~ 10,000,000 사이의 숫자여야 합니다.")
        return redirect(url_for("wallet.index"))
    amount = int(amount_raw)

    db = get_db()
    receiver = db.execute(
        "SELECT id, status FROM users WHERE username = ?", (receiver_name,)
    ).fetchone()
    if receiver is None or receiver["status"] != "active":
        flash("받는 사람을 찾을 수 없습니다.")
        return redirect(url_for("wallet.index"))
    if receiver["id"] == g.user["id"]:
        flash("자기 자신에게는 송금할 수 없습니다.")
        return redirect(url_for("wallet.index"))

    # 잔액 확인과 차감을 한 트랜잭션으로 묶어 이중 지불(race condition) 방지
    try:
        db.execute("BEGIN IMMEDIATE")
        balance = db.execute(
            "SELECT balance FROM users WHERE id = ?", (g.user["id"],)
        ).fetchone()["balance"]
        if balance < amount:
            db.execute("ROLLBACK")
            flash("잔액이 부족합니다.")
            return redirect(url_for("wallet.index"))
        db.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ?", (amount, g.user["id"])
        )
        db.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?", (amount, receiver["id"])
        )
        db.execute(
            "INSERT INTO transfers (sender_id, receiver_id, amount) VALUES (?, ?, ?)",
            (g.user["id"], receiver["id"], amount),
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        flash("송금 처리 중 오류가 발생했습니다.")
        return redirect(url_for("wallet.index"))

    flash(f"{receiver_name}님에게 {amount:,}원을 송금했습니다.")
    return redirect(url_for("wallet.index"))
