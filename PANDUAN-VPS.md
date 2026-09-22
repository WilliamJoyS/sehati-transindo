# Memasang Sehati di satu VPS

Panduan ini untuk VPS BARU Ubuntu 22.04/24.04 LTS. Jangan menjalankan proses restore pada database produksi yang sudah berisi data. Skrip restore menolak database yang tidak kosong.

Arsitektur: internet → Caddy HTTPS → FastAPI + website/admin → PostgreSQL privat.
Hanya Caddy membuka port publik 80/443. App dan PostgreSQL tidak mempublikasikan port.
Data database berada di volume permanen; restart/rebuild aplikasi tidak menghapus data.

## 1. Siapkan server dan DNS

- Dapatkan IP, username SSH dan akses sudo dari provider.
- Gunakan kunci SSH. Jangan kirim password SSH atau private key melalui chat.
- Buat record A untuk domain yang dipilih ke IP VPS. Tambahkan AAAA hanya jika IPv6 VPS benar-benar dikonfigurasi.
- Di firewall provider, buka 80/TCP dan 443/TCP untuk web. 443/UDP opsional untuk HTTP/3. Batasi SSH 22/TCP ke IP pengelola jika memungkinkan.
- Jangan buka port 5432 atau 8000 ke internet.
- Paket memakai domain utama dan redirect HTTPS dari www. Tambahkan CNAME www ke domain utama.

## 2. Upload dari Windows

Gunakan WinSCP dengan protokol SFTP, atau PowerShell. Ganti USER dan IP_VPS sesuai data provider:

```powershell
cd "C:\Users\PC\Downloads\Sehati-VPS-20260920-130634"
scp .\sehati-vps.zip USER@IP_VPS:~/sehati-vps.zip
scp -r .\migrasi-privat USER@IP_VPS:~/migrasi-sehati
ssh USER@IP_VPS
```

Provider biasanya tidak mempunyai tombol "submit ZIP → website langsung jadi". Pada unmanaged VPS, langkah berikut dikerjakan melalui terminal SSH. Pada managed VPS, berikan panduan ini kepada teknisi yang dipercaya.

## 3. Ekstrak dan instal kebutuhan (terminal SSH Linux)

```sh
sudo apt-get update
sudo apt-get install -y unzip
sudo mkdir -p /opt/sehati
sudo unzip -n "$HOME/sehati-vps.zip" -d /opt/sehati
sudo install -d -m 700 /opt/sehati/migration
sudo cp "$HOME/migrasi-sehati/database.dump" "$HOME/migrasi-sehati/database.json" "$HOME/migrasi-sehati/app-secrets.json" /opt/sehati/migration/
sudo chmod 600 /opt/sehati/migration/database.dump /opt/sehati/migration/database.json /opt/sehati/migration/app-secrets.json
cd /opt/sehati
sudo sh deploy/install-ubuntu.sh
```

Installer mengambil Docker dari repositori resmi, serta memasang Python host dan restic untuk backup. Ia tidak mengubah firewall atau kredensial SSH.

## 4. Isi domain dan buat konfigurasi privat

Ganti domain/email contoh dengan milik perusahaan:

```sh
sudo python3 deploy/configure.py --domain sehati-domain-anda.id --email pengelola@domain-anda.id
sudo docker compose config --quiet
```

Script membuat .env untuk domain/email dan secrets/ untuk password database baru serta kunci authenticator yang diimpor. Kunci rahasia tidak dicetak. Folder secrets hanya dapat dilalui pemiliknya; file di dalamnya dipasang read-only hanya ke container yang membutuhkannya.

Script menolak menimpa konfigurasi yang sudah ada. Jangan membuat ulang password database secara sembarang setelah volume database terbentuk.

compose.yaml menggunakan format JSON yang valid sebagai YAML; Docker Compose membacanya langsung.

## 5. Pulihkan data SEBELUM menyalakan app

```sh
sudo docker compose up -d --wait db
sudo python3 deploy/manage.py restore --file migration/database.dump
sudo docker compose build --pull app
```

