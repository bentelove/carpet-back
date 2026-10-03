import hashlib
import os
import secrets
from datetime import timezone
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session
from argon2 import PasswordHasher, exceptions
from .db import get_db, utcnow, iso_utc
from .models import Cart, Product, Variant

THRESHOLD = int(os.getenv('FREE_DELIVERY_THRESHOLD', '10000'))
DELIVERY_FEE = int(os.getenv('DELIVERY_FEE', '500'))
security = HTTPBasic(auto_error=False)

class APIError(HTTPException):
    def __init__(self, status_code, code, message, details=None):
        super().__init__(status_code, {'code': code, 'message': message, 'details': details or {}})

def admin(credentials: HTTPBasicCredentials | None = Depends(security)):
    username = os.getenv('ADMIN_USERNAME', '')
    password_hash = os.getenv('ADMIN_PASSWORD_HASH', '')
    if not credentials or not username or not password_hash:
        raise APIError(401, 'UNAUTHORIZED', 'Требуется авторизация администратора')
    valid_user = secrets.compare_digest(credentials.username, username)
    try: valid_password = PasswordHasher().verify(password_hash, credentials.password)
    except (exceptions.VerificationError, exceptions.InvalidHashError): valid_password = False
    if not valid_user or not valid_password:
        raise APIError(401, 'UNAUTHORIZED', 'Неверные учетные данные')
    return username

def cart_auth(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Cart:
    if not authorization or not authorization.startswith('Bearer ') or len(authorization.split()) != 2:
        raise APIError(401, 'UNAUTHORIZED', 'Необходим токен корзины')
    token = authorization.split()[1]
    cart = db.scalar(select(Cart).where(Cart.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if cart is None or cart.expires_at.replace(tzinfo=timezone.utc) <= utcnow():
        raise APIError(401, 'TOKEN_EXPIRED', 'Токен неизвестен или истёк')
    return cart

def active_variants(db, product):
    return db.scalars(select(Variant).where(Variant.product_id == product.id, Variant.is_active.is_(True), Variant.stock_quantity > 0).order_by(Variant.price, Variant.id)).all()

def product_out(db, product, detail=False):
    variants = active_variants(db, product)
    data = dict(id=product.id, slug=product.slug, name=product.name, description=product.description,
                style=product.style, color=product.color, colorCode=product.color_code,
                countryCode=product.country_code, images=product.images, badge=product.badge,
                isActive=product.is_active, createdAt=iso_utc(product.created_at), updatedAt=iso_utc(product.updated_at),
                priceFrom=min((v.price for v in variants), default=None), currency='RUB')
    if detail: data['variants'] = [variant_out(v) for v in variants]
    return data

def variant_out(v):
    return dict(id=v.id, productId=v.product_id, sku=v.sku, sizeLabel=v.size_label,
                sizeCode=v.size_code, lengthCm=v.length_cm, widthCm=v.width_cm, diameterCm=v.diameter_cm,
                price=v.price, oldPrice=v.old_price, stockQuantity=v.stock_quantity, isActive=v.is_active)

def delivery_cost(subtotal, method='manual_delivery'):
    if method != 'manual_delivery': raise APIError(422, 'INVALID_DELIVERY_METHOD', 'Неизвестный способ доставки')
    return 0 if subtotal >= THRESHOLD else DELIVERY_FEE

def cart_out(db, cart):
    db.refresh(cart, ['items'])
    lines = []
    for item in cart.items:
        v = db.get(Variant, item.variant_id)
        p = db.get(Product, v.product_id)
        lines.append(dict(id=item.id, variantId=v.id, productSlug=p.slug, name=p.name, sizeLabel=v.size_label,
                          image=p.images[0]['url'] if p.images else None, unitPrice=v.price,
                          quantity=item.quantity, lineTotal=v.price * item.quantity,
                          priceChanged=v.price != item.unit_price, available=v.stock_quantity if v.is_active and p.is_active else 0))
    subtotal = sum(x['lineTotal'] for x in lines)
    delivery = delivery_cost(subtotal)
    return dict(items=lines, currency='RUB', subtotal=subtotal, delivery=delivery, total=subtotal+delivery,
                freeDeliveryThreshold=THRESHOLD, amountToFreeDelivery=max(0, THRESHOLD-subtotal))
