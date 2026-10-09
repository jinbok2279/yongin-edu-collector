// 용인 맘 교육알림 - 오프라인 지원
const CACHE = "edu-app-v28";
const SHELL = ["./", "./index.html", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// 인터넷 먼저, 안 되면 마지막 저장본
function networkFirst(req) {
  return fetch(req)
    .then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
      return res;
    })
    .catch(() => caches.match(req, { ignoreSearch: true }));
}

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  // 수집 데이터 (이 사이트 data/ 폴더 또는 GitHub 원본)
  if (url.hostname === "raw.githubusercontent.com" || (url.origin === self.location.origin && url.pathname.includes("/data/"))) {
    e.respondWith(networkFirst(e.request));
    return;
  }
  // 앱 첫 화면(index.html): 인터넷 먼저 → 새 버전이 바로 보이게
  if (url.origin === self.location.origin && (e.request.mode === "navigate" || url.pathname.endsWith("/") || url.pathname.endsWith("index.html"))) {
    e.respondWith(networkFirst(e.request));
    return;
  }
  // 그 밖의 앱 파일(아이콘 등): 저장본 먼저, 뒤에서 새로 받아 두기
  if (url.origin === self.location.origin) {
    e.respondWith(
      caches.match(e.request).then((hit) => {
        const net = fetch(e.request)
          .then((res) => {
            if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
            return res;
          })
          .catch(() => hit);
        return hit || net;
      })
    );
  }
});
