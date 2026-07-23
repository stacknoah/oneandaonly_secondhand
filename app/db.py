import os
import sqlite3

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        # isolation_level=None: 기본 autocommit. 송금처럼 원자성이 필요한 곳만 명시적 BEGIN IMMEDIATE 사용
        g.db = sqlite3.connect(current_app.config["DATABASE"], isolation_level=None)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))
    # 관리자 계정 시드. 데모 편의상 기본 비밀번호 제공, 운영에서는 ADMIN_PASSWORD 환경변수 필수
    admin_pw = os.environ.get("ADMIN_PASSWORD", "admin1234!")
    db.execute(
        "INSERT INTO users (username, password_hash, bio, role) VALUES (?, ?, ?, 'admin')",
        ("admin", generate_password_hash(admin_pw), "플랫폼 관리자"),
    )


@click.command("init-db")
def init_db_command():
    init_db()
    click.echo("DB 초기화 완료. 관리자 계정: admin")


@click.command("seed-demo")
def seed_demo_command():
    db = get_db()
    for name in ("alice", "bob"):
        db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (name, generate_password_hash("password1!")),
        )
    rows = db.execute("SELECT id, username FROM users WHERE username IN ('alice','bob')").fetchall()
    ids = {r["username"]: r["id"] for r in rows}
    demo = [
        ("아이패드 에어 5세대", "생활기스 약간, 배터리 성능 92%", 450000, ids["alice"]),
        ("캠핑 의자 2개", "한 시즌 사용, 상태 좋음", 30000, ids["alice"]),
        ("기계식 키보드", "적축, 풀윤활 완료", 80000, ids["bob"]),
    ]
    db.executemany(
        "INSERT INTO products (title, description, price, seller_id) VALUES (?, ?, ?, ?)", demo
    )
    click.echo("데모 데이터 생성 완료 (alice / bob, 비밀번호: password1!)")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
