# TÖPP — backend интернет-магазина ковров

Стек: Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL 16 (psycopg 3), Alembic, Pydantic 2, pytest. Структура: `app/db.py` и `app/models.py` — данные; `app/schemas.py` — входные схемы; `app/catalog.py`, `app/cart.py`, `app/checkout.py`, `app/admin.py` — маршруты; `alembic/` — миграции; `tests/` — проверки; `seed.py` — безопасный импорт подтвержденных товаров. REST API `/api/v1`, OpenAPI 3.x: `/docs`, `/openapi.json` и сохранённый `openapi.json`.

## Запуск локально

```sh
cp .env.example .env
# Создайте Argon2-хеш для нового пароля администратора:
python -c 'from argon2 import PasswordHasher; import getpass; print(PasswordHasher().hash(getpass.getpass()))'
# Если argon2 не установлен локально: сначала docker compose build api; затем docker compose run --rm --no-deps api python -c 'from argon2 import PasswordHasher; import getpass; print(PasswordHasher().hash(getpass.getpass()))'
# Вставьте результат в ADMIN_PASSWORD_HASH в .env **в одинарных кавычках** (например, `ADMIN_PASSWORD_HASH='$argon2id$...'`, чтобы Compose не интерполировал знаки `$`); задайте надежный POSTGRES_PASSWORD.
docker compose up --build -d
curl http://localhost:8000/health
```

API: http://localhost:8000; Swagger UI: http://localhost:8000/docs. Docker Compose автоматически ожидает PostgreSQL и запускает `alembic upgrade head`. При замене POSTGRES_PASSWORD после первого запуска обновите пароль в существующей БД или удалите локальный том командой `docker compose down -v` (УДАЛЯЕТ ДАННЫЕ). Применение миграций вручную: `docker compose run --rm migrate`. Тесты: `docker compose run --rm --no-deps -e DATABASE_URL=sqlite:////tmp/carpet_api_tests.db api pytest -q` (тесты используют SQLite независимо от переменной окружения). Без Docker: `pip install -q -r requirements.txt && DATABASE_URL=... alembic upgrade head && pytest -q`.

## Seed — важное ограничение

Точный `lib/products.ts` текущего фронтенда **не предоставлен**; в доступных репозиториях владельца его нет. Поэтому шесть реальных slug, названий, цен, URL изображений и основной размер НЕ выдуманы и НЕ включены как «реальные». Чтобы завершить первоначальное наполнение, предоставьте `lib/products.ts` и перенесите шесть товаров в JSON по схеме в `seed.py`; затем `docker compose run --rm -v "$PWD/products.json:/srv/products.json:ro" api python seed.py products.json`. Импорт проверяет данные, атомарен и отклоняет повторные slug. Не добавляйте неподтвержденные размеры; `countryCode`, `colorCode` допускают null, остатки подтверждаются владельцем (пока неизвестны, указывайте 0 — такие товары скрыты из публичного каталога). Не запускайте продажи до проверки цен, SKU, изображений, остатков и правил доставки.

## Маршруты и правила

Каталог: `GET /api/v1/products`, `GET /api/v1/products/{slug}`, `GET /api/v1/catalog/filters`. Только активные товары и активные варианты с остатком > 0. `size` — точное совпадение с `sizeCode` из фильтров; `lengthCm`/`widthCm` — точное совпадение обоих полей, если оба переданы; цены фильтруются по одному доступному варианту. `priceFrom` — минимальная цена подходящих вариантов в листинге и всех доступных вариантов в карточке. Сортировки: popular по редактируемому администратором `popularity` (по умолчанию 0, равенства по slug), newest по createdAt, price_asc/price_desc по минимальной подходящей цене, size по минимальной площади прямоугольного варианта (для круглых сортировочное значение — диаметр), discount по максимальной доле скидки среди подходящих вариантов. При равенстве — slug; страницы 1.., limit 1..100. Каталог в MVP сортируется в памяти, для большого каталога понадобится оптимизация запросов.

