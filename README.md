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
