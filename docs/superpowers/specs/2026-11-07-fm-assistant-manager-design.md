# FM Assistant Manager — Design

Tanggal: 2026-11-07
Visual: https://claude.ai/artifact/K6iaS9DMo6eM6tzvMJwTUZ (arsitektur, alur approval, 3 mockup output)

## 1. Intent

Pemilik suka main Football Manager 27 tapi waktunya tidak sebanyak dulu. FM punya banyak aspek manual
yang menyita waktu: cari staf, scouting, menimbang semuanya terhadap budget, training, kontrak, inbox.
Pemilik mau tetap pegang **taktik dan keputusan krusial**; sisanya agent yang menganalisis dan
memberi **rekomendasi**, lalu **mengeksekusi di game setelah di-approve**.

Semua dipakai **lewat CLI dari Claude Code** (ngobrol dengan Claude, Claude memanggil tool).

Tujuan kedua: **proyek portofolio untuk posisi AI/agent engineer**. Yang harus menonjol: desain tool
untuk agent, human-in-the-loop (rekomendasi → approval → aksi), pengaman (backup, audit log),
dan integrasi ke sistem tertutup tanpa API (mod IL2CPP di Apple Silicon).

## 2. Goals

1. Baca data game yang sedang jalan (skuad, staf, kandidat search, scouting, kontrak, keuangan, training,
   jadwal, inbox) dan sajikan ke agent sebagai JSON.
2. Rekomendasi berbasis data + budget untuk semua fitur di §6, selalu dengan alasan dan alternatif.
3. Aksi di game hanya setelah approval eksplisit pemilik, dengan backup save sebelum aksi dan verifikasi sesudahnya.
4. Bisa dipakai agent lain lewat MCP (positioning: "AI assistant manager for FM, works with any agent").
5. Siap dipamerkan: README bergaya halaman produk, demo video 60–90 detik, write-up teknis.

## 3. Non-goals

- Tidak mengatur taktik untuk pemilik (agent boleh menganalisis kecocokan skuad dengan taktik, tidak mengubah taktik).
- Tidak menyimpan game, menekan Continue, atau memainkan/mensimulasikan match. Itu selalu tangan pemilik.
- Tidak mengedit nilai database (bukan editor/cheat seperti FMRTE/FMLE). Aksi hanya yang bisa dilakukan manusia lewat UI normal.
- Tidak mendukung Windows / Intel Mac / Epic di versi awal.
- Tidak ada web dashboard atau aplikasi GUI terpisah.

## 4. Anti-goals (gagal walau teknisnya jalan)

- Aksi apa pun terjadi tanpa approval.
- Save rusak atau karier hilang tanpa bisa dipulihkan.
- Rekomendasi tanpa alasan yang bisa dicek ("percaya saja").
- Menyentuh/memodifikasi file instalasi game asli dari Steam, atau mendistribusikan file game.

## 5. Constraints (fakta yang sudah dicek di mesin pemilik)

- macOS 26.1, **Apple Silicon (arm64)**, SIP **enabled** (harus tetap enabled).
- FM27 Steam, versi `27.0.0+2493426` (early access). **Rilis penuh 10 Nov 2026** → patch akan sering mengubah binary.
- App: `~/Library/Application Support/Steam/steamapps/common/Football Manager 27/fm.app`
  - Unity `6000.3.18f1-custom`, IL2CPP: `Contents/Frameworks/GameAssembly.dylib` (universal), engine SI native di
    `Contents/PlugIns/game_plugin.bundle`.
  - `global-metadata.dat` tidak terenkripsi (magic `AF1BB1FA`, versi 39).
  - Hardened runtime, ditandatangani SEGA. Entitlements: `allow-dyld-environment-variables`,
    `disable-library-validation` — **tanpa `allow-jit`**, jadi CoreCLR butuh **salinan "bayangan" app yang di-re-sign ad-hoc**
    (pola `DadMych/fm26-player-export-macos`). App asli tidak disentuh.
  - Assembly C# terlihat: `FM.Game`, `FM.GamePlugin.Bindings`, `FM.GameSimulation`, dst. Binding yang relevan
    terlihat di metadata: `TrainingCalendarBinding`, `CustomTrainingScheduleBinding`, `SearchValueBinding`,
    `ProcessPersonBinding`, `PlayerIndexBinding`.
