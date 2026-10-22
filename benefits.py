"""놓치기 쉬운 혜택 (아이랑 7개 도시 같은 파일, CITY 로 도시를 고른다).

쓰는 서비스 (공공데이터포털 활용신청, 인증키는 WEATHER_KEY 와 같은 것):
  1) 한국사회보장정보원_중앙부처복지서비스  → 나라 혜택 (아이·가족 관련만 골라 씀)
  2) 한국사회보장정보원_지자체복지서비스    → 우리 시 혜택 (신청 전이면 403 → 건너뜀, 신청되면 자동으로 붙음)
목록 정보(이름·요약·담당·대상·문의·상세 링크)만 쓰고, 자세한 조건은 복지로 원문으로 보낸다.
개인정보는 모으지 않는다. 일주일에 한 번 돌린다(hospitals.yml 에서 함께 실행).
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
CITY = os.environ.get("CITY", "용인").strip()
KEY = os.environ.get("WEATHER_KEY", "").strip()
NAT = "https://apis.data.go.kr/B554287/NationalWelfareInformationsV001/NationalWelfarelistV001"
LOC = "https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/LcgvWelfarelist"
KIDS_LIFE = ("임신", "출산", "영유아", "아동", "청소년")
KIDS_TGT = ("다자녀", "한부모")
SKIP = re.compile(r"농업인|어업|어선|군인|보훈|장애인자립|노인|연금보험료|폐업|소상공인")


def kq():
    return KEY if "%" in KEY else urllib.parse.quote(KEY, safe="")


def get(url, params, tries=3):
    q = "serviceKey=" + kq() + "&" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url + "?" + q, headers={"User-Agent": "airang/1.0"}), timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise          # 활용신청 전 — 다시 해도 같음
            last = e
        except Exception as e:
            last = e
        time.sleep(2 + i * 3)
    raise last


def items(txt, tag):
    return [dict(re.findall(r"<(\w+)>([^<]*)</\1>", m)) for m in re.findall(rf"<{tag}>(.*?)</{tag}>", txt, re.S)]


def all_pages(url, params, tag="servList"):
    out, page = [], 1
    while True:
        txt = get(url, dict(params, pageNo=page, numOfRows=100))
        if "SERVICE_KEY_IS_NOT_REGISTERED" in txt or "<resultCode>3" in txt:
            raise RuntimeError("활용신청 안 됨: " + re.sub(r"\s+", " ", txt)[:120])
        its = items(txt, tag)
        out += its
        m = re.search(r"<totalCount>(\d+)</totalCount>", txt)
        if not its or not m or page * 100 >= int(m.group(1)):
            return out
        page += 1
        time.sleep(0.4)


def split(v):
    return [x.strip() for x in re.split(r"[,|]", v or "") if x.strip()]


def clean_tel(t):
    t = (t or "").strip()
    return t if re.search(r"\d{2,4}-?\d{3,4}-?\d{4}|\d{4}-\d{4}|^1\d{2,3}$", t) else ""


def row(it, scope):
    life = split(it.get("lifeArray") or it.get("lifeNmArray"))
    tgt = split(it.get("trgterIndvdlArray") or it.get("trgterIndvdlNmArray"))
    theme = split(it.get("intrsThemaArray") or it.get("intrsThemaNmArray"))
    tel = it.get("rprsCtadr") or ""   # 시 혜택의 inqNum 은 조회수라 쓰지 않음
    link = it.get("servDtlLink") or ""
    if not link.startswith("http") and it.get("servId"):
        link = "https://www.bokjiro.go.kr/ssis-tbu/twataa/wlfareInfo/moveTWAT52011M.do?wlfareInfoId=" + it["servId"]
    return {"id": it.get("servId", ""), "n": (it.get("servNm") or "").strip(), "sum": re.sub(r"\s+", " ", it.get("servDgst") or "").strip()[:220],
            "org": (it.get("jurMnofNm") or it.get("bizChrDeptNm") or it.get("jurOrgNm") or "").strip(),
            "life": [x.replace(" · ", "·") for x in life], "tgt": tgt, "theme": theme,
            "cyc": (it.get("sprtCycNm") or "").strip(), "kind": (it.get("srvPvsnNm") or "").strip(),
            "tel": clean_tel(tel), "telTxt": tel.strip()[:40],
            "online": (it.get("onapPsbltYn") or "") == "Y" or "온라인" in (it.get("aplyMtdNm") or ""),
            "apply": (it.get("aplyMtdNm") or "").strip()[:40], "link": link, "scope": scope}


KID_WORDS = re.compile(r"출산|출생|임산|임신|난임|산모|신생아|영유아|아이|아동|어린이|자녀|육아|보육|돌봄|다자녀|청소년|입학|학생|교복|급식|방과후")


def for_kids(r):
    """아이·가족 대상인 것만: 임신·출산·영유아·아동이 대상이거나, 다자녀·한부모, 또는 대상이 아동·청소년뿐인 것.
    이름·요약에 아이 관련 말이 있어야 함(장애인활동지원·청년 일자리처럼 대상에 아동이 끼어 있는 일반 사업은 뺌)."""
    life = set(r["life"])
    kid_life = life & {"임신·출산", "영유아", "아동"} or (life and life <= {"임신·출산", "영유아", "아동", "청소년"})
    fam = any(k in "".join(r["tgt"]) for k in KIDS_TGT)
    return bool((kid_life or fam) and KID_WORDS.search(r["n"] + " " + r["sum"]) and not SKIP.search(r["n"]))


def main():
    if not KEY:
        raise SystemExit("WEATHER_KEY 없음")
    res = {"city": CITY, "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "src": {"nat": False, "local": False}, "items": []}
    try:
        nat = [row(it, "nat") for it in all_pages(NAT, {"callTp": "L", "srchKeyCode": "001"})]
        kid = [r for r in nat if r["n"] and for_kids(r)]
        res["items"] += kid
        res["src"]["nat"] = True
        print(f"  나라 혜택 {len(nat)}건 중 아이·가족 {len(kid)}건")
    except Exception as e:
        print("  중앙부처 복지 실패:", e)
    try:
        raw = all_pages(LOC, {"ctpvNm": "경기도", "sggNm": CITY + "시"})
        if raw:
            print("  시 혜택 칸:", sorted(raw[0]))
        loc = [row(it, "local") for it in raw]
        kid = [r for r in loc if r["n"] and (for_kids(r) or (KID_WORDS.search(r["n"]) and not SKIP.search(r["n"])))]
        res["items"] = kid + res["items"]
        res["src"]["local"] = len(kid)
        print(f"  {CITY}시 혜택 {len(loc)}건 중 아이·가족 {len(kid)}건")
    except Exception as e:
        print("  지자체 복지(시 혜택) 건너뜀:", e)
    if not res["src"]["nat"] and not res["src"]["local"]:
        raise SystemExit("혜택 정보를 못 받음 — 저장하지 않음")
    os.makedirs("output", exist_ok=True)
    with open("output/benefits.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, separators=(",", ":"))
    print("  저장:", os.path.getsize("output/benefits.json") // 1024, "KB,", len(res["items"]), "건")


if __name__ == "__main__":
    main()