Корзина: `POST /api/v1/carts` выдаёт криптографически случайный токен (БД хранит только SHA-256); `GET /api/v1/cart`, `POST /api/v1/cart/items`, `PATCH /api/v1/cart/items/{itemId}`, `DELETE /api/v1/cart/items/{itemId}`. Избранное: `GET /api/v1/favorites`, `PUT/DELETE /api/v1/favorites/{productId}`. Все запросы, кроме создания корзины, требуют `Authorization: Bearer <cartToken>`. Токен действует **30 суток от выдачи**, не продлевается; после истечения корзина/избранное становятся недоступны; очистка старых записей — отдельная плановая задача. Повторное добавление варианта увеличивает количество. При изменении цены корзина показывает актуальную цену и `priceChanged`, но оформление блокируется 409 до ручного переподтверждения покупателем: удалите позицию и добавьте снова. Стоимость всегда вычисляется сервером.

Доставка: `GET /api/v1/checkout/options`, `POST /api/v1/checkout/quote`, `POST /api/v1/orders`. Предварительный тариф `manual_delivery`: 500 RUB для суммы < 10000 RUB, иначе 0; обе цифры настраиваются переменными окружения и **ТРЕБУЮТ подтверждения владельцем**. Адрес обязателен, но региональные ограничения/тарифы пока не автоматизированы: магазин вручную подтверждает возможность и окончательные условия; фронтенду нельзя обещать оплату картой онлайн или доставку по всей России. Оплата: `on_delivery` либо `manual_confirmation`, нет статуса «оплачено». Все суммы — целые рубли, currency RUB, временные метки UTC/ISO 8601.

Заказ требует `Idempotency-Key` (8..128 символов; уникален в рамках корзины). Повтор с тем же ключом и тем же телом возвращает тот же заказ; другое тело — 409. PostgreSQL блокирует корзину и варианты по id, проверяет цены/остатки и активность в одной транзакции, сохраняет снимок товаров и списывает остатки, после чего очищает корзину. Если цены/остатки изменились — 409, без списания и очистки. Статусы: `new → confirmed → fulfilled`, `new/confirmed → cancelled` (при отмене возвращается остаток); остальные переходы запрещены. Удаление товаров/вариантов через admin — мягкая деактивация, чтобы сохранить историю. Публичного endpoint для данных заказа нет.

Администрирование (HTTP Basic + Argon2-хеш пароля в переменной окружения; обязательно HTTPS вне локального окружения): `GET/POST /api/v1/admin/products`, `GET/PATCH/DELETE /api/v1/admin/products/{id}`, `POST /api/v1/admin/products/{id}/variants`, `PATCH/DELETE /api/v1/admin/variants/{id}`, `GET /api/v1/admin/orders`, `GET /api/v1/admin/orders/{id}`, `PATCH /api/v1/admin/orders/{id}/status`. Токен корзины не даёт доступ к админке. Логи содержат только метод, путь, статус и задержку; тексты запросов, токены, query string и персональные данные не записываются. CORS ограничен `CORS_ORIGINS` (по умолчанию localhost:3000). Ограничение создания корзин и заказов: 20 и 10 запросов/мин/IP на процесс; **в распределённой конфигурации нужен общий Redis/proxy rate limiter**, ограничения на уровне IP не заменяют защиту от злоупотреблений.

## Пример сценария

```sh
curl 'http://localhost:8000/api/v1/products?style=modern&sort=price_asc'
curl http://localhost:8000/api/v1/products/SLUG  # взять variants[0].id
curl -X POST http://localhost:8000/api/v1/carts  # сохранить cartToken
curl -X POST http://localhost:8000/api/v1/cart/items -H 'Authorization: Bearer TOKEN' -H 'Content-Type: application/json' -d '{"variantId":"UUID_ВАРИАНТА","quantity":1}'
curl -X POST http://localhost:8000/api/v1/checkout/quote -H 'Authorization: Bearer TOKEN' -H 'Content-Type: application/json' -d '{"address":{"city":"Москва","street":"Лесная","house":"1"},"deliveryMethod":"manual_delivery"}'
curl -X POST http://localhost:8000/api/v1/orders -H 'Authorization: Bearer TOKEN' -H 'Idempotency-Key: unique-attempt-001' -H 'Content-Type: application/json' -d '{"customerName":"Иван","phone":"+79991234567","address":{"city":"Москва","street":"Лесная","house":"1"},"deliveryMethod":"manual_delivery","paymentMethod":"on_delivery","personalDataConsent":true}'
```

Ошибки: `{"error":{"code":"CART_CHANGED","message":"...","details":{...}}}`; 401/404/409/422/429. Для продакшена: HTTPS, бэкапы БД, политика хранения и удаления ПД, организационные меры по 152-ФЗ, внешний rate limiting, мониторинг и подтвержденный процесс доставки/оплаты.
