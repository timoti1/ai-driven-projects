# ENVIRONMENT — условия, в которых сделан монтаж

Снято 2026-11-27 на хосте `thinkpad`-класса, Linux Mint 22.3.

## Железо

| | |
|---|---|
| CPU | AMD Ryzen 7 5800 8-Core, 16 потоков, AVX2 (без AVX-512) |
| RAM | 62 ГБ |
| GPU | 2 × AMD RX 9070 (gfx1201), по 17 ГБ VRAM каждая |
| Диск под проект | `/media/timoti/Storage` (nvme0n1p1, 916 ГБ) |

### Карта GPU — это важно для рендера

| ROCm/HIP | PCI | card | render-узел | Роль в llama-swap |
|---|---|---|---|---|
| GPU[0] = HIP0/ROCm0 | `0000:06:00.0` | card1 | **`/dev/dri/renderD128`** | **Sapphire** — для кодирования монтажа |
| GPU[1] = HIP1/ROCm1 | `0000:0B:00.0` | card0 | `/dev/dri/renderD129` | Gigabyte — занята моделями |

Проверяется так:

```bash
rocm-smi --showbusid                 # GPU[i] -> PCI
ls -l /dev/dri/by-path/              # PCI -> card/renderD
rocm-smi --showmeminfo vram          # кто занят
rocm-smi --showpids                  # какой процесс держит VRAM
.venv/bin/python scripts/gpu_free.py # то же самое одной строкой: какой render-узел свободен
```

Проверено на этом железе: `h264_vaapi` на свободной карте выдаёт 6238 с
1080p25 за ~21 мин (≈5× реального времени, RSS ffmpeg ~345 МБ); `libx264
-preset veryfast` на 16 потоках — ~50 мин той же длины. Забитая моделями карта
может отвергать `vp9_vaapi` с EINVAL, тогда как `h264_vaapi` продолжает
работать (GOTCHAS 8), поэтому дефолтный кодек в `style.json` — h264.

Обе карты сообщают `current_link_width=16`, поэтому «Sapphire в медленном
x2-слоте» по sysfs не опознаётся — только по соответствию HIP0 ↔ PCI.

## Память: главное ограничение

Постоянно работает `llama-server` с ~54 ГБ RSS, свободной системной памяти
обычно 7–11 ГБ. Это не «мелочь»: первый вариант рендера был убит OOM-киллером
на 12.7 ГБ RSS и попутно унёс `strata-host`. Любой новый ffmpeg-граф на этом
хосте обязан быть **с плоской памятью**; проверять так:

```bash
ps -o rss=,pcpu= -C ffmpeg --no-headers | awk '{s+=$1}END{printf "ffmpeg rss=%.0f MB\n",s/1024}'
```

## Софт

| Инструмент | Версия | Как установлен |
|---|---|---|
| yt-dlp | 2026.11.23 | `$V/.venv/bin/pip install yt-dlp` |
| ffmpeg / ffprobe | 6.1.1-3ubuntu5 | системный, собран с VAAPI |
| faster-whisper | 1.2.1 | venv (установлен, в этом эпизоде не понадобился) |
| numpy | 2.5.5 | venv |
| Pillow | 13.0.0 | venv: пластина дашборда (`make_plate.py`) и замеры ширины текста в `render.py`/`probe_dashboard.py` |
| tesseract | 5.3.4 + rus | `apt-get install tesseract-ocr tesseract-ocr-rus` |
| ImageMagick | системный (`convert`) | не понадобился |
| Mesa / libva | Mesa 25.2.8 radeonsi, libva 2.12, VA-API 1.20 | система |
| ядро | 7.0.0-38-generic | — |
| Node.js | 22.23.1 (из pi) | нужен `yt-dlp` для решения JS-challenge YouTube |

Итого установка venv одной строкой:

```bash
.venv/bin/pip install yt-dlp faster-whisper pillow numpy pymorphy3 fonttools
```

scipy в конвейере не нужен (дилатация маски в `probe_dashboard.py` сделана
`PIL.ImageFilter.MaxFilter`), и он удалён из venv, чтобы список зависимостей
совпадал с документацией.

Проверка, что VAAPI-кодирование доступно:

```bash
vainfo | grep -E "Driver|EncSlice" | head
ffmpeg -hide_banner -encoders | grep vaapi
```

Поддерживается `h264_vaapi` (VAProfileH264High + VAEntrypointEncSlice) — им и
кодируется.

## Доступные шрифты с кириллицей

В системе: DejaVu Sans / DejaVu Sans Bold (`/usr/share/fonts/truetype/dejavu/`),
Noto Sans, Liberation. В проекте: **Manrope** (`fonts/Manrope-*.ttf`, SIL Open
Font License 1.1 — лежит в проекте, в систему ставить не нужно). Панель и
карточки пишутся Manrope SemiBold/Medium; DejaVu Sans Bold остался только для
gалочки ✓, потому что в Manrope нет U+2713 (GOTCHAS 28).

Покрытие шрифта проверяется численно, а не «на глаз":

```bash
.venv/bin/python -c "from fontTools.ttLib import TTFont; \
  print(sorted(hex(c) for c in TTFont('fonts/Manrope-Semibold.ttf').getBestCmap() \
  if c in (0x2713,0x0451,0x2013,0x201C,0x00B7)))"
```

(`fc-query --format='%{charset}'` покрытие по конкретным кодовым точкам не
показывает — молча выдаёт пусто.)

## Чего на хосте нет

`sox`, `exiftool`, `radeontop`, `deno`. Монтаж на них не зависит. `whisper`
(системный CLI) отсутствует — есть `faster-whisper` в venv.

## Чем проверяется картинка

Монтаж делает агент, который **не видит изображения**: «посмотреть кадр»
невозможно в принципе. Поэтому каждая важная визуальная свойства превращена в
число и проверяется скриптом:

| что | чем |
|---|---|
| скруглённые углы пластины | доля нетронутых пикселей в углах и в угловых квадратах |
| полупрозрачность | эффективная альфа по чистому пятну пластины на однотонном фоне |
| читаемость подписей | OCR строки дашборда (`tesseract`, построчно) |
| контраст | яркость глифов против подушечки под ними |
| прогресс | ширина акцентной линии по пикселям в ранний и поздний кадры |
| панель не мешает | доля «чернил» в прямоугольнике панели (`panel_gates.py`) |
| склейки не жгут слова | кросс-корреляция звука с `audio_cut.wav`, уровни на стыках |

Инструменты: `scripts/probe_dashboard.py` (до рендера), `scripts/verify_output.py`
(после). Если у свойства нет проверки — значит оно может сломаться молча.

## Сетевые тонкости

- YouTube для старых yt-dlp: `HTTP 400 Bad Request` / «Precondition check failed».
- На загрузке субтитров периодически прилетает `429 Too Many Requests`;
  субтитры и видео лучше качать раздельно и с `--retries 30`.
- Все обращения к YouTube в этом проекте шли через `-4` (IPv6-проблемы нет,
  IPv4 стабильнее).
