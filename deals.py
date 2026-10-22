"""동네 할인 수집기 (용인·수원·성남 공통, 환경변수 CITY 로 도시 선택)

1) 지역화폐: 확인된 혜택(아래 MONEY, 사람이 기사로 확인해 적어 둠) + 최근 기사 링크(다음 검색)
2) 백화점·아울렛: 도시 안 점포 이름으로 다음 웹문서·블로그를 최근순 검색 → 행사·세일·키즈 관련 글만
3) 동네 가게: 앱의 광고 칸(사람이 직접 받음)으로 채우고, 여기서는 만들지 않는다

KAKAO_KEY(카카오 REST API 키)가 없으면 1)의 확인된 혜택만 저장한다.
결과는 output/deals.json 으로 저장한다.
"""

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
CITY = os.environ.get("CITY", "용인").strip()
KEY = os.environ.get("KAKAO_KEY", "").strip()
API = "https://dapi.kakao.com/v2/search/"
DAYS = 21   # 최근 3주 글만

# 사람이 기사로 확인한 지역화폐 혜택. 바뀌면 여기만 고치면 된다. (as_of: 확인한 날, src: 근거 기사)
MONEY = {
    "용인": {"name": "용인와이페이", "q": "용인와이페이 인센티브",
             "facts": [{"title": "용인와이페이 충전하면 10% 더", "sub": "한 달 30만원까지 충전하면 최대 3만원을 더 줘요.",
                        "meta": "용인시 · 2026년 8월부터 · 예산 소진 시 종료", "as_of": "2026-10-15",
                        "link": "https://www.dailian.co.kr/news/view/1671167/"}]},
    "수원": {"name": "수원페이", "q": "수원페이 인센티브", "facts": []},
    "성남": {"name": "성남사랑상품권", "q": "성남사랑상품권 할인", "facts": []},
    "안양": {"name": "안양사랑페이", "q": "안양사랑페이 인센티브", "facts": []},
    "고양": {"name": "고양페이", "q": "고양페이 인센티브", "facts": []},
    "화성": {"name": "행복화성지역화폐", "q": "화성 지역화폐 인센티브", "facts": []},
    "부천": {"name": "부천페이", "q": "부천페이 인센티브", "facts": []},
}
STORES = {
    "용인": ["신세계백화점 경기점", "AK플라자 기흥", "롯데프리미엄아울렛 기흥점"],
    "수원": ["AK플라자 수원", "타임빌라스 수원", "갤러리아 광교"],
    "성남": ["현대백화점 판교점", "롯데백화점 분당점", "AK플라자 분당점", "NC백화점 야탑점"],
    "안양": ["롯데백화점 평촌점", "NC백화점 평촌점"],
    "고양": ["현대백화점 킨텍스점", "롯데백화점 일산점", "스타필드 고양"],
    "화성": ["롯데백화점 동탄점"],
    "부천": ["현대백화점 중동점", "롯데백화점 중동점"],
}
GOOD = re.compile(r"행사|세일|할인|특가|팝업|이벤트|사은|증정|키즈|어린이|아이|가족|체험|공연|페스티벌|축제|마켓|클래스|오픈")
BAD = re.compile(r"채용|알바|구인|부동산|분양|매매|전세|주가|증권|실적|영업이익|사고|화재|폭행|경찰|사망|소송|노조|파업|대출|코인"
                 r"|나무위키|위키|인터뷰|시장에게|개봉|여행사|인플루언서|Image Library|섭외|제작|배송|택배|최저가|노사|개막"
                 r"|아이폰|갤럭시|휴대폰|지원금|성지|동물병원|영양제|위스키|와인|골프|리뷰 모음", re.I)
MONEY_GOOD = re.compile(r"인센티브|할인|충전|한도|캐시백|추가\s*지급|특별")


def clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return " ".join(html.unescape(s).split())


def search(kind, query, size=10):
    """다음 검색 (kind: web / blog / cafe). 키가 없거나 실패하면 빈 목록"""
    if not KEY:
        return []
    url = API + kind + "?" + urllib.parse.urlencode({"query": query, "sort": "recency", "size": size})
    req = urllib.request.Request(url, headers={"Authorization": "KakaoAK " + KEY})
    for i in range(2):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8")).get("documents") or []
        except urllib.error.HTTPError as e:
            print(f"  검색 실패 {kind} '{query}': HTTP {e.code}")
            if e.code in (401, 403):
                return []
        except Exception as e:
            print(f"  검색 실패 {kind} '{query}': {e}")
        time.sleep(2)
    return []



def ended(title, today):
    """제목에 끝나는 날짜가 있고 이미 지났으면 True. 예: '~10월 18일', '10월 18일까지', '10/18까지', '~10.18'"""
    t = title.replace(" ", "")
    pats = [r"~(\d{1,2})월(\d{1,2})일", r"(\d{1,2})월(\d{1,2})일까지", r"(\d{1,2})[./](\d{1,2})까지", r"~(\d{1,2})[./](\d{1,2})(?!\d)"]
    for pat in pats:
        for mo, d in re.findall(pat, t):
            mo, d = int(mo), int(d)
            if not (1 <= mo <= 12 and 1 <= d <= 31):
                continue
            y = today.year - (1 if mo - today.month > 6 else 0)   # 12월 글을 1월에 보는 경우
            try:
                if date(y, mo, d) < today:
                    return True
            except ValueError:
                pass
    return False

