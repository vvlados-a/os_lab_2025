# Лабораторная работа 8

Три задания: SQLite FUSE, сравнение s3fs/goofys/boto3, гибридное хранилище.
Исходники находятся только в этой папке. Git-команды не нужны.

## Зависимости и проверки без монтирования

Python 3.11+; для полного стенда — Docker Desktop с Linux engine, WSL2 и `/dev/fuse`.
Контейнеры устанавливают зависимости внутри образа, настройки Ubuntu не меняются.
Образ tools рассчитан на Linux amd64 (официальный бинарник goofys 0.24.0).

Из PowerShell в этой папке:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -B -m unittest -v
docker compose config --quiet
```

Unit-тесты также выполняются без сторонних пакетов: `python -B -m unittest -v`.
В этих тестах WARM — временная локальная папка; интеграционная проверка ниже использует s3fs.
Для Ubuntu venv: `python3 -m venv .venv-linux`, затем
`.venv-linux/bin/python -m pip install -r requirements.txt`.
Если в Ubuntu отсутствуют venv/libfuse2, используйте готовый контейнерный путь ниже;
глобальная установка пакетов для него не требуется.

## Общий стенд заданий 2 и 3

```powershell
docker compose build
docker compose up -d --wait --wait-timeout 180
docker compose ps
docker compose exec -T tools sh -c 'mountpoint /mnt/s3fs; mountpoint /mnt/goofys; mountpoint /mnt/warm'
```

Сборка требует Интернета для публичных зависимостей. Готовые официальные теги MinIO
при проверке 17.10.2026 не выдавались registry, поэтому один Dockerfile собирает
MinIO из фиксированного исходного релиза `RELEASE.2025-09-07T16-13-09Z` через Go module proxy
без Git-команд. Первый build заметно дольше последующих. Базовые Go/Python образы
имеют фиксированные версии. Приложения работают локально; API MinIO доступен на
`http://localhost:9000`, консоль — `http://localhost:9001`.
Учебные credentials: `lab8demo` / `lab8-local-only-password`; их нельзя использовать вне стенда.
Buckets `lab8-benchmark` и `lab8-hybrid` создаются через boto3, `mc` не требуется.

`tools` получает только `SYS_ADMIN`, `/dev/fuse` и отключение AppArmor для своего контейнера;
`privileged` не используется. Три FUSE mount и Python работают в одном контейнере,
поэтому распространение mount через общие volumes не требуется. HOT, COLD и JSON
состояния хранятся в `hybrid-data`, объекты MinIO — в `minio-data`.

Если tools не стал healthy:

```powershell
docker compose logs tools minio
docker compose exec -T tools sh -c 'cat /tmp/s3fs.log /tmp/goofys.log /tmp/warm.log'
```

## Задание 1

SQLite FS реализует `create/unlink/read/write/mkdir/rmdir/getattr/readdir`.
Для отличной оценки добавлены `chmod/chown/rename/utimens` и чанки по 4096 байт.
В `files` находятся метаданные и постоянный id, в `file_data` — `(file_id, chunk_index, data)`.
Внешний ключ с `ON DELETE CASCADE` удаляет чанки вместе с файлом.
Небольшая запись меняет только затронутые чанки; отсутствующие блоки читаются как нули.
`truncate` обрезает хвост последнего чанка и удаляет лишние; увеличение размера не выделяет блоки.
`rename` транзакционно меняет пути всего поддерева, сохраняет id/чанки и допускает
замену файла либо пустого каталога. Ошибки не оставляют частично перенесённую структуру.
`chown` сохраняет поле при -1; `utimens` поддерживает также обычный touch и touch -a/-m.
Используется один FUSE-поток; `open` нужен для cat, `truncate` — для перезаписи через echo.

**Совместимость БД:** прежний формат с BLOB в files не изменяется и не мигрируется.
Попытка открыть его завершается понятной ошибкой. Ниже используется новая
`files-chunks.db`; старую `files.db` сохраняйте отдельно и не удаляйте.

При установленном libfuse2 и fusepy в Ubuntu (терминал 1):

```bash
cd /mnt/d/Study/3-course/OSIS/Lab8/lab8
mkdir -p mnt/sqlitefs data
.venv-linux/bin/python sqlitefs.py mnt/sqlitefs --database data/files-chunks.db --foreground
```

Альтернатива без установки libfuse2 в Ubuntu — уже собранный стенд, PowerShell, терминал 1:

```powershell
docker compose exec tools mkdir -p /mnt/sqlitefs
docker compose exec tools python sqlitefs.py /mnt/sqlitefs --database /data/files-chunks.db --foreground
```

