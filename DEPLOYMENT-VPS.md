# Website Sehati di VPS

Deployment: 20 September 2026. Dokumen ini menggantikan status pra-deployment pada laporan persiapan sebelumnya.

- Website: https://sehatihutamatransindo.web.id/
- Admin: https://sehatihutamatransindo.web.id/admin/
- www dialihkan ke domain utama melalui HTTPS.
- VPS Biznet Gio SHTransindo: 139.190.98.51, Ubuntu 22.04, 1 vCPU / 1 GB RAM / 60 GB disk.
- Website, FastAPI dan PostgreSQL berjalan pada satu VPS dengan Docker Compose, di /opt/sehati.
- Swap 2 GB dan batas memori container disiapkan untuk kapasitas VPS ini. Kapasitas kecil tetap perlu dipantau; ini bukan hasil uji beban.

## Akses admin

Akun tetap **admin_sehati**, tidak ada admin tambahan. Password VPS dan kode pemulihan BARU disimpan secara privat di **migrasi-privat/AKSES-ADMIN-VPS.json**. Jangan unggah file itu ke website atau kirimkan ke partner. Google Authenticator yang sudah dipasangkan tetap digunakan. Password localhost tidak berubah.

Setelah mulai menggunakan VPS, lakukan entri bisnis hanya pada VPS. Database lokal merupakan salinan terpisah dan tidak tersinkron otomatis.

## Data dan pemeriksaan

- Backup migrasi terbaru: 20 September 2026 22:27:41 WIB, 1.652 baris pengiriman total.
- Uji HTTPS publik, halaman website/admin, password + authenticator, logout, penolakan akses anonim, dan perlindungan file rahasia berhasil.
- Preview BRIDGESTONE 2025.xlsx berhasil di VPS, tanpa konfirmasi impor dan tanpa mengubah data bisnis.
- API diuji dengan key sementara yang hanya boleh melihat satu pelanggan dan kolom pilihan. Pelanggan Bridgestone yang diuji memiliki 826 baris; total seluruh pelanggan 1.652. Key pengujian sudah dicabut.
- Key partner lama dari localhost dinonaktifkan saat migrasi. Buat key produksi dari halaman API Partner sesuai pelanggan/kolom yang disepakati; belum ada key dikirim ke Bridgestone.
- Foto Fuso terbaru dan atribusi/lisensinya sudah masuk website.

## Operasional

- HTTPS otomatis dikelola Caddy. SSH menggunakan private key; login SSH dengan password sudah nonaktif.
- Firewall host aktif: SSH 22 dengan pembatasan percobaan, HTTP 80, HTTPS 443 TCP/UDP. Port database dan backend tidak dipublikasikan.
- Volume PostgreSQL permanen. **Jangan menjalankan docker compose down -v.**
- Backup lokal otomatis sekitar 02:30 WIB setiap hari; setiap backup diuji restore ke database sementara.
- Health check berjalan setiap 5 menit. Hasil ada di journal systemd; belum ada penerima notifikasi eksternal.
- Backup produksi terverifikasi juga sudah diunduh ke **migrasi-privat/backup-vps-20260920T153953Z.tar**, mencakup database dan kunci authenticator. Simpan secara terbatas.
- **Backup otomatis ke storage di luar VPS belum dikonfigurasi.** Salinan di komputer saat deployment adalah snapshot satu kali. Tentukan tujuan SFTP/S3 dan kredensial storage sebelum mengaktifkan timer offsite pada panduan. Backup lokal saja tidak melindungi dari hilangnya VPS.
- Retensi backup belum menghapus file otomatis; pantau penggunaan disk. Pembaruan keamanan OS sudah dijalankan; tinjau update OS, image dan dependency secara berkala.

## SSH dan pemeliharaan

Di PowerShell pada komputer ini:

```powershell
ssh -i "$env:USERPROFILE\.ssh\sehati-vps.pem" ssh-ed25519@139.190.98.51
```

Di server:

```sh
cd /opt/sehati
sudo docker compose ps
sudo python3 deploy/health_check.py
sudo python3 deploy/manage.py backup
sudo journalctl -u sehati-health.service -n 30
sudo journalctl -u sehati-local-backup.service -n 30
```

Untuk pembaruan, buat backup dahulu, salin hanya kode yang berubah, lalu build/start ulang. Jangan menimpa .env, secrets, migration atau volume database dengan paket instalasi awal. PANDUAN-VPS.md adalah panduan pemasangan server baru, bukan perintah untuk mengulang restore pada server aktif.

DNS authoritative sudah benar. Sebagian resolver masih dapat menyimpan jawaban kosong lama hingga sekitar satu jam; tunggu cache DNS berakhir bila komputer tertentu belum bisa membuka domain. Pemeriksaan koneksi langsung ke IP tetap memvalidasi sertifikat HTTPS untuk domain asli.
