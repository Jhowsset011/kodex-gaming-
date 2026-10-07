let products = [];
let currentPage = 1;
const PAGE_SIZE = 24;
let catalogLoading = true;

const money = value => 'RD$' + Number(value).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $ = selector => document.querySelector(selector);
const grid = $('#products'), cartDialog = $('#cart'), detailDialog = $('#product-detail');
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
function renderProducts(resetPage = true) {
  if (catalogLoading) return;
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
    `${p.name} ${p.spec || ''} ${p.category || ''} ${p.brand || ''}`.toLocaleLowerCase('es').includes(query) &&
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
  grid.innerHTML = visible.map(p => {
    const badge = badgeFor(p);
    const art = p.image ? `<img src="${escapeHTML(p.image)}" alt="${escapeHTML(p.name)}" loading="lazy">` : '';
    const addBtn = p.stock
      ? `<button class="add" data-add="${p.id}" aria-label="Añadir ${escapeHTML(p.name)} al carrito"><span aria-hidden="true">+</span> Añadir al carrito</button>`
      : `<button class="add" disabled aria-label="${escapeHTML(p.name)} agotado">Agotado</button>`;
    return `<article class="product" data-product="${p.id}">
    <div class="product-art">${badge ? `<span class="badge ${p.old && p.stock ? 'sale' : ''}">${escapeHTML(badge)}</span>` : ''}<button class="product-image-button" data-detail="${p.id}" aria-label="Ver detalles de ${escapeHTML(p.name)}">${art}</button></div>
    <div class="product-copy"><span class="product-type">${escapeHTML(p.category || '')} · ${escapeHTML(p.brand || '')}</span><h3><button class="product-title" data-detail="${p.id}">${escapeHTML(p.name)}</button></h3><p class="product-spec">${escapeHTML(p.spec || '')}</p><div class="product-price"><strong>${money(p.price)}</strong>${p.old ? `<del>${money(p.old)}</del>` : ''}</div>${addBtn}</div></article>`;
  }).join('');
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
function renderCart() {
  const items = products.filter(p => cart[p.id]);
  const total = items.reduce((sum, p) => sum + p.price * cart[p.id], 0);
  $('#cart-count').textContent = Object.values(cart).reduce((a,b) => a+b, 0);
  $('#header-total').textContent = money(total);
  $('#cart-total').textContent = money(total);
  $('#cart-items').innerHTML = items.length ? items.map(p => `<div class="cart-line">${p.image ? `<img src="${escapeHTML(p.image)}" alt="">` : ''}<div><h3>${escapeHTML(p.name)}</h3><p>${money(p.price)}</p><div class="quantity"><button data-change="${p.id}" data-step="-1" aria-label="Quitar una unidad de ${escapeHTML(p.name)}">−</button><span>${cart[p.id]}</span><button data-change="${p.id}" data-step="1" aria-label="Añadir una unidad de ${escapeHTML(p.name)}" ${cart[p.id] >= 99 ? 'disabled' : ''}>+</button></div></div><button class="remove" data-remove="${p.id}" aria-label="Eliminar ${escapeHTML(p.name)}">Eliminar</button></div>`).join('') : '<div class="empty"><strong>Tu próximo upgrade te espera.</strong><p>Explora el catálogo y añade tus favoritos.</p></div>';
  try { localStorage.setItem('kodex-cart', JSON.stringify(cart)); } catch {}
}
let toastTimer;
function addProduct(id) {
  const p = products.find(x => x.id === id);
  if (!p || !p.stock) return;
  cart[id] = Math.min((cart[id] || 0) + 1, 99);
  renderCart();
  const toast = $('#toast');
  toast.textContent = 'Producto añadido a tu carrito';
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2400);
}
function showDetail(id) {
  const p = products.find(p => p.id === id);
  if (!p) return;
  $('#detail-content').innerHTML = `${p.image ? `<img class="detail-image" src="${escapeHTML(p.image)}" alt="${escapeHTML(p.name)}">` : ''}<span class="product-type">${escapeHTML(p.category || '')} · ${escapeHTML(p.brand || '')}</span><h2 id="detail-title">${escapeHTML(p.name)}</h2><p>${escapeHTML(p.spec || '')}</p><p class="detail-price">${money(p.price)}</p><p>Precio y disponibilidad según el catálogo importado de Nexcom. Aún no se procesan pedidos ni pagos.</p><button class="button" data-add="${p.id}" ${p.stock ? '' : 'disabled'}>${p.stock ? 'Añadir al carrito' : 'Agotado'} <span aria-hidden="true">+</span></button>`;
  detailDialog.showModal();
}
function scrollToCatalog() {
  $('#catalogo').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
}

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
  if (detail) showDetail(detail.dataset.detail);
});
$('#detail-content').addEventListener('click', event => {
  const add = event.target.closest('[data-add]');
  if (add) { addProduct(add.dataset.add); detailDialog.close(); }
});
function openCart() { if (catalogLoading) return; renderCart(); cartDialog.showModal(); }
$('#open-cart').addEventListener('click', openCart);
$('#footer-cart').addEventListener('click', openCart);
$('#close-cart').addEventListener('click', () => cartDialog.close());
$('#continue-shopping').addEventListener('click', () => cartDialog.close());
$('#close-detail').addEventListener('click', () => detailDialog.close());
[cartDialog, detailDialog].forEach(dialog => dialog.addEventListener('click', event => {
  if (event.target !== dialog) return;
  const rect = dialog.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
}));
$('#cart-items').addEventListener('click', event => {
  const change = event.target.closest('[data-change]'), remove = event.target.closest('[data-remove]');
  if (change) {
    const id = change.dataset.change;
    if (!products.some(p => p.id === id && p.stock)) return;
    cart[id] = Math.min(99, (cart[id] || 0) + Number(change.dataset.step));
    if (cart[id] <= 0) delete cart[id];
    renderCart();
  }
  if (remove) { delete cart[remove.dataset.remove]; renderCart(); }
});
const mobileQuery = matchMedia('(max-width: 640px)');
function adaptFilters() { $('#filter-panel').open = !mobileQuery.matches; }
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
  grid.setAttribute('aria-busy', 'true');
  $('#empty').hidden = true;
  $('#catalog-error').hidden = true;
  $('#open-cart').disabled = true;
  $('#footer-cart').disabled = true;
  $('#result-count').textContent = 'Cargando productos…';
  try {
    const response = await fetch('js/productos.json', {cache:'no-cache'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const data = await response.json();
    products = validateCatalog(data);
    sanitizeCart();
    renderFilterUI();
    catalogLoading = false;
    renderProducts();
    renderCart();
    $('#open-cart').disabled = false;
    $('#footer-cart').disabled = false;
  } catch {
    $('#catalog-error').hidden = false;
    $('#result-count').textContent = 'Catálogo no disponible';
  } finally {
    $('#catalog-loading').hidden = true;
    grid.setAttribute('aria-busy', 'false');
  }
}
function changePage(page) {
  currentPage = page;
  renderProducts(false);
  scrollToCatalog();
}
$('#retry-catalog').addEventListener('click', loadCatalog);
$('#previous-page').addEventListener('click', () => changePage(Math.max(1, currentPage - 1)));
$('#next-page').addEventListener('click', () => changePage(currentPage + 1));
$('#page-select').addEventListener('change', event => changePage(Number(event.target.value)));
document.addEventListener('error', event => {
  const image = event.target;
  if (image.tagName === 'IMG' && image.closest('.product, .cart-line, #detail-content') && !image.src.endsWith('/sin-imagen.svg')) {
    image.src = 'img/catalogo/sin-imagen.svg';
  }
}, true);
loadCatalog();
