"""놓치기 쉬운 혜택 — 공공데이터 시험 (한 번 돌려 보고 지울 것). 결과는 logs/benefits-probe.txt"""
import json, os, urllib.parse, urllib.request
KEY = os.environ.get("WEATHER_KEY", "").strip()
kq = KEY if "%" in KEY else urllib.parse.quote(KEY, safe="")
def get(url, timeout=60):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "airang/1.0"}), timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:
        return 0, str(e)

print("== 1) 행정안전부 공공서비스(혜택) 정보 (보조금24)")
base = "https://api.odcloud.kr/api/gov24/v3/"
for city in ["용인시", "수원시"]:
    q = urllib.parse.urlencode({"page": 1, "perPage": 100, "returnType": "JSON", "cond[소관기관명::LIKE]": city})
    st, txt = get(base + "serviceList?serviceKey=" + kq + "&" + q)
    print(city, "상태", st)
    try:
        j = json.loads(txt)
        print("  총", j.get("totalCount"), "건, 이번", j.get("currentCount"))
        data = j.get("data") or []
        if data:
            print("  칸:", sorted(data[0].keys()))
        for d in data[:40]:
            print("  -", d.get("서비스명"), "|", d.get("소관기관명"), "|", d.get("서비스분야"), "|", d.get("사용자구분"), "|", (d.get("지원내용") or "")[:50].replace("\n", " "))
    except Exception as e:
        print("  ", txt[:300])
st, txt = get(base + "supportConditions?serviceKey=" + kq + "&page=1&perPage=2&returnType=JSON")
print("supportConditions 상태", st, txt[:700])

print("\n== 2) 한국사회보장정보원 지자체 복지서비스 (복지로)")
b2 = "https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/LcgvWelfarelist"
for city in ["용인시", "수원시"]:
    q = urllib.parse.urlencode({"pageNo": 1, "numOfRows": 100, "ctpvNm": "경기도", "sggNm": city})
    st, txt = get(b2 + "?serviceKey=" + kq + "&" + q)
    print(city, "상태", st, "길이", len(txt))
    print(txt[:2500])
