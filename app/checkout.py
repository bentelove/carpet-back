import hashlib
import json
from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db, iso_utc
from .models import Cart, CartItem, Order, OrderItem, Product, Variant
from .schemas import QuoteIn, OrderIn
from .common import APIError, THRESHOLD, DELIVERY_FEE, cart_auth, cart_out, delivery_cost

router = APIRouter(prefix='/api/v1')

@router.get('/checkout/options')
def options():
    return {'deliveryMethods':[{'code':'manual_delivery','name':'Доставка по согласованию с магазином'}],
            'paymentMethods':[{'code':'on_delivery','name':'Оплата при получении'}, {'code':'manual_confirmation','name':'Оплата по согласованию'}],
            'rules':{'currency':'RUB','freeDeliveryThreshold':THRESHOLD,'deliveryFee':DELIVERY_FEE,
                     'notice':'Стоимость и доступность доставки должны быть подтверждены магазином; тарифы MVP предварительные.'}}

@router.post('/checkout/quote')
def quote(data: QuoteIn, cart: Cart = Depends(cart_auth), db: Session = Depends(get_db)):
    result = cart_out(db,cart)
    if not result['items']: raise APIError(409,'EMPTY_CART','Корзина пуста')
    problems = [{'variantId':i['variantId'],'available':i['available'],'priceChanged':i['priceChanged']}
                for i in result['items'] if i['priceChanged'] or i['quantity']>i['available']]
    if problems: raise APIError(409,'CART_CHANGED','Цены или остатки изменились',{'items':problems})
    return {**result,'deliveryMethod':data.deliveryMethod,'address':data.address.model_dump()}

def order_out(order, private=False):
    data = dict(orderId=order.id,orderNumber=order.number,status=order.status,
                items=[dict(variantId=i.variant_id,name=i.product_name,sku=i.sku,sizeLabel=i.size_label,
                            unitPrice=i.unit_price,quantity=i.quantity,lineTotal=i.unit_price*i.quantity) for i in order.items],
                currency='RUB',subtotal=order.subtotal,delivery=order.delivery,total=order.total,
                deliveryMethod=order.delivery_method,paymentMethod=order.payment_method,createdAt=iso_utc(order.created_at))
    if private: data.update(customerName=order.customer_name,phone=order.phone,email=order.email,address=order.address,comment=order.comment)
    return data

@router.post('/orders', status_code=201)
def create_order(data: OrderIn, idempotency_key: str = Header(alias='Idempotency-Key',min_length=8,max_length=128),
                 cart: Cart = Depends(cart_auth), db: Session = Depends(get_db)):
    digest = hashlib.sha256(json.dumps(data.model_dump(mode='json'),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    # The cart row serializes check / create / replay for this anonymous shopper in PostgreSQL.
    db.execute(select(Cart).where(Cart.id==cart.id).with_for_update()).scalar_one()
    existing = db.scalar(select(Order).where(Order.cart_id==cart.id,Order.idempotency_key==idempotency_key))
    if existing:
        if existing.request_hash!=digest: raise APIError(409,'IDEMPOTENCY_CONFLICT','Ключ уже использован с другим запросом')
        return order_out(existing)
    lines = db.scalars(select(CartItem).where(CartItem.cart_id==cart.id).order_by(CartItem.variant_id)).all()
    if not lines: raise APIError(409,'EMPTY_CART','Корзина пуста')
    variants = {v.id:v for v in db.scalars(select(Variant).where(Variant.id.in_([i.variant_id for i in lines])).order_by(Variant.id).with_for_update()).all()}
    problems = []
    for line in lines:
        v=variants.get(line.variant_id); p=db.get(Product,v.product_id) if v else None
        if not v or not p or not v.is_active or not p.is_active or v.stock_quantity<line.quantity or v.price!=line.unit_price:
            problems.append({'variantId':line.variant_id,'available':v.stock_quantity if v and v.is_active and p and p.is_active else 0,
                             'expectedPrice':line.unit_price,'currentPrice':v.price if v else None})
    if problems: raise APIError(409,'CART_CHANGED','Цены или остатки изменились',{'items':problems})
    subtotal=sum(variants[i.variant_id].price*i.quantity for i in lines)
    delivery=delivery_cost(subtotal,data.deliveryMethod)
    order=Order(cart_id=cart.id,idempotency_key=idempotency_key,request_hash=digest,
                customer_name=data.customerName,phone=data.phone,email=str(data.email) if data.email else None,
                address=data.address.model_dump(),delivery_method=data.deliveryMethod,payment_method=data.paymentMethod,
                comment=data.comment,subtotal=subtotal,delivery=delivery,total=subtotal+delivery)
    db.add(order); db.flush()
    for line in lines:
        v=variants[line.variant_id]; p=db.get(Product,v.product_id)
        db.add(OrderItem(order_id=order.id,variant_id=v.id,product_name=p.name,sku=v.sku,
                         size_label=v.size_label,unit_price=v.price,quantity=line.quantity))
        v.stock_quantity-=line.quantity
        db.delete(line)
    db.commit(); db.refresh(order, ['items'])
    return order_out(order)