- User data: `~/Library/Application Support/Sports Interactive/Football Manager 27/`
  (`games/*.fm`, `cloud/` berisi slot `views`, `schedules`, `staff shortlists`, `tactics`, dll.).
- Save karier aktif: "Nael Anggara - Java United" (Indonesia). Parser `cli-anything-fm27` (Apache-2.0) **sudah terbukti**
  membaca save Mac ini tanpa modifikasi (manager, klub, tanggal in-game, skuad, 1.212 part).
- Export view bawaan FM tidak bisa diandalkan (rusak/dihapus di FM26, FM27 belum jelas) dan pemilik menolak langkah manual.

## 6. Fitur

Semua fitur: baca → rekomendasi + alasan + alternatif → (opsional) aksi setelah approval.

| # | Fitur | Data yang dibutuhkan | Aksi setelah approval |
|---|---|---|---|
| F1 | Session briefing (`/fm-briefing`) | inbox/news sejak sesi terakhir, status skuad | eksekusi rekomendasi terpilih (A1…An) |
| F2 | Squad health | moral, kebugaran, cedera, kontrak, menit main | — (memicu fitur lain) |
| F3 | Role fit vs taktik pemilik | atribut pemain, taktik aktif (posisi/role) | — |
| F4 | Lineup & rotasi | kondisi, form, jadwal | set XI (fase akhir, opsional) |
| F5 | Contract advisor | kontrak, gaji, struktur gaji, nilai | tawarkan perpanjangan / pasang status jual |
| F6 | Transfer & scouting ranker berbasis budget | hasil player search, laporan scout, budget transfer/gaji | tambah ke shortlist, minta laporan scout, ajukan tawaran |
| F7 | Youth & loan planner | pemain muda, potensi (versi scout), menit main | pasang status pinjam |
| F8 | Opponent prep | laporan lawan, jadwal | — |
| F9 | Tren musim | snapshot antar sesi (disimpan lokal) | — |
| F10 | **Training schedule** | jadwal training, kondisi, jadwal match | terapkan jadwal mingguan + jadwal individu |
| F11 | **Staff search** berbasis budget | staff search, atribut staf, budget gaji, slot staf kosong | tawarkan kontrak staf |

Prioritas pemilik: **F11, F6, budget-awareness, F10**, lalu F1–F3.
Atribut tersembunyi hanya sejauh yang FM tampilkan ke manager (scout/staff report); agent tidak "mengintip" nilai tersembunyi.

## 7. Arsitektur (keputusan)

```
Kamu ─ Claude Code (skill fm-manager) ─ CLI `fm` / MCP server ─ fm core (Python) ─ WebSocket localhost ─ Plugin FM27 (BepInEx, C#)
                                                                    └─ save parser (fork cli-anything-fm27) ─ file .fm (game tertutup)
```

