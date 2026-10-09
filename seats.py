"""용인시 도서관 열람실 실시간 좌석 수집기

용인시도서관 홈페이지의 '좌석현황 보기' 페이지를 읽어
도서관별 열람실 전체·사용·잔여·대기 좌석 수를 output/seats.json 으로 저장한다.
"""

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

KST = timezone(timedelta(hours=9))
URL = "https://lib.yongin.go.kr/yongin/seatStatusList.do"
SITE = "https://lib.yongin.go.kr"


class SeatParser(HTMLParser):
    """<table class="roomTbl ..."> 표에서 도서관·열람실 숫자를 뽑는다."""

    def __init__(self):
        super().__init__()
        self.libs = []
        self.in_table = self.in_caption = self.in_td = False
        self.gu = ""
        self.row = []
        self.cell = None
        self.cur = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and "roomTbl" in (a.get("class") or ""):
            self.in_table, self.cur = True, None
        elif not self.in_table:
            return
        elif tag == "caption":
            self.in_caption = True
        elif tag == "tr":
            self.row = []
        elif tag == "td":
            self.in_td = True
            self.cell = {"text": "", "colspan": int(a.get("colspan") or 1), "href": None, "lib": "lib" in (a.get("class") or "")}
        elif tag == "a" and self.cell is not None:
            self.cell["href"] = a.get("href")

    def handle_endtag(self, tag):
        if not self.in_table:
            return
        if tag == "caption":
            self.in_caption = False
        elif tag == "td" and self.cell is not None:
            self.cell["text"] = " ".join(self.cell["text"].replace("좌석현황 바로가기", "").split())
            self.row.append(self.cell)
            self.in_td, self.cell = False, None
        elif tag == "tr":
            self.add_row(self.row)
        elif tag == "table":
            self.in_table = False

    def handle_data(self, data):
        if self.in_caption:
            self.gu = data.replace("좌석현황 안내", "").strip()
        elif self.in_td and self.cell is not None:
            self.cell["text"] += data

    def add_row(self, cells):
        if not cells:
            return
        if cells[0]["lib"]:                       # 새 도서관 시작
            c = cells.pop(0)
            href = c["href"] or ""
            if href.startswith("/"):
                href = SITE + href
            self.cur = {"name": c["text"], "gu": self.gu, "link": href, "status": "open", "message": "", "rooms": []}
            self.libs.append(self.cur)
        if self.cur is None or not cells:
            return
        if len(cells) == 1 and cells[0]["colspan"] > 1:   # 휴관일 등 안내 문구
            self.cur["status"] = "closed" if "휴관" in cells[0]["text"] else "info"
            self.cur["message"] = cells[0]["text"]
            return
        nums = [to_int(c["text"]) for c in cells[1:5]]
        if len(nums) == 4 and None not in nums:
            total, used, left, wait = nums
            self.cur["rooms"].append({"name": cells[0]["text"], "total": total, "used": used, "left": left, "wait": wait})


def to_int(s):
    s = s.replace(",", "").strip()
    return int(s) if s.isdigit() else None


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (yongin-edu-collector)"})
    with urllib.request.urlopen(req, timeout=30) as res:
        html = res.read().decode("utf-8", errors="replace")
    p = SeatParser()
    p.feed(html)
    libs = [l for l in p.libs if l["rooms"] or l["message"]]
    now = datetime.now(KST)
    result = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "용인시도서관 좌석현황",
        "source_url": URL,
        "libraries": libs,
    }
    os.makedirs("output", exist_ok=True)
    with open("output/seats.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    opened = sum(1 for l in libs if l["status"] == "open")
    print(f"도서관 {len(libs)}곳 (운영 {opened}곳) 좌석 정보 저장")
    for l in libs:
        rooms = ", ".join(f"{r['name']} {r['left']}/{r['total']}" for r in l["rooms"]) or l["message"]
        print(f"  [{l['gu']}] {l['name']}: {rooms}")


if __name__ == "__main__":
    main()
