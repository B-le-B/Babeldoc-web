const CACHE_NAME = 'pdf-translator-cache-v1';
// 需要缓存的核心文件列表
const urlsToCache = [
  '/static/offline.html',
  '/static/icons/192x192.png',
  '/static/icons/512x512.png'
];

// 安装 Service Worker 时，缓存核心资源
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
  );
});

// 拦截网络请求
self.addEventListener('fetch', event => {
  event.respondWith(
    // 优先尝试从网络获取资源
    fetch(event.request)
      .catch(() => {
        // 如果网络请求失败（即离线），则从缓存中查找
        // 特别是对于页面导航请求，返回离线页面
        if (event.request.mode === 'navigate') {
          return caches.match('/static/offline.html');
        }
      })
  );
});
