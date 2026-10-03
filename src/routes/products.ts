import { FastifyInstance } from 'fastify';
import { db, fail, outProduct } from '../lib.js';

export async function productRoutes(app: FastifyInstance) {
  app.get('/api/v1/products', async (req: any) => {
    const query = req.query as any;
    const products = await db.product.findMany({ where: { isActive: true }, include: { variants: true } });
    let rows = products.map(product => [product, product.variants.filter(variant => variant.isActive && variant.stockQuantity > 0).filter(variant => (!query.style || product.style === query.style) && (!query.colorCode || product.colorCode === query.colorCode) && (!query.countryCode || product.countryCode === query.countryCode) && (!query.size || variant.sizeCode === query.size) && (!query.lengthCm || variant.lengthCm === +query.lengthCm) && (!query.widthCm || variant.widthCm === +query.widthCm) && (!query.minPrice || variant.price >= +query.minPrice) && (!query.maxPrice || variant.price <= +query.maxPrice))] as const).filter(([, variants]) => variants.length);
    const sort = query.sort || 'newest';
    rows.sort(([a, av], [b, bv]) => sort === 'popular' ? b.popularity - a.popularity : sort === 'price_asc' ? Math.min(...av.map(v => v.price)) - Math.min(...bv.map(v => v.price)) : sort === 'price_desc' ? Math.min(...bv.map(v => v.price)) - Math.min(...av.map(v => v.price)) : sort === 'discount' ? Math.max(...bv.map(v => v.oldPrice ? (v.oldPrice - v.price) / v.oldPrice : 0)) - Math.max(...av.map(v => v.oldPrice ? (v.oldPrice - v.price) / v.oldPrice : 0)) : b.createdAt.getTime() - a.createdAt.getTime());
    const page = Math.max(1, +(query.page || 1));
    const limit = Math.min(100, Math.max(1, +(query.limit || 20)));
    return { items: rows.slice((page - 1) * limit, page * limit).map(([product]) => outProduct(product)), page, limit, total: rows.length, totalPages: Math.ceil(rows.length / limit) };
  });

  app.get('/api/v1/products/:slug', async (req: any, reply) => {
    const product = await db.product.findUnique({ where: { slug: req.params.slug }, include: { variants: true } });
    if (!product || !product.isActive || !product.variants.some(v => v.isActive && v.stockQuantity > 0)) return fail(reply, 404, 'NOT_FOUND', 'Товар не найден');
    return outProduct(product, true);
  });

  app.get('/api/v1/catalog/filters', async () => {
    const products = await db.product.findMany({ where: { isActive: true }, include: { variants: true } });
    const variants = products.flatMap(p => p.variants.filter(v => v.isActive && v.stockQuantity > 0));
    return { styles: [...new Set(products.map(p => p.style))].sort(), colors: [...new Set(products.map(p => p.colorCode).filter(Boolean))].sort(), countries: [...new Set(products.map(p => p.countryCode).filter(Boolean))].sort(), sizes: [...new Map(variants.map(v => [v.sizeCode, { code: v.sizeCode, label: v.sizeLabel }])).values()], minPrice: variants.length ? Math.min(...variants.map(v => v.price)) : null, maxPrice: variants.length ? Math.max(...variants.map(v => v.price)) : null, currency: 'RUB' };
  });
}
