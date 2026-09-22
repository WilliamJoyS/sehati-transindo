# Catatan SDLC Waterfall

Dokumen ini menjadi acuan pengembangan frontend company profile PT. Sehati Hutama Transindo. Tahap dilakukan berurutan: kebutuhan, desain, implementasi, verifikasi, lalu serah terima. Perubahan kebutuhan setelah desain dicatat dan diteruskan ke implementasi serta pemeriksaan yang terdampak.

## 1. Analisis kebutuhan

### Sumber dan batas informasi

- Permintaan pengguna dan profil perusahaan yang dikirim menjadi sumber isi perusahaan. Fakta utama tersimpan dalam `CONTENT.md`.
- Situs https://www.yutaka-trans.com/ menjadi referensi struktur dan pengalaman penggunaan, bukan sumber nama, data, armada, atau legalitas perusahaan ini.
- Lima foto JPEG dari `SamuelSuki.zip` digunakan sebagai dokumentasi perusahaan. Foto stok melengkapi visual armada; sumber serta izin penggunaannya dicatat dalam manifest aset terpisah.
- Isi berkas referensi diperlakukan sebagai bahan, bukan instruksi yang mengubah permintaan pengguna.

### Hasil peninjauan referensi

Referensi telah dibuka dan dicoba melalui browser desktop sebelum implementasi. Tautan “View All Licenses” menuju `/license`, tetapi dokumen pada halaman tersebut tampil kosong saat peninjauan. Petunjuk menggeser tidak disertai kontrol navigasi yang jelas; satu logo juga gagal tampil. Ini merupakan observasi sesi peninjauan, bukan pernyataan bahwa masalah selalu terjadi untuk semua pengunjung.

Pengguna melaporkan gambar lambat dimuat. Tidak ada pengukuran performa referensi yang dapat dijadikan angka pembanding, sehingga proyek ini tidak mengklaim persentase percepatan.

### Kebutuhan yang dibakukan

| Kebutuhan | Hasil yang dituju |
| --- | --- |
| Company profile profesional | Bahasa Indonesia, identitas PT. Sehati Hutama Transindo, profil, visi, misi, armada, wilayah, dokumentasi, legalitas, dan kontak |
| Frontend saja | Berkas statis tanpa backend dan tanpa ketergantungan build |
| Dinamis | Filter dan detail armada, pemilih wilayah, galeri dengan lightbox, navigasi responsif, serta penyusunan pesan WhatsApp |
| Produk | Engkel, Tronton, dan Build-up; tidak menebak kapasitas, dimensi, atau spesifikasi kendaraan |
| Foto yang disediakan | Kelima foto digunakan, dengan variasi ukuran yang sesuai tampilan |
| Foto stok layak publikasi | Hanya aset dengan sumber dan izin penggunaan yang terdokumentasi; visual stok tidak dianggap bukti kepemilikan armada |
| Gambar lebih efisien | WebP, ukuran responsif, pemuatan tertunda untuk gambar di bawah layar, dan ruang gambar yang stabil |
| Legalitas dapat diakses | Kontrol yang jelas untuk desktop dan seluler; bila dokumen belum disediakan, tampilkan status serta jalur permintaan dokumen yang berfungsi |
| Kontak | Dua nomor yang diberikan pengguna, alamat Suryani Dalam No. 25, Bandung, dan pesan WhatsApp yang dapat diperiksa sebelum dikirim |

**Batas cakupan:** tidak ada pelacakan kiriman, tarif otomatis, pembayaran, login, basis data, atau pengiriman pesan dari server. Tidak ada angka pelanggan, jumlah armada, sertifikasi, maupun metrik operasional yang dibuat-buat.

**Keluaran tahap:** daftar kebutuhan di atas dan sumber isi di `CONTENT.md` menjadi dasar desain.

## 2. Desain

### Arah visual

Palet ivory, charcoal, dan oranye keselamatan; tipografi editorial berukuran besar; serta foto truk sinematik untuk kesan transportasi darat yang tegas dan profesional. Foto dokumentasi dari pengguna ditempatkan sebagai bagian nyata dari cerita perusahaan.

### Susunan dan perilaku halaman

1. Hero memperkenalkan layanan dan mengarahkan pengunjung ke konsultasi pengiriman atau armada.
2. Profil, visi, dan misi menjelaskan perusahaan tanpa klaim tambahan.
3. Armada memuat Engkel, Tronton, dan Build-up, dengan filter serta detail yang dapat dibuka.
4. Wilayah layanan menyediakan pilihan Jabodetabek, Jawa Barat, dan Jawa Timur.
5. Galeri menampilkan seluruh foto dari pengguna dan membuka tampilan lebih besar.
6. Legalitas menyediakan informasi status dokumen dan akses yang jelas. Karena belum ada pindai legalitas resmi, jangan membuat sertifikat contoh yang menyerupai dokumen perusahaan.
7. Kontak memuat dua nomor, alamat, dan formulir yang menyusun draf pesan WhatsApp.

