// static/service-worker.js
const CACHE_NAME = 'pdf-translator-v1.0.1';
const urlsToCache = [
  '/',
  '/static/styles.css',
  '/static/script.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/manifest.json'
];

// 安装事件
self.addEventListener('install', (event) => {
  console.log('Service Worker: Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('Service Worker: Caching files');
        // 逐个添加，跳过404的文件
        return Promise.allSettled(
          urlsToCache.map(url => 
            cache.add(url).catch(err => {
              console.warn(`Failed to cache ${url}:`, err);
            })
          )
        );
      })
      .then(() => {
        console.log('Service Worker: Installed');
        return self.skipWaiting();
      })
  );
});

// 激活事件
self.addEventListener('activate', (event) => {
  console.log('Service Worker: Activating...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('Service Worker: Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      console.log('Service Worker: Activated');
      return self.clients.claim();
    })
  );
});

// 拦截请求
self.addEventListener('fetch', (event) => {
  // 只缓存GET请求
  if (event.request.method !== 'GET') {
    return;
  }

  // 跳过chrome-extension和其他非http请求
  if (!event.request.url.startsWith('http')) {
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then((response) => {
        // 如果缓存中有，直接返回
        if (response) {
          return response;
        }

        // 否则从网络获取
        return fetch(event.request).then((response) => {
          // 检查是否是有效响应
          if (!response || response.status !== 200 || response.type !== 'basic') {
            return response;
          }

          // 克隆响应
          const responseToCache = response.clone();

          // 缓存响应
          caches.open(CACHE_NAME)
            .then((cache) => {
              cache.put(event.request, responseToCache);
            });

          return response;
        });
      })
      .catch(() => {
        // 网络失败时的fallback
        if (event.request.destination === 'document') {
          return caches.match('/');
        }
      })
  );
});