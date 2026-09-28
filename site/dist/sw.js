/* Retire the old WordFlow PWA registration formerly installed on :4174.
   Do not clear IndexedDB or site data. Stock Radar does not use a service worker. */
self.addEventListener('install', event => {
  event.waitUntil(self.skipWaiting());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    await self.registration.unregister();
    const clients = await self.clients.matchAll({type:'window', includeUncontrolled:true});
    for (const client of clients) {
      if (new URL(client.url).origin === self.location.origin) await client.navigate(client.url);
    }
  })());
});
