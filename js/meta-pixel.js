(function (window, document) {
  'use strict';
  if (window.KodexPixel) return;
  const PIXEL_ID = '2319748675459306';
  const viewed = new Set();

  // Meta's base loader queues events while its asynchronous script loads.
  !function(f,b,e,v,n,t,s)
  {if(f.fbq)return;n=f.fbq=function(){n.callMethod?
  n.callMethod.apply(n,arguments):n.queue.push(arguments)};
  if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
  n.queue=[];t=b.createElement(e);t.async=!0;
  t.src=v;s=b.getElementsByTagName(e)[0];
  s.parentNode.insertBefore(t,s)}(window, document,'script',
  'https://connect.facebook.net/en_US/fbevents.js');

  function send() {
    try { if (typeof window.fbq === 'function') window.fbq.apply(window, arguments); }
    catch (_) { /* Measurement failures must not interrupt shopping. */ }
  }

  function details(items) {
    if (!Array.isArray(items) || !items.length) return null;
    if (items.some(item => !item || !item.product || typeof item.product.id !== 'string' ||
        !item.product.id || !Number.isInteger(item.quantity) || item.quantity < 1 || item.quantity > 99)) return null;
    const contents = items.map(({product, quantity}) => {
      const item = {id: product.id, quantity};
      if (Number.isFinite(product.price) && product.price > 0) item.item_price = product.price;
      return item;
    });
    const data = {content_ids: [...new Set(contents.map(item => item.id))],
      content_type: 'product', contents, currency: 'DOP'};
    if (contents.every(item => Number.isFinite(item.item_price))) {
      data.value = Math.round(contents.reduce((sum, item) => sum + item.item_price * item.quantity, 0) * 100) / 100;
    }
    return data;
  }

  window.KodexPixel = Object.freeze({
    viewProduct(product) {
      const data = details([{product, quantity: 1}]);
      if (!data || viewed.has(product.id)) return;
      viewed.add(product.id);
      send('track', 'ViewContent', data);
    },
    addToCart(product, quantity = 1) {
      if (!product || !product.stock || !Number.isFinite(product.price) || product.price <= 0) return;
      const data = details([{product, quantity}]);
      if (data) send('track', 'AddToCart', data);
    },
    contact(items = [], source = 'advisory') {
      const data = details(items) || {};
      send('track', 'Contact', {...data, contact_method: 'WhatsApp',
        contact_source: ['product', 'cart', 'advisory'].includes(source) ? source : 'advisory'});
    }
  });

  // Only the explicit events above are used; no automatic form matching.
  send('set', 'autoConfig', false, PIXEL_ID);
  send('init', PIXEL_ID);
  send('track', 'PageView');
})(window, document);
