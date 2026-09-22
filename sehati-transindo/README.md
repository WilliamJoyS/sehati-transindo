# PT. Sehati Hutama Transindo — Website perusahaan

Frontend statis berbahasa Indonesia, dibangun dengan HTML, CSS, dan JavaScript. Tidak memerlukan instalasi paket, proses build, basis data, maupun backend aplikasi.

## Menjalankan

Cara termudah: buka `index.html` di browser. Untuk pratinjau HTTP lokal dengan Node.js:

```sh
node serve.cjs
```

Buka `http://127.0.0.1:4173`. Server hanya mendengarkan pada komputer lokal. Port dapat diganti melalui variabel `PORT`.

## Halaman

| Berkas | Isi |
| --- | --- |
| `index.html` | Beranda dan ringkasan perusahaan |
| `tentang.html` | Profil, perjalanan, visi, misi, dan komitmen |
| `armada.html` | Katalog dengan filter tiga kategori |
| `engkel.html` | Detail armada Engkel |
| `tronton.html` | Detail armada Tronton |
| `buildup.html` | Detail armada Build-up |
| `jangkauan.html` | Cakupan layanan interaktif |
| `galeri.html` | Lima foto operasional dan penampil foto |
| `legalitas.html` | Informasi legalitas dan akses dokumen |
| `kontak.html` | Alamat, telepon, dan penyusunan draf WhatsApp |

## Interaksi

- Filter armada, detail kendaraan, dan pemilihan kendaraan untuk konsultasi.
- Pemilih wilayah dengan ilustrasi rute; tombol panah keyboard dapat mengganti pilihan.
- Galeri dengan tombol sebelumnya/berikutnya, zoom, Escape, dan pengembalian fokus.
- Validasi formulir, pratinjau pesan, pilihan dua nomor kontak, serta salin pesan.
- Pengiriman pesan dilakukan pengunjung di WhatsApp. Situs tidak mengirim pesan otomatis dan tidak menyimpan isi formulir.
- Foto hero berganti hanya saat tombol dipilih. Animasi menghormati pengaturan pengurangan gerak perangkat.

## Konten yang dapat diperbarui

`config.js` menyimpan nomor tujuan, daftar dokumen publik, dan kredit foto. Isi halaman serta tautan telepon ditulis di HTML; jika kontak berubah, perbarui juga bagian kontak HTML terkait.

Tambahkan dokumen asli yang telah disetujui ke `assets/documents/`, lalu isi `SEHATI_CONFIG.licenses`, misalnya:

```js
licenses: [
  {
    title: 'Nama dokumen resmi',
    number: 'Nomor yang sudah diverifikasi',
    file: 'assets/documents/dokumen-resmi.pdf',
    type: 'pdf' // gunakan 'image' untuk JPG, PNG, atau WebP
  }
]
```

Penampil menyediakan pratinjau, tautan buka, unduh, dan kembali ke daftar. Saat daftar kosong, situs menyampaikan status secara jelas dan menyediakan permintaan dokumen melalui WhatsApp. Tidak ada sertifikat, nomor izin, kapasitas muatan, tarif, atau jumlah pelanggan yang dibuat-buat.

Identitas visual berupa wordmark teks dan bentuk grafis sederhana merupakan rancangan untuk situs ini. Ganti dengan logo resmi jika tersedia. Build-up tetap menggunakan kategori dari pemilik, tanpa menyamakannya dengan model kendaraan tertentu.

## Gambar dan lisensi

Seluruh foto disajikan secara lokal dalam WebP. Hero memiliki prioritas tinggi; gambar di bawah layar memakai lazy loading. Tersedia varian resolusi untuk layar kecil. Foto asli pengguna digunakan di profil dan kelima item galeri; foto kendaraan stok ditandai sebagai ilustrasi.

Daftar fotografer, URL sumber, dan dasar lisensi ada di `ASSET-LICENSES.md`. Foto stok tidak menjanjikan kesamaan model atau konfigurasi dengan unit perusahaan.

## Publikasi

Unggah HTML, `styles.css`, `pages.css`, `app.js`, `config.js`, `ASSET-LICENSES.md`, dan folder `assets/` ke hosting statis. `serve.cjs` hanya alat pratinjau lokal dan tidak perlu diunggah. Semua URL halaman menggunakan `.html`, sehingga tidak memerlukan aturan rewrite.

Website belum dipublikasikan melalui tugas ini. Pastikan dokumen legalitas asli, identitas resmi, serta rincian armada final sesuai sebelum menambahkannya ke publikasi. Tidak ada klaim GPS, TMS, atau nama pelanggan tanpa data dari perusahaan.

## Dokumentasi proses

- `docs/WATERFALL.md`: kebutuhan, desain, implementasi, verifikasi, dan serah terima.
- `docs/CONTENT.md`: fakta dari pemilik serta informasi yang belum tersedia.
- `docs/VERIFICATION.md`: hasil pemeriksaan aktual dan batas pengujian.
