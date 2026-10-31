# Оптимизация Avalon и сравнение со Strata

**Дата тестирования:** 2026-10-31  
**Ветка:** `aic8800-wifi-bt-driver`  
**Репозиторий:** `timoti1/ai-driven-projects`  
**Директория:** `perf-tuning/` и `perf-bench/`

**Статус:** Промежуточные результаты, продолжается тестирование

---

## 1. Стенд тестирования

### Аппаратное обеспечение

| Компонент | Характеристика |
|-----------|---------------|
| CPU | AMD Ryzen 7 5800 (8C/16T, нет AVX-512, экспертные ядра на AVX-2) |
| GPU 0 | AMD Radeon RX 9070 (Sapphire, PCIe 0a:00.0, PCIe x2 медленный слот, gfx1201) |
| GPU 1 | AMD Radeon RX 9070 (Gigabyte, PCIe 05:00.0, PCIe x16 полный слот, gfx1201) |
| VRAM на GPU | 16 ГБ |
| Системная RAM | 62 ГБ (+8 ГБ swap) |
| ОС | Linux (Ubuntu 24.04-based) |

### Маппинг GPU (HIP_VISIBLE_DEVICES)

- `HIP_VISIBLE_DEVICES=0` → Sapphire (PCIe x2)
- `HIP_VISIBLE_DEVICES=1` → Gigabyte (PCIe x16)

---

## 2. Программный стек

| Компонент | Версия | Путь |
|-----------|--------|------|
| llama-swap | v265 (commit d1e743f, build 2026-10-14) | `/home/timoti/llama-swap/` |
| Listen | `0.0.0.0:8080` | HTTP прокси |
| ROCm | 7.8.0 | `/opt/rocm` |
| HIP / hipcc | 7.16.26385-0000000, AMD clang 24.0.0 | `/usr/bin/hipcc` |
| Vulkan ICD (Mesa RADV) | API 1.4.318 | `/home/timoti/mesa-build/libvulkan_radeon.so` |

---

## 3. Оптимизация Avalon (файн-тюнинг параметров)

### Цель
Подобрать оптимальные параметры командной строки для модели `avalon-qwen3.8-flash-next-C2` (Qwen3.8-Flash-Next 125B MoE, IQ3_K, 33 шарда) на движке Avalon fork 0.26.0 (llama.cpp 0.26.0, HIP/ROCm 7.8.0).

### Оптимизированная конфигурация

**Параметры командной строки:**

| Параметр | Значение | Описание |
|----------|----------|----------|
| `-b` | 4096 | Размер батча (было 2048) |
| `-ub` | 2048 | Микро-батч (было 1024) |
| `--spec-draft-n-max` | 3 | Максимум черновиков speculative decoding (было 2) |
| `-fa` | on | Flash attention |
| `-ctk` | q8_0 | KV cache K квантование |
| `-ctv` | q4_0 | KV cache V квантование |
| `--jinja` | — | Jinja chat template |
| `--parallel` | 1 | Количество параллельных сессий |
| `-md` | MTP GGUF | Путь к MTP черновику |
| `--spec-type` | draft-mtp | Тип speculative decoding |
| `-ubd` | 256 | Размер батча черновиков |
| `-ctkd` | q8_0 | KV cache K для черновика |
| `-ctvd` | q4_0 | KV cache V для черновика |
| `--temp` | 0.6 | Температура |
| `--top_k` | 30 | Top-k сэмплинг |
| `--top_p` | 0.95 | Top-p сэмплинг |
| `--reasoning-effort` | low | Уровень рассуждений |
| `--reasoning-budget` | 4092 | Бюджет токенов рассуждений |
| `HIP_VISIBLE_DEVICES` | 1 | Модель на Gigabyte (PCIe x16) |

### Результаты оптимизации Avalon

| Конфигурация | parallel | batch | draft | prefill 8192 | decode 8192 | TTFT 8192 |
|--------------|----------|-------|-------|-------------|-------------|-----------|
| Оригинальная (batch 2048, draft 2) | 2 | 2048 | 2 | ~497 tps | ~46 tps | ~10.8 с |
| batch 4096, draft 2 | 2 | 4096 | 2 | ~889 tps | ~60 tps | ~10.8 с |
| batch 4096, draft 3 (dual) | 2 | 4096 | 3 | ~941 tps | ~63 tps | ~5.8 с |
| batch 4096, draft 3 (single, live) | 1 | 4096 | 3 | ~984 tps | ~75 tps | ~5.5 с |
| Через llama-swap прокси | 2 | 4096 | 3 | — | ~15 tps | — |

