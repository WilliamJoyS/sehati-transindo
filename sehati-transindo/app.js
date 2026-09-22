'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const config = window.SEHATI_CONFIG || { phones: ['6287720006871', '628112486000'], licenses: [] };
const escapeHTML = (value) => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const icon = (name) => `<svg aria-hidden="true"><use href="#${name}"/></svg>`;
const whatsappURL = (number, message) => `https://wa.me/${number}?text=${encodeURIComponent(message)}`;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const detailDialog = $('#detail-dialog');
const galleryDialog = $('#gallery-dialog');
let previousFocus = null;
let currentGalleryIndex = 0;
let toastTimer;

function notify(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('visible'), 3800);
}

function openDialog(dialog) {
  previousFocus = document.activeElement;
  if (!dialog.open) dialog.showModal();
  document.body.classList.add('modal-open');
  dialog.scrollTop = 0;
  $('.dialog-close', dialog).focus({ preventScroll: true });
}

function closeDialog(dialog) {
  if (dialog.open) dialog.close();
}

$$('dialog').forEach(dialog => {
  $('.dialog-close', dialog).addEventListener('click', () => closeDialog(dialog));
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeDialog(dialog);
  });
  dialog.addEventListener('close', () => {
    document.body.classList.remove('modal-open');
    if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
  });
});

// All content is available without scroll animations. Enhance only when supported.
if ('IntersectionObserver' in window && !reducedMotion.matches) {
  document.documentElement.classList.add('js-motion');
  const revealObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('in-view');
      revealObserver.unobserve(entry.target);
    });
  }, { threshold: 0.08, rootMargin: '0px 0px 35px 0px' });
  $$('.reveal').forEach(element => revealObserver.observe(element));
}

const menuToggle = $('.menu-toggle');
const mobileMenu = $('#mobile-nav');
function setMenu(open) {
  menuToggle.setAttribute('aria-expanded', String(open));
  menuToggle.setAttribute('aria-label', open ? 'Tutup menu' : 'Buka menu');
  mobileMenu.hidden = !open;
}
menuToggle.addEventListener('click', () => setMenu(menuToggle.getAttribute('aria-expanded') !== 'true'));
$$('a', mobileMenu).forEach(link => link.addEventListener('click', () => setMenu(false)));
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !mobileMenu.hidden) { setMenu(false); menuToggle.focus(); }
});
document.addEventListener('click', event => {
  if (!mobileMenu.hidden && !$('.site-header').contains(event.target)) setMenu(false);
});
window.matchMedia('(min-width: 1001px)').addEventListener('change', event => { if (event.matches) setMenu(false); });

if ('IntersectionObserver' in window) {
  const sectionObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      $$('.desktop-nav a').forEach(link => {
        if (!link.getAttribute('href').startsWith('#')) return;
        const active = link.getAttribute('href') === '#' + entry.target.id;
        link.classList.toggle('is-current', active);
        if (active) link.setAttribute('aria-current', 'location'); else link.removeAttribute('aria-current');
      });
    });
  }, { rootMargin: '-15% 0px -65% 0px', threshold: 0 });
  $$('main > section[id]').forEach(section => sectionObserver.observe(section));
}

