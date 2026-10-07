function renderProductPage() {
  const id = new URLSearchParams(location.search).get('id');
  const product = products.find(item => item.id === id);
  const view = $('#product-view');
  if (!product) {
    document.title = 'Producto no encontrado | Kodex Gaming';
    $('#product-breadcrumb').textContent = 'Producto no encontrado';
    view.innerHTML = '<div class="empty"><strong>No encontramos este producto.</strong><p>Explora la tienda para encontrar tu próximo upgrade.</p><a class="button" href="index.html#catalogo">Volver a la tienda</a></div>';
    $('#related-section').hidden = true;
    return;
  }
  document.title = `${product.name} | Kodex Gaming`;
  document.querySelector('meta[name="description"]').content = `${product.name}. ${product.description || product.spec || ''}`;
  $('#product-breadcrumb').textContent = product.name;
  const specifications = Array.isArray(product.specifications) ? product.specifications : [];
  const features = Array.isArray(product.features) ? product.features : [];
  const description = product.description || product.spec || '';
  const paragraphs = description.split(/\n+/).filter(Boolean).map(text => `<p>${escapeHTML(text)}</p>`).join('');
  const rows = specifications.map(row => `<div class="spec-row"><dt>${escapeHTML(row.label)}</dt><dd>${escapeHTML(row.value)}</dd></div>`).join('');
  view.innerHTML = `<div class="product-overview">
    <div class="product-photo"><img src="${escapeHTML(product.image || 'img/catalogo/sin-imagen.svg')}" alt="${escapeHTML(product.name)}" width="520" height="440" fetchpriority="high"></div>
    <div class="product-information">
      <a class="eyebrow" href="index.html?categoria=${encodeURIComponent(product.category)}#catalogo">${escapeHTML(product.brand)} · ${escapeHTML(product.category)}</a>
      <h1>${escapeHTML(product.name)}</h1>
      <p class="product-reference">Referencia: <span>${escapeHTML(product.reference || product.id)}</span>${product.model ? ` · Modelo: <span>${escapeHTML(product.model)}</span>` : ''}</p>
      <div class="product-description">${paragraphs}</div>
      <a class="text-link specifications-link" href="#caracteristicas">Ver características principales <span aria-hidden="true">↓</span></a>
      <div class="page-pricing"><strong>${money(product.price)}</strong>${product.old ? `<del>${money(product.old)}</del>` : ''}</div>
      ${productActions(product, true)}
      <p class="purchase-hint">${product.stock ? 'Pedidos y asesoría por WhatsApp.' : 'Consulta alternativas con nuestro equipo por WhatsApp.'}</p>
    </div>
  </div>
  <section class="specifications-section" id="caracteristicas" aria-labelledby="specifications-title">
    <div class="section-heading"><div><span class="eyebrow">CONOCE TU PRÓXIMO UPGRADE</span><h2 id="specifications-title">Características principales</h2></div></div>
    <div class="specifications-card">${rows ? `<dl class="specifications-list">${rows}</dl>` : ''}${features.length ? `<ul class="product-features">${features.map(feature => `<li>${escapeHTML(feature)}</li>`).join('')}</ul>` : ''}${!rows && !features.length ? `<p>${escapeHTML(description)}</p>` : ''}${product.specificationNote ? `<p class="specification-note">${escapeHTML(product.specificationNote)}</p>` : ''}</div>
  </section>`;
  const related = products.filter(item => item.category === product.category && item.id !== product.id).slice(0, 3);
  $('#related-products').innerHTML = related.map(productCard).join('');
  $('#related-section').hidden = !related.length;
}
