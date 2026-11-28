# Монтаж видео — LearnToCode (worked example выпуска 1)

> Это **разбор первого выпуска**, а не инструкция: он показывает, какие решения
> были приняты и какие числа получились.  Порядок действий для нового выпуска —
> [`../README.md`](../README.md) и [`../docs/PIPELINE.md`](../docs/PIPELINE.md).
> Пути вида `scripts/…`, `docs/…` здесь указаны от корня рабочей папки эпизода
> (того, что создаёт `make dirs init`), а не от этой папки.


Рабочая папка проекта монтажа. Первый выполненный эпизод:

> **Теоретическая часть — 01. Процесс обработки данных. Жизненный цикл данных.
> Понятие ETL-процесса** (`F6fCcoNNdEE`, 1:49:37, канал LearnToCode)

Готовый файл: `render/final.mp4` (копия с именем — в `/media/timoti/Storage/Work/`).

## Что это за папка

```
vidproj/
├── source/     исходник с YouTube: mp4, субтитры, info.json, превью
├── work/       анализ: транскрипт, тишина, громкость, движение экрана, миниатюры, слайды
├── edit/       решения: карта тем, план склеек, гейты видимости панели, статистика, стиль
├── render/     выходные файлы + панель-пластина + сгенерированный filter graph
├── scripts/    конвейер (python + ffmpeg), всё воспроизводимо по команде
├── docs/       промпт, стиль, конвейер, окружение, решения, ловушки, чек-лист
└── logs/       логи фоновых прогонов (абсолютные пути, см. GOTCHAS 12)
```

Идея конвейера: **сырьё → измеренные факты → план → рендер**. Ни один шаг не
догадывается о содержимом — он читает результат предыдущего. Монтаж нового
эпизода = новый `edit/topics.json` плюс те же команды.

## Быстрый старт для нового видео

Полный порядок, все параметры и что проверять на каждом шаге —
**`docs/PIPELINE.md`**; короткая версия для галочек — **`docs/CHECKLIST.md`**.

```bash
V=/media/timoti/Storage/Work/vidproj
ID=<youtube id>
mkdir -p $V/logs

# 1. сырьё: видео + русские субтитры + метаданные
$V/.venv/bin/yt-dlp -4 -f "bv[ext=mp4][height=1080]+ba[ext=m4a]/b" \
    --merge-output-format mp4 --write-info-json --write-subs \
    --write-auto-subs --sub-langs "ru,*.ru" \
    -o "$V/source/%(id)s.%(ext)s" "https://www.youtube.com/watch?v=$ID"

# 2. анализ (порядок не критичен, кроме thumbs2fps перед panel_gates)
$V/.venv/bin/python $V/scripts/parse_vtt.py     $V/source/$ID.ru.vtt $V/work/speech.json
$V/.venv/bin/python $V/scripts/analyze_audio.py $V/source/$ID.mp4 $V/work
$V/.venv/bin/python $V/scripts/detect_hum.py    $V/source/$ID.mp4 $V/work/hum.json
$V/.venv/bin/python $V/scripts/analyze_motion.py $V/source/$ID.mp4 $V/work
$V/.venv/bin/python $V/scripts/extract_slides.py $V/source/$ID.mp4 $V/work/slides.json
ffmpeg -nostats -v info -i $V/source/$ID.mp4 -vn \
    -af silencedetect=noise=-35dB:d=0.17 -f null - 2> $V/work/silence_raw.txt

# 3. темы: edit/topics.json (video_id, channel, lesson, title, topics[{t,title,short}])

# 4. план склеек -> гейты панели -> проверка дашборда -> звук
$V/.venv/bin/python $V/scripts/build_plan.py
$V/.venv/bin/python $V/scripts/panel_gates.py
$V/.venv/bin/python $V/scripts/probe_dashboard.py            # PASS до рендера
$V/.venv/bin/python $V/scripts/cut_audio.py

# 5. рендер и проверка результата
$V/.venv/bin/python $V/scripts/render.py --test 120          # короткий тест
$V/.venv/bin/python $V/scripts/render.py                     # контент + заставки + склейка
$V/.venv/bin/python $V/scripts/verify_output.py $V/render/final.mp4
```

`verify_output.py` сверяет в том числе **число кадров** с планом: длительность
контейнера — это самая длинная дорожка, поэтому видеодорожку на 52 кадра короче
аудио она не выдаёт, а на слух это расходящаяся рассинхронизация (GOTCHAS 25).

## Документация

| Файл | О чём |
|---|---|
| `docs/PROMPT_TEMPLATE.md` | оформленный промпт заказчика: копировать в новую сессию |
| `docs/STYLE_GUIDE.md` | вид: палитра, пластина дашборда, шрифты, геометрия, заставки, легимость |
| `docs/PIPELINE.md` | конвейер по шагам: каждая команда, что читает/пишет каждый скрипт, что проверять |
| `docs/ENVIRONMENT.md` | железо, версии софта, карта GPU, память, чем проверяется картинка |
| `docs/DECISIONS.md` | почему конвейер устроен так (14 решений) и что сломается при упрощении |
| `docs/EDIT_DECISIONS.md` | что именно вырезано в первом эпизоде и почему |
| `docs/GOTCHAS.md` | 27 ловушек, в которые уже наступили (OOM, `setpts`, `between(t,…)`, альфа PNG, OCR, 429 от YouTube) |
| `docs/CHECKLIST.md` | чек-лист нового эпизода |

## Ключевые числа первого эпизода

| | |
|---|---|
| Исходник | 6577.03 с (1:49:37), 1920×1080, 25 fps, русские автосубтитры |
| Слово в транскрипте | 12 478 (первое в 45.26 с — начало с беззвучной заставки) |
| Найдено пауз | 932 (758 с, 11.5 % длины) |
| Сделано склеек | 413, вырезано 338.4 с (5.15 %) |
| Отказано намеренно | 17 склеек (шёл рисунок) + 9 (хвост слова на стыке) |
| Тело редакции | 6238.56 с ровно (155 964 кадра, 25 fps) |
| Финал с заставками | 6255.56 с = 156 389 кадров = 7.0 с заставка + 6238.56 + 10.0 с титры |
| Тем на дашборде | 22, панель скрыта 340.4 с (5.5 %) — там браузер лектора |
| Пластина панели | 320×896 px, скругление 22 px, альфа 0.66, контраст текста 5.05:1 (4.89:1 на движущемся фоне) |
| Шрифт панели | Manrope SemiBold/Medium (OFL, в `fonts/`); галочка — DejaVu Sans Bold, в Manrope нет U+2713 |
| Проверки | `audit_titles.py` PASS (все 22 названия звучат в своих окнах); `probe_dashboard.py` PASS (22/22 подписи OCR); `verify_output.py` PASS — 8 разделов, все числа в `render/verified.json` |
| Кодирование | VAAPI H.264 (`renderD128`, Sapphire RX 9070), QP 20, ~21 мин на 6238 с |

## Про стиль

Всё оформление — палитра, геометрия и альфа пластины, шрифты, обводка текста,
гейты видимости, тексты заставок, переходы, аудиотракт, параметры кодирования и
параметры «лёгкой» копии — лежит в **`edit/style.json`**. `render.py`,
`make_plate.py` и `panel_gates.py` читают его; любой ключ переопределяется для
одного эпизода без правки кода. Именно этот файл отвечает за единый вид серии:
новый эпизод обязан выглядеть как этот, если в нём поменялись только темы.
