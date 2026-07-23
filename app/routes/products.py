import os
import uuid

from flask import (
    Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for,
)

from ..db import get_db
from ..security import login_required

bp = Blueprint("products", __name__, url_prefix="/products")

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
PRICE_MAX = 100_000_000


def save_image(file):
    """확장자 화이트리스트 검증 후 랜덤 파일명으로 저장. 실패 시 (None, 에러) 반환."""
    if not file or not file.filename:
        return None, None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        return None, "이미지는 png/jpg/jpeg/gif/webp만 업로드할 수 있습니다."
    # 사용자 파일명을 그대로 쓰지 않음 (경로 조작·덮어쓰기 방지)
    name = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(current_app.config["UPLOAD_DIR"], name))
    return name, None


def parse_form():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    price_raw = request.form.get("price", "").strip()

    if not title or len(title) > 100:
        return None, "상품명은 1~100자여야 합니다."
    if len(description) > 2000:
        return None, "상품 설명은 2000자 이내여야 합니다."
    if not price_raw.isdigit() or int(price_raw) > PRICE_MAX:
        return None, "가격은 0 ~ 1억 사이의 숫자여야 합니다."
    return {"title": title, "description": description, "price": int(price_raw)}, None


@bp.route("/")
def index():
    q = request.args.get("q", "").strip()
    db = get_db()
    if q:
        rows = db.execute(
            "SELECT id, title FROM products WHERE status = 'active' AND title LIKE ? "
            "ORDER BY id DESC",
            (f"%{q}%",),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, title FROM products WHERE status = 'active' ORDER BY id DESC"
        ).fetchall()
    history = []
    if g.user:
        history = db.execute(
            "SELECT m.content, m.created_at, u.username FROM messages m "
            "JOIN users u ON u.id = m.sender_id "
            "WHERE m.receiver_id IS NULL ORDER BY m.id DESC LIMIT 50"
        ).fetchall()[::-1]
    return render_template("products/list.html", products=rows, q=q, history=history)


@bp.route("/new", methods=("GET", "POST"))
@login_required
def new():
    if request.method == "POST":
        data, error = parse_form()
        if error is None:
            image, error = save_image(request.files.get("image"))
        if error:
            flash(error)
        else:
            cur = get_db().execute(
                "INSERT INTO products (title, description, price, image, seller_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (data["title"], data["description"], data["price"], image, g.user["id"]),
            )
            return redirect(url_for("products.detail", product_id=cur.lastrowid))
    return render_template("products/new.html")


@bp.route("/<int:product_id>")
def detail(product_id):
    product = get_db().execute(
        "SELECT p.*, u.username AS seller_name FROM products p "
        "JOIN users u ON u.id = p.seller_id WHERE p.id = ?",
        (product_id,),
    ).fetchone()
    if product is None:
        abort(404)
    is_manager = g.user and (g.user["id"] == product["seller_id"] or g.user["role"] == "admin")
    # 차단된 상품은 판매자·관리자 외에는 노출하지 않음
    if product["status"] == "blocked" and not is_manager:
        abort(404)
    return render_template("products/detail.html", product=product, is_manager=is_manager)


@bp.route("/mine")
@login_required
def mine():
    rows = get_db().execute(
        "SELECT id, title, price, status, created_at FROM products WHERE seller_id = ? "
        "ORDER BY id DESC",
        (g.user["id"],),
    ).fetchall()
    return render_template("products/mine.html", products=rows)


def get_owned(product_id):
    """수정·삭제 전 소유자 검증. 관리자는 허용 (IDOR 방지 핵심 지점)."""
    product = get_db().execute(
        "SELECT * FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    if product is None:
        abort(404)
    if g.user["id"] != product["seller_id"] and g.user["role"] != "admin":
        abort(403)
    return product


@bp.route("/<int:product_id>/edit", methods=("GET", "POST"))
@login_required
def edit(product_id):
    product = get_owned(product_id)
    if request.method == "POST":
        data, error = parse_form()
        image = product["image"]
        if error is None and request.files.get("image") and request.files["image"].filename:
            image, error = save_image(request.files.get("image"))
        if error:
            flash(error)
        else:
            get_db().execute(
                "UPDATE products SET title = ?, description = ?, price = ?, image = ? "
                "WHERE id = ?",
                (data["title"], data["description"], data["price"], image, product_id),
            )
            return redirect(url_for("products.detail", product_id=product_id))
    return render_template("products/edit.html", product=product)


@bp.route("/<int:product_id>/delete", methods=("POST",))
@login_required
def delete(product_id):
    get_owned(product_id)
    get_db().execute("DELETE FROM products WHERE id = ?", (product_id,))
    flash("상품을 삭제했습니다.")
    return redirect(url_for("products.mine"))
