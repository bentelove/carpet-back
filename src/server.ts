import Fastify from 'fastify';
import cors from '@fastify/cors';
import swagger from '@fastify/swagger';
import swaggerUi from '@fastify/swagger-ui';
import { z } from 'zod';
import { cartRoutes } from './routes/cart.js';
import { productRoutes } from './routes/products.js';
import { favoriteRoutes } from './routes/favorites.js';
import { checkoutRoutes } from './routes/checkout.js';
import { adminRoutes } from './routes/admin.js';
import { db } from './lib.js';

export const app = Fastify({ logger: { redact: ['req.headers.authorization', 'req.body.phone', 'req.body.email', 'req.body.address'] } });

export async function register() {
  await app.register(cors, { origin: (process.env.CORS_ORIGINS || 'http://localhost:3000').split(',') });
  await app.register(swagger, { openapi: { info: { title: 'TÖPP API', version: '1.0.0' } } });
  await app.register(swaggerUi, { routePrefix: '/docs' });
  app.get('/health', async () => { await db.$queryRaw`SELECT 1`; return { status: 'ok' }; });
  app.setErrorHandler((error, request, reply) => {
    if (error instanceof z.ZodError) return reply.code(422).send({ error: { code: 'VALIDATION_ERROR', message: 'Некорректные данные', details: { fields: error.issues.map(issue => ({ field: issue.path.join('.'), reason: issue.code })) } } });
    request.log.error(error);
    return reply.code(500).send({ error: { code: 'INTERNAL_ERROR', message: 'Внутренняя ошибка сервера', details: {} } });
  });
  await app.register(productRoutes);
  await app.register(cartRoutes);
  await app.register(favoriteRoutes);
  await app.register(checkoutRoutes);
  await app.register(adminRoutes);
  return app;
}

if (process.env.NODE_ENV !== 'test') register().then(() => app.listen({ host: '0.0.0.0', port: Number(process.env.PORT || 8000) }));
