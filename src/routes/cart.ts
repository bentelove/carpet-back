import crypto from 'node:crypto';
import { FastifyInstance } from 'fastify';
import { db, cartOut, fail, hash, auth } from '../lib.js';
import { item } from '../lib.js';

export async function cartRoutes(app: FastifyInstance) {
  app.post('/api/v1/carts', async (_, reply) => {
    const token = crypto.randomBytes(32).toString('base64url');
    const cart = await db.cart.create({ data: { tokenHash: hash(token), expiresAt: new Date(Date.now() + Number(process.env.CART_TTL_DAYS || 30) * 86400000) } });
    return reply.code(201).send({ cartToken: token, expiresAt: cart.expiresAt.toISOString(), cart: await cartOut(cart.id) });
  });

  app.get('/api/v1/cart', { preHandler: auth }, async (req: any) => cartOut(req.cart.id));

  app.post('/api/v1/cart/items', { preHandler: auth }, async (req: any, reply) => {
    const data = item.parse(req.body);
    const variant = await db.variant.findUnique({ where: { id: data.variantId }, include: { product: true } });
    if (!variant || !variant.isActive || !variant.product.isActive) return fail(reply, 404, 'VARIANT_NOT_FOUND', 'Вариант недоступен');
    const current = await db.cartItem.findUnique({ where: { cartId_variantId: { cartId: req.cart.id, variantId: variant.id } } });
    const quantity = data.quantity + (current?.quantity || 0);
    if (quantity > variant.stockQuantity) return fail(reply, 409, 'INSUFFICIENT_STOCK', 'Недостаточно товара в наличии', { variantId: variant.id, available: variant.stockQuantity });
    await db.cartItem.upsert({ where: { cartId_variantId: { cartId: req.cart.id, variantId: variant.id } }, create: { cartId: req.cart.id, variantId: variant.id, quantity, unitPrice: variant.price }, update: { quantity } });
    return cartOut(req.cart.id);
  });

  app.patch('/api/v1/cart/items/:id', { preHandler: auth }, async (req: any, reply) => {
    const data = item.pick({ quantity: true }).parse(req.body);
    const current = await db.cartItem.findFirst({ where: { id: req.params.id, cartId: req.cart.id }, include: { variant: true } });
    if (!current) return fail(reply, 404, 'NOT_FOUND', 'Позиция не найдена');
    if (data.quantity > current.variant.stockQuantity) return fail(reply, 409, 'INSUFFICIENT_STOCK', 'Недостаточно товара в наличии', { available: current.variant.stockQuantity });
    await db.cartItem.update({ where: { id: current.id }, data: { quantity: data.quantity } });
    return cartOut(req.cart.id);
  });

  app.delete('/api/v1/cart/items/:id', { preHandler: auth }, async (req: any) => {
    await db.cartItem.deleteMany({ where: { id: req.params.id, cartId: req.cart.id } });
    return cartOut(req.cart.id);
  });
}
