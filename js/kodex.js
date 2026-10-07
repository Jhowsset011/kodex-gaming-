const products = [
 {id:'forge321',name:'MSI MAG Forge 321R',brand:'MSI',category:'Gabinetes',spec:'Mid Tower · 4 ventiladores ARGB',price:4550,old:5000,image:'img/productos/case/msi2.png',badge:'−9%'},
 {id:'rtx5070',name:'MSI GeForce RTX 5070',brand:'MSI',category:'Componentes',spec:'12 GB GDDR7 · Shadow 3X OC',price:42900,image:'img/productos/nuevos/tarjeta1.png',badge:'NUEVO'},
 {id:'aoc49',name:'AOC Gaming 49″ Curvo',brand:'AOC',category:'Monitores',spec:'5120 × 1440 · 165 Hz',price:48900,image:'img/productos/nuevos/monitor1.png',badge:'ULTRAWIDE'},
 {id:'a550',name:'MSI MAG A550BN',brand:'MSI',category:'Componentes',spec:'550 W · Certificación 80 Plus Bronze',price:4350,old:4555.4,image:'img/productos/power/power msi1.png',badge:'−5%'},
 {id:'forge120',name:'MSI MAG Forge 120A',brand:'MSI',category:'Gabinetes',spec:'Mid Tower · Airflow · RGB',price:4550.4,image:'img/productos/case/msi1.png'},
 {id:'rtx3060',name:'MSI GeForce RTX 3060',brand:'MSI',category:'Componentes',spec:'12 GB · Ventus 2X OC',price:21900,image:'img/productos/nuevos/tarjeta2.png'},
 {id:'corsair',name:'Corsair Crystal 280X RGB',brand:'Corsair',category:'Gabinetes',spec:'Micro ATX · Cristal templado',price:10900,image:'img/productos/nuevos/case1.png',badge:'FAVORITO'},
 {id:'fury',name:'Kingston Fury Beast',brand:'Kingston',category:'Componentes',spec:'Memoria RAM · Rendimiento gaming',price:3200,image:'img/productos/memoria ram/fury1.png'}
];

const money = value => 'RD$' + value.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $ = selector => document.querySelector(selector);
const grid = $('#products'), cartDialog = $('#cart'), detailDialog = $('#product-detail');
let filter = 'Todos', cart = {};
try {
  const saved = JSON.parse(localStorage.getItem('kodex-cart') || '{}');
  for (const p of products) if (Number.isInteger(saved?.[p.id]) && saved[p.id] > 0) cart[p.id] = Math.min(saved[p.id], 99);
} catch {}

function renderProducts() {
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
    (filter === 'Todos' || (filter === 'ofertas' ? Boolean(p.old) : p.category === filter)) &&
    `${p.name} ${p.spec} ${p.category} ${p.brand}`.toLocaleLowerCase('es').includes(query) &&
    (!brands.length || brands.includes(p.brand)) && p.price >= min && p.price <= max
  );
  const sort = $('#sort').value;
  if (sort === 'price-asc') list.sort((a,b) => a.price - b.price);
  if (sort === 'price-desc') list.sort((a,b) => b.price - a.price);
  if (sort === 'name') list.sort((a,b) => a.name.localeCompare(b.name, 'es'));
  grid.innerHTML = list.map(p => `<article class="product" data-product="${p.id}">
    <div class="product-art">${p.badge ? `<span class="badge ${p.old ? 'sale' : ''}">${escapeHTML(p.badge)}</span>` : ''}<button class="product-image-button" data-detail="${p.id}" aria-label="Ver detalles de ${escapeHTML(p.name)}"><img src="${escapeHTML(p.image)}" alt="${escapeHTML(p.name)}" loading="lazy"></button></div>
    <div class="product-copy"><span class="product-type">${escapeHTML(p.category)} · ${escapeHTML(p.brand)}</span><h3><button class="product-title" data-detail="${p.id}">${escapeHTML(p.name)}</button></h3><p class="product-spec">${escapeHTML(p.spec)}</p><div class="product-price"><strong>${money(p.price)}</strong>${p.old ? `<del>${money(p.old)}</del>` : ''}</div><button class="add" data-add="${p.id}" aria-label="Añadir ${escapeHTML(p.name)} al carrito"><span aria-hidden="true">+</span> Añadir al carrito</button></div></article>`).join('');
  $('#empty').hidden = list.length > 0;
  $('#result-count').textContent = `Mostrando ${list.length} de ${products.length} productos`;
  $('#catalog-title').textContent = filter === 'Todos' ? 'Zona Gamer' : filter === 'ofertas' ? 'Ofertas gaming' : filter;
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
  $('#cart-items').innerHTML = items.length ? items.map(p => `<div class="cart-line"><img src="${escapeHTML(p.image)}" alt=""><div><h3>${escapeHTML(p.name)}</h3><p>${money(p.price)}</p><div class="quantity"><button data-change="${p.id}" data-step="-1" aria-label="Quitar una unidad de ${escapeHTML(p.name)}">−</button><span>${cart[p.id]}</span><button data-change="${p.id}" data-step="1" aria-label="Añadir una unidad de ${escapeHTML(p.name)}" ${cart[p.id] >= 99 ? 'disabled' : ''}>+</button></div></div><button class="remove" data-remove="${p.id}" aria-label="Eliminar ${escapeHTML(p.name)}">Eliminar</button></div>`).join('') : '<div class="empty"><strong>Tu próximo upgrade te espera.</strong><p>Explora el catálogo y añade tus favoritos.</p></div>';
  try { localStorage.setItem('kodex-cart', JSON.stringify(cart)); } catch {}
}
let toastTimer;
function addProduct(id) {
  if (!products.some(p => p.id === id)) return;
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
  $('#detail-content').innerHTML = `<img class="detail-image" src="${escapeHTML(p.image)}" alt="${escapeHTML(p.name)}"><span class="product-type">${escapeHTML(p.category)} · ${escapeHTML(p.brand)}</span><h2 id="detail-title">${escapeHTML(p.name)}</h2><p>${escapeHTML(p.spec)}</p><p class="detail-price">${money(p.price)}</p><p>Precio de referencia. Este catálogo aún no procesa pedidos ni pagos.</p><button class="button" data-add="${p.id}">Añadir al carrito <span aria-hidden="true">+</span></button>`;
  detailDialog.showModal();
}
function scrollToCatalog() {
  $('#catalogo').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
}

document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => selectFilter(button.dataset.filter)));
document.querySelectorAll('[data-category]').forEach(button => button.addEventListener('click', () => {
  resetFilters();
  selectFilter(button.dataset.category);
  if (button.tagName === 'BUTTON') scrollToCatalog();
}));
$('#search').addEventListener('input', renderProducts);
$('#search-form').addEventListener('submit', event => { event.preventDefault(); renderProducts(); scrollToCatalog(); });
$('#sort').addEventListener('change', renderProducts);
['#min-price', '#max-price'].forEach(selector => $(selector).addEventListener('input', renderProducts));
document.querySelectorAll('[name="brand"]').forEach(input => input.addEventListener('change', renderProducts));
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
function openCart() { renderCart(); cartDialog.showModal(); }
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
renderProducts();
renderCart();
