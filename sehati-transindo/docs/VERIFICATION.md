# Hasil verifikasi — 10 September 2026

Pengujian menggunakan browser Chromium bawaan aplikasi dan pemeriksaan berkas statis. Catatan ini membedakan hal yang benar-benar diperiksa dari hal yang masih memerlukan materi perusahaan.

## Pemeriksaan yang telah dilakukan

| Area | Hasil aktual |
| --- | --- |
| Referensi | Homepage dibuka secara visual. “View All Licenses” dicoba di desktop; halaman tujuan tidak menampilkan dokumen saat sesi pemeriksaan. Struktur katalog, detail produk, teknologi, dan legalitas juga diperiksa melalui halaman publik. |
| JavaScript | Pemeriksaan sintaks `node --check` lulus untuk kode aplikasi, konfigurasi, dan server pratinjau. |
| Filter armada | Memilih Tronton menghasilkan satu kartu dan status “Menampilkan 1 armada”. |
| Detail armada | Detail Tronton terbuka sesuai kartu; Escape menutup dialog dan mengembalikan fokus ke pemicu. |
| Pilihan formulir | Tombol konsultasi Engkel mengisi pilihan Engkel pada formulir. Kekurangan tag option pada versi awal telah diperbaiki dan diuji ulang. |
| Pemilih wilayah | Klik Jawa Timur mengganti teks; ArrowUp memilih Jawa Barat dan memindahkan fokus. Tombol konsultasi mengisi asal Bandung dan tujuan Jawa Barat pada formulir beranda. |
| Galeri | Foto pertama terbuka, tombol berikutnya memuat foto kedua, pembesaran bekerja, Escape menutup. Foto kelima dapat berputar ke foto pertama. |
| Galeri lanskap | Pada viewport 844 × 390, kedua tombol navigasi berada di dalam batas dialog setelah perbaikan flex layout. Tombol berikutnya tetap berfungsi. |
| Legalitas | Tombol membuka informasi legalitas dan jalur permintaan dokumen ke nomor pertama. Tidak ada pindai resmi atau nomor izin rekaan. |
| Penampil dokumen | Cabang penampil gambar diuji menggunakan foto operasional sebagai fixture bertanda “bukan dokumen legalitas” pada salinan lokal terpisah. Gambar termuat, tautan unduh mengarah ke berkas, dan tombol kembali menampilkan daftar. Fixture tidak termasuk dalam website publik. |
| Formulir kosong | Submit diblokir oleh validasi native dan fokus menuju kolom nama. |
| Draf WhatsApp | Nama, perusahaan, armada, asal, tujuan, dan detail masuk ke pratinjau. Pemilihan nomor kedua menghasilkan URL tujuan `628112486000`. Karakter HTML ditampilkan sebagai teks, tanpa elemen HTML dari input. |
| Pengiriman pesan | Tautan WhatsApp tidak diklik selama pengujian. Tidak ada pesan dikirim dan data uji tidak diteruskan ke WhatsApp. |
| Tanpa JavaScript | Formulir menggunakan `inert` sampai penangan submit terpasang. Pada mode noscript formulir disembunyikan dan kontak telepon tetap tersedia. Pemeriksaan ini berdasarkan kode; mode JavaScript-off belum diuji melalui pengaturan browser. |
| Seluler | Menu pada 390 × 844 dapat dibuka, navigasi menutup menu, dialog legalitas dan galeri bekerja. Teks hero yang semula menyatu setelah line break diperbaiki. |
| Lebar sempit | Pada viewport 320 piksel tidak ditemukan elemen halaman yang melampaui batas horizontal. |
| Pengurangan gerak | CSS `prefers-reduced-motion` menonaktifkan animasi/transisi; pengguliran dan pergantian foto menyesuaikan preferensi. Diperiksa pada kode, belum melalui simulasi pengaturan sistem. |

## Ukuran dan sumber gambar

Delapan belas varian WebP berjumlah **1.000.566 byte** (sekitar 977 KiB). Berkas hero desktop berukuran **42.760 byte** (sekitar 42 KiB). Browser memilih varian sesuai `srcset`; angka tersebut adalah jumlah seluruh berkas, bukan jumlah transfer setiap kunjungan.

Semua foto dikirim dari aset lokal. Kelima foto kiriman digunakan. Sumber foto stok dan lisensi tercantum dalam `ASSET-LICENSES.md`; foto produk ditandai sebagai ilustrasi.

Tidak ada benchmark kecepatan referensi atau klaim skor Lighthouse. Performa hosting publik masih bergantung pada server, jaringan, cache, dan perangkat pengunjung.

## Batas yang perlu diketahui

- Salinan dokumen resmi belum diberikan. Pratinjau PDF aktual perlu diperiksa setelah berkas resmi ditambahkan; tautan buka dan unduh disediakan sebagai alternatif pratinjau browser.
- Tidak ada nomor izin, nama pelanggan, jumlah armada, tonase, dimensi, harga, atau waktu tempuh pasti yang dibuat-buat.
- Pemilik menyatakan perusahaan tidak memiliki GPS. Peta hanya ilustrasi wilayah layanan, bukan pelacakan kendaraan.
- Pengujian tidak mengirim pesan, melakukan panggilan, atau memublikasikan situs.
- Pemeriksaan lintas Safari/Firefox belum dilakukan. Tidak ada klaim audit aksesibilitas atau sertifikasi formal.

## Pemeriksaan halaman terpisah

Pemeriksaan statis pada 11 September 2026 lulus untuk 10 halaman HTML, 488 referensi lokal, dan 181 anchor: tautan, ID, heading, judul, label, komponen bersama, serta perlindungan formulir. Katalog armada terpisah juga telah dibuka dan diperiksa secara visual di desktop. Pemeriksaan browser menyeluruh untuk seluruh halaman tambahan belum dilakukan sebelum ekspor ZIP yang diminta pengguna.
