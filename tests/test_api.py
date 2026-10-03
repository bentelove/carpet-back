import os
import uuid
from pathlib import Path
os.environ['DATABASE_URL']='sqlite:////tmp/carpet_api_tests.db'
os.environ['ADMIN_USERNAME']='admin'
from argon2 import PasswordHasher
os.environ['ADMIN_PASSWORD_HASH']=PasswordHasher().hash('test-secret')
import pytest
from fastapi.testclient import TestClient
from app.db import Base, engine, SessionLocal
from app.models import Product, Variant, Order
from app.main import app

client=TestClient(app)
AUTH=('admin','test-secret')

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    yield

def sample(slug,style,color,price,size='160x230',stock=5,popularity=0,old=None):
    with SessionLocal.begin() as db:
        p=Product(slug=slug,name=slug,style=style,color=color,color_code=color,images=[{'url':'https://example.com/rug.jpg','alt':'Ковер'}],popularity=popularity)
        db.add(p); db.flush()
        v=Variant(product_id=p.id,sku='sku-'+slug,size_label=size,size_code=size,length_cm=160,width_cm=230,price=price,old_price=old,stock_quantity=stock)
        db.add(v);db.flush();return p.id,v.id

def shopper():
    token=client.post('/api/v1/carts').json()['cartToken']
    return {'Authorization':'Bearer '+token}

def order_payload():
    return {'customerName':'Ivan Test','phone':'+79991234567','address':{'city':'Москва','street':'Тестовая','house':'1'},
            'deliveryMethod':'manual_delivery','paymentMethod':'on_delivery','personalDataConsent':True}

def test_catalog_filters_sort_and_nonexistent_size():
    sample('alpha','modern','sand',12000,popularity=3,old=15000)
    sample('beta','classic','blue',8000,size='200x300',popularity=10)
    assert client.get('/api/v1/products',params={'style':'modern'}).json()['total']==1
    assert client.get('/api/v1/products',params={'size':'nonexistent'}).json()['total']==0
    assert client.get('/api/v1/products',params={'colorCode':'blue'}).json()['items'][0]['slug']=='beta'
    assert client.get('/api/v1/products',params={'sort':'price_asc'}).json()['items'][0]['slug']=='beta'
    assert client.get('/api/v1/products',params={'sort':'popular'}).json()['items'][0]['slug']=='beta'
    assert client.get('/api/v1/products',params={'sort':'discount'}).json()['items'][0]['slug']=='alpha'
    assert client.get('/api/v1/catalog/filters').json()['sizes'][0]['code']=='160x230'

def test_cart_favorites_and_stock():
    pid,vid=sample('one','modern','sand',12990,stock=3)
    h=shopper()
    assert client.post('/api/v1/cart/items',headers=h,json={'variantId':str(uuid.uuid4()),'quantity':1}).status_code==404
    r=client.post('/api/v1/cart/items',headers=h,json={'variantId':vid,'quantity':1});assert r.json()['subtotal']==12990
    item=r.json()['items'][0]['id']
    assert client.post('/api/v1/cart/items',headers=h,json={'variantId':vid,'quantity':1}).json()['items'][0]['quantity']==2
    assert client.patch('/api/v1/cart/items/'+item,headers=h,json={'quantity':3}).json()['subtotal']==38970
    assert client.patch('/api/v1/cart/items/'+item,headers=h,json={'quantity':4}).json()['error']['code']=='INSUFFICIENT_STOCK'
    assert len(client.put('/api/v1/favorites/'+pid,headers=h).json()['items'])==1
    assert len(client.put('/api/v1/favorites/'+pid,headers=h).json()['items'])==1
    assert len(client.get('/api/v1/favorites',headers=h).json()['items'])==1
    assert client.delete('/api/v1/cart/items/'+item,headers=h).json()['subtotal']==0
    assert len(client.delete('/api/v1/favorites/'+pid,headers=h).json()['items'])==0

