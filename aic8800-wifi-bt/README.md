# AIC8800 Wi-Fi + Bluetooth USB-адаптер: драйвер для Linux

Драйвер для USB-адаптера **AICsemi AIC8800D80** (combo Wi-Fi 802.11ax + Bluetooth 5.4).
USB-идентификаторы: `a69c:8d80` (Wi-Fi/BT режим) и `a69c:5721` (mass-storage режим).

## Почему нужен

Ядро Linux само не знает, как работать с этим адаптером: USB-интерфейс устройства
обозначен как «Vendor Specific» (класс 255), поэтому без vendor-драйвера система
просто видит «неизвестное USB-устройство», а в `dmesg` оно бесконечно
отключается и переподключается.

Драйвер состоит из **трёх модулей**, которые должны загружаться строго в
определённом порядке:

| Модуль | Назначение |
|--------|------------|
| `aic_load_fw` | Загрузчик прошивки. Перекачивает в адаптер бинарники из `/lib/firmware/aic8800D80/`, после чего устройство перечисливается (re-enumerate) и становится «настоящим» Wi-Fi/BT адаптером. **Без него ничего не работает.** |
| `aic8800_fdrv` | Основной Wi-Fi драйвер (mac80211/cfg80211). Создаёт интерфейс `wl*`. |
| `aic_zlp_quirk` | BT-кво́рк. Подключается к стандартному `btusb` через kretprobe/kprobe и добавляет флаг `URB_ZERO_PACKET` к ACL bulk OUT URB адаптера — иначе Bluetooth (например, AAC-аудио) обрывается примерно через минуту. Должен грузиться **до** `btusb` (указан `MODULE_SOFTDEP("pre: btusb")`). |

Порядок загрузки:

```
aic_load_fw  →  aic8800_fdrv  →  aic_zlp_quirk  →  btusb  →  hciconfig hci0 up
```

## Откуда код

- `driver/` — исходники `aic_load_fw` + `aic8800_fdrv` (ветка bluetooth,
  репозиторий shenmintao/aic8800d80, тег `archive/bluetooth-final`),
  с включённой BT-поддержкой (`aicbluetooth*.c` в `aic_load_fw`).
- `zlp-quirk/` — модуль `aic_zlp_quirk` (тег `fix/issue-63-zlp-quirk`
  того же репозитория).
- `firmware/aic8800D80/` — прошивки адаптера (`.bin`, `.txt`), ставятся в
  `/lib/firmware/aic8800D80/`.

## Структура каталога

```
aic8800-wifi-bt/
├── README.md
├── build.sh                 # сборка под текущее ядро
├── install.sh               # установка + загрузка (+ --load / --unload)
├── driver/
│   ├── Makefile             # верхний Makefile (aic_load_fw/ + aic8800_fdrv/)
│   ├── Kconfig
│   ├── aic_load_fw/         # исходники загрузчика прошивки
│   └── aic8800_fdrv/        # исходники Wi-Fi драйвера
├── zlp-quirk/
│   ├── Makefile
│   ├── aic_zlp_quirk.c
│   └── README-zlp-quirk.md  # документация кворка
└── firmware/
    └── aic8800D80/          # прошивки
```

## Сборка

Драйвер собирается **под конкретное ядро**, поэтому после каждого обновления
ядра его нужно пересобирать.

### Требования

```bash
sudo apt install build-essential linux-headers-$(uname -r)
```

### Компиляция

```bash
cd aic8800-wifi-bt
./build.sh
```

Скрипт:
1. чистит артефакты прошлых сборок (`.o`, `.ko`, `.mod`, `.*.cmd`);
2. собирает `aic_load_fw.ko` и `aic8800_fdrv.ko` через
   `make -C /lib/modules/$(uname -r)/build M=driver ARCH=x86_64 modules`;
3. собирает `aic_zlp_quirk.ko` тем же способом;
4. проверяет `vermagic` — версия модуля должна совпадать с текущим ядром.

