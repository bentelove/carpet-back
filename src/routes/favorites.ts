import { FastifyInstance } from 'fastify';
import { db, auth, fail, outProduct } from '../lib.js';

export async function favoriteRoutes(app: FastifyInstance) {
  app.get('/api/v1/favorites', { preHandler: auth }, async (req: any) => list(req.cart.id));
  app.put('/api/v1/favorites/:productId', { preHandler: auth }, async (req: any, reply) => {
    const product = await db.product.findUnique({ where: { id: req.params.productId }, include: { variants: true } });
    if (!product || !product.isActive || !product.variants.some(v => v.isActive && v.stockQuantity > 0)) return fail(reply, 404, 'NOT_FOUND', 'Товар не найден');
    await db.favorite.upsert({ where: { cartId_productId: { cartId: req.cart.id, productId: product.id } }, create: { cartId: req.cart.id, productId: product.id }, update: {} });
    return list(req.cart.id);
  });
  app.delete('/api/v1/favorites/:productId', { preHandler: auth }, async (req: any) => { await db.favorite.deleteMany({ where: { cartId: req.cart.id, productId: req.params.productId } }); return list(req.cart.id); });
}
async function list(cartId: string) { const favorites = await db.favorite.findMany({ where: { cartId }, include: { product: { include: { variants: true } } } }); return { items: favorites.map(f => outProduct(f.product)).filter(p => p.priceFrom !== null) }; }
