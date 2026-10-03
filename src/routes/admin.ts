import { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { db, admin, fail, productInput } from '../lib.js';

export async function adminRoutes(app: FastifyInstance) {
  app.post('/api/v1/admin/products', { preHandler: admin }, async (req: any, reply) => { const data = productInput.parse(req.body); const product = await db.product.create({ data }); return reply.code(201).send(product); });
  app.get('/api/v1/admin/orders', { preHandler: admin }, async () => ({ items: await db.order.findMany({ include: { items: true }, orderBy: { createdAt: 'desc' } }) }));
  app.get('/api/v1/admin/orders/:id', { preHandler: admin }, async (req: any, reply) => { const order = await db.order.findUnique({ where: { id: req.params.id }, include: { items: true } }); if (!order) return fail(reply, 404, 'NOT_FOUND', 'Заказ не найден'); return order; });
  app.patch('/api/v1/admin/orders/:id/status', { preHandler: admin }, async (req: any, reply) => {
    const status = z.object({ status: z.enum(['new', 'confirmed', 'cancelled', 'fulfilled']) }).parse(req.body).status;
    const order = await db.order.findUnique({ where: { id: req.params.id } });
    if (!order) return fail(reply, 404, 'NOT_FOUND', 'Заказ не найден');
    const allowed: Record<string, string[]> = { new: ['confirmed', 'cancelled'], confirmed: ['fulfilled', 'cancelled'], cancelled: [], fulfilled: [] };
    if (!allowed[order.status].includes(status)) return fail(reply, 409, 'INVALID_STATUS_TRANSITION', 'Недопустимый переход статуса');
    return db.order.update({ where: { id: order.id }, data: { status } });
  });
}
