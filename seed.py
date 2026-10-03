"""Import confirmed catalog JSON: python seed.py path/to/products.json

Schema: [{"slug":"...","name":"...","description":"...","style":"modern",
"color":"...","colorCode":null,"countryCode":null,"images":[{"url":"https://...","alt":"..."}],
"badge":null,"variants":[{"sku":"...","sizeLabel":"...","sizeCode":"160x230",
"lengthCm":160,"widthCm":230,"diameterCm":null,"price":12990,"oldPrice":null,"stockQuantity":0}]}]
Stock must be confirmed; do not set demonstration stock in production.
"""
import json
import sys
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Product, Variant
from app.schemas import ProductInput, VariantInput


def seed(path):
    rows=json.load(open(path,encoding='utf8'))
    if not isinstance(rows,list): raise ValueError('Expected a JSON array')
    with SessionLocal.begin() as db:
        for row in rows:
            meta=ProductInput.model_validate({k:v for k,v in row.items() if k!='variants'})
            p=db.scalar(select(Product).where(Product.slug==meta.slug))
            if p: raise ValueError(f'duplicate/existing slug: {meta.slug}')
            p=Product(slug=meta.slug,name=meta.name,description=meta.description,style=meta.style,
                      color=meta.color,color_code=meta.colorCode,country_code=meta.countryCode,
                      images=[x.model_dump(mode='json') for x in meta.images],badge=meta.badge,is_active=meta.isActive)
            db.add(p);db.flush()
            for raw in row['variants']:
                v=VariantInput.model_validate(raw)
                db.add(Variant(product_id=p.id,sku=v.sku,size_label=v.sizeLabel,size_code=v.sizeCode,
                               length_cm=v.lengthCm,width_cm=v.widthCm,diameter_cm=v.diameterCm,
                               price=v.price,old_price=v.oldPrice,stock_quantity=v.stockQuantity,is_active=v.isActive))
    print(f'Imported {len(rows)} products')

if __name__=='__main__':
    if len(sys.argv)!=2: sys.exit('Usage: python seed.py products.json (confirmed source data required)')
    seed(sys.argv[1])
