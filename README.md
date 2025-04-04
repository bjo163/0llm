---
title: "0llm - Platform AI Multi-Provider by ZENIX.ID"
emoji: "🤗"
colorFrom: "green"
colorTo: "gray"
sdk: docker
sdk_version: "1.0"
pinned: true
app_file: app.py
---

# 0llm

**0llm** adalah proyek open-source yang dikembangkan oleh **ZENIX.ID** untuk menghadirkan platform AI multi-provider yang mudah digunakan. Proyek ini menyediakan API serta antarmuka web untuk integrasi berbagai layanan AI terkemuka, dengan fitur unggulan seperti load balancing, flow control, dan kemudahan deployment melalui Docker dan Python.

---

## Tentang Proyek

Proyek **0llm** bertujuan untuk:
- **Integrasi Multi-Provider:** Menggabungkan berbagai API AI dalam satu platform sehingga pengguna dapat dengan mudah memilih solusi terbaik.
- **Kinerja Optimal:** Menyediakan load balancing dan kontrol aliran (flow control) untuk memastikan performa yang konsisten.
- **Antarmuka Web Interaktif:** Menyediakan GUI yang intuitif untuk memudahkan interaksi tanpa perlu mengotak-atik kode.
- **Kemudahan Deployment:** Mendukung instalasi melalui Docker maupun instalasi langsung menggunakan Python.

---

## Fitur Utama

- **API Lintas Penyedia:** Solusi integrasi untuk beberapa layanan AI.
- **Antarmuka Web:** GUI yang mendukung text dan image generation.
- **Deployment Fleksibel:** Panduan lengkap untuk instalasi via Docker dan Python.
- **Dokumentasi Komprehensif:** Informasi lengkap seputar instalasi, penggunaan API, dan konfigurasi sistem.

---

## Cara Memulai

### Instalasi dengan Docker

1. **Install Docker:** Pastikan Docker telah terinstal. [Download Docker](https://docs.docker.com/get-docker/).
2. **Setup Direktori:**
   ```bash
   mkdir -p ${PWD}/har_and_cookies ${PWD}/generated_images
   sudo chown -R 1200:1201 ${PWD}/har_and_cookies ${PWD}/generated_images
   ```
3. **Jalankan Container:**
   ```bash
   docker pull hlohaus789/g4f
   docker run -p 8080:8080 -p 7900:7900 \
     --shm-size="2g" \
     -v ${PWD}/har_and_cookies:/app/har_and_cookies \
     -v ${PWD}/generated_images:/app/generated_images \
     hlohaus789/g4f:latest
   ```
4. **Akses GUI:** Buka browser dan kunjungi [http://localhost:8080/chat/](http://localhost:8080/chat/).

---

### Instalasi dengan Python

1. **Install Python 3.10+** dari [python.org](https://www.python.org/).
2. **Clone Repo dan Instal Dependensi:**
   ```bash
   git clone https://github.com/bjo163/0llm.git
   cd 0llm
   pip install -r requirements.txt
   ```
3. **Jalankan Aplikasi:**
   ```bash
   python -m g4f.cli gui --port 8080 --debug
   ```

---

## Penggunaan API

### Text Generation

Contoh kode untuk menghasilkan teks:
```python
from g4f.client import Client

client = Client()
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
    web_search=False
)
print(response.choices[0].message.content)
```

### Image Generation

Contoh kode untuk menghasilkan gambar:
```python
from g4f.client import Client

client = Client()
response = client.images.generate(
    model="flux",
    prompt="a white siamese cat",
    response_format="url"
)
print(f"Generated image URL: {response.data[0].url}")
```

---

## Dokumentasi Lengkap

Untuk panduan lengkap instalasi, penggunaan API, dan konfigurasi, silakan lihat dokumentasi di repository ini atau hubungi tim **ZENIX.ID** untuk informasi lebih lanjut.

---

## Kontribusi

Kami menyambut kontribusi dari komunitas. Silakan buat pull request dengan perbaikan atau fitur baru setelah membaca panduan kontribusi. Setiap kontribusi sangat berarti untuk kemajuan proyek ini.

---

## Lisensi

Proyek ini dilisensikan di bawah **GNU GPL v3**. Silakan lihat file [LICENSE](LICENSE) untuk detail lisensi.

---

## Kontak

Untuk pertanyaan atau dukungan, hubungi tim **ZENIX.ID** melalui email atau platform komunitas yang tersedia.

© 2025 **ZENIX.ID**. All rights reserved.

---