Простая ручная сборка (то же самое):

```bash
KVER=$(uname -r)
make -C /lib/modules/$KVER/build M=driver ARCH=x86_64 modules
make -C /lib/modules/$KVER/build M=zlp-quirk ARCH=x86_64 modules
```

## Установка и загрузка

```bash
sudo ./install.sh              # установка модулей + прошивок + загрузка
sudo ./install.sh --load       # только загрузить (модули уже установлены)
sudo ./install.sh --unload     # выгрузить все AIC-модули
```

`install.sh`:
1. копирует прошивки в `/lib/firmware/aic8800D80/`;
2. ставит `.ko` в `/lib/modules/$(uname -r)/kernel/drivers/net/wireless/aic8800/`
   и запускает `depmod`;
3. выгружает старые модули, затем загружает в правильном порядке
   (`aic_load_fw` → `aic8800_fdrv` → `aic_zlp_quirk` → `btusb`);
4. поднимает Bluetooth: `hciconfig hci0 up`;
5. печатает статус: модули, `lsusb`, сетевые интерфейсы, `hciconfig -a`.

## Проверка работы

```bash
# Bluetooth
bluetoothctl
  power on
  agent on
  scan on

# Wi-Fi
nmcli device wifi list
nmcli device wifi connect "<SSID>" password "<PASS>"
```

Успешная загрузка в `dmesg` выглядит так:

```
aic_zlp_quirk: attached to system btusb for USB device 368b:8d81
aic_zlp_quirk: enabled ZLP on the first 368b:8d81 ACL bulk OUT URB
```

Bluetooth-адаптер: `hciconfig -a` → `hci0 ... UP RUNNING`.
Wi-Fi-интерфейс: `wl*` в `ip link`.

## Автозагрузка при старте

Создайте systemd-сервис `/etc/systemd/system/aic8800-load.service`:

```ini
[Unit]
Description=AIC8800 WiFi+BT module load
After=bluetooth.service
Wants=bluetooth.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/bash -c '! /sbin/lsmod | grep -q aic_load_fw'
ExecStart=/sbin/modprobe aic_load_fw
ExecStartPost=/bin/bash -c 'sleep 3 && /sbin/modprobe aic8800_fdrv && /sbin/modprobe aic_zlp_quirk && /sbin/modprobe btusb'
ExecStartPost=/bin/bash -c 'sleep 2 && /usr/bin/hciconfig hci0 up 2>/dev/null || true'

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable aic8800-load.service
```

Важно: `aic_zlp_quirk` стоит **до** `btusb` в строке `ExecStartPost` —
иначе кво́рк не подхватится.

## Типичные проблемы

| Симптом | Причина / решение |
|---------|--------------------|
| В `lsusb` видно `a69c:5721`, Wi-Fi/BT нет | Адаптер в mass-storage режиме. Переключить: `usb_modeswitch -v 0xa69c -p 0x5721 -K -Q` (пакет `usb-modeswitch`). |
| `modprobe: FATAL: Module aic_load_fw not found` | Драйвер собран под **другое ядро**. Пересобрать: `./build.sh && sudo ./install.sh`. |
| BT обрывается через ~1 минуту | Не загружен `aic_zlp_quirk` (или загружен после `btusb`). Выгрузить всё и загрузить в правильном порядке. |
| `aic_zlp_quirk: attached USB submit fallback` | Нормально: в этом ядре `btusb:alloc_bulk_urb` заинлайнена, кворк повесился на `usb_submit_urb`. |
| `aic_zlp_quirk: CONFIG_KPROBES is disabled` | Ядро собрано без kprobes — кворк не работает, BT будет нестабилен. |
| Wi-Fi есть, BT нет (или наоборот) | Проверить порядок: сначала `aic_load_fw` (он перечисливает устройство), потом остальные. |
