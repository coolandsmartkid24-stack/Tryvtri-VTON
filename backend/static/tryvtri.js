/*! TryVtri SDK 1.0.0 | vanilla JS, no dependencies, works on any website */
(function (w, d) {
  'use strict';
  if (w.TryVtri && w.TryVtri.version) return;

  var VERSION = '1.0.0';
  var HOUR = 36e5;
  var PRIVACY_URL = 'https://tryvtri.lovable.app/privacy';
  var CREDIT_URL = 'https://fit.tryvtri.com/';
  // Same storage keys as the original Shopify block, so returning visitors keep their state.
  var K = { sid: 'vto_sid', email: 'vto_email', uses: 'vto_uses', consent: 'vto_consent', result: 'vto_result_', look: 'vto_appearance_' };
  var TIPS = [
    'Use a full body photo for best results',
    'Stand straight facing the camera',
    'Use a plain background for the cleanest result',
    'Wear fitted clothes for accurate sizing',
    'Make sure your photo is well lit'
  ];
  var STAGES = ['Analyzing your photo…', 'Fitting the outfit…', 'Adding finishing touches…'];

  var ICONS = {
    scan: '<path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4"/><circle cx="12" cy="10.2" r="2.6"/><path d="M7.6 18c.6-2.6 2.4-4 4.4-4s3.8 1.4 4.4 4"/>',
    sparkle: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"/>',
    sparkles: '<path d="M10 4l1.6 4.4L16 10l-4.4 1.6L10 16l-1.6-4.4L4 10l4.4-1.6L10 4z"/><path d="M18 14l.8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8L18 14z"/>',
    camera: '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
    person: '<circle cx="12" cy="8" r="4"/><path d="M4 21c.8-4 4-6 8-6s7.2 2 8 6"/>',
    hanger: '<path d="M12 8V7a2 2 0 1 0-2-2"/><path d="M12 8l8.5 6.2a1 1 0 0 1-.6 1.8H4.1a1 1 0 0 1-.6-1.8L12 8z"/>'
  };
  var ICON_KEYS = ['scan', 'sparkle', 'sparkles', 'camera', 'person', 'hanger'];
  function svg(inner, size, sw) {
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' + (sw || 2) + '" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + inner + '</svg>';
  }
  var G = {
    shield: svg('<path d="M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6l7-3z"/><path d="M9 12l2 2 4-4"/>', 18),
    spark: svg('<path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3z"/><path d="M18 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2z"/>', 18, 1.8),
    bars: svg('<rect x="3" y="13" width="4" height="8" rx="1"/><rect x="10" y="8" width="4" height="13" rx="1"/><rect x="17" y="3" width="4" height="18" rx="1"/>', 18, 1.8),
    err: svg('<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>', 15),
    clock: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', 18, 1.8),
    clockBig: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', 28, 1.8),
    x: svg('<path d="M6 18L18 6M6 6l12 12"/>', 18),
    cart: svg('<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.7 13.4a2 2 0 0 0 2 1.6h9.7a2 2 0 0 0 2-1.6L23 6H6"/>', 15),
    upload: svg('<path d="M12 16V4M12 4l-4 4M12 4l4 4"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>', 18, 1.7),
    swap: svg('<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>', 20)
  };
  var ARROW = '<svg class="tv-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square" aria-hidden="true"><path d="M4 12h15M13 6l6 6-6 6"/></svg>';
  var CREDIT = '<div class="tv-credit"><svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2l1.8 5.6L19.4 9.4 13.8 11.2 12 17l-1.8-5.8L4.6 9.4l5.6-1.8L12 2z"/></svg><span>Powered by <a href="' + CREDIT_URL + '" target="_blank" rel="noopener">TryVtri</a></span></div>';
  var POWERED = '<div class="tv-powered">Powered by <a href="' + CREDIT_URL + '" target="_blank" rel="noopener">TryVtri</a></div>';

  // Settings: window.TryVtriConfig (set before the script) and TryVtri.init({...}) override these.
  var DEFAULTS = {
    api: '', shop: '', platform: 'shopify', productId: '', productTitle: '', productUrl: '', garmentUrl: '', variantId: '', category: 'tops',
    customerId: '', customerEmail: '',
    buyUrl: '', onBuy: null, limit: 2, windowHours: 24, privacyUrl: PRIVACY_URL, termsUrl: '',
    primary: '#16130f', accent: '#2563eb', sync: true, syncInterval: 0, credit: true,
    title: 'Try It On Me', description: 'See it on you in seconds', icon: 'scan'
  };
  function assign(t) { for (var i = 1; i < arguments.length; i++) { var s = arguments[i]; if (s) for (var k in s) if (Object.prototype.hasOwnProperty.call(s, k)) t[k] = s[k]; } return t; }
  assign(DEFAULTS, w.TryVtriConfig);

  // ---------- small helpers ----------
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function safeUrl(u) { u = String(u || ''); return /^(https?:)?\/\//i.test(u) || u.charAt(0) === '/' || /^data:image\//i.test(u) ? u : ''; }
  function emit(name, detail) { try { d.dispatchEvent(new CustomEvent('tryvtri:' + name, { detail: detail || {} })); } catch (e) {} }
  function cookieSet(k, v, days) { try { d.cookie = k + '=' + encodeURIComponent(v) + '; expires=' + new Date(Date.now() + days * 864e5).toUTCString() + '; path=/; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : ''); } catch (e) {} }
  function cookieGet(k) { try { var p = d.cookie ? d.cookie.split('; ') : []; for (var i = 0; i < p.length; i++) { var n = p[i].indexOf('='); if (p[i].slice(0, n) === k) return decodeURIComponent(p[i].slice(n + 1)); } } catch (e) {} return null; }
  function lsGet(k) { try { return w.localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { w.localStorage.setItem(k, v); } catch (e) {} }
  function lsDel(k) { try { w.localStorage.removeItem(k); } catch (e) {} }
  function ssGet(k) { try { return w.sessionStorage.getItem(k); } catch (e) { return null; } }
  function ssSet(k, v) { try { w.sessionStorage.setItem(k, v); } catch (e) {} }
  function ssDel(k) { try { w.sessionStorage.removeItem(k); } catch (e) {} }
  function remember(k, v, days) { cookieSet(k, v, days); lsSet(k, v); }
  function recall(k) { return cookieGet(k) || lsGet(k); }
  function forget(k) { cookieSet(k, '', -1); lsDel(k); }
  function uuid() {
    try { if (w.crypto && crypto.randomUUID) return crypto.randomUUID(); } catch (e) {}
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) { var r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3 | 8)).toString(16); });
  }
  function sessionId() { var s = recall(K.sid); if (!s) s = uuid(); remember(K.sid, s, 30); return s; }
  function isColor(v) { return typeof v === 'string' && /^(#[0-9a-f]{3,8}|rgba?\(|hsla?\()/i.test(v.trim()); }
  function pick(o, keys) { for (var i = 0; i < keys.length; i++) if (o[keys[i]] != null) return o[keys[i]]; }

  function fromDataset(el) {
    var s = el.dataset || {}, o = {};
    var map = { tvApi: 'api', tvShop: 'shop', tvPlatform: 'platform', tvProductId: 'productId', tvProductTitle: 'productTitle', tvProductUrl: 'productUrl', tvGarmentUrl: 'garmentUrl', tvVariantId: 'variantId', tvCategory: 'category', tvCustomerId: 'customerId', tvCustomerEmail: 'customerEmail', tvBuyUrl: 'buyUrl', tvPrivacyUrl: 'privacyUrl', tvTermsUrl: 'termsUrl', tvPrimary: 'primary', tvAccent: 'accent', tvLimit: 'limit', tvWindowHours: 'windowHours', tvSync: 'sync', tvTitle: 'title', tvDescription: 'description' };
    for (var k in map) if (s[k] !== undefined && s[k] !== '') o[map[k]] = s[k];
    if (o.sync !== undefined) o.sync = o.sync !== 'false';
    if (o.limit) o.limit = +o.limit;
    if (o.windowHours) o.windowHours = +o.windowHours;
    return o;
  }

  function adapterFor(platform) { var a = (w.TryVtriAdapters && w.TryVtriAdapters[platform]) || TryVtri.adapters[platform]; return a && typeof a.buy === 'function' ? a : null; }

  function shrink(file, max) {      // smaller upload = faster try-on
    return new Promise(function (resolve) {
      if (!w.createImageBitmap || !file.type || file.type.indexOf('image/') !== 0) return resolve(file);
      w.createImageBitmap(file, { imageOrientation: 'from-image' }).then(function (bmp) {
        var s = Math.min(1, max / Math.max(bmp.width, bmp.height));
        if (s === 1 && file.size < 1.5e6) return resolve(file);
        var c = d.createElement('canvas'); c.width = Math.round(bmp.width * s); c.height = Math.round(bmp.height * s);
        c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
        c.toBlob(function (b) { resolve(b ? new File([b], 'photo.jpg', { type: 'image/jpeg' }) : file); }, 'image/jpeg', 0.88);
      }, function () { resolve(file); });
    });
  }

  // ---------- launcher card markup (server templates output the same markup for instant paint) ----------
  function iconSvg(name) {
    var sq = name === 'scan';
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="' + (sq ? 'square' : 'round') + '" stroke-linejoin="round" aria-hidden="true">' + ICONS[name] + '</svg>';
  }
  function cardHTML(o) {
    o = assign({}, DEFAULTS, o);
    var icon = ICONS[o.icon] ? o.icon : 'scan';
    return '<div class="tv-group"><button class="tv-launcher" type="button" data-tv-open aria-haspopup="dialog">' +
      '<span class="tv-ico" data-tv-icon="' + icon + '">' + iconSvg(icon) + '</span>' +
      '<span class="tv-txt"><span class="tv-t1">' + esc(o.title) + '</span>' + (o.description ? '<span class="tv-t2">' + esc(o.description) + '</span>' : '') + '</span>' +
      ARROW + '</button>' + (o.credit === false ? '' : CREDIT) + '</div>';
  }

  // =====================================================================
  function Instance(el, o) {
    var opts = o || {};
    var S = { email: recall(K.email) || '', file: null, resultUrl: null, stream: null, p: 0, tick: 0, tipT: 0, tipI: 0, ctl: null };
    var modal, overlay, ui, histBtn, panel, lastFocus, syncT, destroyed = false;
    var launcher = el.querySelector('[data-tv-open]');

    function cfg() {
      var c = assign({}, DEFAULTS, opts, fromDataset(el));
      c.api = String(c.api || '').replace(/\/+$/, '');
      c.shop = c.shop || location.hostname;
      c.productTitle = c.productTitle || d.title;
      c.productUrl = c.productUrl || location.href;
      c.garmentUrl = safeUrl(c.garmentUrl);
      c.limit = c.limit > 0 ? c.limit : 2;
      c.windowHours = c.windowHours > 0 ? c.windowHours : 24;
      return c;
    }
    function resultKey() { return K.result + cfg().productId; }

    // ---- automatic variant synchronization ----
    var productCtx = null;
    try {
      var ctxTag = el.querySelector('[data-tv-product-context]');
      if (ctxTag) productCtx = JSON.parse(ctxTag.textContent || '{}');
    } catch (e) {}

    function updateVariant(vid) {
      if (!vid) return;
      vid = String(vid);
      el.setAttribute('data-tv-variant-id', vid);
      opts.variantId = vid;
      if (productCtx && productCtx.variants && productCtx.variants.length) {
        for (var i = 0; i < productCtx.variants.length; i++) {
          var v = productCtx.variants[i];
          if (String(v.id) === vid) {
            var newImg = v.imageUrl || productCtx.featuredImageUrl || '';
            if (newImg) {
              el.setAttribute('data-tv-garment-url', newImg);
              opts.garmentUrl = newImg;
              emit('variant:change', { variantId: vid, garmentUrl: newImg });
            }
            break;
          }
        }
      }
    }

    function initVariantListeners() {
      d.addEventListener('variant:change', function (e) {
        var v = e.detail && (e.detail.variant || e.detail);
        if (v && v.id) updateVariant(v.id);
      });
      d.addEventListener('theme:variant:change', function (e) {
        var v = e.detail && (e.detail.variant || e.detail);
        if (v && v.id) updateVariant(v.id);
      });
      d.addEventListener('change', function (e) {
        var t = e.target;
        if (t && (t.name === 'id' || (t.form && t.form.action && t.form.action.indexOf('/cart/add') !== -1))) {
          var vVal = t.value;
          if (vVal && /^\d+$/.test(vVal)) updateVariant(vVal);
        }
      });
      try {
        var p = new URLSearchParams(w.location.search);
        var uVar = p.get('variant');
        if (uVar) updateVariant(uVar);
      } catch (e) {}
    }

    // ---- usage limit (client side). The server must enforce the same limit, see API.md ----
    function uses() {
      var raw = recall(K.uses), a = [];
      try { a = JSON.parse(raw || '[]'); } catch (e) { a = []; }
      if (!Array.isArray(a)) a = [];
      var from = Date.now() - cfg().windowHours * HOUR;
      return a.filter(function (t) { return typeof t === 'number' && t > from; });
    }
    function blockedHours() {
      var c = cfg(), a = uses();
      if (a.length < c.limit) return 0;
      return Math.max(1, Math.ceil((Math.min.apply(null, a) + c.windowHours * HOUR - Date.now()) / HOUR));
    }
    function addUse() { var a = uses(); a.push(Date.now()); var v = JSON.stringify(a.slice(-cfg().limit)); remember(K.uses, v, 1); }

    // ---- modal shell (built lazily on first click) ----
    function buildModal() {
      if (modal) return;
      modal = d.createElement('div');
      modal.className = 'tv-modal';
      modal.innerHTML = '<div class="tv-overlay"><div class="tv-panel" role="dialog" aria-modal="true" aria-label="Virtual try-on" tabindex="-1">' +
        '<div class="tv-head"><div class="tv-head-text"><h2>Try It On</h2><p>See how it looks on you</p></div><div class="tv-head-right">' +
        '<button class="tv-icon-btn" type="button" data-tv-history aria-label="See your last look" title="Your last look" hidden>' + G.clock + '</button>' +
        '<button class="tv-close" type="button" data-tv-close aria-label="Close">' + G.x + '</button></div></div>' +
        '<div class="tv-screen" data-tv-screen></div></div></div>';
      d.body.appendChild(modal);
      overlay = modal.querySelector('.tv-overlay'); panel = modal.querySelector('.tv-panel');
      ui = modal.querySelector('[data-tv-screen]'); histBtn = modal.querySelector('[data-tv-history]');
      modal.querySelector('[data-tv-close]').addEventListener('click', close);
      histBtn.addEventListener('click', function () { if (S.resultUrl) showResult(); });
      overlay.addEventListener('mousedown', function (e) { if (e.target === overlay) close(); });
    }
    function onKey(e) { if (e.key === 'Escape') close(); }

    function open() {
      if (destroyed) return;
      var c = cfg();
      buildModal();
      modal.style.setProperty('--tv-primary', c.primary);
      modal.style.setProperty('--tv-accent', c.accent);
      S.resultUrl = ssGet(resultKey());
      histBtn.hidden = !S.resultUrl;
      lastFocus = d.activeElement;
      overlay.classList.add('open');
      d.body.style.overflow = 'hidden';
      d.addEventListener('keydown', onKey);
      emit('open', { productId: c.productId });
      start();
      try { panel.focus({ preventScroll: true }); } catch (e) {}
    }
    function close() {
      if (!modal) return;
      stopProgress(); stopCamera();
      if (S.ctl) { try { S.ctl.abort(); } catch (e) {} S.ctl = null; }
      overlay.classList.remove('open');
      d.body.style.overflow = '';
      d.removeEventListener('keydown', onKey);
      if (lastFocus && lastFocus.focus) try { lastFocus.focus(); } catch (e) {}
      emit('close');
    }

    // ---- flow ----
    function start() {
      if (recall(K.consent) !== '1') return showConsent();
      next();
    }
    function next() {
      if (S.resultUrl) showResult();
      else if (S.email) checkUsage(S.email, null, showUpload);
      else showEmail();
    }

    function checkUsage(email, busy, ok) {
      var c = cfg(), h = blockedHours();
      if (h > 0) return showLimit(h);
      if (!c.api) return ok();
      if (busy) busy(true);
      var qs = '?email=' + encodeURIComponent(email) + '&shop=' + encodeURIComponent(c.shop) + '&session_id=' + encodeURIComponent(sessionId());
      if (c.customerId) qs += '&shopify_customer_id=' + encodeURIComponent(c.customerId);
      fetch(c.api + '/tryvtri-vton/check-usage' + qs)
        .then(function (r) { return r.ok ? r.json() : fetch(c.api + '/api/widget/check-usage' + qs).then(function (r2) { return r2.ok ? r2.json() : null; }); })
        .then(function (j) {
          if (busy) busy(false);
          if (j) {
            if (j.eligible === false || (j.remaining !== undefined && j.remaining <= 0)) {
              var hLeft = j.reset_at ? Math.max(1, Math.ceil((new Date(j.reset_at).getTime() - Date.now()) / HOUR)) : c.windowHours;
              return showLimit(hLeft);
            }
            var n = j.count || 0, last = j.last_tryon ? new Date(j.last_tryon) : null;
            var age = last ? (Date.now() - last.getTime()) / HOUR : 999;
            if (n >= c.limit && age < c.windowHours) return showLimit(Math.max(1, Math.ceil(c.windowHours - age)));
          }
          ok();
        })
        .catch(function () { if (busy) busy(false); ok(); });
    }

    function errBox() {
      var box = ui.querySelector('[data-tv-error]'), txt = ui.querySelector('[data-tv-error-text]'), ic = ui.querySelector('[data-tv-error-icon]');
      if (ic) ic.innerHTML = G.err;
      return { show: function (m) { if (box) { txt.textContent = m; box.hidden = false; } }, clear: function () { if (box) box.hidden = true; } };
    }
    function steps(n) {
      return '<div class="tv-steps"><div class="tv-dot ' + (n >= 1 ? 'active' : '') + '">' + (n > 1 ? '✓' : '1') + '</div><div class="tv-dot-line ' + (n >= 2 ? 'done' : '') + '"></div><div class="tv-dot ' + (n >= 2 ? (n > 2 ? 'done' : 'active') : '') + '">2</div></div>';
    }
    var PRIV = '<div class="tv-privacy">' + G.shield + '<span><strong>Your photo is not stored.</strong> It is deleted automatically when your try-on is done.</span></div>';
    function thumb(c, cls) { return c.garmentUrl ? '<img class="' + cls + '" src="' + esc(c.garmentUrl) + '" alt="' + esc(c.productTitle) + '">' : ''; }

    // 1) first-time message
    function showConsent() {
      var c = cfg(); stopCamera();
      ui.innerHTML = '<div class="tv-consent">' + thumb(c, 'tv-consent-thumb') +
        '<div class="tv-consent-title">Virtual Try-On</div>' +
        '<div class="tv-consent-sub">We don’t keep your data — only your email. Your photos are never stored.</div>' +
        '<ul class="tv-consent-list"><li><span class="tv-consent-ico">' + G.spark + '</span><span>Your photo is sent to our secure AI service, only to create your try-on preview.</span></li>' +
        '<li><span class="tv-consent-ico">' + G.bars + '</span><span>We keep your email and your number of try-ons, to run this service and apply the free limit.</span></li></ul>' +
        '<div class="tv-consent-fine">By continuing, you agree to the <a href="' + esc(c.privacyUrl) + '" target="_blank" rel="noopener">Try-On Privacy Policy</a>.</div>' +
        '<button class="tv-agree" type="button" data-tv-agree>Agree and continue</button>' +
        '<button class="tv-later" type="button" data-tv-later>Not now</button></div>';
      ui.querySelector('[data-tv-agree]').addEventListener('click', function () { remember(K.consent, '1', 365); next(); });
      ui.querySelector('[data-tv-later]').addEventListener('click', close);
    }

    // 2) email
    function showEmail(prefill) {
      var c = cfg(); stopCamera();
      ui.innerHTML = steps(1) + PRIV + '<div class="tv-title">Ready to try it on?</div><div class="tv-sub">Upload your photo and see how it looks on you instantly.</div>' + thumb(c, 'tv-thumb') +
        '<input class="tv-input" type="email" data-tv-email placeholder="your@email.com" autocomplete="email" inputmode="email" value="' + esc(prefill || '') + '" aria-label="Email address">' +
        '<div class="tv-error" data-tv-error hidden><span data-tv-error-icon></span><span data-tv-error-text></span></div>' +
        '<div class="tv-stack"><button class="tv-btn tv-btn-primary" type="button" data-tv-next>Choose Your Photo →</button></div>' +
        '<div class="tv-fine">By continuing you agree to our ' + (c.termsUrl ? '<a href="' + esc(c.termsUrl) + '">Terms</a> &amp; ' : '') + '<a href="' + esc(c.privacyUrl) + '" target="_blank" rel="noopener">Privacy Policy</a>. We use a cookie to remember your email and session on this device. AI can make mistakes.</div>' + POWERED;
      var eb = errBox(), input = ui.querySelector('[data-tv-email]'), btn = ui.querySelector('[data-tv-next]');
      function go() {
        var v = input.value.trim();
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) return eb.show('Please enter a valid email.');
        eb.clear(); S.email = v; remember(K.email, v, 30);
        checkUsage(v, function (b) { btn.disabled = b; btn.textContent = b ? 'Checking…' : 'Choose Your Photo →'; }, showUpload);
      }
      setTimeout(function () { try { input.focus(); } catch (e) {} }, 80);
      btn.addEventListener('click', go);
      input.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
    }

    // 3) upload
    function showUpload() {
      var c = cfg(); stopCamera();
      ui.innerHTML = steps(2) + PRIV + '<div class="tv-title">Upload your photo</div><div class="tv-sub">A clear, front-facing, full-body photo works best.</div>' + thumb(c, 'tv-thumb') +
        (S.email ? '<div class="tv-sub" style="margin-bottom:6px">Signed in as <strong>' + esc(S.email) + '</strong></div><button class="tv-link" type="button" data-tv-change>Not you? Change email</button>' : '') +
        '<input type="file" accept="image/*" data-tv-file style="display:none">' +
        '<div class="tv-upload" data-tv-area tabindex="0" role="button" aria-label="Upload a photo"><div class="tv-upload-ico" data-tv-uico>' + G.upload + '</div>' +
        '<img class="tv-preview" data-tv-preview style="display:none" alt="Your photo"><div class="tv-upload-t" data-tv-ut>Choose your photo</div><div class="tv-upload-s" data-tv-us>JPG or PNG, up to 8MB</div></div>' +
        '<div class="tv-error" data-tv-error hidden><span data-tv-error-icon></span><span data-tv-error-text></span></div>' +
        '<div class="tv-stack"><button class="tv-btn tv-btn-primary" type="button" data-tv-go>Try It On Now</button><button class="tv-btn tv-btn-ghost" type="button" data-tv-cam>Use camera instead</button></div>' + POWERED;
      var eb = errBox(), area = ui.querySelector('[data-tv-area]'), file = ui.querySelector('[data-tv-file]'), prev = ui.querySelector('[data-tv-preview]'),
        uico = ui.querySelector('[data-tv-uico]'), ut = ui.querySelector('[data-tv-ut]'), us = ui.querySelector('[data-tv-us]'), ch = ui.querySelector('[data-tv-change]');
      if (ch) ch.addEventListener('click', function () { var e = S.email; forget(K.email); S.email = ''; showEmail(e); });
      area.addEventListener('click', function () { file.click(); });
      area.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); file.click(); } });
      file.addEventListener('change', function () {
        var f = file.files && file.files[0]; if (!f) return;
        if (f.type.indexOf('image/') !== 0) return eb.show('Please choose an image file.');
        if (f.size > 8388608) return eb.show('That photo is over 8MB — please choose a smaller file.');
        eb.clear(); S.file = f; area.classList.add('has-file'); uico.style.display = 'none';
        prev.src = URL.createObjectURL(f); prev.style.display = 'block';
        ut.textContent = f.name.length > 26 ? f.name.slice(0, 26) + '…' : f.name; us.textContent = 'Tap to change photo';
      });
      ui.querySelector('[data-tv-cam]').addEventListener('click', showCamera);
      ui.querySelector('[data-tv-go]').addEventListener('click', function () { S.file ? run() : eb.show('Please select a photo first.'); });
    }

    function stopCamera() { if (S.stream) { S.stream.getTracks().forEach(function (t) { t.stop(); }); S.stream = null; } }
    function showCamera() {
      ui.innerHTML = steps(2) + '<div class="tv-title">Take your photo</div><div class="tv-sub">Stand back so your full body is visible.</div>' +
        '<div class="tv-cam"><video data-tv-video autoplay playsinline muted></video></div><canvas data-tv-canvas style="display:none"></canvas>' +
        '<div class="tv-error" data-tv-error hidden><span data-tv-error-icon></span><span data-tv-error-text></span></div>' +
        '<div class="tv-row" style="margin-bottom:8px"><button class="tv-btn tv-btn-dark" type="button" data-tv-snap style="flex:2">Capture &amp; Try On</button><button class="tv-btn" type="button" data-tv-back>Back</button></div>' + POWERED;
      var eb = errBox(), v = ui.querySelector('[data-tv-video]');
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' } }).then(function (s) { v.srcObject = s; S.stream = s; }).catch(function () { eb.show('Camera access was denied. Please use file upload instead.'); });
      } else eb.show('Camera is not available here. Please use file upload instead.');
      ui.querySelector('[data-tv-back]').addEventListener('click', function () { stopCamera(); showUpload(); });
      ui.querySelector('[data-tv-snap]').addEventListener('click', function () {
        var cv = ui.querySelector('[data-tv-canvas]'); if (!v.videoWidth) return;
        cv.width = v.videoWidth; cv.height = v.videoHeight; cv.getContext('2d').drawImage(v, 0, 0); stopCamera();
        cv.toBlob(function (b) { if (b) { S.file = new File([b], 'capture.jpg', { type: 'image/jpeg' }); run(); } else showUpload(); }, 'image/jpeg', 0.9);
      });
    }

    // 4) loading: animated progress bar + rotating tips
    function paint() {
      var v = Math.min(100, Math.round(S.p)), bar = ui.querySelector('[data-tv-bar]');
      if (!bar) return;
      bar.style.width = v + '%'; ui.querySelector('[data-tv-pct]').textContent = v + '%';
      ui.querySelector('[data-tv-stage]').textContent = STAGES[v < 30 ? 0 : v < 70 ? 1 : 2];
      var pb = ui.querySelector('[data-tv-pb]'); if (pb) pb.setAttribute('aria-valuenow', v);
    }
    function showTip() {
      var t = ui.querySelector('[data-tv-tip]'); if (!t) return;
      t.textContent = ''; var s = d.createElement('span'); s.textContent = TIPS[S.tipI++ % TIPS.length]; t.appendChild(s);
    }
    function startProgress() {
      stopProgress(); S.p = 0; S.tipI = Math.floor(Math.random() * TIPS.length); paint(); showTip();
      S.tick = setInterval(function () { S.p = Math.min(95, S.p + (92 - S.p) * 0.035 + 0.15); paint(); }, 120);
      S.tipT = setInterval(showTip, 2800);
    }
    function stopProgress() { clearInterval(S.tick); clearInterval(S.tipT); S.tick = S.tipT = 0; }

    function showLoading() {
      var c = cfg(), me = S.file ? URL.createObjectURL(S.file) : '';
      ui.innerHTML = steps(2) + '<div class="tv-pair"><img src="' + me + '" alt="You"><span class="tv-swap">' + G.swap + '</span>' + (c.garmentUrl ? '<img src="' + esc(c.garmentUrl) + '" alt="Outfit">' : '') + '</div>' +
        '<div class="tv-title" style="font-size:16px" data-tv-stage>Analyzing your photo…</div>' +
        '<div class="tv-bar" role="progressbar" data-tv-pb aria-valuemin="0" aria-valuemax="100"><i data-tv-bar></i></div><div class="tv-pct" data-tv-pct>0%</div>' +
        '<div class="tv-tip"><small>TIP</small><p data-tv-tip></p></div>' + PRIV +
        '<button class="tv-link" type="button" data-tv-cancel style="margin:4px 0 0">Cancel</button>' + POWERED;
      ui.querySelector('[data-tv-cancel]').addEventListener('click', function () { if (S.ctl) S.ctl.abort(); stopProgress(); showUpload(); });
      startProgress();
    }

    function run() {
      var c = cfg(), h = blockedHours();
      if (h > 0) return showLimit(h);
      if (!c.api) return showFail('The try-on service is not connected for this store yet.');
      if (!S.file) return showUpload();
      showLoading();
      S.ctl = w.AbortController ? new AbortController() : null;
      shrink(S.file, 1280).then(function (f) {
        var fd = new FormData();
        fd.append('person_image', f);
        fd.append('shop', c.shop);
        if (c.customerId) fd.append('shopify_customer_id', c.customerId);
        fd.append('email', S.email);
        fd.append('session_id', sessionId());
        fd.append('product_id', c.productId);
        if (c.variantId) fd.append('variant_id', c.variantId);
        fd.append('category', c.category || 'tops');
        fd.append('product_url', c.productUrl);
        fd.append('product_title', c.productTitle);
        fd.append('platform', c.platform);
        if (c.garmentUrl) fd.append('garment_url', c.garmentUrl);

        return fetch(c.api + '/try-on-vton', { method: 'POST', body: fd, signal: S.ctl ? S.ctl.signal : undefined })
          .then(function (res) {
            if (res.status === 404) {
              return fetch(c.api + '/api/tryon/2d', { method: 'POST', body: fd, signal: S.ctl ? S.ctl.signal : undefined });
            }
            return res;
          });
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (r.status === 429) {
            var e = new Error('limit');
            e.limit = true;
            if (j.details && j.details.reset_at) {
              e.hours = Math.max(1, Math.ceil((new Date(j.details.reset_at).getTime() - Date.now()) / HOUR));
            }
            throw e;
          }
          if (!r.ok) throw new Error(j.message || j.detail || 'Try-on failed (' + r.status + ')');
          return j;
        });
      }).then(function (j) {
        var url = safeUrl(j.output_url || j.result_image);
        if (!url) throw new Error('No image was returned. Please try again.');
        S.resultUrl = url; ssSet(resultKey(), url); addUse(); histBtn.hidden = false;
        var im = new Image(); im.src = url;
        return (im.decode ? im.decode() : Promise.resolve()).catch(function () {}).then(function () {
          stopProgress(); S.p = 100; paint(); emit('result', { productId: c.productId, url: url });
          setTimeout(function () { if (S.resultUrl === url) showResult(); }, 250);
        });
      }).catch(function (e) {
        if (e && e.name === 'AbortError') return;
        stopProgress();
        if (e && e.limit) {
          var a = e.hours || c.windowHours;
          remember(K.uses, JSON.stringify(Array(c.limit).fill(Date.now())), 1);
          return showLimit(a);
        }
        showFail(e && e.message);
      });
    }

    function showFail(msg) {
      ui.innerHTML = '<div class="tv-center"><div class="tv-alert-ico">' + G.err.replace('width="15" height="15"', 'width="28" height="28"') + '</div><div class="tv-title">Processing failed</div><div class="tv-sub" style="margin-left:auto;margin-right:auto">' + esc(msg || 'Something went wrong.') + '</div><button class="tv-btn tv-btn-primary" type="button" data-tv-retry>Try again</button></div>' + POWERED;
      ui.querySelector('[data-tv-retry]').addEventListener('click', showUpload);
    }

    // alert when the free limit (default 3 try-ons) is used up
    function showLimit(hours) {
      var c = cfg();
      ui.innerHTML = '<div class="tv-center" role="alert"><div class="tv-alert-ico">' + G.clockBig + '</div><div class="tv-title">Try-on limit reached</div>' +
        '<div class="tv-sub" style="margin-left:auto;margin-right:auto">You’ve used all ' + c.limit + ' free try-ons.</div>' +
        '<div class="tv-blocked-time">Try again in ' + hours + ' hour' + (hours !== 1 ? 's' : '') + '.</div><button class="tv-btn" type="button" data-tv-lc style="padding:12px 28px">Close</button></div>' + POWERED;
      ui.querySelector('[data-tv-lc]').addEventListener('click', close);
      emit('limit', { hours: hours });
    }

    // 5) result (no watermark)
    function canBuy(c) { return !!(c.onBuy || adapterFor(c.platform) || c.buyUrl); }
    function showResult() {
      var c = cfg(), buy = canBuy(c);
      ui.innerHTML = steps(2) + '<div class="tv-result"><img class="tv-result-img" src="' + esc(S.resultUrl) + '" alt="Your try-on result">' + thumb(c, 'tv-result-thumb') + '</div>' +
        '<div class="tv-result-title">' + esc(c.productTitle) + '</div>' +
        (buy ? '<button class="tv-btn-buy" type="button" data-tv-buy>' + G.cart + '<span data-tv-buy-label>Buy now</span></button><div style="height:10px"></div>' : '') +
        '<div class="tv-error" data-tv-error hidden><span data-tv-error-icon></span><span data-tv-error-text></span></div>' +
        '<div class="tv-row"><button class="tv-btn" type="button" data-tv-save>Save</button><button class="tv-btn" type="button" data-tv-again>Try another</button><button class="tv-btn tv-btn-dark" type="button" data-tv-done>Done</button></div>' + POWERED;
      var eb = errBox();
      ui.querySelector('[data-tv-save]').addEventListener('click', function () { save(S.resultUrl); });
      ui.querySelector('[data-tv-again]').addEventListener('click', function () { S.resultUrl = null; ssDel(resultKey()); S.file = null; histBtn.hidden = true; checkUsage(S.email, null, showUpload); });
      ui.querySelector('[data-tv-done]').addEventListener('click', close);
      var b = ui.querySelector('[data-tv-buy]'); if (b) b.addEventListener('click', function () { doBuy(b, ui.querySelector('[data-tv-buy-label]'), eb); });
    }
    function save(url) {
      function fallback() { var a = d.createElement('a'); a.href = url; a.download = 'try-on-look.jpg'; a.target = '_blank'; a.rel = 'noopener'; a.click(); }
      fetch(url).then(function (r) { return r.blob(); }).then(function (b) {
        var u = URL.createObjectURL(b), a = d.createElement('a'); a.href = u; a.download = 'try-on-look.jpg'; a.click(); setTimeout(function () { URL.revokeObjectURL(u); }, 4000);
      }).catch(fallback);
    }
    function doBuy(btn, label, eb) {
      var c = cfg(), ctx = { productId: c.productId, variantId: c.variantId, productUrl: c.productUrl, title: c.productTitle, resultUrl: S.resultUrl, platform: c.platform }, p;
      eb.clear(); btn.disabled = true; label.textContent = 'Adding to cart…';
      try {
        var ad = adapterFor(c.platform);
        p = c.onBuy ? c.onBuy(ctx) : ad ? ad.buy(ctx) : (location.href = c.buyUrl, false);
      } catch (e) { p = Promise.reject(e); }
      Promise.resolve(p).then(function (r) {
        emit('buy', ctx);
        if (typeof r === 'string') location.href = r; else if (r !== false) close();
        btn.disabled = false; label.textContent = 'Buy now';
      }).catch(function (e) { btn.disabled = false; label.textContent = 'Buy now'; eb.show((e && e.message) || 'Could not add to cart. Please try again.'); });
    }

    // ---- appearance saved on the TryVtri dashboard ----
    function setVar(name, v) { if (isColor(v)) el.style.setProperty(name, v.trim()); }
    function applyLook(e) {
      if (!e || typeof e !== 'object') return;
      if (e.settings && typeof e.settings === 'object') e = e.settings;
      if (e.appearance && typeof e.appearance === 'object') e = e.appearance;
      var txt = el.querySelector('.tv-txt'), t1 = el.querySelector('.tv-t1');
      var title = pick(e, ['heading', 'title', 'btn_text', 'button_text', 'headline']);
      if (typeof title === 'string' && title.trim() && t1) t1.textContent = title;
      var desc = pick(e, ['description', 'subtitle', 'btn_sub', 'sub_text', 'subheading', 'btn_description']);
      if (typeof desc === 'string' && txt) {
        var t2 = el.querySelector('.tv-t2');
        if (desc.trim()) { if (!t2) { t2 = d.createElement('span'); t2.className = 'tv-t2'; txt.appendChild(t2); } t2.textContent = desc; }
        else if (t2) t2.parentNode.removeChild(t2);
      }
      var ik = pick(e, ['icon', 'icon_type', 'icon_name', 'icon_style']), name = '';
      if (typeof ik === 'number' && ICON_KEYS[ik]) name = ICON_KEYS[ik];
      else if (ik != null) { ik = String(ik).toLowerCase(); name = /^\d+$/.test(ik) && ICON_KEYS[+ik] ? ICON_KEYS[+ik] : /sparkles|stars/.test(ik) ? 'sparkles' : /spark|star|magic|wand/.test(ik) ? 'sparkle' : /camera|photo/.test(ik) ? 'camera' : /hanger|cloth|shirt|wardrobe/.test(ik) ? 'hanger' : /person|user|profile|body/.test(ik) ? 'person' : /scan|frame|viewfinder|default/.test(ik) ? 'scan' : ''; }
      var tile = el.querySelector('.tv-ico');
      if (name && tile && tile.getAttribute('data-tv-icon') !== name) { tile.setAttribute('data-tv-icon', name); tile.innerHTML = iconSvg(name); }
      setVar('--tv-icon-bg', pick(e, ['icon_tile_color', 'icon_bg', 'icon_bg_color', 'tile_color', 'icon_background']));
      setVar('--tv-icon-c', pick(e, ['icon_color', 'icon_fg']));
      setVar('--tv-bg', pick(e, ['card_color', 'card_bg', 'card_background', 'btn_bg']));
      var tc = pick(e, ['heading_color', 'title_color', 'text_color', 'btn_text_color']); setVar('--tv-title-c', tc); setVar('--tv-arrow-c', tc);
      setVar('--tv-desc-c', pick(e, ['description_color', 'desc_color', 'subtitle_color', 'sub_color']));
      var h = parseInt(pick(e, ['card_height', 'height', 'btn_height']), 10); if (h >= 30 && h <= 400) el.style.setProperty('--tv-h', h + 'px');
    }
    function syncLook() {
      var c = cfg(); if (!c.api || !c.sync) return;
      fetch(c.api + '/api/widget/settings?shop=' + encodeURIComponent(c.shop) + '&_=' + Date.now(), { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) { if (j && !destroyed) { applyLook(j); lsSet(K.look + c.shop, JSON.stringify(j)); } }).catch(function () {});
    }
    function initLook() {
      var c = cfg(); if (!c.sync) return;
      try { var cached = lsGet(K.look + c.shop); if (cached) applyLook(JSON.parse(cached)); } catch (e) {}
      syncLook();
      if (c.syncInterval > 0) syncT = setInterval(syncLook, c.syncInterval);
      d.addEventListener('visibilitychange', onVis);
    }
    function onVis() { if (!d.hidden) syncLook(); }

    function onLauncher(e) { e.preventDefault(); e.stopPropagation(); open(); }
    if (launcher) { launcher.addEventListener('click', onLauncher); initLook(); initVariantListeners(); }

    return {
      open: open, close: close,
      update: function (n) { assign(opts, n); },
      destroy: function () {
        destroyed = true; close(); clearInterval(syncT); d.removeEventListener('visibilitychange', onVis);
        if (launcher) launcher.removeEventListener('click', onLauncher);
        if (modal && modal.parentNode) modal.parentNode.removeChild(modal);
        el.__tv = null; el.removeAttribute('data-tv-ready');
      }
    };
  }

  // ---------- public API ----------
  var TryVtri = {
    version: VERSION,
    defaults: DEFAULTS,
    adapters: {},                       // TryVtri.adapters.myplatform = { buy: function (ctx) { return Promise } }
    cardHTML: cardHTML,
    init: function (o) { assign(DEFAULTS, o); TryVtri.scan(d); return TryVtri; },
    attach: function (el, o) {          // bind to a card that is already in the page (server-rendered markup)
      if (!el) return null;
      if (el.__tv) { el.__tv.update(o); return el.__tv; }
      if (!el.querySelector('[data-tv-open]')) el.innerHTML = cardHTML(assign({}, o, fromDataset(el)));
      if (!/\btv-card\b/.test(el.className)) el.className += (el.className ? ' ' : '') + 'tv-card';
      el.setAttribute('data-tv-ready', '1');
      return (el.__tv = Instance(el, o));
    },
    mount: function (el, o) { return TryVtri.attach(el, o); },
    open: function (o) { var i = Instance(d.createElement('div'), o); i.open(); return i; },
    scan: function (root) {
      var list = (root || d).querySelectorAll('[data-tryvtri]:not([data-tv-ready])');
      for (var i = 0; i < list.length; i++) TryVtri.attach(list[i]);
    }
  };

  // Built-in Shopify adapter (Add to cart, then checkout)
  TryVtri.adapters.shopify = {
    buy: function (ctx) {
      var id = null, f = d.querySelector('form[action*="/cart/add"]');
      function ok(v) { return v && /^\d+$/.test(String(v)); }
      if (f) {
        var r = f.querySelector('[name="id"]:checked'), s = f.querySelector('select[name="id"]'), i = f.querySelector('input[name="id"]');
        id = r && ok(r.value) ? r.value : s && ok(s.value) ? s.value : i && ok(i.value) ? i.value : null;
      }
      if (!id && ok(ctx.variantId)) id = ctx.variantId;
      if (!id) return Promise.reject(new Error('Please select a size or variant first.'));
      return fetch('/cart/add.js', { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, credentials: 'same-origin', body: JSON.stringify({ items: [{ id: Number(id), quantity: 1 }] }) })
        .then(function (res) { return res.json().catch(function () { return {}; }).then(function (j) { if (!res.ok) throw new Error(j.description || j.message || 'Could not add item to cart.'); return '/checkout'; }); });
    }
  };

  w.TryVtri = TryVtri;
  if (typeof module === 'object' && module.exports) module.exports = TryVtri;

  function boot() { TryVtri.scan(d); }
  if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', boot); else boot();
  d.addEventListener('shopify:section:load', function (e) { TryVtri.scan(e.target); });
})(window, document);
