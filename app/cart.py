import hashlib
import secrets
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db, iso_utc
from .models import Cart, CartItem, Favorite, Product, Variant
from .schemas import ItemIn, QuantityIn
from .common import APIError, cart_auth, cart_out, product_out, active_variants

router = APIRouter(prefix='/api/v1')

@router.post('/carts', status_code=201)
def create_cart(db: Session = Depends(get_db)):
    token = secrets.token_urlsafe(32)
    cart = Cart(token_hash=hashlib.sha256(token.encode()).hexdigest())
    db.add(cart); db.commit()
    return dict(cartToken=token, expiresAt=iso_utc(cart.expires_at), cart=cart_out(db, cart))

@router.get('/cart')
def get_cart(cart: Cart = Depends(cart_auth), db: Session = Depends(get_db)):
    return cart_out(db,cart)

def purchasable(db,variant_id):
    v = db.get(Variant, variant_id)
    if not v or not v.is_active or not db.get(Product,v.product_id).is_active:
        raise APIError(404,'VARIANT_NOT_FOUND','Вариант недоступен')
    return v

def stock(v, quantity):
    if quantity > v.stock_quantity: raise APIError(409,'INSUFFICIENT_STOCK','Недостаточно товара в наличии',{'variantId':v.id,'available':v.stock_quantity})

@router.post('/cart/items')
def add_item(data: ItemIn, cart: Cart = Depends(cart_auth), db: Session = Depends(get_db)):
    db.refresh(cart, ['items']); v = purchasable(db,data.variantId)
    existing = next((x for x in cart.items if x.variant_id == v.id),None)
    quantity = data.quantity + (existing.quantity if existing else 0)
    stock(v, quantity)
    if existing: existing.quantity = quantity
    else: db.add(CartItem(cart_id=cart.id,variant_id=v.id,quantity=quantity,unit_price=v.price))
    db.commit(); return cart_out(db,cart)

@router.patch('/cart/items/{item_id}')
def update_item(item_id: str, data: QuantityIn, cart: Cart = Depends(cart_auth), db: Session = Depends(get_db)):
    item = db.scalar(select(CartItem).where(CartItem.id==item_id,CartItem.cart_id==cart.id))
    if not item: raise APIError(404,'NOT_FOUND','Позиция не найдена')
    stock(purchasable(db,item.variant_id),data.quantity)
    item.quantity=data.quantity; db.commit(); return cart_out(db,cart)

@router.delete('/cart/items/{item_id}')
def delete_item(item_id: str, cart: Cart = Depends(cart_auth), db: Session = Depends(get_db)):
    item = db.scalar(select(CartItem).where(CartItem.id==item_id,CartItem.cart_id==cart.id))
    if not item: raise APIError(404,'NOT_FOUND','Позиция не найдена')
    db.delete(item); db.commit(); return cart_out(db,cart)

@router.get('/favorites')
def favorites(cart: Cart = Depends(cart_auth), db: Session = Depends(get_db)):
    ids = db.scalars(select(Favorite.product_id).where(Favorite.cart_id==cart.id)).all()
    return {'items':[product_out(db,p) for p in db.scalars(select(Product).where(Product.id.in_(ids),Product.is_active.is_(True))).all() if active_variants(db,p)]}

@router.put('/favorites/{product_id}')
def favorite_add(product_id: str, cart: Cart = Depends(cart_auth), db: Session = Depends(get_db)):
    p = db.get(Product,product_id)
    if not p or not p.is_active or not active_variants(db,p): raise APIError(404,'NOT_FOUND','Товар не найден')
    if not db.scalar(select(Favorite).where(Favorite.cart_id==cart.id,Favorite.product_id==product_id)):
        db.add(Favorite(cart_id=cart.id,product_id=product_id)); db.commit()
    return favorites(cart,db)

@router.delete('/favorites/{product_id}')
def favorite_delete(product_id: str, cart: Cart = Depends(cart_auth), db: Session = Depends(get_db)):
    f = db.scalar(select(Favorite).where(Favorite.cart_id==cart.id,Favorite.product_id==product_id))
    if f: db.delete(f); db.commit()
    return favorites(cart,db)