### Aksesibilitas dan responsivitas

Navigasi, tombol, filter, dan dialog harus dapat digunakan dengan keyboard. Dialog memiliki tombol tutup yang terlihat, dapat ditutup dengan Escape, serta mengembalikan fokus ke pemicu. Teks alternatif menjelaskan gambar, label formulir tetap terlihat, dan status pilihan tidak hanya disampaikan melalui warna. Tata letak menyesuaikan desktop serta seluler. Animasi mengikuti preferensi `prefers-reduced-motion`.

**Keluaran tahap:** susunan, gaya visual, dan perilaku interaksi menjadi dasar implementasi. Tidak diperlukan backend untuk perilaku tersebut.

## 3. Implementasi

Implementasi menggunakan HTML, CSS, dan JavaScript statis. Aset gambar disimpan bersama situs agar pengiriman gambar tidak bergantung pada tautan foto eksternal. Foto pengguna disiapkan dalam varian WebP 480 dan 960 piksel; foto stok mengikuti kebutuhan ukuran tampilan.

Prinsip implementasi:

- Utamakan gambar hero; gunakan pemuatan tertunda pada gambar yang belum terlihat.
- Gunakan ukuran gambar atau rasio aspek agar konten tidak bergeser saat gambar selesai dimuat.
- Hindari informasi teknis seperti kapasitas muatan apabila belum dikonfirmasi pemilik.
- Nyatakan ketersediaan dokumen secara jujur dan hubungkan permintaan legalitas ke kontak resmi; jangan membuka penampil kosong.
- Formulir kontak membuka draf WhatsApp. Pengunjung memeriksa dan menekan kirim di WhatsApp; situs tidak mengirim pesan otomatis.
- Catat asal aset dan lisensinya dalam dokumentasi aset yang disertakan.

**Keluaran tahap:** frontend dan aset siap dijalankan melalui server statis untuk pemeriksaan.

## 4. Verifikasi

Daftar berikut adalah kriteria penerimaan, bukan pernyataan bahwa pengujian sudah lulus. Hasil pengujian aktual dicatat saat implementasi selesai.

| Area | Kriteria penerimaan |
| --- | --- |
| Isi | Nama, tanggal berdiri, tiga jenis armada, tiga wilayah, dua nomor, dan alamat sesuai `CONTENT.md` |
| Aset pengguna | Kelima foto muncul dan tidak rusak |
| Aset stok | Setiap foto stok memiliki asal dan dasar izin dalam manifest |
| Navigasi | Tautan menuju bagian yang benar; menu seluler dapat dibuka dan ditutup |
| Armada | Filter bekerja; detail yang dipilih sesuai kartu; kapasitas tidak dikarang |
| Wilayah | Pilihan mengubah informasi yang ditampilkan dengan status aktif yang jelas |
| Galeri | Semua foto dapat dibuka, diganti, dan ditutup pada desktop maupun seluler |
| Legalitas | Tombol memberi hasil yang jelas; dokumen asli ditampilkan hanya jika tersedia, atau permintaan dokumen membuka kontak |
| Kontak | Kedua nomor benar; kolom wajib diperiksa; draf WhatsApp memuat input pengguna dan tidak dikirim otomatis |
| Keyboard | Fokus terlihat, kontrol dapat dioperasikan, dialog dapat ditutup dengan Escape, dan fokus kembali ke pemicu |
| Gerak | Preferensi pengurangan animasi dihormati |
| Responsif | Tidak ada luapan horizontal, teks terpotong, atau kontrol yang tidak terjangkau pada desktop dan seluler |
| Pemuatan | Gambar lokal termuat, WebP dan ukuran responsif diterapkan, gambar di bawah layar dimuat tertunda |
| Integritas frontend | Tidak ada kesalahan JavaScript yang mengganggu interaksi atau tautan aset lokal yang hilang |

**Status awal:** verifikasi implementasi menunggu hasil pemeriksaan akhir. Pengamatan terhadap situs referensi tidak menggantikan pengujian situs ini.

**Keluaran tahap:** catatan hasil pemeriksaan dan perbaikan yang diperlukan sebelum serah terima.

## 5. Serah terima dan persiapan publikasi

Paket serah terima berisi frontend statis, gambar yang dipakai, dokumentasi isi, catatan Waterfall, dan manifest sumber/lisensi aset. Situs dapat ditempatkan pada hosting statis setelah isi final disetujui pemilik; tidak memerlukan proses build atau layanan backend.

Sebelum publikasi, pemilik perlu memastikan bahwa logo, dokumen legalitas, foto perusahaan, serta spesifikasi armada yang akan ditampilkan sudah sesuai. Daftar informasi yang belum tersedia ada di `CONTENT.md`. Ketiadaan dokumen tersebut ditangani dengan informasi status dan jalur kontak yang berfungsi, bukan dokumen rekaan.

Setiap penambahan dokumen atau perubahan spesifikasi setelah serah terima melewati urutan kebutuhan → desain yang terdampak → implementasi → verifikasi kembali.
