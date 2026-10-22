"""동네 병원 — 의원 / 병원·종합병원 / 응급실 목록을 모은다 (공공데이터포털).

쓰는 서비스 (공공데이터포털에서 '활용신청' 필요, 인증키는 WEATHER_KEY 와 같은 것):
  1) 건강보험심사평가원_병원정보서비스            → 병원 종류·진료과·주소·전화·위치   (필수)
  2) 국립중앙의료원_전국 응급의료기관 정보 조회 서비스 → 응급실 목록·응급실 전화         (없으면 응급실 칸 비움)
  3) 국립중앙의료원_전국 병·의원 찾기 서비스        → 요일별 진료시간                  (없으면 시간 없이 저장)

개인정보는 모으지 않는다. 병원 이름·종류·진료과·주소·대표 전화·위치·진료시간(공개 정보)만.
출처: 공공누리 제1유형(출처표시) — 앱 화면 아래에 출처를 적는다.
하루에 부르는 횟수가 많지 않게(구 3개 × 종류·과 몇 개) 일주일에 한 번 돌린다.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
CITY = os.environ.get("CITY", "용인").strip()
KEY = os.environ.get("WEATHER_KEY", "").strip()
SIDO, SIDO_CD = "경기도", "310000"          # 심평원 시도 코드 (경기)
GU = ["수지구", "기흥구", "처인구"]
SGGU_ENV = os.environ.get("HOSP_SGGU", "").strip()   # 예: "수지구=310402,기흥구=310403,처인구=310401" (자동으로 못 찾을 때만)

HIRA = "https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList"
ER_LIST = "https://apis.data.go.kr/B552657/ErmctInfoInqireService/getEgytListInfoInqire"
HOURS = "https://apis.data.go.kr/B552657/HsptlAsembySearchService/getHsptlMdcncListInfoInqire"

# 의원 칸에서 고를 수 있는 진료과 (심평원 진료과목 코드)
DEPTS = [("11", "소아청소년과"), ("13", "이비인후과"), ("01", "내과"), ("14", "피부과"), ("12", "안과"),
         ("23", "가정의학과"), ("10", "산부인과"), ("05", "정형외과")]
# 이름으로 과를 한 번 더 확인 (코드가 틀렸을 때 잘못 붙는 것을 막음)
DEPT_HINT = {"소아청소년과": "소아", "이비인후과": "이비인후", "피부과": "피부", "안과": "안과", "산부인과": "산부인|여성", "정형외과": "정형"}
CLINIC_CL = {"31": "의원", "51": "치과의원"}
HOSP_CL = {"01": "상급종합병원", "11": "종합병원", "21": "병원", "41": "치과병원"}


def kq():
    return KEY if "%" in KEY else urllib.parse.quote(KEY, safe="")


def get(url, params, tries=3):
    q = "ServiceKey=" + kq() + "&" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url + "?" + q, headers={"User-Agent": "airang/1.0"}), timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(2 + i * 3)
    raise last


def hira(params):
    """심평원 목록을 끝까지 넘겨 가며 받는다."""
    out, page = [], 1
    while True:
        txt = get(HIRA, dict(params, pageNo=page, numOfRows=500, _type="json"))
        if txt.lstrip().startswith("<"):
            raise RuntimeError("심평원 응답이 JSON 이 아님(활용신청 확인): " + re.sub(r"\s+", " ", txt)[:160])
        body = json.loads(txt).get("response", {}).get("body", {}) or {}
        items = (body.get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        out += items
        total = int(body.get("totalCount") or 0)
        if page * 500 >= total or not items:
            return out
        page += 1
        time.sleep(0.4)


def xml_items(txt):
    root = ET.fromstring(txt)
    code = root.findtext(".//resultCode")
    if code not in (None, "00", "0000"):
        raise RuntimeError("응답 코드 " + str(code) + " " + str(root.findtext(".//resultMsg")))
    return [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]


def nmc(url, params):
    out, page = [], 1
    while True:
        txt = get(url, dict(params, pageNo=page, numOfRows=500))
        if not txt.lstrip().startswith("<"):
            raise RuntimeError("국립중앙의료원 응답이 XML 이 아님: " + txt[:160])
        items = xml_items(txt)
        out += items
        m = re.search(r"<totalCount>(\d+)</totalCount>", txt)
        if not items or not m or page * 500 >= int(m.group(1)):
            return out
        page += 1
        time.sleep(0.4)


def gu_of(addr):
    for g in GU:
        if g in (addr or ""):
            return g
    return ""


def short_addr(addr):
    a = re.sub(r"^\s*경기도\s*", "", addr or "")
    a = re.sub(r"^용인시\s*", "", a)
    return re.sub(r"\s+", " ", a).strip()[:60]


def digits(t):
    return re.sub(r"\D", "", t or "")


def sggu_codes():
    """용인 구 3개의 심평원 시군구 코드. 경기도 종합병원·병원 목록에서 찾아낸다."""
    if SGGU_ENV:
        return dict(x.split("=") for x in SGGU_ENV.split(",") if "=" in x)
    found = {}
    for cl in ("11", "21"):
        for it in hira({"sidoCd": SIDO_CD, "clCd": cl}):
            g = gu_of(it.get("addr", ""))
            if g and "용인" in it.get("addr", "") and it.get("sgguCd"):
                found.setdefault(g, str(it["sgguCd"]))
        if len(found) == len(GU):
            break
    return found


def pt(it):
    try:
        return round(float(it.get("YPos")), 5), round(float(it.get("XPos")), 5)
    except (TypeError, ValueError):
        return None, None


def row(it, kind):
    y, x = pt(it)
    addr = it.get("addr", "")
    r = {"n": it.get("yadmNm", "").strip(), "k": kind, "g": gu_of(addr), "a": short_addr(addr),
         "t": (it.get("telno") or "").strip(), "y": y, "x": x}
    u = (it.get("hospUrl") or "").strip()
    if re.match(r"^https?://", u):
        r["u"] = u
    return r


def main():
    if not KEY:
        raise SystemExit("WEATHER_KEY 없음")
    today = datetime.now(KST)
    result = {"city": CITY, "updated": today.strftime("%Y-%m-%d %H:%M"), "depts": [d for _, d in DEPTS] + ["치과"],
              "src": {"hira": False, "er": False, "hours": False}, "clinics": [], "hospitals": [], "er": []}

    # 1) 심평원 — 의원·병원
    try:
        codes = sggu_codes()
        print("  시군구 코드:", codes)
        if not codes:
            raise RuntimeError("용인 구 코드를 못 찾음 (HOSP_SGGU 로 직접 넣기)")
        clinics, hosps = {}, {}
        for g, sc in codes.items():
            for cl, kind in CLINIC_CL.items():
                for it in hira({"sidoCd": SIDO_CD, "sgguCd": sc, "clCd": cl}):
                    r = row(it, kind)
                    if r["n"]:
                        r["d"] = ["치과"] if cl == "51" else []
                        clinics[it.get("ykiho") or r["n"] + r["t"]] = r
            for code, dept in DEPTS:
                n = 0
                for it in hira({"sidoCd": SIDO_CD, "sgguCd": sc, "clCd": "31", "dgsbjtCd": code}):
                    c = clinics.get(it.get("ykiho") or "")
                    if c is not None and dept not in c["d"]:
                        c["d"].append(dept)
                        n += 1
                print(f"  {g} {dept} {n}곳")
                time.sleep(0.3)
            for cl, kind in HOSP_CL.items():
                for it in hira({"sidoCd": SIDO_CD, "sgguCd": sc, "clCd": cl}):
                    r = row(it, kind)
                    if r["n"]:
                        hosps[it.get("ykiho") or r["n"] + r["t"]] = r
        # 이름이 진료과와 어긋나면(예: 'OO피부과의원'이 소아청소년과로 잡힘) 이름 쪽 과를 맨 앞에
        for c in clinics.values():
            for dept, hint in DEPT_HINT.items():
                if re.search(hint, c["n"]):
                    if dept in c["d"]:
                        c["d"].remove(dept)
                    c["d"].insert(0, dept)
                    break
        order = {"상급종합병원": 0, "종합병원": 1, "병원": 2, "치과병원": 3}
        result["clinics"] = sorted(clinics.values(), key=lambda r: (r["g"], r["n"]))
        result["hospitals"] = sorted(hosps.values(), key=lambda r: (order.get(r["k"], 9), r["g"], r["n"]))
        result["src"]["hira"] = True
        print(f"  의원 {len(result['clinics'])}곳, 병원 {len(result['hospitals'])}곳")
    except Exception as e:
        print("  심평원 병원정보 실패:", e)

    # 2) 국립중앙의료원 — 응급실
    try:
        ers = nmc(ER_LIST, {"Q0": SIDO, "Q1": CITY + "시"})
        for it in ers:
            try:
                y, x = round(float(it.get("wgs84Lat")), 5), round(float(it.get("wgs84Lon")), 5)
            except (TypeError, ValueError):
                y = x = None
            result["er"].append({"n": it.get("dutyName", ""), "k": it.get("dutyEmclsName", "") or "응급실",
                                 "g": gu_of(it.get("dutyAddr", "")), "a": short_addr(it.get("dutyAddr", "")),
                                 "t": it.get("dutyTel3") or it.get("dutyTel1", ""), "t1": it.get("dutyTel1", ""), "y": y, "x": x})
        rank = {"권역응급의료센터": 0, "지역응급의료센터": 1, "지역응급의료기관": 2}
        result["er"].sort(key=lambda r: (rank.get(r["k"], 3), r["n"]))
        result["src"]["er"] = True
        print(f"  응급실 {len(result['er'])}곳")
    except Exception as e:
        print("  응급실 목록 실패:", e)

    # 3) 국립중앙의료원 — 요일별 진료시간 (전화번호로 맞춰 붙임). 없어도 된다.
    try:
        hrs = nmc(HOURS, {"Q0": SIDO, "Q1": CITY + "시"})
        by_tel = {}
        for it in hrs:
            h = [[it.get(f"dutyTime{i}s", ""), it.get(f"dutyTime{i}c", "")] for i in range(1, 9)]  # 월~일, 공휴일
            if any(a for a, _ in h):
                by_tel[digits(it.get("dutyTel1"))] = ["".join(p) if p[0] else "" for p in h]
        hit = 0
        for r in result["clinics"] + result["hospitals"]:
            h = by_tel.get(digits(r["t"]))
            if h:
                r["h"] = h
                hit += 1
        result["src"]["hours"] = hit > 0
        print(f"  진료시간 붙임 {hit}곳 (받은 것 {len(by_tel)}곳)")
    except Exception as e:
        print("  진료시간 실패(없이 저장):", e)

    if not any(result["src"].values()):
        raise SystemExit("세 서비스 모두 실패 — 저장하지 않음 (활용신청 확인)")
    # 이번에 실패한 칸은 지난번 것을 그대로 둔다 (빈 목록으로 덮어쓰지 않게)
    try:
        prev = json.load(open("output/hospitals.json", encoding="utf-8"))
        if not result["src"]["hira"] and prev.get("clinics"):
            result["clinics"], result["hospitals"], result["src"]["hira"] = prev["clinics"], prev.get("hospitals", []), "prev"
        if not result["src"]["er"] and prev.get("er"):
            result["er"], result["src"]["er"] = prev["er"], "prev"
    except (OSError, ValueError):
        pass
    os.makedirs("output", exist_ok=True)
    with open("output/hospitals.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    print("  저장:", os.path.getsize("output/hospitals.json") // 1024, "KB")


if __name__ == "__main__":
    main()