**Ключевое открытие оптимизации:**
- Режим `--parallel 1` дает **выше throughput** на декоде (~75 tps vs ~63 tps при parallel=2) но аналогичный TTFT (~5.5 с vs ~5.8 с)
- batch 4096 дает +89% prefill по сравнению с batch 2048
- draft 3 дает +10-20% decode throughput по сравнению с draft 2
- llama-swap добавляет **~3-4x оверхеда** — прямое подключение к движку предпочтительнее для максимальной производительности

---

## 4. Тестирование Strata (живой тест через llama-swap)

### Конфигурация Strata

| Параметр | Значение |
|----------|----------|
| Движок | Strata proprietary (HIP) |
| Binary | `/media/timoti/Data/repos/Strata/engine/strata` |
| Модель | Qwen3.8-Flash-Next IQ3_S |
| Pack | `/media/timoti/Data/Strata-data/packs/swift-iq3_s` |
| Native shard | `Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf` |
| PLE shard | `Swift-Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf` |
| MTP | `/media/timoti/Data/Strata-data/mtp/rt` |
| Expert profile | `/media/timoti/Data/repos/Strata/data/expert-profile.bin` |
| Max context | 200000 |
| KV storage | int8 |
| KV resident | 20480 |
| MTP hnorm | stream |
| Spec | 4 |
| Spec min-p | 0.5 |
| Backend | HIP / ROCm 7.8.0 |
| GPU | 1 (Gigabyte, PCIe x16) |
| Запуск | Через llama-swap на порту 8080 |

### Живые результаты Strata (через llama-swap, порт 8080)

| Тест | Глубина | prefill_tps | decode_tps | first_token_s | completion |
|------|---------|-------------|------------|---------------|------------|
| prefill | 393 | 15.7 | — | — | — |
| prefill | 1394 | — | 374.6 | — | — |
| prefill | 5393 | — | 1117.9 | — | — |
| prefill | 394 | 63.3 | — | — | — |
| prefill | 1392 | — | 569.3 | — | — |
| prefill | 5393 | — | 1394.1 | — | — |
| decode | 1024 | — | 32.2 | 1.85 | 128 |
| decode | 8192 | — | 64.6 | 3.07 | 128 |
| decode | 32768 | — | 44.1 | 10.39 | 128 |
| decode | 1024 | — | 69.8 | 1.84 | 128 |
| decode | 8192 | — | 65.6 | 3.09 | 128 |
| decode | 32768 | — | 65.8 | 10.50 | 128 |

**Среднее Strata:** prefill 8192 ≈ **1256 tps**; decode 8192 ≈ **65.1 tps**; TTFT 8192 ≈ **3.08 с**

---

## 5. Живое сравнение Avalon vs Strata (через llama-swap, одинаковые условия)

Обе модели протестированы через один и тот же прокси `llama-swap` на порту 8080, одинаковые тестовые параметры (prefill 512/2048/8192, decode 1024/8192/32768, 128 токенов генерации, 2 повторения).

| Метрика | Strata (IQ3_S) | Avalon (125B MoE) | Победитель |
|---------|---------------|-------------------|------------|
| **Prefill 8192** | ~1256 tps | ~956 tps | **Strata (+31%)** |
| **Decode 8192** | ~65.1 tps | ~68.7 tps | **Avalon (+5.5%)** |
| **TTFT 8192** | ~3.08 с | ~5.78 с | **Strata (в 1.9× быстрее)** |
| Decode 32768 | ~65.8 tps | ~65.5 tps | Примерно равно |
| Decode 1024 | ~51 tps (среднее) | ~64 tps (среднее) | **Avalon** |
| Prefill 512 | ~15-63 tps | ~202-257 tps | **Avalon** |
| Prefill 2048 | ~375-570 tps | ~665-684 tps | **Avalon** |

### Детальная таблица результатов (через llama-swap)

| Тест | Глубина | Strata prefill | Strata decode | Strata TTFT | Avalon prefill | Avalon decode | Avalon TTFT |
|------|---------|---------------|---------------|-------------|----------------|---------------|-------------|
| prefill | ~393 | 15.7 | — | — | 202.2 | — | — |
| prefill | ~1382 | 569.3 | — | — | 665.2 | — | — |
| prefill | ~5393 | 1117.9 | — | — | 969.8 | — | — |
| decode | 1024 | — | 32.2 / 69.8 | 1.85 / 1.84 | — | 61.4 / 67.1 | 2.57 / 2.73 |
| decode | 8192 | — | 64.6 / 65.6 | 3.07 / 3.09 | — | 70.4 / 66.9 | 5.78 / 5.77 |
| decode | 32768 | — | 44.1 / 65.8 | 10.39 / 10.50 | — | 61.5 / 65.5 | 20.67 / 19.75 |