1. **Plugin FM27 (C#, BepInEx 6 IL2CPP, arm64).** Berjalan di dalam game. Membaca data lewat framework binding SI
   (referensi: `redznn/fm-dof-mcp`, MIT, FM26 arm64 — `PersonReference`, `PropertyIdentifierSet`, `SI.Bindable.Bindings`).
   Membuka WebSocket di `127.0.0.1` saja, request dieksekusi di main thread (antrian). Menyediakan:
   - endpoint baca (read-only, tanpa batas approval);
   - endpoint aksi, yang **menolak** dijalankan tanpa `plan_id` yang valid dari core (lihat §8).
2. **fm core (Python library).** Satu library, dipakai CLI dan MCP. Isi: klien WebSocket, normalisasi JSON, logika
   *data* (filter budget, skor role-fit deterministik), pembuat plan aksi, backup, audit log, save parser.
   Catatan: di diagram tertulis "Core service"; keputusan: **library, bukan daemon** — plugin sudah jadi servernya.
3. **CLI `fm` (Python, click).** Pembungkus tipis core. Semua perintah punya `--json`. Grup: `game`, `squad`, `staff`,
   `players`, `scout`, `club`, `training`, `fixtures`, `inbox`, `plan`, `apply`, `save`, `log`.
4. **MCP server.** Pembungkus tipis core yang sama (tool baca + tool `propose`/`apply`).
5. **Skill Claude Code `fm-manager` + slash command** (`/fm-briefing`, `/fm-staff-search`, `/fm-training`, …).
   Skill berisi *cara menimbang*: bobot role, aturan budget, format jawaban (tabel kandidat, alasan, alternatif,
   kotak approval). Claude yang menimbang; CLI hanya menyediakan data dan menjalankan aksi.
6. **Loader.** Salinan bayangan `fm.app` + Unity Doorstop via `DYLD_INSERT_LIBRARIES`, dijalankan lewat Steam launch
   option. Pilihan loader (sptndc FM27 build vs. port DadMych) diputuskan di Fase 0 — **utamakan yang kodenya bisa dibaca**;
   binary komunitas yang tidak ditandatangani wajib direview sebelum dipakai.

## 8. Approval & pengaman (keputusan)

Dua lapis, supaya approval tidak hanya bergantung pada "kepatuhan" model:

1. **Di percakapan:** agent menampilkan rekomendasi + kotak approval (lihat mockup). Aksi dikemas sebagai plan:
   `fm plan create …` → file JSON di `~/.fm-assistant/plans/<id>.json` (isi: aksi, parameter, alasan, ringkasan).
2. **Gerbang keras di harness:** `fm apply <plan-id>` dan tool MCP `apply` dikonfigurasi sebagai **"ask"** di
   permission Claude Code (dan butuh konfirmasi di klien MCP). Semua perintah baca di-allow. Jadi walau model mencoba
   apply tanpa bertanya, Claude Code tetap memunculkan prompt izin ke pemilik.

**Threat model (keputusan builder-check):** gerbang melindungi dari *kesalahan* model dan apply yang tidak sengaja,
bukan dari model yang sengaja membobol. Tambahan murah yang tetap dipasang: deny rule Claude Code untuk akses langsung
ke port WebSocket plugin (mis. `websocat`, `nc`, skrip ad-hoc), dan plugin hanya menerima aksi dengan token per-plan
yang dibuat `fm apply` saat itu juga (bukan file plan biasa). Threat model yang sama berlaku untuk pengguna komunitas
(tool lokal di mesin masing-masing); port hanya `127.0.0.1`.

**Daftar aksi tertutup (keputusan builder-check):** plugin punya registry aksi eksplisit; agent hanya bisa mengusulkan aksi
yang ada di registry. Rekomendasi di luar registry ditampilkan sebagai "lakukan manual: langkah UI …". Registry awal:
`staff.offer`, `shortlist.add`, `scout.request_report`, `transfer.bid`, `transfer.reject_bid`, `transfer.set_asking_price`,
`contract.offer_renewal`, `player.set_transfer_status`, `player.set_loan_status`, `training.apply_week`, `training.set_individual`.
Fase 0 menentukan mana yang benar-benar bisa dijangkau.

Saat `apply`:
1. Backup save aktif (copy + SHA-256, folder di luar `games/` agar FM tidak memindainya) — wajib, gagal backup = batal.
2. Kirim aksi ke plugin; plugin mengeksekusi lewat jalur yang sama dengan UI normal.
3. Verifikasi: baca ulang state terkait dan bandingkan dengan plan.
4. Tulis audit log JSONL (`~/.fm-assistant/log.jsonl`): waktu, plan, alasan, hasil, hash backup.

**Negosiasi (keputusan pemilik):** seperti FM sungguhan. Satu approval = satu tawaran yang dikirim. Setiap balasan
(counter-offer, penolakan, permintaan klausul) dilaporkan ke pemilik beserta rekomendasi respons, dan respons itu
butuh approval baru. Agent tidak bernegosiasi sendiri dalam batas apa pun. "Terverifikasi" untuk tawaran berarti
tawaran tercatat di game dengan status menunggu jawaban; balasan muncul di briefing/inbox berikutnya.

Batch: satu plan boleh berisi banyak aksi (mis. 21 sesi training + 4 jadwal individu, atau A1–A4 briefing) → satu approval, satu backup.
Plugin tidak pernah mengekspos save/continue/match.

Catatan: backup save hanya menyelamatkan state per file save terakhir; aksi yang dilakukan setelah save terakhir hanya
bisa "di-rollback" dengan load save. Pemilik perlu tahu ini (ditulis di README dan disebut di kotak approval pertama).

**Mode game tertutup (keputusan builder-check):** hampir semua fitur butuh game berjalan. Save parser hanya untuk:
info save dasar (manager, klub, tanggal, skuad), verifikasi backup, dan snapshot ringan F9. Tidak ada reverse-engineering
format save tambahan di luar itu.

## 9. Fase

**Fase 0 — Spike kelayakan (throwaway, wajib lulus sebelum Fase 1).** Kriteria lulus, semua di Mac pemilik:
1. BepInEx IL2CPP termuat di FM27 lewat salinan bayangan; app asli & SIP tidak disentuh.
2. Plugin membaca skuad Java United (nama + 3 atribut + kontrak) dan mengirimnya via WebSocket ke skrip Python.
3. Plugin membaca hasil staff search (≥ 1 halaman kandidat + gaji yang diminta).
4. Satu aksi kecil berhasil dan terverifikasi: mengubah satu sesi training.
Kalau 1 gagal → evaluasi loader lain; kalau 4 gagal → aksi turun ke "rekomendasi + instruksi langkah UI" dan dokumen ini direvisi.
Jadwalkan setelah rilis penuh 10 Nov, atau ulangi tes sesudahnya.

**Fase 1 — Baca + rekomendasi.** Plugin endpoint baca, core, CLI `fm`, skill. Urutan: F11, F6, F10, F1, F2, F3, lalu sisanya.

**Fase 2 — Aksi setelah approval.** Plan/apply, backup, verifikasi, log. Urutan: tawaran staf (F11) → shortlist & minta
laporan scout (F6) → terapkan training (F10) → kontrak (F5) → sisanya.

**Fase 3 — Kemasan portofolio.** MCP server, plugin Claude Code (marketplace), README produk + diagram, demo video,
write-up (mod IL2CPP di Apple Silicon; desain agent human-in-the-loop), rilis ke komunitas (sortitoutsi, FM Scout, r/footballmanagergames).

## 9b. Rilis komunitas & maintenance (keputusan pemilik)

Tool dirilis ke komunitas dan dirawat mengikuti update Steam FM27 (tidak mengunci versi). Konsekuensi untuk desain:
- **Installer satu perintah** yang membuat salinan bayangan, memasang loader + plugin, dan mengatur launch option Steam;
  ada perintah uninstall yang bersih. Salinan bayangan dibangun ulang otomatis setelah update Steam.
- **Lookup binding berdasarkan nama** (class/method/property via metadata IL2CPP), bukan offset/RVA hard-coded.
- **Deteksi versi:** plugin & CLI melaporkan build game; build yang belum diuji → mode baca saja + pesan jelas, aksi dimatikan
  sampai build itu ditandai kompatibel.
- **Self-test** (`fm doctor`): cek loader, koneksi plugin, versi, dan satu panggilan baca per fitur; hasilnya bisa
  ditempel pengguna di issue GitHub.
- Kompatibilitas tetap: Apple Silicon + Steam saja (lihat Non-goals).

**Tempo (keputusan pemilik):** tidak ada deadline; kualitas di atas kecepatan. Urutan fase tetap seperti di atas.

## 10. Repo & bahasa

- Repo baru di `/Users/labs/fm-cli` (monorepo): `plugin/` (C#), `fm/` (Python: core, CLI, MCP), `skills/`, `docs/`.
- Fork/vendor parser dari `mattboostkit/cli-anything-fm27` dengan atribusi Apache-2.0 (`LICENSE` + `NOTICE`).
- Python ≥ 3.10, dikelola `uv`. .NET runtime arm64 untuk BepInEx (belum terpasang di mesin).
- Kode, CLI, README: bahasa Inggris (portofolio). Jawaban agent ke pemilik: bahasa Indonesia.
- Proyek tidak resmi, tanpa logo/branding SI/SEGA/FM, tanpa file game di repo.

## 11. Diserahkan ke builder

- Protokol WebSocket persis (format pesan, versioning), struktur paket Python, nama perintah final (mockup hanya usulan).
- Cara menemukan class/method binding per fitur (dump Cpp2IL/Il2CppInterop, referensi fm-dof-mcp).
- Skema JSON per entitas, strategi cache/snapshot untuk F9, batching untuk menghindari batas ~20 orang per call.
- Bobot role-fit awal (boleh mulai dari heuristik komunitas, harus bisa diubah pemilik).
- Strategi tes: unit test core dengan fixture JSON; tes plugin manual di game; satu skrip smoke test end-to-end.
- Cara mendeteksi versi game berubah dan memberi pesan jelas ("plugin belum mendukung build X") alih-alih crash.