Restore memverifikasi checksum dan memastikan database kosong. Ia mempertahankan seluruh data bisnis, lalu menonaktifkan sesi, kode pemulihan, akun dan API key hasil salinan untuk mencegah pemakaian kredensial percobaan di internet.

Jika restore menolak karena database tidak kosong: BERHENTI. Jangan menjalankan docker compose down -v atau menghapus volume. Periksa apakah server sudah berisi data, atau gunakan VPS/volume baru untuk pemulihan.

## 6. Aktifkan admin yang sama

```sh
sudo docker compose run --rm --no-deps app python /srv/deploy/activate_admin.py --username admin_sehati
```

Masukkan password BARU minimal 14 karakter dua kali. Input password tidak terlihat di terminal. Tidak ada akun baru dibuat; akun inspeksi lain tetap nonaktif.

- Jika HP sudah dipasangkan saat backup: Google Authenticator yang sama tetap berlaku. Simpan kode pemulihan BARU yang dicetak sekali.
- Jika belum dipasangkan: izin pemasangan awal dibuka 24 jam. Website akan menampilkan QR setelah username/password benar.
- Kunci enkripsi yang salah membuat aktivasi gagal sebelum akun diubah.

Perubahan di VPS tidak mengganti password akun lokal di komputer Anda.

## 7. Jalankan website dan cek HTTPS

```sh
sudo docker compose up -d --wait
sudo docker compose ps
curl -f https://sehati-domain-anda.id/api/health
sudo python3 deploy/health_check.py
```

Caddy mengurus sertifikat HTTPS setelah DNS benar dan port 80/443 dapat diakses. Jika gagal, periksa:

```sh
sudo docker compose logs --tail=80 caddy
sudo docker compose logs --tail=80 app
```

Jangan membuka port backend sebagai jalan pintas. Rahasia dan backup tidak ada di web root.

## 8. Pemeriksaan sebelum dipakai

- Website/gambar/tautan kontak terbuka di domain HTTPS.
- Masuk dengan admin_sehati dan Google Authenticator; logout lalu login kembali.
- Tabel/periode/jumlah data sesuai snapshot. Upload workbook percobaan → preview → konfirmasi hanya bila memang ingin menyimpan perubahan.
- Buat API key produksi dari halaman API Partner, pilih pelanggan dan kolomnya.
- Tanpa key, endpoint partner menghasilkan 401. Key satu pelanggan tidak bisa membaca pelanggan lain. Lihat API-PARTNER.md.
- /docs dan /openapi.json hanya tersedia setelah login sebagai admin.
- Akun dan API key dari backup tidak otomatis aktif; ini sengaja.

## 9. Backup otomatis di luar VPS

Backup membutuhkan storage terpisah (SFTP atau S3) dan password enkripsi restic. Isian ini belum dapat ditentukan tanpa layanan backup Anda.

1. Salin deploy/backup.env.example menjadi secrets/backup.env, isi tujuan yang sebenarnya.
2. Buat secrets/restic_password memakai password kuat yang berbeda. Simpan salinannya secara offline/di password manager.
3. Untuk SFTP, pasang kunci SSH backup dan verifikasi fingerprint host storage secara manual. Untuk S3, isi kredensial terbatas hanya untuk bucket backup tersebut.
4. Inisialisasi repository sekali menggunakan environment yang sama. Jangan mengetik password sebagai argumen command line:

```sh
sudo -i
cd /opt/sehati
umask 077
cp deploy/backup.env.example secrets/backup.env
nano secrets/backup.env
nano secrets/restic_password
chmod 600 secrets/backup.env secrets/restic_password
set -a
. ./secrets/backup.env
set +a
restic init
python3 deploy/offsite_backup.py
exit
```

Isi backup.env hanya format NAMA=nilai; untuk konfigurasi contoh, tidak perlu tanda kutip atau ekspresi shell. Pastikan file ini milik root dan tidak dapat diedit pengguna lain sebelum di-source.

