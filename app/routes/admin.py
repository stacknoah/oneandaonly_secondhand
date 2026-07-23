from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..db import get_db
from ..security import admin_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@admin_required
def index():
    db = get_db()
    stats = {
        "users": db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"],
        "dormant": db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE status = 'dormant'"
        ).fetchone()["c"],
        "products": db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"],
        "blocked": db.execute(
            "SELECT COUNT(*) AS c FROM products WHERE status = 'blocked'"
        ).fetchone()["c"],
        "reports": db.execute("SELECT COUNT(*) AS c FROM reports").fetchone()["c"],
    }
    return render_template("admin/index.html", stats=stats)


@bp.route("/users")
@admin_required
def users():
    rows = get_db().execute(
        "SELECT id, username, role, status, balance, created_at FROM users ORDER BY id"
    ).fetchall()
    return render_template("admin/users.html", users=rows)


@bp.route("/users/<int:user_id>/status", methods=("POST",))
@admin_required
def user_status(user_id):
    status = request.form.get("status")
    if status not in ("active", "dormant"):
        abort(400)
    if user_id == g.user["id"]:
        flash("자기 자신의 상태는 변경할 수 없습니다.")
        return redirect(url_for("admin.users"))
    get_db().execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/delete", methods=("POST",))
@admin_required
def user_delete(user_id):
    if user_id == g.user["id"]:
        flash("자기 자신은 삭제할 수 없습니다.")
        return redirect(url_for("admin.users"))
    get_db().execute("DELETE FROM users WHERE id = ?", (user_id,))
    return redirect(url_for("admin.users"))


@bp.route("/products")
@admin_required
def products():
    rows = get_db().execute(
        "SELECT p.id, p.title, p.price, p.status, u.username AS seller "
        "FROM products p JOIN users u ON u.id = p.seller_id ORDER BY p.id DESC"
    ).fetchall()
    return render_template("admin/products.html", products=rows)


@bp.route("/products/<int:product_id>/status", methods=("POST",))
@admin_required
def product_status(product_id):
    status = request.form.get("status")
    if status not in ("active", "blocked"):
        abort(400)
    get_db().execute("UPDATE products SET status = ? WHERE id = ?", (status, product_id))
    return redirect(url_for("admin.products"))


@bp.route("/products/<int:product_id>/delete", methods=("POST",))
@admin_required
def product_delete(product_id):
    get_db().execute("DELETE FROM products WHERE id = ?", (product_id,))
    return redirect(url_for("admin.products"))


@bp.route("/messages")
@admin_required
def messages():
    rows = get_db().execute(
        "SELECT m.id, m.content, m.created_at, m.receiver_id, u.username AS sender "
        "FROM messages m JOIN users u ON u.id = m.sender_id ORDER BY m.id DESC LIMIT 100"
    ).fetchall()
    return render_template("admin/messages.html", messages=rows)


@bp.route("/messages/<int:message_id>/delete", methods=("POST",))
@admin_required
def message_delete(message_id):
    get_db().execute("DELETE FROM messages WHERE id = ?", (message_id,))
    return redirect(url_for("admin.messages"))


@bp.route("/transfers")
@admin_required
def transfers():
    rows = get_db().execute(
        "SELECT t.id, t.amount, t.created_at, s.username AS sender, r.username AS receiver "
        "FROM transfers t JOIN users s ON s.id = t.sender_id "
        "JOIN users r ON r.id = t.receiver_id ORDER BY t.id DESC LIMIT 100"
    ).fetchall()
    return render_template("admin/transfers.html", transfers=rows)


@bp.route("/reports")
@admin_required
def reports():
    rows = get_db().execute(
        "SELECT r.id, r.target_type, r.target_id, r.reason, r.created_at, "
        "u.username AS reporter FROM reports r JOIN users u ON u.id = r.reporter_id "
        "ORDER BY r.id DESC"
    ).fetchall()
    return render_template("admin/reports.html", reports=rows)
