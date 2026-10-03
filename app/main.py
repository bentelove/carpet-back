import json
import logging
import os
import time
from collections import defaultdict, deque
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from .db import engine
from .common import APIError
from . import catalog, cart, checkout, admin

logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'),format='%(message)s')
logger=logging.getLogger('carpet')
app=FastAPI(title='TÖPP API',version='1.0.0',description='REST API интернет-магазина ковров; цены в целых рублях. /docs для интерактивного OpenAPI.')
origins=[x.strip() for x in os.getenv('CORS_ORIGINS','http://localhost:3000').split(',') if x.strip()]
if '*' in origins: raise RuntimeError('CORS_ORIGINS cannot contain wildcard')
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,allow_methods=['GET','POST','PATCH','PUT','DELETE'],allow_headers=['Authorization','Content-Type','Idempotency-Key'])
limits=defaultdict(deque)

@app.middleware('http')
async def request_log_and_limit(request:Request,call_next):
    start=time.monotonic()
    # No body, token, query string or client-provided personal data in logs.
    kind = 'cart' if request.method=='POST' and request.url.path=='/api/v1/carts' else 'order' if request.method=='POST' and request.url.path=='/api/v1/orders' else None
    if kind:
        key=(kind,request.client.host if request.client else 'unknown')
        now=time.monotonic(); q=limits[key]
        while q and q[0]<now-60: q.popleft()
        cap=int(os.getenv('CART_RATE_PER_MINUTE','20') if kind=='cart' else os.getenv('ORDER_RATE_PER_MINUTE','10'))
        if len(q)>=cap:
            return JSONResponse(status_code=429,content={'error':{'code':'RATE_LIMITED','message':'Слишком много запросов','details':{}}},headers={'Retry-After':'60'})
        q.append(now)
    response=await call_next(request)
    logger.info(json.dumps({'method':request.method,'path':request.url.path,'status':response.status_code,'durationMs':round((time.monotonic()-start)*1000)},ensure_ascii=False))
    return response

@app.exception_handler(HTTPException)
async def http_error(request:Request,exc:HTTPException):
    if isinstance(exc.detail,dict) and 'code' in exc.detail: error=exc.detail
    else: error={'code':'HTTP_ERROR','message':str(exc.detail),'details':{}}
    return JSONResponse(status_code=exc.status_code,content={'error':error},headers=exc.headers)

@app.exception_handler(RequestValidationError)
async def validation_error(request:Request,exc:RequestValidationError):
    # Don't include input values (can contain personal data) in responses/logs.
    details=[{'field':'.'.join(map(str,e['loc'])),'reason':e['type']} for e in exc.errors()]
    return JSONResponse(status_code=422,content={'error':{'code':'VALIDATION_ERROR','message':'Некорректные данные','details':{'fields':details}}})

@app.get('/health')
def health():
    with engine.connect() as conn: conn.execute(text('SELECT 1'))
    return {'status':'ok'}

for router in (catalog.router,cart.router,checkout.router,admin.router): app.include_router(router)

# Keep the served OpenAPI contract and the checked-in specification identical.
def checked_in_openapi():
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parent.parent / 'openapi.json').read_text(encoding='utf8'))

app.openapi = checked_in_openapi
