from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import Product, Variant
from .common import APIError, active_variants, product_out

router = APIRouter(prefix='/api/v1')

@router.get('/products')
def list_products(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                  style: str | None = None, colorCode: str | None = None, countryCode: str | None = None,
                  size: str | None = None, lengthCm: int | None = Query(None, gt=0), widthCm: int | None = Query(None, gt=0),
                  minPrice: int | None = Query(None, ge=0), maxPrice: int | None = Query(None, ge=0),
                  sort: str = Query('newest', pattern='^(popular|newest|price_asc|price_desc|size|discount)$'),
                  db: Session = Depends(get_db)):
    if minPrice is not None and maxPrice is not None and minPrice > maxPrice:
        raise APIError(422, 'INVALID_PRICE_RANGE', 'minPrice больше maxPrice')
    q = select(Product).where(Product.is_active.is_(True))
    if style: q = q.where(Product.style == style)
    if colorCode: q = q.where(Product.color_code == colorCode)
    if countryCode: q = q.where(Product.country_code == countryCode)
    rows = []
    for p in db.scalars(q).all():
        vs = active_variants(db, p)
        match = [v for v in vs if (size is None or v.size_code == size)
                 and (lengthCm is None or v.length_cm == lengthCm) and (widthCm is None or v.width_cm == widthCm)
                 and (minPrice is None or v.price >= minPrice) and (maxPrice is None or v.price <= maxPrice)]
        if match: rows.append((p, match))
    if sort == 'popular': rows.sort(key=lambda t: (-t[0].popularity, t[0].slug))
    elif sort == 'newest': rows.sort(key=lambda t: (-t[0].created_at.timestamp(), t[0].slug))
    elif sort == 'price_asc': rows.sort(key=lambda t: (min(v.price for v in t[1]), t[0].slug))
    elif sort == 'price_desc': rows.sort(key=lambda t: (-min(v.price for v in t[1]), t[0].slug))
    elif sort == 'size': rows.sort(key=lambda t: (min(v.diameter_cm or (v.length_cm or 0)*(v.width_cm or 0) for v in t[1]), t[0].slug))
    else: rows.sort(key=lambda t: (-max(((v.old_price-v.price)*100/v.old_price if v.old_price else 0) for v in t[1]), t[0].slug))
    total = len(rows)
    return dict(items=[{**product_out(db, p), 'priceFrom': min(v.price for v in vs)} for p,vs in rows[(page-1)*limit:page*limit]],
                page=page, limit=limit, total=total, totalPages=(total+limit-1)//limit)

@router.get('/catalog/filters')
def filters(db: Session = Depends(get_db)):
    products = db.scalars(select(Product).where(Product.is_active.is_(True))).all()
    entries = [(p, active_variants(db, p)) for p in products]
    entries = [(p,vs) for p,vs in entries if vs]
    prices = [v.price for _,vs in entries for v in vs]
    return dict(styles=sorted({p.style for p,_ in entries}), colors=sorted({p.color_code for p,_ in entries if p.color_code}),
                countries=sorted({p.country_code for p,_ in entries if p.country_code}),
                sizes=[dict(code=code,label=label) for code,label in sorted({(v.size_code,v.size_label) for _,vs in entries for v in vs})],
                minPrice=min(prices,default=None), maxPrice=max(prices,default=None), currency='RUB')

@router.get('/products/{slug}')
def product_detail(slug: str, db: Session = Depends(get_db)):
    p = db.scalar(select(Product).where(Product.slug == slug, Product.is_active.is_(True)))
    if not p or not active_variants(db,p): raise APIError(404, 'NOT_FOUND', 'Товар не найден')
    return product_out(db,p,True)
