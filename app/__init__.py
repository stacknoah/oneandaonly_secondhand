import os
import secrets

from flask import Flask, render_template
from flask_socketio import SocketIO

socketio = SocketIO()


def create_app():
    app = Flask(__name__)
    app.config.update(
        # 운영에서는 반드시 환경변수로 고정 키 주입. 미설정 시 매 부팅마다 랜덤 키(세션 초기화됨)
        SECRET_KEY=os.environ.get("SECRET_KEY", secrets.token_hex(32)),
        DATABASE=os.path.join(app.instance_path, "market.sqlite"),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,  # 업로드 2MB 제한
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        UPLOAD_DIR=os.path.join(app.static_folder, "uploads"),
        REPORT_THRESHOLD=3,  # 누적 신고 시 자동 차단/휴면 기준
    )
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    from . import db
    db.init_app(app)

    from . import security
    app.before_request(security.load_logged_in_user)
    app.before_request(security.csrf_protect)
    app.jinja_env.globals["csrf_token"] = security.generate_csrf_token

    from .routes import auth, products, chat, reports, wallet, admin
    app.register_blueprint(auth.bp)
    app.register_blueprint(products.bp)
    app.register_blueprint(chat.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(wallet.bp)
    app.register_blueprint(admin.bp)

    @app.route("/")
    def home():
        return render_template("home.html")

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("errors/error.html", code=400, message="잘못된 요청입니다."), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/error.html", code=403, message="접근 권한이 없습니다."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/error.html", code=404, message="페이지를 찾을 수 없습니다."), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("errors/error.html", code=413, message="파일이 너무 큽니다. (최대 2MB)"), 413

    socketio.init_app(app)
    return app
