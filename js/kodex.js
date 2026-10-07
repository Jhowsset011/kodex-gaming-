let products = [];
let currentPage = 1;
const PAGE_SIZE = 24;
const WHATSAPP_NUMBER = '18098796463';
let catalogLoading = true;

const money = value => 'RD$' + Number(value).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $ = selector => document.querySelector(selector);
const grid = $('#products'), cartDialog = $('#cart');
const isProductPage = Boolean($('#product-page'));
const productURL = product => `producto.html?id=${encodeURIComponent(product.id)}`;
let filter = 'Todos', cart = {};
try {
  const saved = JSON.parse(localStorage.getItem('kodex-cart') || '{}');
  if (saved && typeof saved === 'object' && !Array.isArray(saved)) cart = saved;
} catch {}

function sanitizeCart() {
  const cleaned = {};
  for (const p of products) {
    const quantity = cart[p.id];
    if (p.stock && Number.isInteger(quantity) && quantity > 0) cleaned[p.id] = Math.min(quantity, 99);
  }
  cart = cleaned;
}
function countBy(key) {
  const map = new Map();
  for (const p of products) {
    const k = p[key] || 'Otros';
    map.set(k, (map.get(k) || 0) + 1);
  }
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0], 'es'));
}
function offerCount() { return products.filter(p => p.old && p.old > p.price).length; }
function renderFilterUI() {
  const catBox = $('#category-buttons');
  if (catBox) {
    const cats = countBy('category');
    catBox.innerHTML =
      `<button class="${filter === 'Todos' ? 'active' : ''}" data-filter="Todos" aria-pressed="${filter === 'Todos'}">Todos los productos <span>${products.length}</span></button>` +
      cats.map(([c, n]) => `<button class="${filter === c ? 'active' : ''}" data-filter="${escapeHTML(c)}" aria-pressed="${filter === c}">${escapeHTML(c)} <span>${n}</span></button>`).join('') +
      `<button class="${filter === 'ofertas' ? 'active' : ''}" data-filter="ofertas" aria-pressed="${filter === 'ofertas'}">Ofertas <span>${offerCount()}</span></button>`;
    catBox.querySelectorAll('[data-filter]').forEach(button =>
      button.addEventListener('click', () => selectFilter(button.dataset.filter)));
  }
  const brandBox = $('#brand-options');
  if (brandBox) {
    brandBox.innerHTML = countBy('brand').map(([b, n]) =>
      `<label><input type="checkbox" value="${escapeHTML(b)}" name="brand"> ${escapeHTML(b)} <span>${n}</span></label>`).join('');
    brandBox.querySelectorAll('[name="brand"]').forEach(input =>
      input.addEventListener('change', renderProducts));
  }
}
function badgeFor(p) {
  if (!p.stock) return 'AGOTADO';
  if (p.old && p.old > p.price) return `−${Math.round((1 - p.price / p.old) * 100)}%`;
  return '';
}
const cartIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 4h2l3 12h11l2-8H6M10 20h.01M18 20h.01"/></svg>';
const arrowIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19 19 5M5 5h14v14"/></svg>';
function orderURL(items) {
  const total = items.reduce((sum, {product, quantity}) => sum + product.price * quantity, 0);
  const lines = items.map(({product, quantity}) => `${quantity} × ${product.name}\nCódigo: ${product.reference || product.id} · Precio unitario: ${money(product.price)}\nSubtotal: ${money(product.price * quantity)}`);
  const text = `Hola, Kodex Gaming. Quiero hacer este pedido:\n\n${lines.join('\n\n')}\n\nTotal de productos: ${money(total)}\n¿Me confirman disponibilidad y costo de entrega?`;
  return `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(text)}`;
}
function productActions(p, detail = false) {
  if (!p.stock) return '<button class="order-product" disabled>Agotado</button>';
  return `<div class="product-actions ${detail ? 'detail-actions' : ''}"><a class="order-product" href="${escapeHTML(orderURL([{product:p, quantity:1}]))}" target="_blank" rel="noopener noreferrer" aria-label="Hacer pedido de ${escapeHTML(p.name)} por WhatsApp">Hacer pedido ${arrowIcon}</a><button class="add" data-add="${p.id}" aria-label="Añadir ${escapeHTML(p.name)} al carrito" title="Añadir al carrito">${cartIcon}${detail ? '<span>Añadir al carrito</span>' : ''}</button></div>`;
}
function productCard(p) {
    const badge = badgeFor(p);
    const art = p.image ? `<img src="${escapeHTML(p.image)}" alt="${escapeHTML(p.name)}" loading="lazy">` : '';
    return `<article class="product" data-product="${p.id}">
    <div class="product-art">${badge ? `<span class="badge ${p.old && p.stock ? 'sale' : ''}">${escapeHTML(badge)}</span>` : ''}<a class="product-image-button" href="${productURL(p)}" data-detail="${p.id}" aria-label="Ver detalles de ${escapeHTML(p.name)}">${art}</a><span class="view-product">Ver detalles ${arrowIcon}</span></div>
    <div class="product-copy"><span class="product-type"><span>${escapeHTML(p.brand || '')}</span> ${escapeHTML(p.category || '')}</span><h3><a class="product-title" href="${productURL(p)}" data-detail="${p.id}">${escapeHTML(p.name)}</a></h3><div class="product-price"><strong>${money(p.price)}</strong>${p.old ? `<del>${money(p.old)}</del>` : ''}</div>${productActions(p)}</div></article>`;
}