// Manual carousel: no autoplay or hidden background network requests.
const slides = [
  { src: 'assets/images/hero-1600.webp', srcset: 'assets/images/hero-800.webp 800w, assets/images/hero-1600.webp 1600w', alt: 'Truk melintasi jalan saat matahari terbenam, foto ilustrasi', caption: 'Perjalanan penuh kepercayaan', note: 'Foto ilustrasi' },
  { src: 'assets/images/operations-1-960.webp', srcset: 'assets/images/operations-1-480.webp 480w, assets/images/operations-1-960.webp 960w', alt: 'Armada truk oranye di halaman operasional Sehati', caption: 'Armada di balik perjalanan', note: 'Dokumentasi operasional Sehati' },
  { src: 'assets/images/operations-3-960.webp', srcset: 'assets/images/operations-3-480.webp 480w, assets/images/operations-3-960.webp 960w', alt: 'Truk oranye di area perawatan Sehati', caption: 'Dipersiapkan dengan sepenuh hati', note: 'Dokumentasi operasional Sehati' }
];
let heroTimer;
$$('[data-slide]').forEach(button => button.addEventListener('click', () => {
  const index = Number(button.dataset.slide);
  const slide = slides[index];
  const photo = $('#hero-photo');
  clearTimeout(heroTimer);
  photo.classList.add('changing');
  heroTimer = setTimeout(() => {
    photo.srcset = slide.srcset;
    photo.src = slide.src;
    photo.alt = slide.alt;
    photo.classList.remove('changing');
  }, reducedMotion.matches ? 0 : 200);
  $('#slide-caption').innerHTML = `${String(index + 1).padStart(2, '0')} <span>/</span> ${slide.caption}`;
  $('#hero-image-note').textContent = slide.note;
  $$('[data-slide]').forEach(dot => {
    const active = dot === button;
    dot.classList.toggle('active', active);
    dot.setAttribute('aria-pressed', String(active));
  });
}));

// Fleet catalogue: intentionally no unverified dimensions, capacities or prices.
const fleetData = {
  engkel: { name: 'Engkel', eyebrow: 'Fleksibel untuk distribusi', type: 'Box dan bak terbuka', body: 'Pilihan armada untuk distribusi barang dan kebutuhan pengiriman harian. Tim kami membantu menyesuaikan kendaraan dengan jenis barang dan akses tujuan Anda.', use: 'Distribusi barang dan pengiriman harian', dimensions: [{ name: 'Box', length: '8,3', width: '2,4', height: '2,5' }, { name: 'Bak terbuka', length: '6', width: '2,4', height: '2,5' }] },
  tronton: { name: 'Tronton', eyebrow: 'Dukungan untuk muatan besar', type: 'Armada box', body: 'Armada untuk menunjang pengiriman bervolume besar dan distribusi antarkota. Konsultasikan jumlah muatan, dimensi barang, serta jadwal agar tim kami dapat menyiapkan solusi yang sesuai.', use: 'Distribusi barang bervolume besar', dimensions: [{ name: 'Box', length: '7,5', width: '2,4', height: '2,5' }] },
  buildup: { name: 'Build-up', eyebrow: 'Untuk kebutuhan operasional', type: 'Tronton build-up box', body: 'Pilihan kendaraan untuk mendukung kebutuhan transportasi bisnis. Konfigurasi armada dan kesesuaian muatan akan dikonfirmasi langsung oleh tim Sehati berdasarkan kebutuhan pengiriman Anda.', use: 'Pengiriman sesuai kebutuhan bisnis', dimensions: [{ name: 'Tronton build-up box', length: '9,3', width: '2,4', height: '2,5' }] }
};

function fleetDimensions(rows) {
  return `<div class="vehicle-dimensions"><table class="dimensions-table"><caption>Dimensi armada</caption><thead><tr><th scope="col">Jenis bak</th><th scope="col">Panjang</th><th scope="col">Lebar</th><th scope="col">Tinggi</th></tr></thead><tbody>${rows.map(row => `<tr><th scope="row">${row.name}</th><td>${row.length} m</td><td>${row.width} m</td><td>${row.height} m</td></tr>`).join('')}</tbody></table></div>`;
}
$$('[data-filter]').forEach(button => button.addEventListener('click', () => {
  const category = button.dataset.filter;
  let count = 0;
  $$('.fleet-card').forEach(card => {
    card.hidden = category !== 'all' && category !== card.dataset.category;
    if (!card.hidden) count++;
  });
  $$('[data-filter]').forEach(filter => {
    const active = filter === button;
    filter.classList.toggle('active', active);
    filter.setAttribute('aria-pressed', String(active));
  });
  $('#fleet-count').textContent = `Menampilkan ${count} armada`;
}));