В терминале 2 откройте shell контейнера (`docker compose exec tools sh`) и выполните:

```sh
echo 'Hello, FUSE!' > /mnt/sqlitefs/test.txt
cat /mnt/sqlitefs/test.txt
echo 'short' > /mnt/sqlitefs/test.txt
mkdir /mnt/sqlitefs/mydir
echo 'nested' > /mnt/sqlitefs/mydir/file.txt
ls -la /mnt/sqlitefs /mnt/sqlitefs/mydir
chmod 640 /mnt/sqlitefs/test.txt
chown 1234:2345 /mnt/sqlitefs/test.txt
touch -d @1234567890 /mnt/sqlitefs/test.txt
mv /mnt/sqlitefs/test.txt /mnt/sqlitefs/saved.txt
mv /mnt/sqlitefs/mydir /mnt/sqlitefs/renamed-dir
stat -c '%a:%u:%g:%X:%Y' /mnt/sqlitefs/saved.txt
fusermount -u /mnt/sqlitefs
```

Повторите запуск в терминале 1 с той же БД, затем в терминале 2:

```sh
stat -c '%a:%u:%g:%X:%Y' /mnt/sqlitefs/saved.txt
cat /mnt/sqlitefs/saved.txt /mnt/sqlitefs/renamed-dir/file.txt
rm /mnt/sqlitefs/renamed-dir/file.txt
rmdir /mnt/sqlitefs/renamed-dir
rm /mnt/sqlitefs/saved.txt
fusermount -u /mnt/sqlitefs
```

Для прямого запуска в Ubuntu используйте `mnt/sqlitefs` вместо `/mnt/sqlitefs`.
Пример chown выше выполняется в контейнере от root; sudo на хосте не нужен.
БД обязательно находится вне mountpoint; программа проверяет это при запуске.

Покрытие — только инструмент разработки, не runtime-зависимость. В PowerShell из lab8:

```powershell
python -m venv .venv-coverage
.venv-coverage\Scripts\python -m pip install coverage
.venv-coverage\Scripts\python -B -m coverage run --source=sqlitefs -m unittest -v
.venv-coverage\Scripts\python -m coverage report --include=sqlitefs.py --precision=2 --fail-under=81 -m
```

Фактически получено **88.68%** для всего `sqlitefs.py`: 212 исполняемых строк, 24 пропущены.
CLI-код не исключался из расчёта; пропущенные строки относятся к запуску FUSE из main.
Измерение выполнено coverage.py 7.16.2 на Python 3.14.4. Файл `.coverage` и dev-venv исключены.

## Задание 2

Одинаковый запуск всех методов, параметры методички: 100 файлов по 1 MiB,
1000 случайных чтений по 4096 B, 1000 маленьких файлов по 4096 B:

```powershell
docker compose exec -T tools python benchmark.py --output /results/benchmark.json
```

Быстрая проверка с меньшим числом операций:

```powershell
docker compose exec -T tools python benchmark.py --count 3 --small-count 5 --random-count 10 --output /results/quick.json
docker compose exec -T tools python benchmark.py --plot /results/quick.json
```

JSON и PNG появляются в `lab8/results/`. JSON содержит параметры, окружение,
каждую попытку с latency/байтами/ошибкой и итоговые метрики. При ошибках exit code = 1.
При отсутствии настоящего mount измерение FUSE не запускается.
Параметр `--methods boto3` позволяет отдельно проверить native S3.
Методология, ограничения кэша и выводы — в [REPORT.md](REPORT.md).

Очистка только объектов конкретного запуска (JSON и график остаются):

```powershell
docker compose exec -T tools python benchmark.py --cleanup /results/quick.json
docker compose exec -T tools python benchmark.py --cleanup /results/benchmark.json
```

Не выполняйте очистку, пока эти объекты нужны для анализа. Все ключи имеют уникальный
префикс `lab8-bench/<uuid>/`; чужие объекты и buckets не удаляются. После очистки через
API FUSE может временно показывать закэшированные записи; следующий прогон использует новый UUID.

## Задание 3

```powershell
docker compose exec tools python hybrid_storage.py
```

Введите команды (для нового файла выбирайте свободное имя):

```text
put test.txt Hello, Hybrid Storage!
get test.txt
status
migrate
quit
```

