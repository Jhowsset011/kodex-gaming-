const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../js/meta-pixel.js'), 'utf8');

function load(existing) {
  const inserted = [];
  const window = existing || {};
  const document = {
    createElement: () => ({}),
    getElementsByTagName: () => [{parentNode: {insertBefore: element => inserted.push(element)}}]
  };
  const context = vm.createContext({window, document});
  vm.runInContext(source, context);
  const events = () => JSON.parse(JSON.stringify((window.fbq.queue || []).map(event => Array.from(event))));
  return {window, inserted, context, events};
}
const product = {id: '90000094202', reference: '94202', price: 1900, stock: true,
  name: 'Producto público', purchaseCost: 'never-send', privateRules: 'never-send', customerPhone: 'never-send'};

test('correct pixel starts one PageView and one asynchronous loader even after repeated initialization', () => {
  const tracker = load();
  assert.equal(tracker.inserted.length, 1);
  assert.equal(tracker.inserted[0].src, 'https://connect.facebook.net/en_US/fbevents.js');
  assert.equal(tracker.inserted[0].async, true);
  assert.deepEqual(tracker.events(), [
    ['set','autoConfig',false,'2319748675459306'],
    ['init','2319748675459306'], ['track','PageView']
  ]);
  vm.runInContext(source, tracker.context);
  assert.equal(tracker.events().length, 3);
  assert.equal(tracker.inserted.length, 1);
});

test('product views use the storefront ID and public DOP price, once per page', () => {
  const tracker = load();
  tracker.window.KodexPixel.viewProduct(product);
  tracker.window.KodexPixel.viewProduct(product);
  const events = tracker.events().filter(event => event[1] === 'ViewContent');
  assert.equal(events.length, 1);
  assert.deepEqual(events[0][2], {content_ids: [product.id], content_type:'product',
    contents:[{id:product.id,quantity:1,item_price:1900}],currency:'DOP',value:1900});
  assert(!JSON.stringify(events).includes('never-send'));
});

test('adding units reports only the added quantity; invalid quantities or unavailable products produce no event', () => {
  const tracker = load();
  tracker.window.KodexPixel.addToCart(product, 3);
  for (const quantity of [0, -1, 100, 1.5, NaN]) tracker.window.KodexPixel.addToCart(product, quantity);
  tracker.window.KodexPixel.addToCart({...product, stock:false});
  tracker.window.KodexPixel.addToCart({...product, price:null});
  const events = tracker.events().filter(event => event[1] === 'AddToCart');
  assert.equal(events.length, 1);
  assert.equal(events[0][2].value, 5700);
  assert.equal(events[0][2].contents[0].quantity, 3);
});

test('WhatsApp contact reports cart items and total without claiming a purchase', () => {
  const tracker = load();
  tracker.window.KodexPixel.contact([{product, quantity:2}], 'cart');
  tracker.window.KodexPixel.contact([], 'advisory');
  const events = tracker.events().filter(event => event[1] === 'Contact');
  assert.equal(events[0][2].value, 3800);
  assert.equal(events[0][2].contact_source, 'cart');
  assert.deepEqual(events[1][2], {contact_method:'WhatsApp',contact_source:'advisory'});
  assert(!tracker.events().some(event => ['Purchase','Lead','InitiateCheckout'].includes(event[1])));
  assert(!JSON.stringify(events).includes('never-send'));
});

test('missing prices and missing products never turn into a fabricated zero sale', () => {
  const tracker = load();
  tracker.window.KodexPixel.viewProduct(null);
  tracker.window.KodexPixel.viewProduct({...product, price:null});
  const event = tracker.events().find(event => event[1] === 'ViewContent');
  assert.equal(event[2].currency, 'DOP');
  assert(!('value' in event[2]));
  assert(!('item_price' in event[2].contents[0]));
});

test('blocked or throwing Meta SDK does not interrupt product and cart operations', () => {
  const tracker = load({fbq: () => {throw new Error('blocked tracker');}});
  assert.doesNotThrow(() => tracker.window.KodexPixel.viewProduct(product));
  assert.doesNotThrow(() => tracker.window.KodexPixel.addToCart(product));
  assert.doesNotThrow(() => tracker.window.KodexPixel.contact([{product,quantity:1}], 'product'));
  assert.equal(tracker.inserted.length, 0);
});
