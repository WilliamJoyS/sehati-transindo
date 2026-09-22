/* Local staff workspace. Credentials stay in memory; API authorization is server-side. */
'use strict';

(() => {
  const $ = id => document.getElementById(id);
  let authenticator = null;
  const state = { session: null, customers: [], customerId: '', view: 'overview', report: null,
    recordOffset: 0, documentId: '', previewOffset: 0, pageSize: 50, busy: false, customerEpoch: 0,
    dashboardRequest: 0, recordsRequest: 0, historyRequest: 0, partnerRequest: 0, previewRequest: 0 };
  const views = { overview: 'Ringkasan', upload: 'Impor Excel', records: 'Data pengiriman', history: 'Riwayat impor', partner: 'Akses partner', account: 'Akun saya' };
  const sheetColumns = [
    ['source_number','No.'],['transporter','Transporter'],['do_number','No. D/O'],['vehicle_plate','No. Truck'],
    ['load_date','Tanggal Muat'],['estimated_unload_date','Perkiraan Tgl Bongkar'],['actual_unload_date','Actual Tgl Bongkar'],
    ['origin','Dari'],['destination','Tujuan'],['distributor','Agen / Distributor'],['capacity_m3','Kapasitas Truck (m³)'],
    ['vehicle_type','Tipe'],['quantity','Qty tire'],['volume_m3','M3'],['normal_charge','Tarif Normal'],
    ['additional_charge','Tarif Tambahan'],['reported_total','Total Tagihan'],['note','Ket.'],['rit_source','Rit (sumber)']
  ];
  const roles = { admin: 'Administrator', importer: 'Staf impor', viewer: 'Pembaca' };
  const actions = { new: 'Baru', updated: 'Diperbarui', unchanged: 'Tetap', blocked: 'Perlu koreksi' };
  const statuses = { preview: 'Siap ditinjau', committed: 'Tersimpan', blocked: 'Perlu koreksi', failed: 'Gagal / ditolak', rejected: 'Ditolak', preview_only: 'Pemeriksaan lama' };
  const fieldLabels = { id: 'ID sistem', version: 'Versi record', updated_at: 'Waktu pembaruan', do_number: 'Nomor D/O',
    load_date: 'Tanggal muat', estimated_unload_date: 'Perkiraan bongkar', actual_unload_date: 'Tanggal bongkar aktual',
    origin: 'Asal', destination: 'Tujuan', quantity: 'Jumlah barang', volume_m3: 'Volume (m³)',
    vehicle_plate: 'Nomor kendaraan', distributor: 'Distributor', capacity_m3: 'Kapasitas (m³)', vehicle_type: 'Jenis kendaraan', transporter: 'Transporter',
    'charge.normal_charge': 'Biaya normal', 'charge.additional_charge': 'Biaya tambahan', 'charge.reported_total': 'Total sesuai sumber',
    'charge.note': 'Catatan biaya', notes: 'Catatan', invoice_number: 'Nomor invoice' };

  const number = value => new Intl.NumberFormat('id-ID').format(Number(value) || 0);
  const customer = () => state.customers.find(item => item.id === state.customerId);
  const isAdmin = () => state.session?.user?.role === 'admin';
  const canImport = () => ['admin', 'importer'].includes(state.session?.user?.role);
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }
  function message(id, text = '') { $(id).textContent = text; $(id).hidden = !text; }
  function clearMessages() { message('global-error'); message('global-success'); }
  function dateText(value, includeTime = false) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat('id-ID', includeTime
      ? { dateStyle: 'medium', timeStyle: 'short' }
      : { day: '2-digit', month: 'short', year: 'numeric' }).format(date);
  }
  function errorText(body, fallback) {
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail)) return body.detail.map(item => item.msg || 'Nilai tidak valid.').join(' ');
    if (body?.detail?.message) return body.detail.message;
    return body?.message || fallback;
  }
  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.json !== undefined) headers.set('Content-Type', 'application/json');
    if (options.method && !['GET', 'HEAD'].includes(options.method)) {
      if (state.session?.csrf_token) headers.set('X-CSRF-Token', state.session.csrf_token);
    }
    let response;
    try {
      response = await fetch(path, { ...options, headers, credentials: 'same-origin', cache: 'no-store',
        body: options.json !== undefined ? JSON.stringify(options.json) : options.body });
    } catch (_) { throw new Error('Server belum dapat dihubungi. Silakan coba lagi.'); }
    let body;
    if (options.blob && response.ok) return response.blob();
    try { body = await response.json(); } catch (_) { body = null; }
    if (!response.ok) {
      if (response.status === 401 && !path.startsWith('/api/auth/')) {
        showLogin('Sesi telah berakhir. Silakan masuk kembali.');
      }
      const error = new Error(errorText(body, `Permintaan gagal (HTTP ${response.status}).`));
      error.status = response.status;
      throw error;
    }
    return body;
  }
  function customerQuery(extra = {}) {
    return new URLSearchParams({ customer_id: state.customerId, ...extra }).toString();
  }
  function pill(text, warning = false) { return element('span', text, `pill${warning ? ' warning' : ''}`); }
  function td(row, value, className) {
    const cell = element('td', value, className); row.append(cell); return cell;
  }
  function clearSecrets() {
    authenticator?.reset();
    $('delete-password').value = '';
    $('new-api-key').value = '';
    $('new-api-key').type = 'password';
    $('test-api-key').value = '';
    $('new-key-card').hidden = true;
    $('test-result').textContent = '';
    $('test-result').hidden = true;
    $('test-status').textContent = '';
    $('key-status').textContent = '';
  }
  function showLogin(reason = '') {
    state.session = null;
    state.customerEpoch += 1;
    state.report = null;
    clearSecrets();
    $('workspace').hidden = true;
    $('boot').hidden = true;
    $('login').hidden = false;
    $('password').value = '';
    $('totp').value = '';
    message('login-error', reason);
  }
  function applyPermissions() {
    document.querySelectorAll('.admin-only').forEach(node => {
      if (node.id === 'customer-form') { if (!isAdmin()) node.hidden = true; }
      else node.hidden = !isAdmin();
    });
    $('partner-permission-note').hidden = isAdmin();
    $('user-name').textContent = state.session?.user.username || 'Staf';
    $('user-role').textContent = roles[state.session?.user.role] || 'Staf';
    $('avatar').textContent = (state.session?.user.username || 'S').slice(0, 1).toUpperCase();
    updateControls();
  }
  function updateControls() {
    $('customer-select').disabled = state.busy || !state.customers.length;
    $('show-customer-form').disabled = state.busy;
    $('customer-submit').disabled = state.busy;
    $('workbook').disabled = state.busy || !canImport() || !state.customerId;
    $('upload-submit').disabled = state.busy || !canImport() || !state.customerId;
    $('export-workbook').disabled = state.busy || !state.customerId;
    $('partner-create').disabled = state.busy || !isAdmin() || !state.customerId;
    $('logout').disabled = state.busy;
    if ($('mobile-logout')) $('mobile-logout').disabled = state.busy;
    const warnings = state.report?.issues?.some(item => item.severity === 'warning');
    $('confirm-import').disabled = state.busy || !canImport() || !state.report?.can_confirm ||
      state.report?.customer_id !== state.customerId || (warnings && !$('warning-review').checked);
  }
  function setBusy(value) { state.busy = value; updateControls(); }
  function issueText(issue) {
    const counts = (issue.message || '').match(/\d+/g) || [];
    if (issue.code === 'NULLS_PRESERVED') return `${counts[0] || 'Sejumlah'} baris memiliki kolom opsional atau gabungan yang kosong. Nilainya tetap kosong; data dan biaya tidak disalin dari baris lain.`;
    if (issue.code === 'REFERENCE_ROWS') return `${counts[0] || 'Sejumlah'} baris ringkasan dan ${counts[1] || 'sejumlah'} baris referensi tambahan tidak dimasukkan sebagai data pengiriman. Sumbernya tetap tersedia di workbook asli.`;
    const messages = {
      INVOICE_LEVEL_CHARGE: 'Biaya tanpa D/O disimpan pada invoice. Sistem tidak mengaitkannya ke pengiriman atau perjalanan tertentu.',
      NUMERIC_ID: 'D/O berbentuk angka dipertahankan sebagai teks. Angka nol di depan yang sudah hilang pada sumber tidak dapat dikembalikan.',
      REPEATED_DO_PRESERVED: 'D/O berulang disimpan sebagai baris terpisah dengan ID masing-masing. D/O tidak dipakai untuk menentukan record yang diperbarui.',
      HIDDEN_SHEET: 'Tampilkan dan tinjau seluruh lembar tersembunyi sebelum mengimpor.',
      STALE_OR_FOREIGN_RECORD: 'Versi record tertinggal atau record milik pelanggan lain. Unduh Excel terbaru dan tinjau kembali perubahan.',
      LEGACY_UPDATE_REQUIRES_IDS: 'Invoice ini sudah tersimpan dengan isi berbeda. Gunakan Excel hasil ekspor yang membawa ID tetap untuk melakukan koreksi.',
      DOCUMENT_PERIOD_CONFLICT: 'Periode invoice berbeda dari data tersimpan. Periksa referensi invoice dan periodenya.',
      COMMIT_FAILED: 'Transaksi gagal. Tidak ada perubahan data yang disimpan. Buat pratinjau baru.',
      CUSTOMER_TEMPLATE_MISMATCH: 'Workbook ini berasal dari pelanggan atau versi template yang berbeda.'
    };
    return messages[issue.code] || issue.message || issue.code;
  }
  function renderIssues(targetId, issues) {
    const target = $(targetId); target.replaceChildren();
    for (const issue of issues || []) {
      const article = element('div', null, 'issue');
      article.append(element('span', null, `issue-marker ${issue.severity || 'info'}`));
      const body = element('div');
      body.append(element('p', issueText(issue)));
      const details = [issue.severity === 'blocking' ? 'PERLU KOREKSI' : issue.severity === 'warning' ? 'PERLU DITINJAU' : 'INFORMASI',
        issue.sheet, ...(issue.cells || [])].filter(Boolean);
      body.append(element('small', details.join(' · ')));
      article.append(body); target.append(article);
    }
  }
  async function loadCustomers(preferred = '') {
    const result = await request('/api/customers');
    state.customers = result.customers.filter(item => item.active);
    $('customer-select').replaceChildren();
    if (!state.customers.length) {
      const option = element('option', 'Belum ada pelanggan'); option.value = ''; $('customer-select').append(option);
    } else {
      state.customers.forEach(item => {
        const option = element('option', item.name); option.value = item.id; $('customer-select').append(option);
      });
    }
    state.customerId = state.customers.some(item => item.id === preferred) ? preferred : (state.customers[0]?.id || '');
    $('customer-select').value = state.customerId;
    syncCustomerLabels();
  }
  function syncCustomerLabels() {
    const name = customer()?.name || 'pelanggan yang dipilih';
    $('upload-customer-name').textContent = name;
    $('partner-customer-name').textContent = name;
    $('customer-context').textContent = customer() ? `${customer().code} · Data dan kredensial terpisah per pelanggan.`
      : 'Tambahkan pelanggan untuk mulai mengimpor data.';
    updateControls();
  }
  async function loadDashboard() {
    const epoch = state.customerEpoch; const serial = ++state.dashboardRequest;
    $('dashboard-loading').hidden = false;
    try {
      if (!state.customerId) {
        ['metric-deliveries', 'metric-invoices', 'metric-charges', 'metric-version'].forEach(id => { $(id).textContent = '0'; });
        $('period-body').replaceChildren(); $('issue-list').replaceChildren();
        $('periods-empty').hidden = false; $('issues-empty').hidden = false;
        $('issue-count').textContent = '0'; $('source-name').textContent = 'Belum ada berkas'; return;
      }
      const result = await request(`/api/dashboard?${customerQuery()}`);
      if (epoch !== state.customerEpoch || serial !== state.dashboardRequest) return;
      $('metric-deliveries').textContent = number(result.business.deliveries);
      $('metric-invoices').textContent = number(result.business.invoices);
      $('metric-charges').textContent = number(result.business.charges);
      $('metric-version').textContent = number(result.business.data_version);
      $('source-name').textContent = result.source || 'Belum ada berkas';
      $('report-description').textContent = result.source
        ? `${result.source} · ${statuses[result.status] || 'Hasil pemeriksaan'}${result.reused ? ' · unggahan dikenali kembali' : ''}`
        : 'Belum ada laporan impor untuk pelanggan ini.';
      $('period-body').replaceChildren();
      for (const period of result.periods || []) {
        const row = element('tr'); td(row, period.sheet); td(row, period.period || '—'); td(row, number(period.do_rows), 'numeric'); $('period-body').append(row);
      }
      $('periods-empty').hidden = Boolean(result.periods?.length);
      $('issue-count').textContent = number(result.issues?.length);
      renderIssues('issue-list', result.issues);
      $('issues-empty').hidden = Boolean(result.issues?.length);
    } finally { if (serial === state.dashboardRequest) $('dashboard-loading').hidden = true; }
  }
  async function loadRecords() {
    const epoch = state.customerEpoch; const serial = ++state.recordsRequest;
    if (!state.customerId) { $('records-body').replaceChildren(); $('records-empty').hidden = false; $('records-count').textContent = 'Belum ada pelanggan.'; return; }
    $('records-count').textContent = 'Memuat data tersimpan…';
    const query = { limit: state.pageSize, offset: state.recordOffset };
    if (state.documentId) query.document_id = state.documentId;
    const [result, invoices] = await Promise.all([
      request(`/api/register?${customerQuery(query)}`), request(`/api/invoices?${customerQuery({limit:100})}`)
    ]);
    if (epoch !== state.customerEpoch || serial !== state.recordsRequest) return;
    $('records-body').replaceChildren();
    $('sheet-tabs').replaceChildren();
    const documents = [...invoices.items].sort((a,b)=>a.period_start.localeCompare(b.period_start));
    const selected = documents.find(d=>d.id===state.documentId);
    $('sheet-title').textContent = selected ? `${dateText(selected.period_start)} – ${dateText(selected.period_end)}` : 'Seluruh periode';
    $('sheet-invoice').textContent = selected ? `Invoice: ${selected.invoice_number}` : `${invoices.total} dokumen tagihan · ${customer()?.name || ''}`;
    for (const doc of [{id:'',label:'Semua periode'}, ...documents]) {
      const button = element('button', doc.label || `${dateText(doc.period_start)} – ${dateText(doc.period_end)}`, `sheet-tab${doc.id===state.documentId ? ' active' : ''}`);
      button.type='button'; button.setAttribute('aria-pressed',String(doc.id===state.documentId));
      if (doc.invoice_number) button.title=doc.invoice_number;
      button.addEventListener('click',()=>run(async()=>{state.documentId=doc.id;state.recordOffset=0;await loadRecords();}));
      $('sheet-tabs').append(button);
    }
    for (const item of result.items) {
      const row = element('tr', null, item.kind==='charge' ? 'invoice-charge' : '');
      row.title=`Invoice ${item.invoice_number} · ${item.source_sheet || 'Data baru'}${item.source_row ? ' baris '+item.source_row : ''} · ID ${item.id} · versi ${item.version}`;
      for (const [field] of sheetColumns) {
        let value=item[field]; let className='';
        if (field.endsWith('_date')) value=value ? dateText(value) : '';
        if (['capacity_m3','quantity','volume_m3','normal_charge','additional_charge','reported_total'].includes(field)) {
          className='numeric';
          value=value===null || value===undefined ? '' : new Intl.NumberFormat('id-ID',{maximumFractionDigits:6}).format(Number(value));
        }
        if (field==='do_number' && item.kind==='charge') value='Biaya invoice';
        if (field==='note') className='note-cell';
        const cell=td(row,value??'',className);
        if (value===null || value===undefined || value==='') cell.classList.add('blank');
        if (field==='rit_source') cell.title='Catatan Rit pada workbook sumber; tidak dihitung ulang.';
      }
      $('records-body').append(row);
    }
    $('records-empty').hidden = result.total !== 0;
    $('records-count').textContent = `${number(result.total)} baris · pengiriman dan biaya invoice · ${customer()?.name || 'pelanggan ini'}`;
    $('records-page').textContent = result.total ? `${number(state.recordOffset + 1)}–${number(state.recordOffset + result.items.length)} dari ${number(result.total)}` : '0 record';
    $('records-prev').disabled = state.recordOffset === 0;
    $('records-next').disabled = state.recordOffset + result.items.length >= result.total;
  }
  async function loadHistory() {
    const epoch = state.customerEpoch; const serial = ++state.historyRequest;
    if (!state.customerId) { $('history-body').replaceChildren(); $('history-empty').hidden = false; return; }
    const result = await request(`/api/imports?${customerQuery()}`);
    if (epoch !== state.customerEpoch || serial !== state.historyRequest) return;
    $('history-body').replaceChildren();
    for (const batch of result.imports) {
      const row = element('tr');
      const file = td(row, batch.filename, 'history-file'); file.title = batch.filename;
      file.append(element('small', batch.id, 'history-sub'));
      td(row, dateText(batch.created_at, true)); td(row, number(batch.summary?.do_rows), 'numeric');
      td(row).append(pill(statuses[batch.status] || batch.status, ['blocked', 'failed'].includes(batch.status)));
      const button = element('button', 'Buka hasil →', 'table-button'); button.type = 'button';
      button.addEventListener('click', () => run(async () => {
        button.disabled = true;
        try {
          const report = await request(`/api/imports/${encodeURIComponent(batch.id)}`);
          if (report.customer_id !== state.customerId) return;
          setView('upload'); await renderPreview(report); $('upload-result').scrollIntoView({ behavior: 'smooth', block: 'start' });
        } finally { button.disabled = false; }
      }));
      td(row).append(button); $('history-body').append(row);
    }
    $('history-empty').hidden = result.imports.length !== 0;
  }
  function previewPagination() {
    if ($('preview-prev')) return;
    const bar = element('div', null, 'pagination');
    const prev = element('button', '← Sebelumnya', 'button outline compact'); prev.id = 'preview-prev'; prev.type = 'button';
    const page = element('span', '—'); page.id = 'preview-page'; page.setAttribute('aria-live', 'polite');
    const next = element('button', 'Berikutnya →', 'button outline compact'); next.id = 'preview-next'; next.type = 'button';
    bar.append(prev, page, next); $('preview-rows-note').after(bar);
    prev.addEventListener('click', () => run(async () => { state.previewOffset = Math.max(0, state.previewOffset - state.pageSize); await loadPreviewRows(); }));
    next.addEventListener('click', () => run(async () => { state.previewOffset += state.pageSize; await loadPreviewRows(); }));
  }
  async function renderPreview(report) {
    state.report = report; state.previewOffset = 0;
    $('upload-result').hidden = false; $('warning-review').checked = false;
    message('confirm-error'); $('confirm-status').textContent = '';
    const committed = report.status === 'committed';
    $('preview-status').textContent = statuses[report.status] || report.status;
    $('preview-status').className = `pill${['blocked', 'failed'].includes(report.status) ? ' warning' : ''}`;
    $('preview-title').textContent = committed ? (report.reused ? 'Unggahan sudah pernah disimpan.' : 'Data sudah tersimpan.') : 'Tinjau perubahan sebelum menyimpan.';
    $('preview-revision').textContent = `${report.source || 'Workbook'} · revisi ${report.revision || 1}`;
    $('upload-result-summary').textContent = `${number(report.summary?.do_rows)} baris D/O · ${number(report.summary?.distinct_do)} referensi D/O berbeda · ${number(report.total_stage_rows)} baris operasional. ${report.reused ? 'Pengulangan ini tidak menambah atau menimpa record.' : 'D/O berulang tetap memiliki ID sistem tersendiri.'}`;
    ['new', 'updated', 'unchanged', 'charges'].forEach(key => {
      const value = report.reused && key !== 'charges' ? (key === 'unchanged' ? report.total_stage_rows : 0) : report.summary?.[key];
      $(`preview-${key}`).textContent = number(value);
    });
    renderIssues('preview-issues', report.issues);
    const warnings = report.issues?.some(item => item.severity === 'warning');
    $('warning-review-label').hidden = !warnings || !report.can_confirm;
    $('open-records-after-import').hidden = !committed;
    $('confirm-import').hidden = committed;
    $('confirm-guidance').textContent = committed ? 'PostgreSQL menjadi sumber respons API.'
      : !canImport() ? 'Akun Anda hanya dapat membaca hasil pemeriksaan.'
      : !report.can_confirm ? 'Perbaiki temuan yang menghalangi, lalu unggah pratinjau baru.'
      : warnings ? 'Tinjau catatan dan centang persetujuan sebelum mengonfirmasi.' : 'Konfirmasi menyimpan seluruh batch dalam satu transaksi.';
    document.querySelectorAll('.workflow > span').forEach((node, index) => node.classList.toggle('current', index === (committed ? 2 : 1)));
    updateControls();
    await loadPreviewRows();
  }
  async function loadPreviewRows() {
    if (!state.report?.batch_id) return;
    const batchId = state.report.batch_id; const epoch = state.customerEpoch; const serial = ++state.previewRequest;
    $('preview-prev').disabled = true; $('preview-next').disabled = true;
    $('preview-rows-note').textContent = 'Memuat rincian perubahan…';
    const result = await request(`/api/imports/${encodeURIComponent(batchId)}/rows?${new URLSearchParams({ limit: state.pageSize, offset: state.previewOffset })}`);
    if (epoch !== state.customerEpoch || state.report?.batch_id !== batchId || serial !== state.previewRequest) return;
    $('preview-rows').replaceChildren();
    for (const item of result.items) {
      const row = element('tr'); td(row, `${item.source_sheet} · baris ${item.source_row}`);
      td(row, item.do_number || (item.kind === 'charge' ? 'Biaya tingkat invoice' : '—'));
      td(row).append(pill(actions[item.action] || item.action, item.action === 'blocked'));
      const changes = td(row);
      if (!item.changes?.length) changes.textContent = item.action === 'unchanged' ? 'Tidak ada perubahan' : 'Lihat catatan pemeriksaan';
      else {
        const details = element('details'); const summary = element('summary', `${item.changes.length} kolom · lihat rincian`);
        details.append(summary);
        for (const change of item.changes) {
          const line = element('div', null, 'change-line');
          line.append(element('strong', fieldLabels[change.field] || change.field));
          line.append(element('span', `${displayValue(change.old)} → ${displayValue(change.new)}`));
          details.append(line);
        }
        changes.append(details);
      }
      $('preview-rows').append(row);
    }
    $('preview-rows-note').textContent = result.total
      ? 'Semua baris dapat ditinjau melalui halaman berikut. Nilai kosong ditampilkan sebagai ∅.' : 'Tidak ada baris yang berhasil dikenali.';
    $('preview-page').textContent = result.total ? `${number(state.previewOffset + 1)}–${number(state.previewOffset + result.items.length)} dari ${number(result.total)} baris` : '0 baris';
    $('preview-prev').disabled = state.previewOffset === 0;
    $('preview-next').disabled = state.previewOffset + result.items.length >= result.total;
  }
  function displayValue(value) { return value === null || value === undefined || value === '' ? '∅' : String(value); }
  async function loadPartners() {
    if (!isAdmin()) return;
    const epoch = state.customerEpoch; const serial = ++state.partnerRequest;
    const result = await request('/api/partner-clients');
    if (epoch !== state.customerEpoch || serial !== state.partnerRequest) return;
    const checked = new Set(Array.from($('partner-fields').querySelectorAll('input:checked')).map(node => node.value));
    const hadFields = Boolean($('partner-fields').childElementCount);
    $('partner-fields').replaceChildren();
    for (const field of result.available_fields) {
      const label = element('label', null, 'check-label');
      const box = document.createElement('input'); box.type = 'checkbox'; box.value = field; box.name = 'allowed_fields';
      box.disabled = result.mandatory_fields.includes(field);
      box.checked = box.disabled || (hadFields ? checked.has(field) : result.default_fields.includes(field));
      label.append(box, element('span', `${fieldLabels[field] || field}${box.disabled ? ' · wajib' : ''}`));
      $('partner-fields').append(label);
    }
    const clients = result.clients.filter(item => item.customer_id === state.customerId);
    $('partner-body').replaceChildren();
    for (const client of clients) {
      const row = element('tr'); td(row, client.name); td(row, client.key_hint); td(row, dateText(client.expires_at, true));
      const expired = new Date(client.expires_at).getTime() <= Date.now();
      td(row).append(pill(!client.active ? 'Dicabut' : expired ? 'Kedaluwarsa' : 'Aktif', !client.active || expired));
      const controls = td(row);
      if (client.active) {
        const button = element('button', 'Cabut akses', 'table-button'); button.type = 'button';
        button.addEventListener('click', () => run(async () => {
          button.disabled = true;
          try {
            await request(`/api/partner-clients/${encodeURIComponent(client.id)}/revoke`, { method: 'POST' });
            clearSecrets(); message('global-success', `Akses “${client.name}” telah dicabut.`); await loadPartners();
          } finally { button.disabled = false; }
        }));
        controls.append(button);
      } else controls.textContent = '—';
      $('partner-body').append(row);
    }
    $('partners-empty').hidden = clients.length !== 0;
  }
  async function loadView() {
    if (!state.session) return;
    if (state.view === 'records') return loadRecords();
    if (state.view === 'history') return loadHistory();
    if (state.view === 'partner') return loadPartners();
    if (state.view === 'account') {
      const account=await request('/api/account');
      $('account-username').textContent=account.username;
      $('account-role').textContent=`${roles[account.role] || account.role} · Login dengan kode autentikator`;
      $('mfa-account-status').textContent=`${account.authenticator_enrolled ? 'Authenticator sudah dipasangkan melalui website.' : 'Akun menggunakan autentikator lokal. Pasangkan HP untuk penggunaan sehari-hari.'} Kode pemulihan tersisa: ${account.recovery_codes_remaining}.`;
      $('account-protected').hidden=account.can_delete;
      $('delete-account-form').hidden=!account.can_delete;
      $('delete-account-form').reset(); message('delete-error');
      return;
    }
    if (state.view === 'overview') return loadDashboard();
  }
  function setView(name, updateHash = true) {
    if (!Object.hasOwn(views, name)) name = 'overview';
    state.view = name;
    document.querySelectorAll('.view').forEach(node => { node.hidden = node.id !== `view-${name}`; });
    document.querySelectorAll('[data-view]').forEach(node => {
      const active = node.dataset.view === name;
      node.classList.toggle('active', active);
      if (active) node.setAttribute('aria-current', 'page'); else node.removeAttribute('aria-current');
    });
    $('breadcrumb-current').textContent = views[name];
    if (updateHash && location.hash !== `#${name}`) history.replaceState(null, '', `#${name}`);
  }
  async function changeCustomer() {
    state.customerEpoch += 1;
    state.recordOffset = 0; state.documentId = ''; state.previewOffset = 0; state.report = null;
    clearSecrets(); clearMessages();
    $('upload-result').hidden = true; $('workbook').value = ''; $('file-info').textContent = 'Belum ada berkas dipilih';
    message('upload-error'); message('confirm-error'); $('upload-status').textContent = '';
    syncCustomerLabels();
    await Promise.all([loadDashboard(), state.view !== 'overview' ? loadView() : Promise.resolve()]);
  }
  async function enterWorkspace(session) {
    authenticator?.reset();
    state.session = session;
    $('password').value = ''; $('totp').value = '';
    $('boot').hidden = true; $('login').hidden = true; $('workspace').hidden = false;
    applyPermissions();
    await loadCustomers(state.customerId);
    setView(location.hash.slice(1) || 'overview', false);
    await changeCustomer();
  }
  async function run(action, errorId = 'global-error') {
    try { await action(); }
    catch (error) { message(errorId, error.message || 'Permintaan belum berhasil. Silakan coba lagi.'); }
  }

  previewPagination();
  const letters=element('tr',null,'letters'); const headers=element('tr');
  sheetColumns.forEach(([field,label],index)=>{
    const letter=element('th',String.fromCharCode(65+index)); letter.setAttribute('aria-hidden','true'); letters.append(letter);
    const heading=element('th',label); heading.scope='col'; headers.append(heading);
  });
  $('records-head').append(letters,headers);
  const mobileLogout = $('mobile-logout');

  async function logout() {
    await request('/api/auth/logout', { method: 'POST' });
    showLogin();
  }
  $('logout').addEventListener('click', () => run(logout));
  mobileLogout.addEventListener('click', () => run(logout));
  document.querySelectorAll('[data-view], [data-go]').forEach(node => node.addEventListener('click', () => {
    setView(node.dataset.view || node.dataset.go); clearMessages(); run(loadView);
  }));
  window.addEventListener('hashchange', () => { setView(location.hash.slice(1), false); run(loadView); });
  $('customer-select').addEventListener('change', () => {
    state.customerId = $('customer-select').value; run(changeCustomer);
  });
  $('show-customer-form').addEventListener('click', () => {
    const open = $('customer-form').hidden;
    $('customer-form').hidden = !open; $('show-customer-form').setAttribute('aria-expanded', String(open));
    if (open) $('customer-name').focus();
  });
  $('cancel-customer').addEventListener('click', () => { $('customer-form').hidden = true; $('show-customer-form').setAttribute('aria-expanded', 'false'); });
  $('customer-form').addEventListener('submit', event => {
    event.preventDefault();
    run(async () => {
      message('customer-error'); setBusy(true);
      try {
        const created = await request('/api/customers', { method: 'POST', json: { name: $('customer-name').value.trim(), code: $('customer-code').value.trim() } });
        $('customer-form').reset(); $('customer-form').hidden = true; $('show-customer-form').setAttribute('aria-expanded', 'false');
        await loadCustomers(created.id); await changeCustomer();
        message('global-success', `Pelanggan “${created.name}” telah ditambahkan.`);
      } finally { setBusy(false); }
    }, 'customer-error');
  });
  $('workbook').addEventListener('change', () => {
    const file = $('workbook').files[0];
    $('file-info').textContent = file ? `${file.name} · ${number(Math.ceil(file.size / 1024))} KB` : 'Belum ada berkas dipilih';
    message('upload-error');
  });
  $('upload-form').addEventListener('submit', event => {
    event.preventDefault();
    run(async () => {
      message('upload-error'); clearMessages();
      const file = $('workbook').files[0];
      if (!file || !/\.xlsx$/i.test(file.name)) throw new Error('Pilih berkas Excel berformat .xlsx.');
      if (file.size > 10 * 1024 * 1024) throw new Error('Berkas melebihi batas 10 MB.');
      if (!state.customerId) throw new Error('Pilih pelanggan terlebih dahulu.');
      const form = new FormData(); form.append('file', file); form.append('customer_id', state.customerId);
      setBusy(true); $('upload-status').textContent = 'Memeriksa berkas dan membandingkan dengan database…';
      try {
        const report = await request('/api/imports/preview', { method: 'POST', body: form });
        await renderPreview(report);
        $('upload-status').textContent = report.reused ? 'Berkas dikenali sebagai unggahan yang sudah disimpan.' : 'Pratinjau selesai. Tinjau hasil di bawah.';
        await loadDashboard(); $('upload-result').scrollIntoView({ behavior: 'smooth', block: 'start' });
      } catch (error) { $('upload-status').textContent = 'Berkas belum disimpan.'; throw error; }
      finally { setBusy(false); }
    }, 'upload-error');
  });
  $('warning-review').addEventListener('change', updateControls);
  $('confirm-import').addEventListener('click', () => run(async () => {
    if (!state.report?.can_confirm || $('confirm-import').disabled) return;
    const report = state.report;
    message('confirm-error'); setBusy(true); $('confirm-status').textContent = 'Menyimpan seluruh batch ke PostgreSQL…';
    try {
      const result = await request(`/api/imports/${encodeURIComponent(report.batch_id)}/confirm`, { method: 'POST', json: { expected_revision: report.revision } });
      await renderPreview(result);
      $('confirm-status').textContent = result.reused ? 'Batch sudah tersimpan. Tidak ada impor ganda.' : 'Selesai. Data sekarang tersedia melalui API yang memiliki izin.';
      await loadDashboard();
    } catch (error) {
      $('confirm-status').textContent = 'Penyimpanan belum dapat dikonfirmasi. Periksa status batch sebelum mencoba kembali.';
      try { await renderPreview(await request(`/api/imports/${encodeURIComponent(report.batch_id)}`)); } catch (_) { /* Keep original failure visible. */ }
      throw error;
    } finally { setBusy(false); }
  }, 'confirm-error'));
  $('records-prev').addEventListener('click', () => run(async () => { state.recordOffset = Math.max(0, state.recordOffset - state.pageSize); await loadRecords(); }));
  $('records-next').addEventListener('click', () => run(async () => { state.recordOffset += state.pageSize; await loadRecords(); }));
  $('refresh-records').addEventListener('click', () => run(loadRecords));
  $('refresh-history').addEventListener('click', () => run(loadHistory));
  $('export-workbook').addEventListener('click', () => run(async () => {
    if (!state.customerId) return;
    setBusy(true);
    try {
      const session = await request('/api/session');
      if (!session.authenticated) { showLogin('Sesi telah berakhir. Silakan masuk kembali.'); return; }
      const anchor = element('a');
      anchor.href = `/api/exports/workbook?${customerQuery()}`;
      anchor.download = `sehati-${customer()?.code || 'records'}-editable.xlsx`;
      document.body.append(anchor); anchor.click(); anchor.remove();
      message('global-success', 'Unduhan Excel diminta. Pertahankan ID dan versi saat melakukan koreksi.');
    } finally { setBusy(false); }
  }));
  $('partner-form').addEventListener('submit', event => {
    event.preventDefault();
    run(async () => {
      message('partner-error'); clearMessages();
      if (!state.customerId) throw new Error('Pilih pelanggan terlebih dahulu.');
      const fields = Array.from($('partner-fields').querySelectorAll('input:checked')).map(node => node.value);
      if (!fields.length) throw new Error('Pilih kolom yang boleh diakses.');
      setBusy(true);
      try {
        const result = await request('/api/partner-clients', { method: 'POST', json: {
          name: $('partner-name').value.trim(), customer_id: state.customerId,
          expires_in_days: Number($('partner-expiry').value), allowed_fields: fields } });
        clearSecrets(); $('new-api-key').value = result.api_key; $('test-api-key').value = result.api_key;
        $('new-key-card').hidden = false; $('key-status').textContent = 'Kunci baru hanya tersedia pada layar ini. Belum dikirim kepada partner.';
        $('partner-name').value = ''; await loadPartners(); $('new-key-card').scrollIntoView({ behavior: 'smooth', block: 'center' });
      } finally { setBusy(false); }
    }, 'partner-error');
  });
  $('refresh-partners').addEventListener('click', () => run(loadPartners));
  $('copy-api-key').addEventListener('click', () => run(async () => {
    if (!$('new-api-key').value) return;
    try { await navigator.clipboard.writeText($('new-api-key').value); $('key-status').textContent = 'Kunci disalin. Simpan di tempat privat.'; }
    catch (_) { $('new-api-key').type = 'text'; $('new-api-key').select(); $('key-status').textContent = 'Penyalinan otomatis tidak tersedia. Salin teks yang dipilih, lalu tutup kartu ini.'; }
  }));
  $('clear-api-key').addEventListener('click', () => { clearSecrets(); $('new-api-key').type = 'password'; });
  $('clear-test').addEventListener('click', () => { $('test-api-key').value = ''; $('test-result').textContent = ''; $('test-result').hidden = true; $('test-status').textContent = ''; });
  $('delete-account-form').addEventListener('submit', event=>{
    event.preventDefault();
    if (!$('delete-confirmation').checked) return;
    run(async()=>{
      $('delete-account').disabled=true; message('delete-error');
      try {
        await request('/api/account',{method:'DELETE',json:{username:$('delete-username').value,password:$('delete-password').value}});
        $('delete-account-form').reset(); showLogin('Akun telah dihapus. Data operasional tetap tersimpan.');
      } finally { $('delete-password').value=''; $('delete-account').disabled=false; }
    },'delete-error');
  });
  $('test-api').addEventListener('click', () => run(async () => {
    const key = $('test-api-key').value.trim();
    if (!key) { $('test-status').textContent = 'Masukkan kunci API terlebih dahulu.'; return; }
    $('test-api').disabled = true; $('test-status').textContent = 'Mengirim permintaan ke API…';
    try {
      const response = await fetch('/api/partner/v1/deliveries?limit=5', {
        headers: { 'X-API-Key': key }, credentials: 'omit', cache: 'no-store' });
      const result = await response.json();
      $('test-result').textContent = JSON.stringify(result, null, 2); $('test-result').hidden = false;
      $('test-status').textContent = `HTTP ${response.status}${response.ok ? ` · ${result.data?.length || 0} record ditampilkan` : ' · permintaan ditolak'}`;
    } catch (_) { $('test-status').textContent = 'Server tidak dapat dihubungi.'; }
    finally { $('test-api').disabled = false; }
  }));
  window.addEventListener('pagehide', clearSecrets);

  authenticator = window.SehatiAuthenticator({ request, enterWorkspace, showLogin,
    session: () => state.session, refreshAccount: loadView });

  run(async () => {
    try {
      const session = await request('/api/session');
      if (session.authenticated) await enterWorkspace(session); else showLogin();
      if (authenticator.hasActivation()) authenticator.openActivation();
    } catch (error) { showLogin(error.message); }
  });
})();