Setiap backup menjalankan pg_dump, mencoba restore ke database sementara yang terisolasi, menyimpan kunci authenticator, lalu mengunggah backup terenkripsi ke storage remote dan memeriksa repository.

Setelah uji manual berhasil, aktifkan jadwal:

```sh
sudo cp deploy/sehati-backup.service deploy/sehati-backup.timer deploy/sehati-health.service deploy/sehati-health.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sehati-backup.timer sehati-health.timer
sudo systemctl list-timers sehati-backup.timer sehati-health.timer
```

Backup berjalan sekitar 02:30 zona waktu server; health check setiap lima menit. Atur timezone server jika perlu. Kegagalan tercatat:

```sh
sudo journalctl -u sehati-backup.service -n 60
sudo journalctl -u sehati-health.service -n 60
sudo systemctl --failed
```

Timer health hanya mencatat hasil; notifikasi ke email/HP belum dikonfigurasi. Atur monitoring eksternal/provider ke /api/health dan penerima alarm untuk backup gagal, disk penuh, atau server mati. VPS tunggal tetap memiliki downtime saat server/provider bermasalah.

Backup lokal/remote tidak dipangkas otomatis. Tinjau ruang disk dan kebijakan retensi (misalnya 14 harian, 8 mingguan, 12 bulanan); lakukan penghapusan terkontrol hanya setelah memastikan backup remote dapat dipulihkan. Backup awal di laptop dan backup di disk VPS saja tidak cukup untuk kegagalan disk/VPS.

## 10. Pemulihan jika VPS rusak

Siapkan VPS baru, ambil kode aplikasi dan satu snapshot remote. Dengan konfigurasi repository/password yang sama:

```sh
restic snapshots
restic restore ID_SNAPSHOT --target /root/sehati-recovery
```

Cari pasangan database.dump, database.json, authenticator.key dari snapshot yang sama. Salin ke migration/ pada VPS baru. Jalankan configure.py dengan --key-file migration/authenticator.key, kemudian langkah restore, aktivasi admin, start dan pengujian seperti di atas. Jangan mencampur database dengan kunci dari instalasi lain.

Latih pemulihan pada lingkungan terpisah secara berkala. Dump/database dan kunci diperlukan bersama; untuk backup restic Anda juga memerlukan password repository.

## 11. Pembaruan dan perpindahan final

- Sebelum migrasi final, hentikan input pada versi lokal, ambil backup terbaru, dan gunakan satu database utama setelah beralih ke VPS.
- Sebelum pembaruan kode: backup terverifikasi, tinjau dependency/security update, lalu build ulang app.
- Image database dipatok ke PostgreSQL 18.6. Pembaruan patch dalam major 18 perlu ditinjau; jangan mengganti major database tanpa prosedur upgrade.
- Python dependencies dipatok di requirements.lock.txt; perbarui dan uji secara berkala. Image Caddy major 2/Python 3.12 mendapat patch saat pull/build --pull; catat digest image hasil deployment.
- Jangan menghapus volume saat deploy ulang. docker compose down -v akan menghapus database dan sertifikat.
- Brute-force login saat ini dibatasi secara global untuk seluruh staf; penyerang dapat mengganggu ketersediaan login dengan banyak percobaan salah. Pertimbangkan pembatasan admin lewat VPN/IP kantor atau rate limiting per sumber sesuai kebutuhan.
- Kehilangan HP dan semua recovery code memerlukan verifikasi identitas oleh pengelola. Tidak ada reset MFA lewat email atau password saja.

## Sumber resmi

- Docker Ubuntu: https://docs.docker.com/engine/install/ubuntu/
- Docker Compose secrets: https://docs.docker.com/compose/how-tos/use-secrets/
- PostgreSQL image dan storage versi 18: https://hub.docker.com/_/postgres
- Caddy HTTPS: https://caddyserver.com/docs/automatic-https
- FastAPI deployment: https://fastapi.tiangolo.com/deployment/concepts/
- Restic repository: https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html
- Restic restore: https://restic.readthedocs.io/en/stable/050_restore.html
