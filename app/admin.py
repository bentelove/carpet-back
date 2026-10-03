from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .models import Product, Variant, Order
from .schemas import ProductInput, ProductPatch, VariantInput, VariantPatch, StatusIn
from .common import APIError, admin, product_out, variant_out
from .checkout import order_out

router = APIRouter(prefix='/api/v1/admin', dependencies=[Depends(admin)])

def save(db):
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise APIError(409,'DUPLICATE','Slug, SKU или другой уникальный идентификатор уже используется')

def product_or_404(db,id):
    p=db.get(Product,id)
    if not p: raise APIError(404,'NOT_FOUND','Товар не найден')
    return p

def variant_or_404(db,id):
    v=db.get(Variant,id)
    if not v: raise APIError(404,'NOT_FOUND','Вариант не найден')
    return v

def admin_product(db,p):
    result=product_out(db,p,True)
    result['variants']=[variant_out(v) for v in db.scalars(select(Variant).where(Variant.product_id==p.id)).all()]
    return result

@router.get('/products')
def products(db: Session=Depends(get_db)):
    return {'items':[admin_product(db,p) for p in db.scalars(select(Product).order_by(Product.slug)).all()]}

@router.get('/products/{id}')
def product_detail(id:str,db:Session=Depends(get_db)):
    return admin_product(db,product_or_404(db,id))

@router.post('/products',status_code=201)
def product_create(data:ProductInput,db:Session=Depends(get_db)):
    p=Product(slug=data.slug,name=data.name,description=data.description,style=data.style,color=data.color,
              color_code=data.colorCode,country_code=data.countryCode,images=[x.model_dump(mode='json') for x in data.images],
              badge=data.badge,is_active=data.isActive,popularity=data.popularity)
    db.add(p);save(db);return admin_product(db,p)

@router.patch('/products/{id}')
def product_patch(id:str,data:ProductPatch,db:Session=Depends(get_db)):
    p=product_or_404(db,id)
    mapping={'colorCode':'color_code','countryCode':'country_code','isActive':'is_active'}
    for key,value in data.model_dump(exclude_unset=True).items():
        if key=='images': value=[x.model_dump(mode='json') for x in data.images]
        setattr(p,mapping.get(key,key),value)
    save(db);return admin_product(db,p)

@router.delete('/products/{id}')
def product_delete(id:str,db:Session=Depends(get_db)):
    p=product_or_404(db,id);p.is_active=False;save(db);return admin_product(db,p)

@router.post('/products/{id}/variants',status_code=201)
def variant_create(id:str,data:VariantInput,db:Session=Depends(get_db)):
    product_or_404(db,id)
    v=Variant(product_id=id,sku=data.sku,size_label=data.sizeLabel,size_code=data.sizeCode,
              length_cm=data.lengthCm,width_cm=data.widthCm,diameter_cm=data.diameterCm,price=data.price,
              old_price=data.oldPrice,stock_quantity=data.stockQuantity,is_active=data.isActive)
    db.add(v);save(db);return variant_out(v)

@router.get('/variants/{id}')
def variant_detail(id:str,db:Session=Depends(get_db)):
    return variant_out(variant_or_404(db,id))

@router.patch('/variants/{id}')
def variant_patch(id:str,data:VariantPatch,db:Session=Depends(get_db)):
    v=variant_or_404(db,id)
    mapping={'sizeLabel':'size_label','sizeCode':'size_code','lengthCm':'length_cm','widthCm':'width_cm',
             'diameterCm':'diameter_cm','oldPrice':'old_price','stockQuantity':'stock_quantity','isActive':'is_active'}
    for key,value in data.model_dump(exclude_unset=True).items(): setattr(v,mapping.get(key,key),value)
    if v.old_price is not None and v.old_price<=v.price: raise APIError(422,'INVALID_PRICE','Старая цена должна быть больше текущей')
    if v.diameter_cm is not None and (v.length_cm is not None or v.width_cm is not None): raise APIError(422,'INVALID_SIZE','Неверные размеры')
    save(db);return variant_out(v)

@router.delete('/variants/{id}')
def variant_delete(id:str,db:Session=Depends(get_db)):
    v=variant_or_404(db,id);v.is_active=False;save(db);return variant_out(v)

@router.get('/orders')
def orders(page:int=Query(1,ge=1),limit:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    rows=db.scalars(select(Order).order_by(Order.created_at.desc()).offset((page-1)*limit).limit(limit)).all()
    return {'items':[order_out(o,True) for o in rows],'page':page,'limit':limit}

@router.get('/orders/{id}')
def order_detail(id:str,db:Session=Depends(get_db)):
    o=db.get(Order,id)
    if not o: raise APIError(404,'NOT_FOUND','Заказ не найден')
    return order_out(o,True)

@router.patch('/orders/{id}/status')
def status_change(id:str,data:StatusIn,db:Session=Depends(get_db)):
    o=db.execute(select(Order).where(Order.id==id).with_for_update()).scalar_one_or_none()
    if not o: raise APIError(404,'NOT_FOUND','Заказ не найден')
    allowed={'new':{'confirmed','cancelled'},'confirmed':{'fulfilled','cancelled'},'cancelled':set(),'fulfilled':set()}
    if data.status not in allowed[o.status]: raise APIError(409,'INVALID_STATUS_TRANSITION','Недопустимый переход статуса')
    if data.status=='cancelled':
        for item in sorted(o.items,key=lambda i:i.variant_id):
            v=db.execute(select(Variant).where(Variant.id==item.variant_id).with_for_update()).scalar_one_or_none()
            if v: v.stock_quantity+=item.quantity
    o.status=data.status;db.commit();return order_out(o,True)
