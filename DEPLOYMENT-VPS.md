# Pemeliharaan VPS

Website, FastAPI, dan PostgreSQL berjalan bersama menggunakan Docker Compose. Panduan pemasangan tersedia di PANDUAN-VPS.md.

## Informasi akses

Simpan alamat SSH, akun administrator, password, kode pemulihan, dan lokasi backup dalam catatan operasional privat di luar repository. Kredensial produksi tidak disediakan dalam source code.

## Pemeriksaan dan pembaruan

Di direktori aplikasi server:

```sh
sudo docker compose ps
sudo python3 deploy/health_check.py
sudo python3 deploy/manage.py backup
sudo journalctl -u sehati-health.service -n 30
sudo journalctl -u sehati-local-backup.service -n 30
```

Buat backup sebelum pembaruan, salin kode yang berubah, lalu build/start ulang. Jangan menimpa `.env`, `secrets`, `migration`, atau volume database dengan paket instalasi awal. Jangan menjalankan `docker compose down -v` pada server yang menyimpan data.

Setelah migrasi, gunakan database produksi sebagai sumber utama. Database lokal tidak tersinkron otomatis.

Backup pada VPS saja tidak melindungi dari hilangnya server. Konfigurasikan tujuan backup di luar VPS, batasi aksesnya, dan uji pemulihan. Pantau kapasitas disk, kegagalan backup, kesehatan aplikasi, serta pembaruan keamanan.
