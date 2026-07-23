# 중고나라 미니 (Tiny Second-hand Shopping Platform)

화이트햇 스쿨 4기 시큐어코딩 과제. Flask + SQLite 기반의 작은 중고거래 플랫폼.

## 기능

- 회원가입 / 로그인 / 프로필 조회 / 마이페이지 (소개글·비밀번호 변경)
- 상품 등록·조회·검색·수정·삭제 (사진 업로드 포함, 목록은 상품명만 → 클릭 시 상세)
- 실시간 전체 채팅, 1:1 채팅 (WebSocket)
- 신고 기능: 사유 작성, 누적 3회 시 상품 자동 차단·유저 자동 휴면 전환
- 유저 간 송금 (잔액 기반, 트랜잭션 처리)
- 관리자: 유저 휴면/활성/삭제, 상품 차단/삭제, 신고 내역 조회

## 프로젝트 구조

```
run.py                  실행 진입점
app/
  __init__.py           앱 팩토리, 보안 설정, 에러 핸들러
  db.py                 SQLite 연결, init-db / seed-demo CLI
  schema.sql            DB 스키마 (users, products, reports, messages, transfers)
  security.py           CSRF, 로그인/관리자 데코레이터, 입력 검증, 로그인 잠금
  routes/
    auth.py             회원가입, 로그인, 프로필, 마이페이지
    products.py         상품 CRUD, 검색, 이미지 업로드
    chat.py             전체 채팅, 1:1 채팅 (Flask-SocketIO)
    reports.py          신고 접수, 누적 신고 자동 차단
    wallet.py           송금, 거래 내역
    admin.py            관리자 대시보드, 유저/상품/신고 관리
  templates/, static/   Jinja 템플릿, CSS, 업로드 저장소
```

## 적용한 보안 조치 요약

| 위협 | 조치 |
|---|---|
| SQL Injection | 전 쿼리 파라미터 바인딩 |
| XSS | Jinja autoescape + 채팅은 textContent 렌더링 |
| CSRF | 세션 토큰 발급, 모든 POST에서 검증 |
| 비밀번호 유출 | scrypt 해시 저장 (werkzeug) |
| IDOR | 상품 수정·삭제 시 소유자 검증, 마이페이지는 세션 기준 |
| 악성 파일 업로드 | 확장자 화이트리스트, 랜덤 파일명, 2MB 제한 |
| 송금 이중 지불·금액 조작 | BEGIN IMMEDIATE 트랜잭션, 서버측 정수·범위 검증 |
| 브루트포스 | 로그인 5회 실패 시 5분 잠금 |
| 세션 탈취 | HttpOnly + SameSite=Lax 쿠키, 휴면 계정 세션 즉시 무효화 |
| 신고 남용 | 동일 대상 중복 신고 차단, 관리자 계정 자동 휴면 제외 |

상세 내용은 제출 보고서 참고.
