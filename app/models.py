import uuid
from datetime import timedelta
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base, utcnow

def uid(): return str(uuid.uuid4())

class Product(Base):
    __tablename__ = 'products'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text, default='')
    style: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(100))
    color_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    images: Mapped[list] = mapped_column(JSON, default=list)
    badge: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    popularity: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    variants: Mapped[list['Variant']] = relationship(back_populates='product', cascade='all, delete-orphan')

class Variant(Base):
    __tablename__ = 'variants'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), index=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True)
    size_label: Mapped[str] = mapped_column(String(100))
    size_code: Mapped[str] = mapped_column(String(100), index=True)
    length_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diameter_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[int] = mapped_column(Integer)
    old_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    product: Mapped[Product] = relationship(back_populates='variants')

class Cart(Base):
    __tablename__ = 'carts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=lambda: utcnow()+timedelta(days=30))
    items: Mapped[list['CartItem']] = relationship(back_populates='cart', cascade='all, delete-orphan')

class CartItem(Base):
    __tablename__ = 'cart_items'
    __table_args__ = (UniqueConstraint('cart_id', 'variant_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    cart_id: Mapped[str] = mapped_column(ForeignKey('carts.id'), index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey('variants.id'))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(Integer)
    cart: Mapped[Cart] = relationship(back_populates='items')
    variant: Mapped[Variant] = relationship()

class Favorite(Base):
    __tablename__ = 'favorites'
    __table_args__ = (UniqueConstraint('cart_id', 'product_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    cart_id: Mapped[str] = mapped_column(ForeignKey('carts.id'), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'))

class Order(Base):
    __tablename__ = 'orders'
    __table_args__ = (UniqueConstraint('cart_id', 'idempotency_key'), UniqueConstraint('number'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    number: Mapped[str] = mapped_column(String(36), default=uid)
    cart_id: Mapped[str] = mapped_column(ForeignKey('carts.id'))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default='new')
    customer_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    address: Mapped[dict] = mapped_column(JSON)
    delivery_method: Mapped[str] = mapped_column(String(50))
    payment_method: Mapped[str] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    subtotal: Mapped[int] = mapped_column(Integer)
    delivery: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    items: Mapped[list['OrderItem']] = relationship(back_populates='order', cascade='all, delete-orphan')

class OrderItem(Base):
    __tablename__ = 'order_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'))
    variant_id: Mapped[str] = mapped_column(String(36))
    product_name: Mapped[str] = mapped_column(String(250))
    sku: Mapped[str] = mapped_column(String(100))
    size_label: Mapped[str] = mapped_column(String(100))
    unit_price: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    order: Mapped[Order] = relationship(back_populates='items')