def test_order_idempotency_snapshot_and_conflicts():
    pid,vid=sample('rug','modern','sand',9000,stock=2)
    h=shopper();client.post('/api/v1/cart/items',headers=h,json={'variantId':vid,'quantity':1})
    assert client.post('/api/v1/checkout/quote',headers=h,json={'address':order_payload()['address'],'deliveryMethod':'manual_delivery'}).json()['total']==9500
    with SessionLocal.begin() as db: db.get(Variant,vid).price=9500
    changed=client.post('/api/v1/orders',headers={**h,'Idempotency-Key':'key-12345678'},json=order_payload())
    assert changed.status_code==409 and changed.json()['error']['code']=='CART_CHANGED'
    with SessionLocal.begin() as db: db.get(Variant,vid).price=9000
    r=client.post('/api/v1/orders',headers={**h,'Idempotency-Key':'key-12345678'},json=order_payload())
    assert r.status_code==201,r.text
    assert r.json()['items'][0]['unitPrice']==9000
    again=client.post('/api/v1/orders',headers={**h,'Idempotency-Key':'key-12345678'},json=order_payload())
    assert again.json()['orderId']==r.json()['orderId']
    assert client.post('/api/v1/orders',headers={**h,'Idempotency-Key':'another-key123'},json=order_payload()).status_code==409
    with SessionLocal.begin() as db:
        assert db.query(Order).count()==1
        assert db.get(Variant,vid).stock_quantity==1
        db.get(Variant,vid).price=12000
    assert client.get('/api/v1/admin/orders/'+r.json()['orderId'],auth=AUTH).json()['items'][0]['unitPrice']==9000
    assert client.get('/api/v1/admin/orders').status_code==401
    assert client.patch('/api/v1/admin/orders/'+r.json()['orderId']+'/status',auth=AUTH,json={'status':'fulfilled'}).status_code==409
    assert client.patch('/api/v1/admin/orders/'+r.json()['orderId']+'/status',auth=AUTH,json={'status':'cancelled'}).status_code==200
    with SessionLocal() as db: assert db.get(Variant,vid).stock_quantity==2

def test_admin_validation_and_public_privacy():
    assert client.post('/api/v1/admin/products',json={}).status_code==401
    body={'slug':'test-rug','name':'Тест','style':'modern','color':'Песочный','images':[{'url':'https://example.com/1.jpg','alt':'Тест'}]}
    p=client.post('/api/v1/admin/products',auth=AUTH,json=body)
    assert p.status_code==201,p.text
    v=client.post('/api/v1/admin/products/'+p.json()['id']+'/variants',auth=AUTH,json={'sku':'SKU','sizeLabel':'160x230','sizeCode':'160x230','price':100,'stockQuantity':1})
    assert v.status_code==201,v.text
    assert client.get('/api/v1/products/test-rug').json()['variants'][0]['price']==100
    assert client.delete('/api/v1/admin/products/'+p.json()['id'],auth=AUTH).status_code==200
    assert client.get('/api/v1/products/test-rug').status_code==404
    assert client.get('/api/v1/orders').status_code==405


def test_bad_consent_insufficient_stock_and_idempotency_reuse():
    _,vid=sample('limited','modern','blue',100,stock=1)
    h=shopper()
    client.post('/api/v1/cart/items',headers=h,json={'variantId':vid,'quantity':1})
    payload=order_payload()
    payload['personalDataConsent']=False
    assert client.post('/api/v1/orders',headers={**h,'Idempotency-Key':'unique-key-100'},json=payload).status_code==422
    payload['personalDataConsent']=True
    with SessionLocal.begin() as db: db.get(Variant,vid).stock_quantity=0
    r=client.post('/api/v1/orders',headers={**h,'Idempotency-Key':'unique-key-100'},json=payload)
    assert r.status_code==409 and r.json()['error']['details']['items'][0]['available']==0
    with SessionLocal.begin() as db: db.get(Variant,vid).stock_quantity=1
    r=client.post('/api/v1/orders',headers={**h,'Idempotency-Key':'unique-key-100'},json=payload)
    assert r.status_code==201
    payload['comment']='different request'
    assert client.post('/api/v1/orders',headers={**h,'Idempotency-Key':'unique-key-100'},json=payload).json()['error']['code']=='IDEMPOTENCY_CONFLICT'
    order_id=r.json()['orderId']
    assert client.patch('/api/v1/admin/orders/'+order_id+'/status',auth=AUTH,json={'status':'confirmed'}).json()['status']=='confirmed'
    assert client.patch('/api/v1/admin/orders/'+order_id+'/status',auth=AUTH,json={'status':'fulfilled'}).json()['status']=='fulfilled'
    assert client.patch('/api/v1/admin/orders/'+order_id+'/status',auth=AUTH,json={'status':'cancelled'}).status_code==409


def test_rate_limit_carts(monkeypatch):
    from app.main import limits
    limits.clear();monkeypatch.setenv('CART_RATE_PER_MINUTE','1')
    assert client.post('/api/v1/carts').status_code==201
    r=client.post('/api/v1/carts')
    assert r.status_code==429 and r.json()['error']['code']=='RATE_LIMITED'
    limits.clear()