function selectFleet(name) {
  if (!$('#fleet')) {
    window.location.href = `kontak.html?armada=${encodeURIComponent(name)}`;
    return;
  }
  $('#fleet').value = name;
  closeDialog(detailDialog);
  $('#kontak').scrollIntoView({ behavior: reducedMotion.matches ? 'instant' : 'smooth' });
  notify(`Armada ${name} telah dipilih dalam formulir.`);
}

$$('[data-fleet]').forEach(button => button.addEventListener('click', () => {
  const key = button.dataset.fleet;
  const fleet = fleetData[key];
  $('#dialog-body').innerHTML = `<img class="modal-hero" src="assets/images/${key}-800.webp?v=fleet20260922" width="800" height="600" alt="Foto stok ilustrasi kategori ${fleet.name}"><p class="dialog-eyebrow">${fleet.eyebrow}</p><h2 id="dialog-title">Armada ${fleet.name}</h2><p>${fleet.body}</p>${fleetDimensions(fleet.dimensions)}<dl class="modal-specs"><div><dt>Kategori</dt><dd>${fleet.type}</dd></div><div><dt>Kebutuhan</dt><dd>${fleet.use}</dd></div><div><dt>Wilayah layanan</dt><dd>Jabodetabek, Jawa Barat,<br>Jawa Timur</dd></div></dl><p class="modal-note">Kapasitas muatan, jadwal, dan ketersediaan kendaraan dikonfirmasi bersama tim. Foto merupakan ilustrasi, bukan dokumentasi unit yang akan dikirim.</p><button class="button orange" id="choose-fleet">Konsultasikan Armada ${fleet.name} ${icon('diagonal')}</button><div><a class="text-link" href="${key}.html">Lihat halaman armada ${icon('arrow')}</a></div>`;
  $('#choose-fleet').addEventListener('click', () => selectFleet(fleet.name));
  openDialog(detailDialog);
}));

const regions = {
  jabodetabek: { name: 'Jabodetabek', description: 'Mendukung distribusi bisnis menuju Jakarta, Bogor, Depok, Tangerang, dan Bekasi.', path: 'M190 155 Q150 85 112 102', x: 112, y: 102, labelX: 80, labelY: 74, label: 'JABODETABEK' },
  jabar: { name: 'Jawa Barat', description: 'Menghubungkan kebutuhan distribusi di Jawa Barat, dengan Bandung sebagai basis operasional perusahaan.', path: 'M190 155 Q233 101 281 146', x: 281, y: 146, labelX: 256, labelY: 112, label: 'JAWA BARAT' },
  jatim: { name: 'Jawa Timur', description: 'Mendukung pengiriman antarkota menuju Jawa Timur. Diskusikan kota tujuan dan kebutuhan muatan bersama tim kami.', path: 'M190 155 Q365 74 521 222', x: 521, y: 222, labelX: 486, labelY: 190, label: 'JAWA TIMUR' }
};
let selectedRegion = 'jabodetabek';
function setRegion(key, focus = false) {
  const region = regions[key];
  selectedRegion = key;
  $$('[data-region]').forEach(tab => {
    const active = tab.dataset.region === key;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
    if (active && focus) tab.focus();
  });
  $('#region-panel').setAttribute('aria-labelledby', `tab-${key}`);
  $('#region-title').textContent = region.name;
  $('#region-description').textContent = region.description;
  $('#route-line').setAttribute('d', region.path);
  $('#map-destination').setAttribute('cx', region.x);
  $('#map-destination').setAttribute('cy', region.y);
  $('#destination-label').setAttribute('x', region.labelX);
  $('#destination-label').setAttribute('y', region.labelY);
  $('#destination-label').textContent = region.label;
}
$$('[data-region]').forEach((tab, index, tabs) => {
  tab.addEventListener('click', () => setRegion(tab.dataset.region));
  tab.addEventListener('keydown', event => {
    const directions = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 };
    let next;
    if (event.key in directions) next = (index + directions[event.key] + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault();
    setRegion(tabs[next].dataset.region, true);
  });
});
$('#region-cta')?.addEventListener('click', event => {
  if (!$('#origin')) {
    event.preventDefault();
    window.location.href = `kontak.html?asal=Bandung&tujuan=${encodeURIComponent(regions[selectedRegion].name)}`;
    return;
  }
  if (!$('#origin').value) $('#origin').value = 'Bandung';
  $('#destination').value = regions[selectedRegion].name;
});

