# HTTPS для production

**Зачем это обязательно.** При `ENVIRONMENT=production` cookie админки выставляется с флагом `Secure`
(`https_only=True` в `main.py`). Браузер не принимает такую cookie по обычному HTTP, поэтому на реальном домене
без TLS **войти в админку невозможно**. (На `localhost`/`127.0.0.1` Chrome делает исключение — не обманывайтесь
проверкой на своей машине.)

## Что нужно заранее

- Домен с A-записью на сервер, открытые порты 80 и 443.
- Docker Compose v2, `certbot` на хосте (`apt install certbot`).

## Первый запуск

```bash
# 1. Конфиг: домен вместо example.com (server_name ×2, пути сертификата)
cp nginx/nginx.https.conf.example nginx/nginx.conf
sed -i 's/example\.com/ВАШ-ДОМЕН/g' nginx/nginx.conf

# 2. Переменные .env: ENVIRONMENT=production, DOMAIN=https://ВАШ-ДОМЕН,
#    уникальный ADMIN_SESSION_SECRET (приложение не стартует с дефолтным)

# 3. Сертификат. Nginx без файлов сертификата не стартует, поэтому первый раз — standalone (порт 80 свободен)
sudo certbot certonly --standalone -d ВАШ-ДОМЕН -d www.ВАШ-ДОМЕН

# 4. Запуск
mkdir -p certbot-www
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build
```

## Продление сертификата

Ежедневный cron (certbot продлевает только когда осталось < 30 дней):

```bash
0 4 * * *  certbot renew --webroot -w /путь/к/проекту/certbot-www --deploy-hook "docker compose -f /путь/к/проекту/docker-compose.yml -f /путь/к/проекту/docker-compose.tls.yml exec nginx nginx -s reload"
```

Для `renew --webroot` certbot запоминает способ выпуска; если сертификат выпускали через `--standalone`,
один раз переключите: `certbot certonly --webroot -w ./certbot-www -d ВАШ-ДОМЕН -d www.ВАШ-ДОМЕН --force-renewal`.

## HSTS

В конфиге стоит `max-age=300` (5 минут): браузер запоминает HSTS и после этого не пустит на HTTP. Убедитесь, что
сайт и админка работают по HTTPS, и только затем поднимите до `31536000` и перезагрузите Nginx.
`includeSubDomains` и `preload` добавляйте, лишь если все поддомены тоже на HTTPS.

## Проверка

```bash
curl -sI http://ВАШ-ДОМЕН/privacy | head -3          # 301 -> https
curl -sI https://ВАШ-ДОМЕН/ | grep -iE 'strict|content-security'
# В браузере: вход в /admin/login, консоль без ошибок CSP
```

## Если перед Nginx стоит CDN или балансировщик

`nginx.conf` перезаписывает `X-Forwarded-For` адресом соединения (`$remote_addr`) — это защищает rate limit от
подделки заголовка. Если у Nginx на входе CDN, `$remote_addr` будет адресом CDN, и все посетители снова станут
«одним клиентом». Тогда подключите `ngx_http_realip_module` (`set_real_ip_from <подсети CDN>;
real_ip_header X-Forwarded-For;`) — после него `$remote_addr` снова настоящий адрес клиента.
