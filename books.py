"""용인시도서관 인기 도서 수집기

1) 용인시 전체 도서관 대출 베스트 (최근 1달)
2) 초등(8~13세) 인기 도서 - 도서관 정보나루, 경기도 공공도서관, 최근 1달
3) 청소년(14~19세) 인기 도서 - 도서관 정보나루, 경기도 공공도서관, 최근 1달
결과는 output/books.json 으로 저장한다.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

KST = timezone(timedelta(hours=9))
SITE = "https://lib.yongin.go.kr"
LOAN_BEST = SITE + "/namsa/menu/10961/program/30016/plusLoanBestList.do"
POPULAR = SITE + "/namsa/menu/10962/program/30017/plusData4libraryPopularBookList.do"
DETAIL = SITE + "/yongin/plusSearchResultDetail.do"
ISBN_SEARCH = SITE + "/yongin/plusSearchResultList.do"
TOP = 20
VOID = {"img", "br", "hr", "input", "meta", "link", "source", "col", "area", "base", "wbr"}


class Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children, self.text = [], []

    def cls(self):
        return (self.attrs.get("class") or "").split()

    def all_text(self):
        out = list(self.text)
        for c in self.children:
            out.append(c.all_text())
        return " ".join(" ".join(out).split())

    def find_all(self, tag=None, cls=None):
        res = []
        for c in self.children:
            if (tag is None or c.tag == tag) and (cls is None or cls in c.cls()):
                res.append(c)
            res.extend(c.find_all(tag, cls))
        return res

    def find(self, tag=None, cls=None):
        r = self.find_all(tag, cls)
        return r[0] if r else None


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", [])
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        if data.strip():
            self.cur.text.append(data)


def fetch(url, params, tries=3):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0 (yongin-edu-collector)"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                return res.read().decode("utf-8", errors="replace")
        except Exception as e:  # 일시 오류는 다시 시도
            print(f"  다시 시도 {i + 1}/{tries}: {e}")
            time.sleep(5)
    raise RuntimeError("접속 실패: " + url)


def book_items(html):
    t = Tree()
    t.feed(html)
    ul = t.root.find("ul", "listWrap")
    return [c for c in ul.children if c.tag == "li"] if ul else []


def cover_of(li):
    img = li.find("img")
    src = (img.attrs.get("src") or "") if img else ""
    if src.startswith("//"):
        src = "https:" + src
    return src if src.startswith("http") else ""


def rank_of(li, i):
    r = li.find(cls="rankingNum")
    m = re.search(r"\d+", r.all_text() if r else "")
    return int(m.group()) if m else i + 1


def clean_title(s):
    s = re.sub(r"^도서\s*", "", s.strip())
    s = re.sub(r"^\((만화|그림책|큰글자|전자책)\)\s*", r"", s)
    s = re.sub(r"\s+([.,])", r"\1", s)
    return " ".join(s.split())


def loan_best():
    html = fetch(LOAN_BEST, {"searchLibrary": "ALL", "searchPeriod": "1M", "searchSubject": "ALL", "searchRecordCount": "50"})
    books = []
    for i, li in enumerate(book_items(html)[:TOP]):
        name = li.find(cls="book_name")
        if not name:
            continue
        kind = name.find("b")
        title = name.all_text()
        if kind:
            title = title.replace(kind.all_text(), "", 1)
        link = ""
        for a in li.find_all("a"):
            m = re.search(r"fnSearchResultDetail\(\s*'?(\d+)'?\s*,\s*'?(\d+)'?\s*,\s*'?(\w+)'?", a.attrs.get("onclick") or "")
            if m:
                link = DETAIL + "?" + urllib.parse.urlencode({"recKey": m.group(1), "bookKey": m.group(2), "publishFormCode": m.group(3)})
                break
        w, p = li.find(cls="bk_writer"), li.find(cls="bk_publish")
        books.append({
            "rank": rank_of(li, i),
            "title": clean_title(title),
            "author": tidy_author(w.all_text() if w else ""),
            "publisher": (p.all_text() if p else "").rstrip(" :"),
            "cover": cover_of(li),
            "link": link,
        })
    return books


def tidy_author(s):
    s = re.sub(r"^(저자|지은이)\s*:\s*", "", s.strip())
    s = re.sub(r"\s*;\s*", ", ", s)
    return re.sub(r"지은이\s*:\s*", "", s).strip(" ,")


def popular(age):
    end = datetime.now(KST).date() - timedelta(days=1)
    start = end - timedelta(days=30)
    html = fetch(POPULAR, {"searchAgesArr": age, "searchRegionArr": "31", "searchRecordCount": str(TOP),
                           "searchStartDate": start.isoformat(), "searchEndDate": end.isoformat()})
    books = []
    for i, li in enumerate(book_items(html)[:TOP]):
        name = li.find(cls="book_name")
        if not name:
            continue
        info = {}
        for item in li.find_all("li"):
            k, _, v = item.all_text().partition(":")
            info[k.strip()] = v.strip()
        title = name.all_text().split(" :")[0]
        isbn = re.sub(r"\D", "", info.get("ISBN", ""))
        books.append({
            "rank": rank_of(li, i),
            "title": clean_title(title),
            "author": tidy_author(info.get("저자", "")),
            "publisher": info.get("발행사", ""),
            "cover": cover_of(li),
            "link": ISBN_SEARCH + "?" + urllib.parse.urlencode({"searchType": "ISBN", "searchIsbn": isbn, "searchLibrary": "ALL"}) if isbn else "",
        })
    return books


def main():
    lists = []
    plan = [
        ("kids", "초등 인기 도서", "경기도 공공도서관 · 초등(8~13세) 대출 · 최근 1달", lambda: popular("8")),
        ("teen", "청소년 인기 도서", "경기도 공공도서관 · 청소년(14~19세) 대출 · 최근 1달", lambda: popular("14")),
        ("yongin", "용인시 대출 베스트", "용인시 전체 도서관 · 전 연령 · 최근 1달", loan_best),
    ]
    old = {}
    if os.path.exists("output/books.json"):
        try:
            old = {l["key"]: l for l in json.load(open("output/books.json", encoding="utf-8"))["lists"]}
        except Exception:
            old = {}
    for key, title, desc, fn in plan:
        try:
            books = fn()
        except Exception as e:
            print(f"[{title}] 실패: {e}")
            books = []
        if not books and key in old:  # 실패하면 지난번 목록 유지
            books = old[key]["books"]
        lists.append({"key": key, "title": title, "desc": desc, "books": books})
        print(f"[{title}] {len(books)}권")
        for b in books[:5]:
            print(f"  {b['rank']}. {b['title']} / {b['author']}")
    if not any(l["books"] for l in lists):
        raise SystemExit("인기 도서를 하나도 가져오지 못했습니다")
    os.makedirs("output", exist_ok=True)
    result = {"updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"), "source": "용인시도서관 · 도서관 정보나루", "lists": lists}
    with open("output/books.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