const gallery = [
  { file: 'operations-1-960.webp', title: 'Area armada', alt: 'Deretan truk oranye di area armada perusahaan' },
  { file: 'operations-2-960.webp', title: 'Persiapan di bengkel', alt: 'Area bengkel dan persediaan ban untuk perawatan' },
  { file: 'operations-3-960.webp', title: 'Perawatan armada', alt: 'Truk oranye di dalam bengkel Sehati' },
  { file: 'operations-4-960.webp', title: 'Setelah senja', alt: 'Kendaraan di halaman perusahaan pada malam hari' },
  { file: 'operations-5-960.webp', title: 'Hari yang baru', alt: 'Halaman armada di bawah langit biru' }
];
function showGallery(index) {
  currentGalleryIndex = (index + gallery.length) % gallery.length;
  const item = gallery[currentGalleryIndex];
  const image = $('#lightbox-image');
  image.src = 'assets/images/' + item.file;
  image.alt = item.alt;
  $('#gallery-title').textContent = item.title;
  $('#gallery-caption').textContent = `${String(currentGalleryIndex + 1).padStart(2, '0')} / 05 — Dokumentasi operasional Sehati`;
  $('.lightbox-stage').classList.remove('zoomed');
  $('#gallery-zoom').textContent = '+ Perbesar';
  $('#gallery-zoom').setAttribute('aria-label', 'Perbesar foto');
}
$$('[data-gallery]').forEach(button => button.addEventListener('click', () => {
  showGallery(Number(button.dataset.gallery));
  openDialog(galleryDialog);
}));
$('#gallery-prev').addEventListener('click', () => showGallery(currentGalleryIndex - 1));
$('#gallery-next').addEventListener('click', () => showGallery(currentGalleryIndex + 1));
$('#gallery-zoom').addEventListener('click', () => {
  const zoomed = $('.lightbox-stage').classList.toggle('zoomed');
  $('#gallery-zoom').textContent = zoomed ? '− Sesuaikan' : '+ Perbesar';
  $('#gallery-zoom').setAttribute('aria-label', zoomed ? 'Sesuaikan foto ke layar' : 'Perbesar foto');
});
galleryDialog.addEventListener('keydown', event => {
  if (event.key === 'ArrowRight') { event.preventDefault(); showGallery(currentGalleryIndex + 1); }
  if (event.key === 'ArrowLeft') { event.preventDefault(); showGallery(currentGalleryIndex - 1); }
});

