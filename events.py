"""아이와 함께 갈 만한 용인 행사 수집기

1) 용인시청 문화달력 (공연·전시·축제) 중 가족·어린이에게 맞는 것
2) 용인시도서관 문화행사 중 대상이 유아·초등·부모·가족인 프로그램 (접수중·접수전)
결과는 output/events.json 으로 저장한다.
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from books import Tree  # 같은 저장소의 간단한 HTML 파서

KST = timezone(timedelta(hours=9))
CITY_LIST = "https://www.yongin.go.kr/partInfo/cultureArt/BD_selectCultureArtList.do"
CITY_VIEW = "https://www.yongin.go.kr/partInfo/cultureArt/BD_selectCultureArt.do"
LIB = "https://lib.yongin.go.kr"
LIB_LIST = LIB + "/yongin/menu/10264/program/30027/lectureList.do"
LIB_VIEW = LIB + "/yongin/menu/10264/program/30027/lectureDetail.do"

KID_WORDS = re.compile(r"가족|어린이|아이|키즈|kids|유아|아동|동화|인형|마술|매직|체험|그림책|놀이|과학|축제|페스티벌|야시장|버블|뮤지컬|캐릭터|만들기|숲|생태|방학|드림|피노키오|공주|동물|공룡|로봇", re.I)
NOT_KID = re.compile(r"19세|청소년\s*관람\s*불가|성인|어르신|트로트|콘서트\s*<|스탠드업|stand-up|장애인|합창단\s*정기", re.I)


def get(url, params=None, tries=3):
    full = url + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0 (yongin-edu-collector)"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=40) as res:
                return res.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  다시 시도 {i + 1}/{tries}: {e}")
            time.sleep(4)
    raise RuntimeError("접속 실패: " + url)


def txt(n):
    return " ".join(n.all_text().split()) if n else ""


def dates(s):
    return re.findall(r"(\d{4})[.\-](\d{2})[.\-](\d{2})", s)


def ymd(t):
    return f"{t[0]}-{t[1]}-{t[2]}"


def city_events(today):
    horizon = today + timedelta(days=60)
    found = []
    for page in range(1, 13):
        try:
            t = Tree(); t.feed(get(CITY_LIST, {"q_currPage": page}))
        except Exception as e:
            print("  시청 목록 실패:", e); break
        rows = [r for r in t.root.find_all("tr") if r.find("td")]
        newest_end = None
        for r in rows:
            tds = r.find_all("td")
            a = r.find("a")
            m = re.search(r"detailView\('?(\d+)", (a.attrs.get("onclick") or "") if a else "")
            ds = dates(txt(r))
            if not m or not ds:
                continue
            start, end = ymd(ds[0]), ymd(ds[-1])
            newest_end = max(newest_end or end, end)
            title = txt(a)
            place = txt(tds[-1]) if tds else ""
            if end < today.isoformat() or start > horizon.isoformat():
                continue
            found.append({"id": m.group(1), "title": title, "start": start, "end": end, "place": place})
        if not rows:
            break
    out = []
    for ev in found:
        if NOT_KID.search(ev["title"]):
            continue
        info = {}
        try:
            t = Tree(); t.feed(get(CITY_VIEW, {"q_showIdx": ev["id"]}))
            for li in t.root.find_all("li", "info_item"):
                ems = li.find_all("em")
                if len(ems) >= 2:
                    info[txt(ems[0])] = txt(ems[1])
        except Exception as e:
            print("  상세 실패:", ev["id"], e)
        grade, price = info.get("관람등급", ""), info.get("가격", "")
        kid = bool(KID_WORDS.search(ev["title"])) or bool(re.search(r"전체|어린이|유아|\d+개월|[3-9]세|초등", grade))
        if not kid or re.search(r"19세|청소년관람불가|14세 이상|15세 이상", grade):
            continue
        out.append({**ev, "time": info.get("관람시간", ""), "grade": grade, "price": price,
                    "free": bool(re.search(r"무료", price)), "src": "city",
                    "link": CITY_VIEW + "?" + urllib.parse.urlencode({"q_showIdx": ev["id"]})})
        time.sleep(0.3)
    return out


def lib_events():
    out, seen = [], set()
    for status in ("apply", "ready"):
        for page in range(1, 4):
            params = {"searchTargetCdArr": ["T02", "T03", "T08", "T09"], "statusCd": status, "currentPageNo": page}
            try:
                t = Tree(); t.feed(get(LIB_LIST, params))
            except Exception as e:
                print("  도서관 목록 실패:", e); break
            ul = [u for u in t.root.find_all("ul") if "article-list" in u.cls()]
            items = [li for li in (ul[0].children if ul else []) if li.tag == "li"]
            for li in items:
                a = li.find("a", "title")
                m = re.search(r"fnDetail\(\s*'?(\d+)", (a.attrs.get("onclick") or "") if a else "")
                if not m or m.group(1) in seen:
                    continue
                seen.add(m.group(1))
                lib = txt(a.find("span")) if a else ""
                title = txt(a)
                if lib and title.endswith(lib):
                    title = title[: -len(lib)].strip()
                elif lib and title.startswith(lib):
                    title = title[len(lib):].strip()
                # 지점 이름이 빠진 꼬리표 정리: "[ ]" 없애고 "[ _대면]" → "[대면]"
                title = re.sub(r"\[\s*\]\s*", "", title)
                title = re.sub(r"\[\s*_\s*", "[", title).strip()
                f = {}
                for p in li.find_all("p"):
                    k, _, v = txt(p).partition(":")
                    f[k.strip()] = v.strip()
                period, apply_p = f.get("수강기간", ""), f.get("접수기간", "")
                ds, ads = dates(period), dates(apply_p)
                cnt = txt(li.find("span", "apply"))
                btn = li.find("button")
                out.append({
                    "id": "L" + m.group(1), "title": title, "lib": lib + ("도서관" if lib and not lib.endswith("도서관") else ""),
                    "target": f.get("대상", ""), "place": f.get("교육장소", ""),
                    "start": ymd(ds[0]) if ds else "", "end": ymd(ds[-1]) if ds else "", "period": period,
                    "applyStart": ymd(ads[0]) if ads else "", "applyEnd": ymd(ads[-1]) if ads else "", "apply": apply_p,
                    "count": cnt.replace("신청 :", "").strip(), "status": "접수중" if status == "apply" else "접수전",
                    "btn": txt(btn), "free": True, "src": "lib",
                    "link": LIB_VIEW + "?" + urllib.parse.urlencode({"lectureIdx": m.group(1)}),
                })
            if len(items) < 40:
                break
    return out


def main():
    today = datetime.now(KST).date()
    city, lib = [], []
    try:
        city = city_events(today)
    except Exception as e:
        print("시청 행사 실패:", e)
    try:
        lib = lib_events()
    except Exception as e:
        print("도서관 프로그램 실패:", e)
    old = {}
    if os.path.exists("output/events.json"):
        try:
            old = json.load(open("output/events.json", encoding="utf-8"))
        except Exception:
            old = {}
    if not city and old.get("city"):
        city = [e for e in old["city"] if e.get("end", "") >= today.isoformat()]
    if not lib and old.get("lib"):
        lib = old["lib"]
    if not city and not lib:
        raise SystemExit("행사 정보를 하나도 가져오지 못했습니다")
    city.sort(key=lambda e: (e["start"], e["title"]))
    lib.sort(key=lambda e: (e["status"] != "접수중", e.get("applyEnd") or "9", e["start"]))
    os.makedirs("output", exist_ok=True)
    result = {"updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
              "source": "용인시청 문화달력 · 용인시도서관 문화행사", "city": city, "lib": lib}
    with open("output/events.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"시청 가족 행사 {len(city)}건, 도서관 어린이·가족 프로그램 {len(lib)}건")
    for e in city[:6]:
        print("  [시청]", e["start"], e["title"], "|", e["place"], "|", e["grade"], e["price"])
    for e in lib[:6]:
        print("  [도서관]", e["status"], e["title"], "|", e["lib"], e["target"], e["count"])


if __name__ == "__main__":
    main()
