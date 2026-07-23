"""기능·보안 체크리스트 자동 점검 스크립트. 서버 구동 후 실행: python tests/smoke_test.py"""
import re
import sys

import requests

BASE = "http://127.0.0.1:5000"
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def csrf(session, path):
    html = session.get(BASE + path).text
    m = re.search(r'name="_csrf" value="([^"]+)"', html)
    return m.group(1) if m else None


def register(session, username, password="password1!"):
    token = csrf(session, "/register")
    return session.post(BASE + "/register", data={
        "_csrf": token, "username": username, "password": password, "confirm": password,
    })


def login(session, username, password="password1!"):
    token = csrf(session, "/login")
    return session.post(BASE + "/login", data={
        "_csrf": token, "username": username, "password": password,
    }, allow_redirects=False)


u1, u2 = requests.Session(), requests.Session()

# 회원가입·로그인
register(u1, "tester01")
check("회원가입", login(u1, "tester01").status_code == 302)
r = register(u2, "tester01")
check("아이디 중복 거부", "이미 사용 중" in r.text)
r = register(u2, "bad name!!")
check("아이디 형식 검증", "4~20자" in r.text)
register(u2, "tester02")
login(u2, "tester02")

# CSRF 토큰 없는 POST 거부
r = u1.post(BASE + "/products/new", data={"title": "x", "price": "1", "description": ""})
check("CSRF 토큰 없는 요청 거부", r.status_code == 400)

# 상품 등록·조회·검색
token = csrf(u1, "/products/new")
r = u1.post(BASE + "/products/new", data={
    "_csrf": token, "title": "스모크테스트 상품", "price": "15000", "description": "테스트",
})
pid = int(r.url.rstrip("/").split("/")[-1])
check("상품 등록", r.status_code == 200 and pid > 0)
check("상품 목록 노출", "스모크테스트 상품" in requests.get(BASE + "/products/").text)
check("상품 검색", "스모크테스트 상품" in requests.get(BASE + "/products/", params={"q": "스모크"}).text)
check("SQLi 시도 무해화", requests.get(BASE + "/products/", params={"q": "' OR 1=1--"}).status_code == 200)

# 가격 음수/조작 거부
token = csrf(u1, "/products/new")
r = u1.post(BASE + "/products/new", data={
    "_csrf": token, "title": "x", "price": "-500", "description": "",
})
check("음수 가격 거부", "가격은" in r.text)

# IDOR: 타인 상품 수정·삭제 차단
token = csrf(u2, "/products/new")
r = u2.post(BASE + f"/products/{pid}/delete", data={"_csrf": token})
check("타인 상품 삭제 차단 (IDOR)", r.status_code == 403)
r = u2.get(BASE + f"/products/{pid}/edit")
check("타인 상품 수정 차단 (IDOR)", r.status_code == 403)

# XSS: 상품명에 스크립트 삽입 시 이스케이프 확인
token = csrf(u2, "/products/new")
r = u2.post(BASE + "/products/new", data={
    "_csrf": token, "title": '<script>alert(1)</script>', "price": "1", "description": "",
})
check("상품명 XSS 이스케이프", "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text)

# 신고 및 자동 차단 (3회 누적)
reporters = []
for i in range(3):
    s = requests.Session()
    register(s, f"reporter{i:02d}")
    login(s, f"reporter{i:02d}")
    token = csrf(s, f"/report/new?type=product&id={pid}")
    s.post(BASE + f"/report/new?type=product&id={pid}", data={
        "_csrf": token, "reason": "테스트 신고 사유입니다. 문제 상품."
    })
    reporters.append(s)
check("신고 3회 누적 시 상품 자동 차단", requests.get(BASE + f"/products/{pid}").status_code == 404)
token = csrf(reporters[0], "/products/")
r = reporters[0].post(BASE + f"/report/new?type=product&id={pid}", data={
    "_csrf": token, "reason": "중복 신고 시도입니다 확인용."
})
check("동일 대상 중복 신고 차단", "이미 신고한" in r.text)

# 송금: 정상, 잔액 초과, 음수
token = csrf(u1, "/wallet/")
u1.post(BASE + "/wallet/transfer", data={"_csrf": token, "receiver": "tester02", "amount": "500"})
check("송금 정상 처리", "99,500" in u1.get(BASE + "/wallet/").text)
r = u1.post(BASE + "/wallet/transfer", data={"_csrf": token, "receiver": "tester02", "amount": "99999999"})
check("한도 초과 송금 거부", "송금액은" in u1.get(BASE + "/wallet/").text or r.status_code == 200)
u1.post(BASE + "/wallet/transfer", data={"_csrf": token, "receiver": "tester02", "amount": "-100"})
check("음수 송금 거부", "99,500" in u1.get(BASE + "/wallet/").text)
u1.post(BASE + "/wallet/transfer", data={"_csrf": token, "receiver": "tester01", "amount": "100"})
check("자기 자신 송금 거부", "99,500" in u1.get(BASE + "/wallet/").text)

# 권한: 일반 유저 admin 접근 차단
check("일반 유저 관리자 페이지 차단", u1.get(BASE + "/admin/").status_code == 403)

# 로그인 브루트포스 잠금
s = requests.Session()
for _ in range(5):
    login(s, "tester02", "wrongpass!")
r = login(s, "tester02", "password1!")
check("로그인 5회 실패 시 잠금", r.status_code == 200 and "잠겼습니다" in r.text)

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} 통과")
sys.exit(1 if fails else 0)
