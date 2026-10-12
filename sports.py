"""아이랑 운동교실(용인) 수집기

용인도시공사가 운영하는 시 체육센터 강좌(수영·헬스·요가·필라테스·댄스·사우나)를
각 센터 홈페이지의 '프로그램' 안내 표에서 읽어 output/sports.json 으로 저장한다.
- 센터 4곳(용인시민·기흥국민·아르피아·남사)은 같은 홈페이지 틀(m03/번호)을 쓴다.
- 모든 사이트의 robots.txt 확인: 수집 제한 없음. 요청 사이 1초 쉬어 서버 부담을 줄인다.
- 강사 이름 등 개인정보는 가져오지 않는다.
- 어떤 센터를 못 읽으면 지난번 결과를 그대로 쓴다.
"""

import json
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (yongin-edu-collector; +https://yongin.songgollab.co.kr)"}

CENTERS = [
    {"id": "ysports", "name": "용인시민체육센터", "area": "처인구 포곡읍", "addr": "용인시 처인구 포곡읍 금어로 317", "tel": "031-321-1782",
     "hours": "평일 06:00~22:00 · 토 09:00~18:00", "closed": "일요일·공휴일 휴관", "tags": ["수영", "헬스", "요가·필라테스", "댄스·에어로빅", "사우나", "골프", "스쿼시"],
     "web": "https://www.ysports.or.kr", "apply": "https://www.ysports.or.kr/m04/1/popup.asp", "site": "https://www.ysports.or.kr"},
    {"id": "giheung", "name": "기흥국민체육센터", "area": "기흥구 흥덕", "addr": "용인시 기흥구 흥덕2로 110", "tel": "031-213-6581",
     "hours": "평일 06:00~22:00 · 토 09:00~18:00", "closed": "일요일·공휴일 휴관", "tags": ["수영", "댄스·에어로빅", "파크골프"],
     "web": "https://www.yongings.co.kr", "apply": "https://www.yongings.co.kr/m04/1/popup.asp", "site": "https://www.yongings.co.kr"},
    {"id": "arpia", "name": "아르피아스포츠센터", "area": "수지구 풍덕천", "addr": "용인시 수지구 포은대로 499", "tel": "031-263-6581",
     "hours": "평일 06:00~22:00 · 토 09:00~18:00", "closed": "일요일·공휴일 휴관", "tags": ["수영", "헬스", "요가·필라테스", "댄스·에어로빅", "스피닝", "인공암벽"],
     "web": "https://www.yonginap.co.kr", "apply": "https://www.yonginap.co.kr/m04/1/popup.asp", "site": "https://www.yonginap.co.kr"},
    {"id": "namsa", "name": "남사스포츠센터", "area": "처인구 남사읍", "addr": "용인시 처인구 남사읍 한숲로 100", "tel": "031-8097-7800",
     "hours": "평일 06:00~22:00 · 토 09:00~18:00", "closed": "일요일·공휴일 휴관", "tags": ["수영", "헬스", "요가·필라테스", "댄스·에어로빅", "스피닝", "스쿼시", "골프"],
     "web": "https://www.namsasportscenter.or.kr", "apply": "https://www.namsasportscenter.or.kr/m04/1/popup.asp", "site": "https://www.namsasportscenter.or.kr"},
    {"id": "indoor", "name": "용인실내체육관", "area": "처인구 마평동", "addr": "용인시 처인구 경안천로 76", "tel": "031-323-5211",
     "hours": "평일 06:00~22:00 · 토 09:00~18:00", "closed": "일요일·공휴일 휴관", "tags": ["헬스", "댄스·에어로빅", "탁구", "골프"],
     "web": "https://www.yuc.co.kr/www/wpge/m_534/contents.do", "apply": "", "visit": "강습은 방문 접수"},
    {"id": "dongbaek", "name": "동백미르휴먼센터 스포츠센터", "area": "기흥구 동백", "addr": "용인시 기흥구 동백중앙로 222", "tel": "031-274-8804",
     "hours": "평일 06:00~22:00 · 주말 09:00~18:00", "closed": "1·3·5주 일요일, 공휴일 휴관", "tags": ["수영", "요가·필라테스"],
     "web": "https://www.yuc.co.kr/www/wpge/m_554/contents.do", "apply": "", "visit": "센터에 문의"},
    {"id": "bojeong", "name": "보정미르휴먼센터 스포츠센터", "area": "기흥구 보정", "addr": "용인시 기흥구 죽전로 30", "tel": "031-276-5701",
     "hours": "평일 06:00~22:00 · 주말 09:00~18:00", "closed": "1·3·5주 일요일, 공휴일 휴관", "tags": ["헬스", "댄스·에어로빅"],
     "web": "https://www.yuc.co.kr/www/wpge/m_555/contents.do", "apply": "", "visit": "센터에 문의"},
]

KID = re.compile(r"초등|어린이|유아|아동|키즈|주니어")
SKIP_PAGE = re.compile(r"전체|골프|스쿼시|탁구|암벽|체육관|타석|배드민턴|농구|대관")


def get(url):
    req = urllib.request.Request(url, headers=UA)
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                b = r.read()
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    return b.decode(enc)
                except UnicodeDecodeError:
                    pass
            return b.decode("cp949", errors="replace")
        except Exception as e:
            print("  다시 시도:", url, e)
            time.sleep(3 * (i + 1))
    return ""


class Tables(HTMLParser):
    """표(table)를 행·칸(rowspan/colspan 포함)으로 읽고, 첫 h3/h4 제목도 기억"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack, self.title, self._t = [], [], "", None
        self.links, self._ina = [], False

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "table":
            self.stack.append([])
        elif tag == "tr" and self.stack:
            self.stack[-1].append([])
        elif tag in ("td", "th") and self.stack and self.stack[-1]:
            self.stack[-1][-1].append({"t": "", "rs": int(re.sub(r"\D", "", a.get("rowspan", "1")) or 1), "cs": int(re.sub(r"\D", "", a.get("colspan", "1")) or 1)})
        elif tag in ("h3", "h4") and not self.title:
            self._t = ""
        elif tag == "a" and a.get("href"):
            self.links.append([a["href"], ""])
            self._ina = True
        if tag == "br" and self.stack and self.stack[-1] and self.stack[-1][-1]:
            self.stack[-1][-1][-1]["t"] += " "

    def handle_endtag(self, tag):
        if tag == "a":
            self._ina = False
        if tag == "table" and self.stack:
            self.tables.append(self.stack.pop())
        elif tag in ("h3", "h4") and self._t is not None:
            self.title, self._t = self._t.strip(), None

    def handle_data(self, d):
        if self.stack and self.stack[-1] and self.stack[-1][-1]:
            self.stack[-1][-1][-1]["t"] += d
        if self._t is not None:
            self._t += d
        if self._ina and len(self.links[-1][1]) < 40:
            self.links[-1][1] += d.strip()


def grid(rows):
    """rowspan/colspan을 풀어서 사각형 표로"""
    out, carry = [], {}
    for r in rows:
        line, ci, cells = [], 0, list(r)
        while cells or carry.get(ci):
            if carry.get(ci):
                txt, left = carry[ci]
                line.append(txt)
                carry[ci] = (txt, left - 1) if left > 1 else None
                ci += 1
                continue
            c = cells.pop(0)
            txt = re.sub(r"\s+", " ", c["t"]).strip()
            for _ in range(c["cs"]):
                line.append(txt)
                if c["rs"] > 1:
                    carry[ci] = (txt, c["rs"] - 1)
                ci += 1
        out.append(line)
    return out


def norm(s):
    return re.sub(r"\s+", "", s)


def price_of(cell, kid):
    """'월·수·금 성 인 65,000 청소년 52,000 초등 45,000 화·목 …' → '45,000 / 35,000원'"""
    parts = re.split(r"(?=월\s*·\s*수\s*·\s*금|화\s*·\s*목)", cell)
    parts = [p for p in parts if re.search(r"\d{2},\d{3}", p)] or [cell]
    vals = []
    for p in parts[:2]:
        m = (re.search(r"(?:초등학생|초등|어린이)\s*:?\s*([\d,]{5,})", p) if kid else re.search(r"성\s*인\s*:?\s*([\d,]{5,})", p)) or re.search(r"([\d]{1,3},\d{3})", p)
        if m:
            vals.append(m.group(1))
    vals = list(dict.fromkeys(vals))
    return (" / ".join(vals) + "원") if vals else ""


def category(title, name):
    t, n = norm(title), norm(name)
    if "수영" in t or "수영" in n or "아쿠아" in n:
        return "수영"
    if "사우나" in t or "사우나" in n:
        return "사우나"
    if re.search(r"요가|필라테스", n) or "필라테스" in t:
        return "요가·필라테스"
    if re.search(r"댄스|로빅|줌바|발레|체조|라인|홀라", n):
        return "댄스·에어로빅"
    if re.search(r"헬스|트레이닝|써클|스피닝|PT", n, re.I) or re.search(r"헬스|스피닝", t):
        return "헬스"
    if re.search(r"다목적실|체조교실|소체육실", t):
        return "댄스·에어로빅"
    return ""


def short_time(s):
    s = s.strip()
    m = re.findall(r"(\d{1,2}:\d{2})\s*~\s*\d{1,2}:\d{2}", s)
    if m:
        return ", ".join(dict.fromkeys(m))
    return s if len(s) <= 40 else ""


def parse_page(html, title, cid):
    p = Tables()
    p.feed(html)
    title = title or p.title
    progs = {}
    for t in p.tables:
        g = grid(t)
        if len(g) < 2:
            continue
        head = [norm(x) for x in g[0]]
        find = lambda *keys: next((i for i, h in enumerate(head) if any(k in h for k in keys)), None)
        ci_name, ci_time, ci_who, ci_day, ci_price = find("프로그램", "구분"), find("시간"), find("대상"), find("요일"), find("사용료", "이용료", "요금")
        if ci_price is None:
            continue
        for row in g[1:]:
            if len(row) <= ci_price:
                continue
            name = row[ci_name] if ci_name is not None and ci_name < len(row) else title
            if not name or norm(name) in ("구분", "프로그램", "월정기", "일일입장") or len(name) > 30 or re.match(r"[\d(]", name):
                continue
            price_cell = row[ci_price]
            if not re.search(r"\d{1,3},\d{3}", price_cell):
                continue
            cat = category(title, name)
            if not cat:
                continue
            who = row[ci_who] if ci_who is not None and ci_who < len(row) else ""
            kid = bool(KID.search(name + " " + who)) and cat != "사우나"
            key = (name, kid)
            e = progs.setdefault(key, {"c": cid, "cat": cat, "name": name, "who": who or "성인", "kid": 1 if kid else 0, "days": [], "times": [], "price": price_of(price_cell, kid)})
            if ci_day is not None and ci_day < len(row) and row[ci_day] and row[ci_day] not in e["days"]:
                e["days"].append(row[ci_day])
            if ci_time is not None and ci_time < len(row):
                tm = short_time(row[ci_time])
                if tm and tm not in e["times"]:
                    e["times"].append(tm)
            if who and who not in e["who"]:
                e["who"] = (e["who"] + " · " + who)[:60]
    out = []
    for e in progs.values():
        e["days"] = " / ".join(e["days"])[:60]
        e["times"] = ", ".join(e["times"])[:60]
        if not e["kid"]:
            e.pop("kid")
        out.append(e)
    return out


def collect_center(c):
    home = get(c["site"] + "/")
    if not home:
        raise RuntimeError("홈페이지를 열지 못함")
    p = Tables()
    p.feed(home)
    pages = []
    for href, label in p.links:
        m = re.search(r"/m03/(\d+)/?$", href)
        if m and label and not SKIP_PAGE.search(label) and m.group(1) not in [x[0] for x in pages]:
            pages.append((m.group(1), label))
    print(f" {c['name']}: 프로그램 화면 {len(pages)}개 {[l for _, l in pages]}")
    progs = []
    for num, label in pages:
        time.sleep(1)
        html = get(f"{c['site']}/m03/{num}/")
        got = parse_page(html, label, c["id"]) if html else []
        print(f"   - {label}: {len(got)}개")
        progs += got
    return progs


def main():
    old = {}
    try:
        with open("output/sports.json", encoding="utf-8") as f:
            for p in json.load(f).get("programs", []):
                old.setdefault(p["c"], []).append(p)
    except Exception:
        pass
    programs, status = [], {}
    for c in CENTERS:
        if not c.get("site"):
            continue
        try:
            got = collect_center(c)
            if not got:
                raise RuntimeError("강좌를 하나도 못 읽음")
            programs += got
            status[c["id"]] = "ok"
        except Exception as e:
            print(f" {c['name']} 실패: {e} → 지난번 정보 사용")
            programs += old.get(c["id"], [])
            status[c["id"]] = "old"
    programs.sort(key=lambda p: (0 if p.get("kid") else 1, ["수영", "댄스·에어로빅", "요가·필라테스", "헬스", "사우나"].index(p["cat"]) if p["cat"] in ["수영", "댄스·에어로빅", "요가·필라테스", "헬스", "사우나"] else 9))
    now = datetime.now(KST)
    out = {"city": "용인", "updated": now.strftime("%Y-%m-%d"), "status": status,
           "centers": [{k: v for k, v in c.items() if k != "site"} for c in CENTERS], "programs": programs}
    os.makedirs("output", exist_ok=True)
    with open("output/sports.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"저장: 강좌 {len(programs)}개 (아이 {sum(1 for p in programs if p.get('kid'))}개)")


if __name__ == "__main__":
    main()