function renderProducts(resetPage = true) {
  if (catalogLoading || !grid) return;
  if (resetPage) currentPage = 1;
  const query = $('#search').value.trim().toLocaleLowerCase('es');
  const brands = Array.from(document.querySelectorAll('[name="brand"]:checked'), input => input.value);
  const minInput = $('#min-price'), maxInput = $('#max-price');
  const min = minInput.value === '' ? 0 : minInput.valueAsNumber;
  const max = maxInput.value === '' ? Infinity : maxInput.valueAsNumber;
  const invalid = !minInput.validity.valid || !maxInput.validity.valid || min < 0 || max < 0 || min > max;
  $('#price-error').hidden = !invalid;
  minInput.setAttribute('aria-invalid', String(invalid));
  maxInput.setAttribute('aria-invalid', String(invalid));
  const list = invalid ? [] : products.filter(p =>
    (filter === 'Todos' || (filter === 'ofertas' ? p.old > p.price : p.category === filter)) &&
    `${p.name} ${p.spec || ''} ${p.category || ''} ${p.brand || ''} ${p.reference || ''} ${p.model || ''}`.toLocaleLowerCase('es').includes(query) &&
    (!brands.length || brands.includes(p.brand)) && p.price >= min && p.price <= max
  );
  const sort = $('#sort').value;
  if (sort === 'price-asc') list.sort((a,b) => a.price - b.price);
  if (sort === 'price-desc') list.sort((a,b) => b.price - a.price);
  if (sort === 'name') list.sort((a,b) => a.name.localeCompare(b.name, 'es'));
  const totalPages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
  currentPage = Math.min(currentPage, totalPages);
  const start = (currentPage - 1) * PAGE_SIZE;
  const visible = list.slice(start, start + PAGE_SIZE);
  grid.innerHTML = visible.map(productCard).join('');
  $('#empty').hidden = list.length > 0;
  $('#result-count').textContent = list.length ? `Mostrando ${start + 1}–${Math.min(start + PAGE_SIZE, list.length)} de ${list.length} productos` : 'No hay productos con estos filtros';
  $('#pagination').hidden = list.length <= PAGE_SIZE;
  $('#previous-page').disabled = currentPage === 1;
  $('#next-page').disabled = currentPage === totalPages;
  $('#total-pages').textContent = totalPages;
  $('#page-select').innerHTML = Array.from({length:totalPages}, (_, i) => `<option value="${i + 1}" ${currentPage === i + 1 ? 'selected' : ''}>${i + 1}</option>`).join('');
  $('#catalog-title').textContent = filter === 'Todos' ? 'Todos los productos' : filter === 'ofertas' ? 'Ofertas gaming' : filter;
  const chips = [];
  if (filter !== 'Todos') chips.push({type:'category', text:filter === 'ofertas' ? 'Ofertas' : filter});
  if (query) chips.push({type:'search', text:`Búsqueda: ${$('#search').value.trim()}`});
  if (minInput.value !== '') chips.push({type:'min', text:`Desde ${money(min)}`});
  if (maxInput.value !== '') chips.push({type:'max', text:`Hasta ${money(max)}`});
  brands.forEach(brand => chips.push({type:'brand', value:brand, text:brand}));
  $('#active-filters').innerHTML = chips.map(chip => `<button data-clear="${chip.type}" data-value="${escapeHTML(chip.value || '')}" aria-label="Quitar filtro ${escapeHTML(chip.text)}">${escapeHTML(chip.text)} <span aria-hidden="true">×</span></button>`).join('');
}
function selectFilter(value) {
  filter = value;
  document.querySelectorAll('[data-filter]').forEach(button => {
    const selected = button.dataset.filter === value;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  renderProducts();
}
function resetFilters() {
  $('#search').value = '';
  $('#min-price').value = '';
  $('#max-price').value = '';
  $('#sort').value = 'featured';
  document.querySelectorAll('[name="brand"]').forEach(input => input.checked = false);
  selectFilter('Todos');
}
function updateCartSummary() {
  const items = products.filter(p => cart[p.id]);
  const total = items.reduce((sum, p) => sum + p.price * cart[p.id], 0);
  const quantity = items.reduce((sum, p) => sum + cart[p.id], 0);
  $('#cart-count').textContent = quantity;
  $('#cart-item-count').textContent = quantity;
  $('#header-total').textContent = money(total);
  $('#cart-total').textContent = money(total);
  $('#cart-summary-count').textContent = `${quantity} artículo${quantity === 1 ? '' : 's'}`;
  $('#cart-checkout').hidden = !items.length;
  const orderLink = $('#cart-order');
  if (items.length) orderLink.href = orderURL(items.map(product => ({product, quantity:cart[product.id]})));
  else orderLink.removeAttribute('href');
  return items;
}
function renderCart() {
  const items = updateCartSummary();
  $('#cart-items').innerHTML = items.length ? items.map(p => `<div class="cart-line" data-cart-product="${p.id}"><img src="${escapeHTML(p.image || 'img/catalogo/sin-imagen.svg')}" alt=""><div class="cart-line-info"><div class="cart-line-heading"><h3>${escapeHTML(p.name)}</h3><button class="remove" data-remove="${p.id}" aria-label="Eliminar ${escapeHTML(p.name)}" title="Eliminar producto"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13M10 10v7M14 10v7"/></svg></button></div><p>${money(p.price)} <span>/ unidad</span></p><div class="cart-line-bottom"><div class="quantity"><button data-change="${p.id}" data-step="-1" aria-label="Quitar una unidad de ${escapeHTML(p.name)}" ${cart[p.id] <= 1 ? 'disabled' : ''}>−</button><input type="number" min="1" max="99" step="1" value="${cart[p.id]}" data-quantity="${p.id}" aria-label="Cantidad de ${escapeHTML(p.name)}"><button data-change="${p.id}" data-step="1" aria-label="Añadir una unidad de ${escapeHTML(p.name)}" ${cart[p.id] >= 99 ? 'disabled' : ''}>+</button></div><strong>${money(p.price * cart[p.id])}</strong></div></div></div>`).join('') : `<div class="cart-empty">${cartIcon}<h3>Tu próximo upgrade te espera.</h3><p>Añade tus favoritos para preparar tu pedido.</p><button class="button" data-browse>Explorar la tienda ${arrowIcon}</button></div>`;
  try { localStorage.setItem('kodex-cart', JSON.stringify(cart)); } catch {}
}
function updateQuantity(id, quantity) {
  const product = products.find(p => p.id === id && p.stock);
  if (!product || !cart[id] || !Number.isInteger(quantity) || quantity < 1 || quantity > 99) return;
  cart[id] = quantity;
  const line = document.querySelector(`[data-cart-product="${id}"]`);
  if (line) {
    line.querySelector('[data-quantity]').value = quantity;
    line.querySelector('[data-step="-1"]').disabled = quantity === 1;
    line.querySelector('[data-step="1"]').disabled = quantity === 99;
    line.querySelector('.cart-line-bottom > strong').textContent = money(product.price * quantity);
  }
  updateCartSummary();
  try { localStorage.setItem('kodex-cart', JSON.stringify(cart)); } catch {}
}
let toastTimer;
function hideToast() {
  clearTimeout(toastTimer);
  $('#toast').hidden = true;
  $('#toast').classList.remove('show');
}
function addProduct(id) {
  const p = products.find(x => x.id === id);
  if (!p || !p.stock) return;
  if (cart[id] >= 99) return;
  cart[id] = (cart[id] || 0) + 1;
  renderCart();
  $('#toast-message').textContent = 'Añadido a tu carrito';
  $('#toast').hidden = false;
  $('#toast').classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, 5000);
}
function scrollToCatalog() {
  if (!$('#catalogo')) { location.href = 'index.html#catalogo'; return; }
  $('#catalogo').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
}

function rememberCatalog() {
  try { sessionStorage.setItem('kodex-catalog-state', JSON.stringify({url:location.pathname + location.search, filter, query:$('#search').value, min:$('#min-price').value, max:$('#max-price').value, sort:$('#sort').value, brands:Array.from(document.querySelectorAll('[name="brand"]:checked'), input=>input.value), page:currentPage, scroll:window.scrollY})); } catch {}
}
function restoreCatalog() {
  let state;
  try { state = JSON.parse(sessionStorage.getItem('kodex-catalog-state') || 'null'); sessionStorage.removeItem('kodex-catalog-state'); } catch {}
  if (state && state.url !== location.pathname + location.search) state = null;
  const params = new URLSearchParams(location.search);
  if (!state && (params.has('buscar') || params.has('categoria'))) {
    $('#search').value = params.get('buscar') || '';
    const category = params.get('categoria');
    selectFilter(category === 'ofertas' || products.some(p=>p.category === category) ? category : 'Todos');
    return;
  }
  if (!state) { renderProducts(); return; }
  $('#search').value = typeof state.query === 'string' ? state.query : '';
  $('#min-price').value = state.min || '';
  $('#max-price').value = state.max || '';
  $('#sort').value = ['featured','price-asc','price-desc','name'].includes(state.sort) ? state.sort : 'featured';
  document.querySelectorAll('[name="brand"]').forEach(input => input.checked = Array.isArray(state.brands) && state.brands.includes(input.value));
  selectFilter(state.filter === 'ofertas' || products.some(p=>p.category === state.filter) ? state.filter : 'Todos');
  currentPage = Number.isInteger(state.page) && state.page > 0 ? state.page : 1;
  renderProducts(false);
  if (Number.isFinite(state.scroll)) requestAnimationFrame(()=>scrollTo(0,state.scroll));
}
if (grid) {
  document.querySelectorAll('[data-category]').forEach(button => button.addEventListener('click', () => {
    resetFilters();
    selectFilter(button.dataset.category);
    if (button.tagName === 'BUTTON') scrollToCatalog();
  }));
  $('#search').addEventListener('input', renderProducts);
  $('#search-form').addEventListener('submit', event => { event.preventDefault(); renderProducts(); scrollToCatalog(); });
  $('#sort').addEventListener('change', renderProducts);
  ['#min-price', '#max-price'].forEach(selector => $(selector).addEventListener('input', renderProducts));
  $('#reset-filters').addEventListener('click', resetFilters);
  $('#empty-reset').addEventListener('click', resetFilters);
  $('#active-filters').addEventListener('click', event => {
    const button = event.target.closest('[data-clear]');
    if (!button) return;
    if (button.dataset.clear === 'category') { selectFilter('Todos'); return; }
    if (button.dataset.clear === 'search') $('#search').value = '';
    if (button.dataset.clear === 'min') $('#min-price').value = '';
    if (button.dataset.clear === 'max') $('#max-price').value = '';
    if (button.dataset.clear === 'brand') document.querySelectorAll('[name="brand"]').forEach(input => { if (input.value === button.dataset.value) input.checked = false; });
    renderProducts();
  });
  grid.addEventListener('click', event => {
    const add = event.target.closest('[data-add]'), detail = event.target.closest('[data-detail]');
    if (add) addProduct(add.dataset.add);
    if (detail && !event.ctrlKey && !event.metaKey) rememberCatalog();
  });
}
if (isProductPage) {
  $('#search-form').addEventListener('submit', event => {
    event.preventDefault();
    location.href = `index.html?buscar=${encodeURIComponent($('#search').value.trim())}#catalogo`;
  });
  $('#product-view').addEventListener('click', event => {
    const add = event.target.closest('[data-add]');
    if (add) addProduct(add.dataset.add);
  });
  $('#related-products').addEventListener('click', event => {
    const add = event.target.closest('[data-add]');
    if (add) addProduct(add.dataset.add);
  });
}
function openCart() { if (catalogLoading) return; hideToast(); renderCart(); cartDialog.showModal(); }
$('#open-cart').addEventListener('click', openCart);
$('#footer-cart').addEventListener('click', openCart);
$('#toast-cart').addEventListener('click', openCart);
$('#close-cart').addEventListener('click', () => cartDialog.close());
$('#continue-shopping').addEventListener('click', () => cartDialog.close());
[cartDialog].forEach(dialog => dialog.addEventListener('click', event => {
  if (event.target !== dialog) return;
  const rect = dialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
}));
$('#cart-items').addEventListener('click', event => {
  if (event.target.closest('[data-browse]')) { cartDialog.close(); scrollToCatalog(); return; }
  const change = event.target.closest('[data-change]'), remove = event.target.closest('[data-remove]');
  if (change) {
    const id = change.dataset.change;
    if (!products.some(p => p.id === id && p.stock) || !cart[id]) return;
    updateQuantity(id, Math.max(1, Math.min(99, cart[id] + Number(change.dataset.step))));
    const replacement = document.querySelector(`[data-change="${id}"][data-step="${change.dataset.step}"]`);
    if (replacement && !replacement.disabled) replacement.focus({preventScroll:true});
    else document.querySelector(`[data-quantity="${id}"]`)?.focus({preventScroll:true});
  }
  if (remove) {
    delete cart[remove.dataset.remove];
    renderCart();
    ($('#cart-items .remove') || $('#cart-items [data-browse]') || $('#continue-shopping')).focus({preventScroll:true});
  }
});
$('#cart-items').addEventListener('change', event => {
  const input = event.target.closest('[data-quantity]');
  if (!input || !cart[input.dataset.quantity]) return;
  const value = input.valueAsNumber;
  if (!Number.isInteger(value) || value < 1 || value > 99) { input.value = cart[input.dataset.quantity]; return; }
  updateQuantity(input.dataset.quantity, value);
});
const mobileQuery = matchMedia('(max-width: 640px)');
function adaptFilters() { if ($('#filter-panel')) $('#filter-panel').open = !mobileQuery.matches; }
adaptFilters();
mobileQuery.addEventListener('change', adaptFilters);
$('#year').textContent = new Date().getFullYear();

function validateCatalog(data) {
  if (!data || !Array.isArray(data.products) || !data.products.length) throw new Error('Catálogo vacío o inválido');
  const ids = new Set();
  for (const p of data.products) {
    if (typeof p.id !== 'string' || !/^[a-zA-Z0-9_-]+$/.test(p.id) || ids.has(p.id) ||
        typeof p.name !== 'string' || !p.name.trim() || typeof p.category !== 'string' ||
        typeof p.brand !== 'string' || !Number.isFinite(p.price) || p.price <= 0 ||
        typeof p.stock !== 'boolean' || typeof p.image !== 'string') throw new Error('Producto inválido');
    if (p.image && !p.image.startsWith('img/catalogo/') && !p.image.startsWith('https://nexcomtienda.com.do/')) throw new Error('Imagen inválida');
    if (p.old !== undefined && (!Number.isFinite(p.old) || p.old <= p.price)) throw new Error('Oferta inválida');
    ids.add(p.id);
  }
  return data.products;
}
async function loadCatalog() {
  catalogLoading = true;
  $('#catalog-loading').hidden = false;
  if (grid) grid.setAttribute('aria-busy', 'true');
  if ($('#empty')) $('#empty').hidden = true;
  $('#catalog-error').hidden = true;
  $('#open-cart').disabled = true;
  $('#footer-cart').disabled = true;
  if ($('#result-count')) $('#result-count').textContent = 'Cargando productos…';
  try {
    const response = await fetch('js/productos.json', {cache:'no-cache'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const data = await response.json();
    products = validateCatalog(data);
    sanitizeCart();
    catalogLoading = false;
    if (isProductPage) renderProductPage();
    else { renderFilterUI(); restoreCatalog(); }
    renderCart();
    $('#open-cart').disabled = false;
    $('#footer-cart').disabled = false;
  } catch {
    $('#catalog-error').hidden = false;
    if ($('#result-count')) $('#result-count').textContent = 'Catálogo no disponible';
  } finally {
    $('#catalog-loading').hidden = true;
    if (grid) grid.setAttribute('aria-busy', 'false');
  }
}
function changePage(page) {
  currentPage = page;
  renderProducts(false);
  scrollToCatalog();
}
$('#retry-catalog').addEventListener('click', loadCatalog);
if (grid) {
  $('#previous-page').addEventListener('click', () => changePage(Math.max(1, currentPage - 1)));
  $('#next-page').addEventListener('click', () => changePage(currentPage + 1));
  $('#page-select').addEventListener('change', event => changePage(Number(event.target.value)));
}
document.addEventListener('error', event => {
  const image = event.target;
  if (image.tagName === 'IMG' && image.closest('.product, .cart-line, #product-view') && !image.src.endsWith('/sin-imagen.svg')) {
    image.src = 'img/catalogo/sin-imagen.svg';
  }
}, true);
loadCatalog();
