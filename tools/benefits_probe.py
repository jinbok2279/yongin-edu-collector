"""놓치기 쉬운 혜택·약국 — 공공데이터 시험 (확인 후 지울 것). 결과는 logs/benefits-probe.txt"""
import os, re, urllib.parse, urllib.request
KEY = os.environ.get("WEATHER_KEY", "").strip()
kq = KEY if "%" in KEY else urllib.parse.quote(KEY, safe="")
def get(url, params, timeout=60):
    u = url + "?serviceKey=" + kq + "&" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "airang/1.0"}), timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:
        return 0, str(e)
def items(txt, tag="item"):
    return [dict(re.findall(r"<(\w+)>([^<]*)</\1>", m)) for m in re.findall(rf"<{tag}>(.*?)</{tag}>", txt, re.S)]
def show(title, st, txt, tag="item", keys=None, n=25):
    tc = re.search(r"<totalCount>(\d+)</totalCount>", txt)
    print(f"\n== {title}  상태 {st}  총 {tc.group(1) if tc else '?'}건")
    its = items(txt, tag)
    if not its:
        print(re.sub(r"\s+", " ", txt)[:400]); return
    print("  칸:", sorted(its[0].keys()))
    for it in its[:n]:
        print("  -", " | ".join((it.get(k) or "")[:60] for k in (keys or list(it)[:5])))

# 1) 중앙부처 복지서비스 (복지로)
U1 = "https://apis.data.go.kr/B554287/NationalWelfareInformationsV001/NationalWelfarelistV001"
st, t = get(U1, {"callTp": "L", "pageNo": 1, "numOfRows": 100, "srchKeyCode": "001"})
show("중앙부처 복지 (전체)", st, t, "servList", ["servNm", "jurMnofNm", "lifeArray", "trgterIndvdlArray", "intrsThemaArray", "servDgst"], 15)
for life, nm in [("007", "임신·출산"), ("001", "영유아"), ("002", "아동")]:
    st, t = get(U1, {"callTp": "L", "pageNo": 1, "numOfRows": 100, "srchKeyCode": "001", "lifeArray": life})
    show(f"중앙부처 복지 lifeArray={life}({nm})", st, t, "servList", ["servNm", "jurMnofNm", "lifeArray", "servDgst"], 40)
st, t = get(U1, {"callTp": "L", "pageNo": 1, "numOfRows": 100, "srchKeyCode": "001", "trgterIndvdlArray": "020"})
show("중앙부처 복지 trgterIndvdlArray=020(다자녀?)", st, t, "servList", ["servNm", "trgterIndvdlArray", "servDgst"], 30)

# 2) 지자체 복지서비스 (신청 안 했으면 403)
U2 = "https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/LcgvWelfarelist"
st, t = get(U2, {"pageNo": 1, "numOfRows": 100, "ctpvNm": "경기도", "sggNm": "용인시"})
show("지자체 복지 용인시", st, t, "servList", ["servNm", "sggNm", "lifeNmArray", "trgterIndvdlNmArray", "servDgst"], 40)

# 3) 약국
U3 = "https://apis.data.go.kr/B552657/ErmctInsttInfoInqireService/getParmacyListInfoInqire"
st, t = get(U3, {"Q0": "경기도", "Q1": "용인시", "pageNo": 1, "numOfRows": 20})
show("약국 용인시", st, t, "item", ["dutyName", "dutyAddr", "dutyTel1", "dutyTime1s", "dutyTime1c", "dutyTime7s", "dutyTime7c"], 8)
