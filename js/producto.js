function specificationIcon(label) {
  const key = String(label).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  let shape = '<path d="M8 3h8v3h3v15H5V6h3Z"/><path d="M9 11h6M9 15h6"/>';
  if (/marca|fabricante/.test(key)) shape = '<path d="M3 4h10l8 8-9 9-9-9Z"/><circle cx="8" cy="9" r="1"/>';
  else if (/modelo|numero de parte|referencia/.test(key)) shape = '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 9v6M11 9h2a3 3 0 0 1 0 6h-2Z"/>';
  else if (/tamano|dimension|peso|altura|ancho|largo/.test(key)) shape = '<path d="m4 16 12-12 4 4L8 20Z"/><path d="m10 10 3 3m1-7 3 3m-11 5 3 3"/>';
  else if (/resolucion|pantalla|panel|diseno|curvatura/.test(key)) shape = '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>';
  else if (/refresco|frecuencia|velocidad|potencia/.test(key)) shape = '<path d="m13 2-8 12h7l-1 8 8-12h-7Z"/>';
  else if (/respuesta|latencia/.test(key)) shape = '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M9 2h6m-3 0v3m6 1 2-2"/>';
  else if (/audio|sonido|bocina|auricular/.test(key)) shape = '<path d="M4 13v-1a8 8 0 0 1 16 0v1"/><rect x="3" y="12" width="4" height="8" rx="2"/><rect x="17" y="12" width="4" height="8" rx="2"/>';
  else if (/conect|puerto|interfaz|entrada|salida|usb|hdmi/.test(key)) shape = '<path d="M9 3v5m6-5v5M7 8h10v3a5 5 0 0 1-10 0Zm5 8v6"/>';
  else if (/memoria|procesador|chip|capacidad/.test(key)) shape = '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4"/><path d="M10 10h4v4h-4Z"/>';
  else if (/incluye|contenido|accesorio/.test(key)) shape = '<path d="m3 7 9-4 9 4v10l-9 4-9-4Zm0 0 9 4 9-4M12 11v10m-5-16 10 4"/>';
  else if (/color|iluminacion|rgb/.test(key)) shape = '<path d="M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 0-4 2 2 0 0 1 0-4h4a4 4 0 0 0 4-4c0-3-4-6-9-6Z"/><path d="M7 9h.01M10 6h.01M16 7h.01M6 14h.01"/>';
  return `<svg class="spec-icon" viewBox="0 0 24 24" aria-hidden="true">${shape}</svg>`;
}

function manufacturerLinks(sources) {
  const manufacturers = ["acer.com", "adata.com", "agiler.com", "agilerusa.com", "amd.com", "antec.com", "aoc-europe.com", "aoc.com", "aoc.com.br", "argomtech.com", "asrock.com", "asus.com", "benq.com", "coolermaster.com", "corsair.com", "crucial.com", "deepcool.com", "dell.com", "elotouch.com", "gigabyte.com", "grandstream.com", "hiksemi.com", "hiksemitech.com", "hikvision.com", "hp.com", "hpe.com", "hyperx.com", "intel.com", "jbl.com", "kingston.com", "klipsch.com", "klipxtreme.com", "lenovo.com", "lexar.com", "lg.com", "lian-li.com", "logi.com", "logitech.com", "logitechg.com", "micron.com", "microsoft.com", "msi.com", "nexxtsolutions.com", "nvidia.com", "nzxt.com", "pny.com", "primusgaming.com", "razer.com", "redragonshop.com", "redragonzone.com", "roku.com", "samsung.com", "sandisk.com", "seagate.com", "sonos.com", "teamgroupinc.com", "tenda.com.cn", "thermaltake.com", "tp-link.com", "verbatim-europe.com", "verbatim.com", "viewsonic.com", "wd.com", "westerndigital.com", "xpg.com", "xtechamericas.com"];
  const links = [];
  const seen = new Set();
  for (const source of Array.isArray(sources) ? sources : []) {
    try {
      if (typeof source !== 'string') continue;
      const url = new URL(source);
      const host = url.hostname.toLowerCase();
      if (url.protocol !== 'https:' || host.startsWith('api.') || url.username || url.password || !manufacturers.some(domain => host === domain || host.endsWith(`.${domain}`)) || seen.has(host)) continue;
      seen.add(host);
      links.push(`<a class="manufacturer-link" href="${escapeHTML(url.href)}" target="_blank" rel="noopener noreferrer">Ficha del fabricante <svg class="arrow-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19 19 5M5 5h14v14"/></svg></a>`);
    } catch (_) { /* A source without a valid product URL has no customer link. */ }
  }
  return links.length ? `<div class="manufacturer-links">${links.join('')}</div>` : '';
}

