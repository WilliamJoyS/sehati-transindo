# API partner setelah VPS aktif

Satu API key hanya untuk satu pelanggan, seluruh periode data yang sudah committed, dan kolom yang dipilih admin. Key bersifat read-only, mempunyai masa berlaku, dan dapat dicabut. Data baru untuk pelanggan yang sama otomatis ikut tersedia.

Header wajib: X-API-Key. Kirim lewat HTTPS dari backend partner; jangan tanam di website publik atau query URL.

- GET /api/partner/v1/status
- GET /api/partner/v1/deliveries?limit=50&offset=0
- GET /api/partner/v1/deliveries/ID

Contoh dari terminal Linux, tanpa menyimpan key di command history:

```sh
read -r -s -p "API key: " SEHATI_API_KEY
printf '\n'
printf 'X-API-Key: %s\n' "$SEHATI_API_KEY" | curl --fail-with-body --header @- "https://DOMAIN-ANDA/api/partner/v1/deliveries?limit=50"
unset SEHATI_API_KEY
```

Ikuti meta.next_offset sampai null. Pada halaman berikutnya, sertakan data_version dari respons pertama. Jika mendapat HTTP 409, buang hasil parsial dan mulai lagi dari offset 0; data berubah selama pengambilan.

Default 50, maksimum 100 record per permintaan; 120 permintaan per menit per key. 401 berarti key salah/expired/dicabut; 403 berarti izin tidak sesuai; 429 berarti tunggu Retry-After.

Kolom uang dan catatan internal tidak dibuka oleh kontrak ini. Filter berdasarkan tab/bulan belum tersedia. Key lama pada snapshot lokal dinonaktifkan saat migrasi; buat key baru di admin VPS.

Ini adalah API Sehati. Spesifikasi/sertifikasi integrasi Bridgestone belum diterima; tidak ada koneksi blockchain atau API eksternal Bridgestone yang otomatis terbentuk dengan hosting.
