# TÖPP backend — TypeScript

Стек зафиксирован: **TypeScript, Fastify 5, Prisma 6, PostgreSQL 16, Zod, Vitest**. API-контракт сохраняется под `/api/v1`; Swagger будет доступен на `/docs`, health — `/health`.

## Запуск

```sh
cp .env.example .env
# заполните ADMIN_PASSWORD_HASH bcrypt-хешем и замените локальные пароли
docker compose up --build
```

API: `http://localhost:8000`; OpenAPI UI: `http://localhost:8000/docs`. Без Docker: `npm ci && npx prisma generate && npx prisma migrate dev --name init && npm run dev`. Проверки: `npm test`, типы: `npm run lint`.

## Реализуемые правила

Каталог, фильтры, варианты, анонимная корзина с SHA-256 токеном на 30 суток, избранное, серверный расчёт RUB-сумм, quote, заказы с `Idempotency-Key`, снимки позиций, резервирование/списание остатков, статусы `new → confirmed → fulfilled` и отмена с возвратом остатков, защищённые admin-маршруты через Basic Auth + bcrypt. Все цены — целые рубли. Ошибки единообразны. CORS, лимиты и отсутствие персональных данных в логах обязательны.

`FREE_DELIVERY_THRESHOLD` и `DELIVERY_FEE` — предварительные настройки и должны быть подтверждены владельцем. Онлайн-оплата не реализована; доступны только `on_delivery` и `manual_confirmation`.

## Важное по каталогу

Реальный `lib/products.ts` не был доступен, поэтому seed намеренно пустой: цены, изображения, размеры, страны, цвета и остатки не выдумываются. После предоставления файла добавлю точный `prisma/seed.ts` для шести товаров.

Миграция Prisma создаётся командой `npx prisma migrate dev --name init` при доступной PostgreSQL и коммитится в `prisma/migrations`.

## Подключение к внешнему PostgreSQL с Mac (TLS)

Перед миграцией убедитесь, что база `carpet_shop` действительно предназначена для этого приложения, и создайте резервную копию. **Не запускайте `prisma migrate reset` или `prisma db push` на рабочей базе.** На вашем Mac выполните (пароль вводится интерактивно и не попадает в историю терминала):

```bash
git pull origin main
npm ci
test -f "$HOME/.cloud-certs/root.crt" || { echo 'TLS certificate not found'; exit 1; }
export PGSSLROOTCERT="$HOME/.cloud-certs/root.crt"
read -r -s 'DB_PASSWORD?PostgreSQL password: '; echo
# Если в пароле есть @, : или /, закодируйте его через encodeURIComponent;
# значение DATABASE_URL не выводите и не коммитьте.
export DATABASE_URL="$(DB_PASSWORD="$DB_PASSWORD" node -e 'const p=encodeURIComponent(process.env.DB_PASSWORD);process.stdout.write(`postgresql://gen_user:${p}@da00e417633ece4f103b84d5.twc1.net:5432/carpet_shop?sslmode=verify-full&sslrootcert=${encodeURIComponent(process.env.HOME+"/.cloud-certs/root.crt")}`)')"
unset DB_PASSWORD
npx prisma validate
npx prisma generate
npx prisma migrate status
# ONLY if the database is the correct target and migration status is expected:
npx prisma migrate deploy
npx prisma migrate status
npm run build
npm start
```

В отдельном терминале `curl -i http://localhost:8000/health` должен вернуть 200 (также проверяет запрос SELECT 1 к БД), затем проверьте `curl -i http://localhost:8000/api/v1/products` и `curl -i -X POST http://localhost:8000/api/v1/carts`. Сервис по умолчанию слушает порт 8000. На Mac можно использовать `npm run dev` вместо `npm start`. Переменные окружения сохраняются только в текущей сессии терминала. Дополнительные параметры TLS Prisma могут отличаться от libpq; при ошибке сертификата не переключайтесь на `sslmode=require` или `no-verify`, а проверьте путь к сертификату и документацию провайдера. Не делитесь паролем в чате — ранее отправленный пароль необходимо сменить у провайдера БД.

Текущий каталог пуст: реальные товары из `lib/products.ts` ещё не переданы. Перед заказами нужны проверки данных каталога, остатка, админ-доступа и интеграционные тесты.