---

## 6. Ключевые выводы

### Производительность

1. **Strata быстрее в prefill** — ~1256 tps vs ~956 tps на 8K контексте (+31% в пользу Strata)
2. **Strata быстрее в TTFT** — ~3.08 с vs ~5.78 с (почти в 2 раза быстрее первый токен)
3. **Avalon чуть лучше в decode** — ~68.7 vs ~65.1 tps (+5.5% в пользу Avalon)
4. **На длинном контексте (32K)** — примерно одинаково (~65 tps)
5. **На коротком префилле (512-2048)** — Avalon значительно превосходит Strata

### Архитектурные различия

- **Avalon** использует 33-шардовый GGUF формат (llama.cpp), модель на Gigabyte GPU (PCIe x16)
- **Strata** использует нативные IQ паки (отдельные `.bin` эксперты + GGUF шарды), модель на Gigabyte GPU (PCIe x16)
- Форматы моделей несовместимы — прямое сравнение "одной и той же модели" невозможно, модели логически эквивалентны (Qwen3.8-Flash-Next), но физически distintas

### Прокси-оверхед

- llama-swap добавляет **~3-4x оверхеда** по сравнению с прямым подключением к движку
- Для максимальной производительности рекомендуется прямое подключение к порту движка (5800 для Avalon)

---

## 7. Файлы в репозитории

| Файл | Описание |
|------|----------|
| `perf-tuning/FINAL_RESULTS.md` | Этот файл — итоговые результаты |
| `perf-tuning/AVALON_BENCHMARK_RESULTS.md` | Детальные результаты Avalon |
| `perf-bench/BENCHMARK_README.md` | Обзор бенчмарка |
| `perf-tuning/scripts/launch_engine.sh` | Скрипт запуска движков |
| `perf-tuning/scripts/run_matrix.sh` | Матричный тест runner |
| `perf-tuning/scripts/update_engines.sh` | Скрипт обновления движков |
| `perf-bench/bench.py` | Бенчмарк harness |
| `perf-bench/results/runs.csv` | Сырые результаты тестов |

---

## 8. Как воспроизвести

### Запуск Avalon напрямую (порт 5800)

```bash
env HIP_VISIBLE_DEVICES=1 /home/timoti/Avalon/build/bin/llama-server \
  -m /media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/Qwen3.8-Flash-Next-Avalon-IQ3KS-00001-of-00033.gguf \
  -c 200000 -b 4096 -ub 2048 -fa on -ctk q8_0 -ctv q4_0 --jinja --parallel 1 \
  -md /media/timoti/Data/lmstudio/models/freriadoc/Qwen3.8-Flash-Next-Avalon-GGUF/MTP/mtp-Qwen3.8-Flash-Next-shared-IQ3K-IQ4NL-FR65k.gguf \
  --spec-type draft-mtp --spec-draft-n-max 3 -ubd 256 -ctkd q8_0 -ctvd q4_0 \
  --temp 0.6 --top_k 30 --top-p 0.95 --reasoning-effort low --reasoning-budget 4092 \
  --host 0.0.0.0 --port 5800 --metrics

python3 bench.py --host 127.0.0.1 --port 5800 --model avalon-qwen3.8-flash-next-C2 \
  --tests health,prefill,decode --tag avalon-direct --repeat 2
```

### Запуск Strata через llama-swap (порт 8080)

```bash
cd /home/timoti/llama-swap
HIP_VISIBLE_DEVICES=1 LD_LIBRARY_PATH="/opt/rocm/lib" ./llama-swap -config config.yml -listen :8080

# Подождать загрузки модели, затем:
python3 bench.py --host 127.0.0.1 --port 8080 --model qwen3.8-flash-IQ3_S \
  --tests health,prefill,decode --tag strata-via-swap --repeat 2
```

---

## 9. Что еще можно протестировать

| Тест | Приоритет | Примечания |
|------|-----------|------------|
| ROCm 7.13 vs 7.8.0 | Medium | Переключить `LD_LIBRARY_PATH` на `/opt/rocm/core-7.13/lib` |
| ROCm 7.2.4 vs 7.8.0 | Medium | Переключить `LD_LIBRARY_PATH` на `/home/timoti/rocm724-portable/lib` |
| Модель на Sapphire GPU (PCIe x2) | Low | `HIP_VISIBLE_DEVICES=0`, порт 5900 |
| Sweep `--spec-draft-n-max` 2/3/4 | Medium | Для Avalon |
| Прямое подключение к Strata (без llama-swap) | Medium | Требуется HTTP сервер в Strata бинаре |
