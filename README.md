# OknoPro — сайт компании по установке пластиковых окон

FastAPI-приложение: маркетинговый лендинг с калькулятором стоимости, каталог продукции, приём заявок с
уведомлением менеджеров в Telegram и защищённая админ-панель для управления ценами, каталогом и заявками.

## Содержание

1. [Коротко: что и когда запускать](#коротко-что-и-когда-запускать)
2. [Стек и структура проекта](#стек)
3. [Что реализовано](#что-реализовано)
4. [Сценарий 1. Запуск на сервере (Docker Compose)](#сценарий-1-запуск-на-сервере-docker-compose)
5. [Сценарий 2. Локальная проверка](#сценарий-2-локальная-проверка)
6. [Автоматические проверки](#автоматические-проверки)
7. [Чек-лист ручной проверки](#чек-лист-ручной-проверки)
8. [Если что-то не работает](#если-что-то-не-работает)
9. [Что заменить перед публикацией](#что-заменить-перед-публикацией)
10. [Ограничения](#ограничения) · [GitHub и CI](#github-и-ci)

---

## Коротко: что и когда запускать

| Цель | Что делать | Где |
|---|---|---|
| Быстро посмотреть сайт и поправить вёрстку | [Сценарий 2, вариант А](#вариант-а--без-docker-быстрее-всего) | своя машина |
| Проверить сайт так, как он будет на сервере (Nginx, CSP, Postgres, очередь) | [Сценарий 2, вариант Б](#вариант-б--docker-compose-как-на-сервере) | своя машина с Docker |
| Прогнать автоматические проверки перед коммитом | `pytest -v` и `ruff check .` | своя машина |
| Опубликовать сайт | [Сценарий 1](#сценарий-1-запуск-на-сервере-docker-compose) целиком, по порядку | сервер |
| Узнать, что ещё не готово к публикации | `python release_check.py` | где угодно |

Главное правило: **публиковать можно, только когда `python release_check.py` не показывает блокеров**
(а HTTPS настроен — иначе в production не заработает вход в админку, см. ниже).

---

## Стек

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2, Alembic (миграции), Pydantic Settings
- **БД**: PostgreSQL в проде, SQLite — для локальной разработки и тестов
- **Очередь**: ARQ (Redis) — ретраи отправки в Telegram с экспоненциальным backoff; если `REDIS_URL` не задан,
  отправка идёт сразу в event loop приложения (без очереди)
- **Frontend**: Jinja2-шаблоны, Tailwind CSS (собирается локально, CDN не используется), vanilla JavaScript,
  шрифт Manrope отдаётся с нашего сервера (запросов к Google Fonts нет)
- **Инфраструктура**: Docker Compose (app, worker, db, redis, nginx); Nginx отдаёт статику, проксирует приложение
  и выставляет строгий Content-Security-Policy
- **Тесты**: pytest (+ необязательные браузерные тесты на Playwright); линтер — ruff

## Структура проекта

```
main.py                    FastAPI-приложение, публичные и API-роуты
admin_router.py            Роуты админ-панели (/admin/*)
admin_auth.py              Сессии, RBAC (admin/manager), CSRF
config.py                  Настройки из .env (Pydantic Settings)
database.py                Модели SQLAlchemy, bootstrap-сидирование
catalog_repository.py      Запросы каталога (категории/товары)
catalog_seed_data.py       Контент каталога для сидирования
pricing_service.py         Расчёт стоимости (единственный источник цены)
assets.py                  Версионирование статики: /static/x.css?v=<хеш> (cache busting)
release_check.py           Проверка «готов ли сайт к публикации» (демо-данные, секреты, TODO)
bot.py, telegram_delivery.py, queue_client.py, worker.py   Telegram-уведомления и очередь ARQ
security.py                Хеширование паролей (PBKDF2)
audit.py                   Журнал действий администраторов
middleware.py              Request-ID, security-заголовки
logging_config.py          Структурные JSON-логи
schemas.py, rate_limit.py  Pydantic-схемы запросов, rate limiting (slowapi)
alembic/                   Миграции БД (0001–0004)
templates/                 Jinja2-шаблоны (pages/, partials/, admin/)
static/                    css/ (input.css → output.css), js/, fonts/, images/
nginx/nginx.conf           Nginx по HTTP (+ CSP, заголовки, прокси)
nginx/nginx.https.conf.example   Тот же конфиг с HTTPS (TLS, редирект, HSTS)
docker-compose.yml         Сервисы: db, redis, app, worker, migrate, nginx
docker-compose.tls.yml     Дополнение к compose для HTTPS (порт 443, сертификаты)
docs/DEPLOY_TLS.md         Подробно про выпуск и продление сертификата
scripts/                   create_admin.py, backup_db.sh, restore_db.sh
tests/                     pytest-тесты
.github/workflows/ci.yml   GitHub Actions CI
```

## Что реализовано

- Публичный сайт: главная с калькулятором, политика конфиденциальности, каталог (`/okna/`,
  `/okna/odnostvorchatye/`, `/balkonnye-bloki/`, `/osteklenie-balkonov/`, `/plastikovye-dveri/`,
  `/gotovye-okna/` и т. д.), `sitemap.xml`, `robots.txt`
- Формы заявок (`/api/lead`, `/api/calculator-lead`): honeypot, нормализация телефона, согласие на обработку
  персональных данных, защита от повторной отправки, rate limit
- **Калькулятор: цена считается только на сервере** (`/api/v1/calculator/estimate`, `PricingService`). Браузер
  ничего не рассчитывает сам и не может подставить цену; во время расчёта показывается состояние загрузки,
  ошибки 422/429/5xx и обрыв сети отображаются понятным текстом
- Уведомления в Telegram о новых заявках, с ретраями через ARQ при сбое
- Админ-панель (`/admin/`): дашборд, заявки, цены и каталог, пользователи с ролями `admin`/`manager`, журнал
  аудита, CSRF-защита форм
- Доступность и адаптивность: проверено автоматически (axe-core, WCAG 2.2 AA) на ширинах 320–1440 px;
  навигация с клавиатуры, нативные `<dialog>` с возвратом фокуса, поддержка `prefers-reduced-motion`
- Строгий CSP: на публичных страницах нет inline-скриптов и inline-стилей, единственный внешний хост —
  Яндекс.Метрика (если подключена)

---

## Сценарий 1. Запуск на сервере (Docker Compose)

### Что нужно заранее

- Сервер с Docker Engine 24+ и Docker Compose v2 (команда `docker compose`, не `docker-compose`)
- Node.js 20+ и npm — один раз, чтобы собрать CSS перед сборкой образа (собранный CSS не хранится в git)
- **Домен**, у которого A-запись указывает на сервер, и открытые порты **80 и 443**
- Права на `certbot` (для сертификата Let's Encrypt)

> **Почему нужен HTTPS, а не «потом».** При `ENVIRONMENT=production` cookie админки выставляется с флагом
> `Secure`. Браузер не принимает такую cookie по обычному HTTP, поэтому на реальном домене без TLS **войти в
> админку невозможно**. На `localhost` Chrome делает исключение, поэтому локально проблема не видна.

### Шаг 1. Код и конфигурация

```bash
git clone <URL вашего репозитория> window-landing
cd window-landing
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # скопируйте в ADMIN_SESSION_SECRET
```

Отредактируйте `.env`. Обязательно для production:

| Переменная | Что указать |
|---|---|
| `ENVIRONMENT` | `production` (включает продовые защиты: уникальный секрет, `Secure`-cookie, скрыты `/docs`) |
| `ADMIN_SESSION_SECRET` | случайная строка ≥ 32 символов. С дефолтным значением приложение **не стартует** |
| `POSTGRES_PASSWORD` | свой пароль БД (используется и приложением, и compose) |
| `DOMAIN` | `https://ваш-домен.ru` — без слэша в конце. **Раскомментируйте строку** в `.env` |
| `ALLOWED_ORIGINS` | `https://ваш-домен.ru` (через запятую, без `*`, без `localhost`) |
| `COMPANY_NAME`, `COMPANY_PHONE`, `COMPANY_ADDRESS` | реальные данные. **Раскомментируйте строки** |
| `CALCULATOR_DISCOUNT_PERCENT` | реальный размер скидки. Она применяется к ценам и обещается клиенту в ответе формы. **Раскомментируйте** |
| `LEGAL_ENTITY_NAME` | ООО/ИП, ИНН, ОГРН — для футера и политики |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | токен бота (@BotFather) и chat_id чата менеджеров |
| `REDIS_URL` | `redis://redis:6379/0` (очередь уведомлений) |
| `YANDEX_METRIKA_ID` | ID счётчика, если нужна аналитика |

`DATABASE_URL` в compose менять не нужно — сервис `app` сам собирает его из `POSTGRES_*`.
Пять полей (`DOMAIN`, `COMPANY_*`, `CALCULATOR_DISCOUNT_PERCENT`) в `.env.example` намеренно закомментированы:
пока они не заданы, сайт работает на демо-значениях, а `release_check.py` сообщает о блокерах.

`.env` не коммитится (см. `.gitignore`) и не должен передаваться в открытом виде.

### Шаг 2. Собрать CSS и образы

`Dockerfile` проверяет наличие `static/css/output.css` и остановит сборку, если файла нет:

```bash
npm ci
npm run build:css
docker compose build
```

### Шаг 3. Проверить готовность к публикации

```bash
docker compose run --rm --no-deps app python release_check.py
```

Скрипт перечисляет **блокеры** (демо-данные, дефолтные секреты, `localhost` в `ALLOWED_ORIGINS`, незаполненный
текст политики конфиденциальности и т. п.; код выхода 1) и **предупреждения** (нет Telegram, Redis, `og:image`).
Исправляйте блокеры в `.env` и шаблонах и запускайте проверку снова, пока блокеров не останется.

### Шаг 4. База данных

```bash
docker compose up -d db redis
docker compose run --rm migrate
```

Применяются миграции `alembic/versions/` (`0001` → `0004`). Миграции `0002` и `0003` также сеют стартовые данные
(цены калькулятора, категории и товары каталога) — сайт не будет пустым.

### Шаг 5. Первый администратор

Миграции намеренно не создают пользователей — пароль не должен попасть в историю git:

```bash
docker compose run --rm app python scripts/create_admin.py
```

Скрипт спросит логин и пароль (от 8 символов).

### Шаг 6. HTTPS и запуск (production)

Подробности и продление сертификата — в [docs/DEPLOY_TLS.md](docs/DEPLOY_TLS.md). Минимальный порядок:

```bash
# 1. HTTPS-конфиг Nginx: подставьте свой домен
cp nginx/nginx.https.conf.example nginx/nginx.conf
sed -i 's/example\.com/ваш-домен.ru/g' nginx/nginx.conf

# 2. Сертификат. Порт 80 должен быть свободен, поэтому ДО запуска Nginx
sudo certbot certonly --standalone -d ваш-домен.ru -d www.ваш-домен.ru

# 3. Запуск всего стека с HTTPS
mkdir -p certbot-www
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d
```

Поднимутся: `db` (PostgreSQL), `redis`, `app` (FastAPI/uvicorn), `worker` (ARQ: ретраи Telegram и периодический
sweep), `nginx` (порты 80 → редирект на HTTPS, 443; отдаёт `/static/`, проксирует остальное в `app`).

В конфиге HSTS стоит с коротким сроком (`max-age=300`). Когда убедитесь, что сайт и админка работают по HTTPS,
поднимите его до `31536000` (см. docs/DEPLOY_TLS.md).

**Только для временной проверки на сервере без домена.** Запуск по HTTP (`docker compose up -d`) возможен, но
для входа в админку придётся поставить `ENVIRONMENT=development`: это ослабляет защиты, `/docs` становится
доступен. Не оставляйте так сайт, открытый в интернет.

### Шаг 7. Проверка после запуска

```bash
docker compose ps                                              # все сервисы Up (app — healthy)
curl -sI http://ваш-домен.ru/privacy | head -3                 # 301 -> https
curl -sI https://ваш-домен.ru/ | grep -iE 'HTTP/|strict-transport|content-security'
curl -sf https://ваш-домен.ru/health                           # {"status":"ok"}
```

Затем в браузере: главная, калькулятор (цена должна появиться), отправка тестовой заявки, вход в
`https://ваш-домен.ru/admin/login`; в консоли браузера не должно быть ошибок CSP. Остальное — в
[чек-листе](#чек-лист-ручной-проверки).

### Безопасность за Nginx (уже настроено, не ломайте)

- **Реальный IP клиента.** Rate limit считается по IP. В `docker-compose.yml` задан `FORWARDED_ALLOW_IPS=*`, а
  Nginx **перезаписывает** `X-Forwarded-For` реальным адресом клиента. Это работает только вместе:
  если дописывать заголовок вместо перезаписи, лимит обходится подделкой; если не доверять прокси, все посетители
  выглядят одним адресом и один человек блокирует форму всем.
- **Не публикуйте порт сервиса `app`** (`ports:` в compose) — `*` безопасно только пока до приложения нельзя
  достучаться в обход Nginx. Это проверяет автотест `tests/test_deploy_config.py`.
- Если перед Nginx стоит CDN/балансировщик, настройте `ngx_http_realip_module` (см. docs/DEPLOY_TLS.md).

### Обновление релиза

```bash
git pull
npm ci && npm run build:css
docker compose -f docker-compose.yml -f docker-compose.tls.yml build
docker compose run --rm migrate
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d
```

Старый CSS/JS в браузерах посетителей не «залипнет»: ссылки на статику содержат хеш содержимого
(`?v=…`), и он меняется вместе с файлом. Перед обновлением делайте [бэкап](#резервное-копирование-бд).

### Логи

```bash
docker compose logs -f app       # также worker, nginx, db
```

При старте в production `app` пишет в лог `release-check [БЛОКЕР]: …` по каждому незаменённому демо-значению.

### Резервное копирование БД

```bash
./scripts/backup_db.sh                          # дамп в ./backups/, хранит последние 14
./scripts/restore_db.sh backups/<файл>.sql.gz    # восстановление (перезаписывает текущие данные)
```

---

## Сценарий 2. Локальная проверка

### Вариант А — без Docker (быстрее всего)

Подходит для разработки и быстрой проверки. Нужны **Python 3.12–3.14** (в Docker используется 3.12 — лучший выбор,
если нет причин иначе) и Node.js 20+.

**Linux / macOS (bash):**

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt                      # зависимости + pytest/ruff

npm ci
npm run build:css                                        # собирает static/css/output.css

cp .env.example .env
python3 -c "import re,pathlib; p=pathlib.Path('.env'); p.write_text(re.sub(r'(?m)^DATABASE_URL=.*','DATABASE_URL=sqlite:///./leads.db',p.read_text(encoding='utf-8')),encoding='utf-8')"
```

**Windows (PowerShell):**

```powershell
py -3.12 -m venv venv          # или просто: python -m venv venv
venv\Scripts\Activate.ps1     # если запрещено выполнение скриптов: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements-dev.txt

npm ci
npm run build:css

copy .env.example .env
python -c "import re,pathlib; p=pathlib.Path('.env'); p.write_text(re.sub(r'(?m)^DATABASE_URL=.*','DATABASE_URL=sqlite:///./leads.db',p.read_text(encoding='utf-8')),encoding='utf-8')"
```

(Последняя команда в обоих вариантах заменяет в `.env` строку `DATABASE_URL` на SQLite. Править `.env` в Блокноте тоже
можно — сохраняйте в UTF-8.)

`REDIS_URL` оставьте пустым — уведомления пойдут без очереди (штатный, протестированный режим).
Telegram без токена тоже не мешает: заявки сохраняются, уведомление просто не отправляется.

```bash
uvicorn main:app --reload
```

- Сайт: **http://127.0.0.1:8000**
- Админка: **http://127.0.0.1:8000/admin/** — сначала создайте администратора:

```bash
python scripts/create_admin.py
```

На пустой БД приложение само создаёт таблицы и сеет цены и каталог (`database.init_db()` — это dev-упрощение;
на сервере схему создаёт только Alembic).

Правка стилей на лету: во втором терминале `npm run watch:css`.

### Вариант Б — Docker Compose, как на сервере

Ближе всего к боевой конфигурации: Postgres, Redis, воркер и **Nginx с боевым CSP**, поэтому именно здесь видно
проблемы, которых нет в варианте А (блокировки CSP, заголовки, статика).

```bash
cp .env.example .env              # ENVIRONMENT=development можно оставить
npm ci && npm run build:css
docker compose build
docker compose up -d db redis
docker compose run --rm migrate
docker compose run --rm app python scripts/create_admin.py
docker compose up -d
```

Сайт: **http://localhost/**, админка: **http://localhost/admin/**. Откройте консоль браузера: на всех
страницах не должно быть сообщений `Content Security Policy`.

### Тестовые данные

- Каталог и цены сидируются автоматически (SQLite — через `init_db()`, Postgres — миграциями `0002`/`0003`)
- Тестовая заявка — через форму на главной или:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/lead -H "Content-Type: application/json" \
    -d '{"phone":"+79001234567","consent":true,"name":"Тест"}'
  ```

### Что покажет `release_check.py` локально

```bash
python release_check.py
```

Локально блокеры — **это нормально** (демо-данные, `ENVIRONMENT=development`, `localhost`). Скрипт нужен, чтобы
увидеть, что именно осталось заменить до публикации.

---

## Автоматические проверки

```bash
pytest -v                                     # все тесты
pytest -v --cov --cov-report=term-missing     # с покрытием
ruff check .                                  # линтер, тот же набор, что в CI
```

Тесты используют изолированную SQLite-БД на каждый тест (`tests/conftest.py`); Postgres и Redis не нужны, тесты
очереди подменяют ARQ-пул.

| Файл | Что защищает |
|---|---|
| `test_leads.py`, `test_phone.py`, `test_pricing.py` | заявки, нормализация телефона, расчёт цены |
| `test_admin.py`, `test_security.py`, `test_production_guard.py` | админка, RBAC, CSRF, пароли, защита production |
| `test_catalog.py`, `test_queue.py`, `test_bot.py`, `test_middleware.py` | каталог, очередь и Telegram, заголовки |
| `test_csp_and_head.py` | нет inline-скриптов/обработчиков/`style=` (иначе CSP заблокирует их на сервере); HEAD отвечает как GET; CSP в Nginx строгий |
| `test_assets.py` | вся статика подключена с версией (`?v=`), иначе после деплоя браузеры покажут старые файлы |
| `test_deploy_config.py` | Nginx перезаписывает `X-Forwarded-For`, `app` не опубликован, HTTPS-конфиг не разошёлся с основным |
| `test_release_check.py` | `release_check.py` ловит демо-данные и не шумит на полной конфигурации |
| `test_frontend_layout.py` | **браузерные**: закрытое меню не рисуется, нет горизонтального скролла на 320–1280 px |

Браузерные тесты необязательны и без Playwright **пропускаются**. Чтобы включить:

```bash
pip install playwright && playwright install chromium
npm run build:css
pytest tests/test_frontend_layout.py -v
```

---

## Чек-лист ручной проверки

### Публичный сайт
- [ ] `/` — открывается, hero-форма видна, калькулятор считает цену
- [ ] `/privacy` — открывается
- [ ] `/okna/` — хаб-страница со списком подкатегорий
- [ ] `/okna/odnostvorchatye/`, `/okna/dvuhstvorchatye/`, `/okna/trehstvorchatye/` — карточки товаров с ценой «от»
- [ ] `/balkonnye-bloki/`, `/osteklenie-balkonov/`, `/plastikovye-dveri/`, `/gotovye-okna/` — открываются
- [ ] Несуществующая страница (например `/foo/`) — красивая страница 404 в браузере (для `curl` без
      `Accept: text/html` вернётся JSON — это штатно)
- [ ] `/sitemap.xml`, `/robots.txt` — открываются, sitemap перечисляет реальные URL каталога
- [ ] Навигация в шапке и футере ведёт на существующие разделы и якоря
- [ ] Мобильная версия (ширина 375 px): меню открывается и закрывается, нет горизонтальной прокрутки
- [ ] С клавиатуры: Tab проходит по ссылкам, меню и FAQ открываются Enter/Space, модалка закрывается Escape
      и возвращает фокус

### Формы
- [ ] Hero-форма на главной — отправка с реальным телефоном создаёт заявку, показывается сообщение об успехе
- [ ] Модалка «Вызвать замерщика» — открывается и отправляется на главной, `/privacy`, в каталоге и на 404
- [ ] Отправка без согласия — форма не отправляется, показана ошибка
- [ ] При ошибке сервера введённые поля не очищаются; двойной клик по кнопке не создаёт две заявки
- [ ] Калькулятор: цена приходит с сервера (во время расчёта виден индикатор загрузки), после расчёта можно
      оставить заявку (`/api/calculator-lead`) — она сохраняется с привязанной ценой
- [ ] Ссылка из каталога с параметрами (например `/?window_type=…&profile_type=…`) предзаполняет калькулятор;
      мусорные значения в параметрах игнорируются

### Telegram-интеграция (внешний сервис)
- [ ] Без `TELEGRAM_BOT_TOKEN` заявки всё равно создаются (уведомление не отправляется, `telegram_status=failed`
      видно в админке)
- [ ] С тестовым ботом — уведомление приходит в чат при создании заявки

**Как проверить безопасно, не трогая боевого бота:** создайте отдельного бота через
[@BotFather](https://t.me/BotFather) (минута, бесплатно), впишите его токен и chat_id тестового чата в `.env`,
перезапустите приложение.

### Админ-панель (`/admin/`)
- [ ] Без входа `/admin/` перенаправляет на `/admin/login`
- [ ] Неверный пароль — ошибка; верный — дашборд со счётчиками
- [ ] Роль `manager` не имеет доступа к `/admin/price-rules`, `/admin/catalog/*`, `/admin/users` (403)
- [ ] Роль `admin` имеет доступ ко всем разделам
- [ ] `/admin/leads` — список заявок, фильтры (кнопки «Применить» там, где они есть) работают
- [ ] Смена рабочего статуса заявки (`new`/`contacted`/`closed`) сохраняется
- [ ] Кнопка «Повторить отправку в Telegram» доступна и работает
- [ ] `/admin/price-rules` — изменённая цена **сразу** видна в калькуляторе и на странице каталога
- [ ] `/admin/catalog/categories` и `/admin/catalog/products` — правки отражаются на публичной странице
- [ ] Добавление и удаление характеристики и фото товара
- [ ] `/admin/users` — создание пользователя, деактивация (кроме самого себя)
- [ ] `/admin/audit` — действия выше появляются в журнале
- [ ] POST без верного `csrf_token` отклоняется
- [ ] Выход завершает сессию

### Очередь уведомлений (Redis/ARQ) — опционально
Без Redis (`REDIS_URL` пуст) уведомление отправляется напрямую при создании заявки.

**Как безопасно проверить очередь локально:**
```bash
docker run --rm -p 6379:6379 redis:7-alpine    # временный Redis только для проверки
```
В `.env` укажите `REDIS_URL=redis://localhost:6379/0`, перезапустите приложение и в отдельном терминале запустите
воркер:
```bash
arq worker.WorkerSettings
```
Создайте заявку без настроенного `TELEGRAM_BOT_TOKEN` — она уйдёт в очередь, воркер несколько раз повторит
попытку с нарастающей паузой и в конце выставит `telegram_status=failed` (видно в `/admin/leads/<id>`).