def recent(doc, since):
    d = (doc.get("datetime") or "")[:10]
    return d >= since, d


def money_items(today):
    m = MONEY.get(CITY) or {}
    out = []
    for f in m.get("facts", []):
        out.append({"id": "M" + str(len(out)), "cat": "지역화폐", "title": f["title"], "sub": f["sub"], "meta": f["meta"],
                    "date": f["as_of"], "link": f["link"], "src": "check", "pin": 1})
    since = (today - timedelta(days=45)).isoformat()
    seen = set()
    for kind in ("web", "blog"):
        for d in search(kind, m.get("q", CITY + " 지역화폐 인센티브")):
            ok, day = recent(d, since)
            title = clean(d.get("title"))
            if not ok or not MONEY_GOOD.search(title) or m.get("name", "")[:4] not in title or BAD.search(title) or title in seen or ended(title, today):
                continue
            seen.add(title)
            out.append({"id": "MS" + str(len(out)), "cat": "지역화폐", "title": title, "sub": clean(d.get("contents"))[:90],
                        "meta": (clean(d.get("blogname")) or urllib.parse.urlparse(d.get("url", "")).hostname or "") + " · " + day,
                        "date": day, "link": d.get("url", ""), "src": "daum"})
        time.sleep(0.3)
    pinned = [x for x in out if x.get("pin")]
    news = sorted([x for x in out if not x.get("pin")], key=lambda x: x["date"], reverse=True)[:3]
    return pinned + news


def store_items(today):
    since = (today - timedelta(days=DAYS)).isoformat()
    out, seen = [], set()
    for store in STORES.get(CITY, []):
        got = []
        for kind, q in (("web", store + " 행사"), ("blog", store + " 행사"), ("blog", store + " 키즈 체험")):
            for d in search(kind, q):
                ok, day = recent(d, since)
                title, body = clean(d.get("title")), clean(d.get("contents"))
                short = store.split()[0][:2]
                if not ok or BAD.search(title) or not GOOD.search(title) or short not in title or ended(title, today):
                    continue
                k = re.sub(r"\W", "", title)[:18]
                if k in seen:
                    continue
                seen.add(k)
                got.append({"id": "S" + str(len(out) + len(got)), "cat": "백화점", "store": store, "title": title,
                            "sub": body[:90], "meta": store + " · " + day, "date": day, "link": d.get("url", ""), "src": "daum"})
            time.sleep(0.3)
        got.sort(key=lambda x: x["date"], reverse=True)
        out += got[:3]
        print(f"  {store}: {len(got)}건 중 {min(3, len(got))}건")
    return out



LOCAL_URL = "https://raw.githubusercontent.com/jinbok2279/airang-cities/main/deals/local.json"


def local_items(today):
    """동네 가게가 직접 보내 준 할인 (deals/local.json). 기간 안에 있고 이 도시에 해당하는 것만"""
    data = None
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deals", "local.json")
    try:
        if os.path.exists(here):
            data = json.load(open(here, encoding="utf-8"))
        else:
            with urllib.request.urlopen(urllib.request.Request(LOCAL_URL, headers={"Cache-Control": "no-cache"}), timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("  동네 가게 할인 읽기 실패:", e)
        return []
    out, t = [], today.isoformat()
    for s in (data or {}).get("stores", []):
        if CITY not in (s.get("cities") or []) or not s.get("title"):
            continue
        if (s.get("start") or "0") > t or (s.get("end") or "9") < t:
            continue
        out.append({"id": "G" + str(s.get("id", len(out))), "cat": "동네 가게", "src": "store", "title": s["title"],
                    "sub": s.get("detail", ""), "cond": s.get("cond", ""), "store": s.get("store", ""), "kind": s.get("kind", ""),
                    "area": s.get("area", ""), "tel": s.get("tel", ""), "link": s.get("link", ""), "paid": bool(s.get("paid")),
                    "start": s.get("start", ""), "end": s.get("end", ""), "date": s.get("start", ""),
                    "meta": " · ".join(x for x in (s.get("store", ""), s.get("area", "")) if x)})
    out.sort(key=lambda x: x["end"] or "9")
    print(f"  동네 가게 할인 {len(out)}건")
    return out

def main():
    today = datetime.now(KST).date()
    if CITY not in MONEY:
        raise SystemExit("모르는 도시: " + CITY)
    if not KEY:
        print("KAKAO_KEY 없음: 확인된 지역화폐 혜택만 저장해요.")
    money = money_items(today)
    items = [x for x in money if x.get("pin")] + local_items(today) + [x for x in money if not x.get("pin")] + store_items(today)
    result = {"city": CITY, "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "search": bool(KEY),
              "money": (MONEY[CITY] or {}).get("name", ""), "stores": STORES.get(CITY, []), "items": items}
    os.makedirs("output", exist_ok=True)
    with open("output/deals.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"저장: {CITY} 할인 {len(items)}건 (지역화폐 {sum(1 for x in items if x['cat'] == '지역화폐')}, 백화점 {sum(1 for x in items if x['cat'] == '백화점')})")
    for x in items[:12]:
        print("  [" + x["cat"] + "]", x["date"], x["title"][:50])


if __name__ == "__main__":
    main()