// Public document viewer. No fabricated certificates or broken placeholder URLs.
const isLocalDocument = (file) => typeof file === 'string' && /^assets\/documents\/[a-zA-Z0-9_./-]+\.(pdf|png|jpg|jpeg|webp)$/i.test(file) && !file.includes('..');
const licenses = (config.licenses || []).filter(item => isLocalDocument(item.file));
function renderLicenses() {
  $('#dialog-body').innerHTML = `<p class="dialog-eyebrow">Landasan kepercayaan</p><h2 id="dialog-title">Legalitas perusahaan</h2><p>PT. Sehati Hutama Transindo memiliki legalitas resmi dari Kementerian Hukum dan Hak Asasi Manusia Republik Indonesia.</p>${licenses.length ? '<div class="license-list">' + licenses.map((item, index) => `<button class="license-link" data-license="${index}">${icon('document')}<span>${escapeHTML(item.title)}<small>${escapeHTML(item.number || 'Dokumen perusahaan')}</small></span>${icon('diagonal')}</button>`).join('') + '</div>' : `<div class="license-empty">${icon('document')}<h3>Informasi dokumen melalui tim kami</h3><p>Salinan dokumen belum ditampilkan di situs. Untuk kebutuhan verifikasi atau kerja sama, silakan meminta dokumen legalitas langsung kepada tim Sehati.</p></div>`}<a class="button orange" href="${whatsappURL(config.phones[0], 'Halo tim PT. Sehati Hutama Transindo, saya ingin meminta informasi dan salinan dokumen legalitas perusahaan untuk kebutuhan verifikasi kerja sama.')}" target="_blank" rel="noopener noreferrer">Minta Dokumen Legalitas ${icon('diagonal')}</a>`;
  $$('[data-license]').forEach(button => button.addEventListener('click', () => renderDocument(Number(button.dataset.license))));
}
function renderDocument(index) {
  const doc = licenses[index];
  if (!doc) return;
  const file = escapeHTML(doc.file);
  $('#dialog-body').innerHTML = `<p class="dialog-eyebrow">Dokumen ${index + 1} / ${licenses.length}</p><h2 id="dialog-title">${escapeHTML(doc.title)}</h2>${doc.type === 'image' ? `<img class="document-image" src="${file}" alt="${escapeHTML(doc.title)}">` : `<iframe class="document-frame" src="${file}" title="Pratinjau ${escapeHTML(doc.title)}"></iframe>`}<p class="modal-note">Jika pratinjau tidak tersedia di perangkat Anda, gunakan tombol Buka Dokumen.</p><div class="dialog-actions"><button class="button outline-dark" id="back-licenses">← Daftar dokumen</button><a class="button orange" href="${file}" target="_blank" rel="noopener noreferrer">Buka Dokumen ${icon('diagonal')}</a><a class="text-link" href="${file}" download>Unduh dokumen ↓</a></div>`;
  $('#back-licenses').addEventListener('click', () => { renderLicenses(); $('.license-link', detailDialog)?.focus(); });
  detailDialog.scrollTop = 0;
  $('#back-licenses').focus({ preventScroll: true });
}
$('#open-licenses')?.addEventListener('click', () => { renderLicenses(); openDialog(detailDialog); });

$('#quote-form')?.addEventListener('submit', event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const formData = new FormData(form);
  const read = name => String(formData.get(name) || '').trim();
  for (const name of ['name', 'origin', 'destination', 'message']) {
    const field = form.elements.namedItem(name);
    if (!read(name)) {
      field.setCustomValidity('Mohon isi bagian ini.');
      field.reportValidity();
      field.addEventListener('input', () => field.setCustomValidity(''), { once: true });
      return;
    }
  }
  const number = config.phones.includes(read('contact-person')) ? read('contact-person') : config.phones[0];
  const message = `Halo tim PT. Sehati Hutama Transindo,\n\nSaya ingin berkonsultasi mengenai pengiriman barang.\n\nNama: ${read('name')}\n${read('company') ? 'Perusahaan: ' + read('company') + '\n' : ''}Armada: ${read('fleet')}\nKota asal: ${read('origin')}\nKota tujuan: ${read('destination')}\n\nDetail pengiriman:\n${read('message')}\n\nTerima kasih.`;
  $('#dialog-body').innerHTML = `<p class="dialog-eyebrow">Satu langkah lebih dekat</p><h2 id="dialog-title">Pesan Anda siap.</h2><p>Periksa detailnya, lalu lanjutkan ke WhatsApp. Pesan belum dikirim.</p><pre class="quote-preview">${escapeHTML(message)}</pre><div class="dialog-actions"><a class="button orange" id="send-whatsapp" target="_blank" rel="noopener noreferrer" href="${whatsappURL(number, message)}">Lanjut ke WhatsApp ${icon('diagonal')}</a><button class="button outline-dark" id="copy-quote">Salin Pesan</button></div><p class="modal-note" style="margin-top:20px">Tujuan: +${number}. Pengiriman dilakukan oleh Anda di WhatsApp. Situs ini tidak menyimpan data formulir.</p>`;
  $('#copy-quote').addEventListener('click', async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(message);
      $('#copy-quote').textContent = 'Pesan Tersalin ✓';
    } catch {
      const range = document.createRange();
      range.selectNodeContents($('.quote-preview'));
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      $('#copy-quote').textContent = 'Teks dipilih — salin secara manual';
    }
  });
  openDialog(detailDialog);
});

