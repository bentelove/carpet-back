import { z } from 'zod';
import { FastifyInstance } from 'fastify';
import { db, auth, fail, address, orderInput, threshold, fee, hash } from '../lib.js';

export async function checkoutRoutes(app: FastifyInstance) {
  app.get('/api/v1/checkout/options', async () => ({ deliveryMethods: [{ code: 'manual_delivery', name: 'Доставка по согласованию' }], paymentMethods: [{ code: 'on_delivery', name: 'Оплата при получении' }, { code: 'manual_confirmation', name: 'По согласованию' }], rules: { currency: 'RUB', freeDeliveryThreshold: threshold(), deliveryFee: fee() } }));
  app.post('/api/v1/checkout/quote', { preHandler: auth }, async (req: any, reply) => {
    const cart = await cartData(req.cart.id);
    if (!cart.items.length) return fail(reply, 409, 'EMPTY_CART', 'Корзина пуста');
    if (cart.items.some(i => i.priceChanged || i.quantity > i.available)) return fail(reply, 409, 'CART_CHANGED', 'Цены или остатки изменились');
    const data = zQuote.parse(req.body);
    return { ...cart, ...data };
  });
  app.post('/api/v1/orders', { preHandler: auth }, async (req: any, reply) => {
    const data = orderInput.parse(req.body);
    const key = req.headers['idempotency-key'];
    if (typeof key !== 'string' || key.length < 8) return fail(reply, 422, 'MISSING_IDEMPOTENCY_KEY', 'Требуется Idempotency-Key');
    const requestHash = hash(JSON.stringify(data));
    const existing = await db.order.findUnique({ where: { cartId_idempotencyKey: { cartId: req.cart.id, idempotencyKey: key } }, include: { items: true } });
    if (existing) { if (existing.requestHash !== requestHash) return fail(reply, 409, 'IDEMPOTENCY_CONFLICT', 'Ключ уже использован с другим запросом'); return reply.code(201).send(existing); }
    try {
      const order = await db.$transaction(async tx => {
        const lines = await tx.cartItem.findMany({ where: { cartId: req.cart.id }, include: { variant: { include: { product: true } } } });
        if (!lines.length) throw new Error('EMPTY_CART');
        for (const line of lines) if (!line.variant.isActive || !line.variant.product.isActive || line.variant.stockQuantity < line.quantity || line.unitPrice !== line.variant.price) throw new Error('CART_CHANGED');
        const subtotal = lines.reduce((sum, line) => sum + line.variant.price * line.quantity, 0), delivery = subtotal >= threshold() ? 0 : fee();
        const created = await tx.order.create({ data: { cartId: req.cart.id, idempotencyKey: key, requestHash, customerName: data.customerName, phone: data.phone, email: data.email, address: data.address, deliveryMethod: data.deliveryMethod, paymentMethod: data.paymentMethod, comment: data.comment, subtotal, delivery, total: subtotal + delivery, items: { create: lines.map(line => ({ variantId: line.variantId, productName: line.variant.product.name, sku: line.variant.sku, sizeLabel: line.variant.sizeLabel, unitPrice: line.variant.price, quantity: line.quantity })) } } });
        for (const line of lines) { await tx.variant.update({ where: { id: line.variantId }, data: { stockQuantity: { decrement: line.quantity } } }); await tx.cartItem.delete({ where: { id: line.id } }); }
        return created;
      });
      return reply.code(201).send(order);
    } catch (error: any) { if (error.message === 'EMPTY_CART') return fail(reply, 409, 'EMPTY_CART', 'Корзина пуста'); if (error.message === 'CART_CHANGED') return fail(reply, 409, 'CART_CHANGED', 'Цены или остатки изменились'); throw error; }
  });
}
const zQuote = z.object({ address, deliveryMethod: z.literal('manual_delivery') });
async function cartData(id: string) { const c = await db.cart.findUnique({ where: { id }, include: { items: { include: { variant: { include: { product: true } } } } } }); const items = (c?.items || []).map(i => ({ id: i.id, variantId: i.variantId, productSlug: i.variant.product.slug, name: i.variant.product.name, sizeLabel: i.variant.sizeLabel, image: (i.variant.product.images as any[])?.[0]?.url || null, unitPrice: i.variant.price, quantity: i.quantity, lineTotal: i.variant.price * i.quantity, priceChanged: i.unitPrice !== i.variant.price, available: i.variant.stockQuantity })); const subtotal = items.reduce((s, i) => s + i.lineTotal, 0), delivery = subtotal >= threshold() ? 0 : fee(); return { items, currency: 'RUB', subtotal, delivery, total: subtotal + delivery, freeDeliveryThreshold: threshold(), amountToFreeDelivery: Math.max(0, threshold() - subtotal) }; }