function renderProductPage() {
  const id = $('#product-page').dataset.productId || new URLSearchParams(location.search).get('id');
  const product = products.find(item => item.id === id);
  const view = $('#product-view');
  if (!product) {
    document.title = 'Producto no encontrado | Kodex Gaming';
    $('#product-breadcrumb').textContent = 'Producto no encontrado';
    view.innerHTML = '<div class="empty"><strong>No encontramos este producto.</strong><p>Explora la tienda para encontrar tu próximo upgrade.</p><a class="button" href="index.html#catalogo">Volver a la tienda</a></div>';
    $('#related-section').hidden = true;
    return;
  }
  if (view.dataset.prerendered === product.id) {
    const related = products.filter(item => item.category === product.category && item.id !== product.id).slice(0, 3);
    $('#related-products').innerHTML = related.map(productCard).join('');
    $('#related-section').hidden = !related.length;
    window.KodexPixel?.viewProduct(product);
    return;
  }
  document.title = `${product.name} | Kodex Gaming`;
  document.querySelector('meta[name="description"]').content = `${product.name}. ${product.description || product.spec || ''}`;
  $('#product-breadcrumb').textContent = product.name;
  const description = String(product.description || product.spec || '').trim();
  const normalizeText = text => String(text).replace(/\s+/g, ' ').trim().toLocaleLowerCase('es');
  const specifications = (Array.isArray(product.specifications) ? product.specifications : []).filter(row => row && row.label && row.value && !(normalizeText(row.label) === 'información del producto' && normalizeText(row.value) === normalizeText(description)));
  if (!product.sourceUnavailable && !product.sourceContentConflict && product.brand && !specifications.some(row => /^(marca|fabricante)$/i.test(row.label))) specifications.unshift({label:'Marca', value:product.brand});
  const features = [...new Set((Array.isArray(product.features) ? product.features : []).filter(feature => feature && normalizeText(feature) !== normalizeText(description)))];
  const firstParagraph = description.split(/\n+/).find(Boolean) || '';
  const summary = firstParagraph.length > 240 ? `${firstParagraph.slice(0, 240).replace(/\s+\S*$/, '').replace(/[ ,;:]+$/, '')}…` : firstParagraph;
  const summaryHTML = summary && normalizeText(summary) !== normalizeText(product.name) ? `<p>${escapeHTML(summary)}</p>` : '';
  const descriptionAddsDetail = normalizeText(description) !== normalizeText(product.name) && normalizeText(description) !== normalizeText(summary);
  const paragraphs = descriptionAddsDetail ? description.split(/\n+/).filter(Boolean).map(text => `<p>${escapeHTML(text)}</p>`).join('') : '';
  const rows = specifications.map(row => `<div class="spec-row"><dt>${specificationIcon(row.label)}<span>${escapeHTML(row.label)}</span></dt><dd>${escapeHTML(row.value)}</dd></div>`).join('');
  const sources = manufacturerLinks(product.specificationSources);
  const categoryParams = new URLSearchParams({categoria:product.category, subcategoria:product.subcategory});
  const categoryPath = `<a href="index.html?${escapeHTML(categoryParams.toString())}#catalogo">${escapeHTML(product.subcategory)}</a>`;
  view.innerHTML = `<div class="product-overview">
    <div class="product-photo"><img src="${escapeHTML(product.image || 'img/catalogo/sin-imagen.svg')}" alt="${escapeHTML(product.name)}" width="520" height="440" fetchpriority="high"></div>
    <div class="product-information">
      <a class="eyebrow" href="index.html?categoria=${encodeURIComponent(product.category)}#catalogo">${escapeHTML(product.brand)} · ${escapeHTML(product.category)}</a>
      <nav class="product-category-path" aria-label="Subcategoría del producto">${categoryPath}</nav>
      <h1>${escapeHTML(product.name)}</h1>
      <p class="product-reference">Referencia: <span>${escapeHTML(product.reference || product.id)}</span>${product.model ? ` · Modelo: <span>${escapeHTML(product.model)}</span>` : ''}</p>
      ${summaryHTML ? `<div class="product-description">${summaryHTML}</div>` : ''}
      <a class="text-link specifications-link" href="#caracteristicas">Ver características principales <span aria-hidden="true">↓</span></a>
      <div class="page-pricing"><strong>${money(product.price)}</strong>${hasPrice(product) && product.old > product.price ? `<del>${money(product.old)}</del>` : ''}</div>
      ${productActions(product, true)}
      <p class="purchase-hint">${canOrder(product) ? 'Pedidos y asesoría por WhatsApp.' : 'Consulta alternativas con nuestro equipo por WhatsApp.'}</p>
    </div>
  </div>
  <section class="specifications-section" id="caracteristicas" aria-labelledby="specifications-title">
    <div class="section-heading"><div><span class="eyebrow">CONOCE TU PRÓXIMO UPGRADE</span><h2 id="specifications-title">Descripción y características</h2></div></div>
    <div class="specifications-card">${paragraphs ? `<div class="product-description product-description-full">${paragraphs}</div>` : ''}${rows ? `<dl class="specifications-list">${rows}</dl>` : ''}${features.length ? `<div class="product-highlights"><h3>Lo más destacado</h3><ul class="product-features">${features.map(feature => `<li>${escapeHTML(feature)}</li>`).join('')}</ul></div>` : ''}${!rows && !features.length && !description && !product.specificationNote ? '<p class="specification-note">Consulta los detalles de este producto con nuestro equipo.</p>' : ''}${product.specificationNote ? `<p class="specification-note">${escapeHTML(product.specificationNote)}</p>` : ''}${sources}</div>
  </section>`;
  const related = products.filter(item => item.category === product.category && item.id !== product.id).slice(0, 3);
  $('#related-products').innerHTML = related.map(productCard).join('');
  $('#related-section').hidden = !related.length;
  window.KodexPixel?.viewProduct(product);
}