$('#privacy-button').addEventListener('click', () => {
  $('#dialog-body').innerHTML = `<p class="dialog-eyebrow">Privasi Anda</p><h2 id="dialog-title">Data tetap dalam kendali Anda.</h2><p>Situs ini tidak menggunakan cookie pelacakan, analitik pihak ketiga, atau penyimpanan data formulir. Informasi yang Anda ketik hanya digunakan di browser untuk menyiapkan draf pesan.</p><p>Saat memilih “Lanjut ke WhatsApp”, isi pesan diteruskan ke WhatsApp melalui tautan. Anda meninjau dan mengirimkannya sendiri di aplikasi tersebut. Penggunaan WhatsApp dan Google Maps mengikuti kebijakan masing-masing layanan.</p><p>Foto dan berkas situs disajikan dari situs ini. Penyedia hosting dapat mencatat akses teknis untuk menjalankan layanannya.</p>`;
  openDialog(detailDialog);
});
$('#credits-button').addEventListener('click', () => {
  const credits = window.SEHATI_PHOTO_CREDITS || [];
  $('#dialog-body').innerHTML = `<p class="dialog-eyebrow">Di balik visual kami</p><h2 id="dialog-title">Kredit foto</h2><p>Lima foto operasional disediakan untuk situs ini melalui arsip SamuelSuki.zip. Foto Fuso pada katalog merupakan ilustrasi; model dan ukuran unit aktual dikonfirmasi bersama tim.</p><ul class="credit-list">${credits.map(item => `<li><strong>${escapeHTML(item.use)}</strong><br>${escapeHTML(item.author)} · <a href="${escapeHTML(item.url)}" target="_blank" rel="noopener noreferrer">Sumber foto</a> · <a href="${escapeHTML(item.licenseUrl || item.url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(item.license)}</a>${item.changes ? `<br>${escapeHTML(item.changes)}` : ''}</li>`).join('')}</ul><a class="text-link" href="ASSET-LICENSES.md" target="_blank" rel="noopener noreferrer">Lihat catatan sumber dan lisensi ${icon('diagonal')}</a>`;
  openDialog(detailDialog);
});
$('#year').textContent = new Date().getFullYear();
// Enable the form only after its safe, local submit handler is installed.
$('#quote-form')?.removeAttribute('inert');

// Preserve catalogue and route choices when moving to the contact page.
const query = new URLSearchParams(window.location.search);
if ($('#quote-form')) {
  const requestedFleet = query.get('armada');
  if (Object.values(fleetData).some(fleet => fleet.name === requestedFleet)) $('#fleet').value = requestedFleet;
  if (query.get('asal')) $('#origin').value = query.get('asal').slice(0, 80);
  if (query.get('tujuan')) $('#destination').value = query.get('tujuan').slice(0, 80);
}
const currentPage = location.pathname.split('/').pop() || 'index.html';
const parentPage = ['engkel.html', 'tronton.html', 'buildup.html'].includes(currentPage) ? 'armada.html' : currentPage;
$$('.desktop-nav a, #mobile-nav a').forEach(link => {
  if (link.getAttribute('href') === parentPage) {
    link.setAttribute('aria-current', 'page');
    link.classList.add('is-current');
  }
});
