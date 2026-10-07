const products = [
 {id:'forge321',name:'MSI MAG Forge 321R',category:'Gabinetes',spec:'Mid Tower · 4 ventiladores ARGB',price:4550,old:5000,image:'img/productos/case/msi2.png',badge:'−9%'},
 {id:'rtx5070',name:'MSI GeForce RTX 5070',category:'Componentes',spec:'12 GB GDDR7 · Shadow 3X OC',price:42900,image:'img/productos/nuevos/tarjeta1.png',badge:'NUEVO'},
 {id:'aoc49',name:'AOC Gaming 49″ Curvo',category:'Monitores',spec:'5120 × 1440 · 165 Hz',price:48900,image:'img/productos/nuevos/monitor1.png',badge:'ULTRAWIDE'},
 {id:'a550',name:'MSI MAG A550BN',category:'Componentes',spec:'550 W · Certificación 80 Plus Bronze',price:4350,old:4555.4,image:'img/productos/power/power msi1.png',badge:'−5%'},
 {id:'forge120',name:'MSI MAG Forge 120A',category:'Gabinetes',spec:'Mid Tower · Airflow · RGB',price:4550.4,image:'img/productos/case/msi1.png'},
 {id:'rtx3060',name:'MSI GeForce RTX 3060',category:'Componentes',spec:'12 GB · Ventus 2X OC',price:21900,image:'img/productos/nuevos/tarjeta2.png'},
 {id:'corsair',name:'Corsair Crystal 280X RGB',category:'Gabinetes',spec:'Micro ATX · Cristal templado',price:10900,image:'img/productos/nuevos/case1.png',badge:'FAVORITO'},
 {id:'fury',name:'Kingston Fury Beast',category:'Componentes',spec:'Memoria RAM · Rendimiento gaming',price:3200,image:'img/productos/memoria ram/fury1.png'}
];
const money = value => 'RD$' + value.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
let filter='Todos',cart={};
try { const saved=JSON.parse(localStorage.getItem('kodex-cart')||'{}'); for(const p of products) if(Number.isInteger(saved?.[p.id])&&saved[p.id]>0) cart[p.id]=Math.min(saved[p.id],99); } catch {}
const grid=document.querySelector('#products'),dialog=document.querySelector('#cart');
function renderProducts(){
 const query=document.querySelector('#search').value.trim().toLocaleLowerCase('es');
 const list=products.filter(p=>(filter==='Todos'||(filter==='ofertas'?Boolean(p.old):p.category===filter))&&`${p.name} ${p.spec} ${p.category}`.toLocaleLowerCase('es').includes(query));
 grid.innerHTML=list.map(p=>`<article class="product"><div class="product-art">${p.badge?`<span class="badge ${p.old?'':'dark'}">${p.badge}</span>`:''}<img src="${p.image}" alt="${p.name}" loading="lazy"></div><div class="product-copy"><span class="product-type">${p.category.toUpperCase()}</span><h3>${p.name}</h3><p class="product-spec">${p.spec}</p><div class="product-price"><div>${p.old?`<del>${money(p.old)}</del>`:''}<strong>${money(p.price)}</strong></div><button class="add" data-add="${p.id}" aria-label="Añadir ${p.name} al carrito">+</button></div></div></article>`).join('');
 document.querySelector('#empty').hidden=list.length>0;
 document.querySelector('#result-count').textContent=`${list.length} PRODUCTO${list.length===1?'':'S'}`;
}
function selectFilter(value){filter=value;document.querySelectorAll('[data-filter]').forEach(b=>{const selected=b.dataset.filter===value;b.classList.toggle('active',selected);b.setAttribute('aria-pressed',String(selected));});renderProducts();}
function renderCart(){
 const items=products.filter(p=>cart[p.id]);
 document.querySelector('#cart-count').textContent=Object.values(cart).reduce((a,b)=>a+b,0);
 document.querySelector('#cart-items').innerHTML=items.length?items.map(p=>`<div class="cart-line"><img src="${p.image}" alt=""><div><h3>${p.name}</h3><p>${money(p.price)}</p><div class="quantity"><button data-change="${p.id}" data-step="-1" aria-label="Quitar una unidad de ${p.name}">−</button><span>${cart[p.id]}</span><button data-change="${p.id}" data-step="1" aria-label="Añadir una unidad de ${p.name}" ${cart[p.id]>=99?'disabled':''}>+</button></div></div><button class="remove" data-remove="${p.id}" aria-label="Eliminar ${p.name}">Eliminar</button></div>`).join(''):'<p class="empty">Tu siguiente upgrade te espera.<br>Explora el catálogo y añade tus favoritos.</p>';
 document.querySelector('#cart-total').textContent=money(items.reduce((sum,p)=>sum+p.price*cart[p.id],0));
 try{localStorage.setItem('kodex-cart',JSON.stringify(cart));}catch{}
}
let toastTimer;
function addProduct(id){if(!products.some(p=>p.id===id))return;cart[id]=Math.min((cart[id]||0)+1,99);renderCart();const toast=document.querySelector('#toast');toast.textContent='Producto añadido a tu carrito';toast.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove('show'),2400);}
 document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>selectFilter(b.dataset.filter)));
 document.querySelectorAll('[data-category]').forEach(b=>b.addEventListener('click',()=>{document.querySelector('#search').value='';selectFilter(b.dataset.category);document.querySelector('#catalogo').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}));
 document.querySelector('[data-nav-filter]').addEventListener('click',()=>{document.querySelector('#search').value='';selectFilter('ofertas');});
 document.querySelector('#search').addEventListener('input',renderProducts);
 grid.addEventListener('click',e=>{const b=e.target.closest('[data-add]');if(b)addProduct(b.dataset.add);});
 document.querySelector('#open-cart').addEventListener('click',()=>{renderCart();dialog.showModal();});
 document.querySelector('#close-cart').addEventListener('click',()=>dialog.close());
 document.querySelector('#continue-shopping').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
 document.querySelector('#cart-items').addEventListener('click',e=>{const change=e.target.closest('[data-change]'),remove=e.target.closest('[data-remove]');if(change){const id=change.dataset.change;cart[id]=Math.min(99,(cart[id]||0)+Number(change.dataset.step));if(cart[id]<=0)delete cart[id];renderCart();}if(remove){delete cart[remove.dataset.remove];renderCart();}});
 document.querySelector('#year').textContent=new Date().getFullYear();renderProducts();renderCart();