`put` принимает одно имя файла и текст, всегда сохраняет в HOT; повторное имя выдаёт
`FileExistsError`. `get` проверяет содержимое и возвращает файл в HOT из любого уровня.
`status` показывает уровень, размер, checksum и время доступа. `migrate` применяет политики:
более 7 дней без доступа HOT → WARM, более 30 дней WARM → COLD; один переход за проход.
Фоновый поток этого же приложения проверяет политики каждые 60 секунд, пока открыт shell.
Одновременно запускайте только один менеджер: JSON рассчитан на один процесс.

Воспроизводимая демонстрация всех переходов без ожидания недель:

```powershell
docker compose exec -T -e LAB8_WARM_TEST_ROOT=/mnt/warm tools python -B -m unittest -v test_hybrid_storage
```

Тесты используют настоящий WARM mount и только свои временные файлы. Они сдвигают
время доступа исключительно внутри тестов и показывают put/status/migrate/get:
HOT → WARM → HOT → WARM → COLD → HOT, перезапуск менеджера и сверку байтов.
Отдельно проверяются пороги 7/30 дней, автоматический таймер и ошибки переноса.
Публичного изменения тестового времени в приложении нет. COLD — локальная папка,
восстановление мгновенное; задержка в часы является бизнес-требованием, а не измерением PoC.
Описание архитектуры и условный TCO — в [ARCHITECTURE.md](ARCHITECTURE.md).

## Безопасная остановка

Сначала выйдите из менеджера (`quit`) и размонтируйте SQLite FS, если она запущена.

```powershell
docker compose stop
docker compose down
```

Volumes сохраняются; следующий `docker compose up -d --wait` использует те же данные.
Не добавляйте `-v`. Зависимости, БД и временные файлы исключены через `.gitignore`
и `.dockerignore`. Итоговые `results/benchmark.json` и `results/benchmark.png`
разрешены в `.gitignore`, чтобы ссылка из REPORT работала при передаче проекта;
прочие результаты остаются исключёнными. Git-команды для этой работы не выполнялись.

## Фактически выполненные проверки

После доработки 17.10.2026: **25 тестов** успешно на Windows (Python 3.14.4)
и в Docker Linux (Python 3.12.12). AST всех 6 Python-файлов,
`sh -n entrypoint.sh` и `docker compose config --quiet` — успешно.
Оба Docker-образа успешно собраны; `docker compose up -d --wait` поднял три настоящих
FUSE mount. В контейнере Python 3.12.12, s3fs 1.90, goofys 0.24.0.
`docker compose exec -T -e LAB8_WARM_TEST_ROOT=/mnt/warm tools python -B -m unittest -v`
прошёл все 25 тестов с настоящим WARM/s3fs.

SQLite FS дополнительно проверена через реальный mount: chmod, chown от root
(включая изменение только uid или gid), touch и touch -a/-m, mv файлов и поддерева,
замена файла и пустого каталога, echo/cat, бинарная запись на границе 4096 байт,
запись за EOF с нулевым промежутком, уменьшение/увеличение через truncate,
отказ rmdir для непустого каталога, unlink/rmdir, размонтирование и запуск нового
процесса с той же БД — успешно. Права, uid/gid, atime/mtime и байты сохранены.
После удаления проверены отсутствие чанков и `PRAGMA foreign_key_check`.
Команды для повторения приведены в разделе задания 1.

При первоначальной проверке короткий и полный `benchmark.py` выполнены всеми тремя методами. Полный прогон:
6600 успешных операций, 12 серий, 0 ошибок. Все итоговые метрики повторно сверены
с сырыми samples; JSON и PNG сохранены в results, таблица — в REPORT.
`--plot` проверен, график осмотрен. `--cleanup` проверен по S3 API: сначала удалены
объекты короткого прогона с сохранением полного, затем очищен полный префикс;
buckets и гибридные данные сохранились.
При текущей доработке бенчмарк не перезапускался: исходные JSON/PNG и REPORT сохранены.
Код и документация заданий 2–3, Docker-инфраструктура и runtime-зависимости не менялись.

Проверены put/get/status/migrate и stop/up обоих контейнеров: JSON и файл в WARM
пережили остановку, get после запуска вернул правильные байты и перенёс файл в HOT.
В конце выполнен `docker compose down` без `-v`. Volumes сохранены; небольшой
`demo.txt` остался в HOT как результат проверки. Сборки и зависимости находятся
в Docker, а не в сдаваемых исходниках.

Непроверенными остаются производственные SLA/500+ TB, реальные архивные задержки,
сбой питания и работа на других платформах; это границы локального PoC.
FUSE непосредственно в Ubuntu-хосте не запускалась: там нет libfuse2/fusepy/s3fs/goofys;
вместо установки глобальных пакетов все FUSE-проверки исполнены в Docker Linux.
