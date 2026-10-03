import { FastifyReply, FastifyRequest } from 'fastify';
import crypto from 'node:crypto';
import bcrypt from 'bcryptjs';
import { PrismaClient } from '@prisma/client';
import { z } from 'zod';

export const db = new PrismaClient();
export const threshold = () => Number(process.env.FREE_DELIVERY_THRESHOLD || 10000);
export const fee = () => Number(process.env.DELIVERY_FEE || 500);
export const hash = (s: string) => crypto.createHash('sha256').update(s).digest('hex');
export const fail = (reply: FastifyReply, status: number, code: string, message: string, details: unknown = {}) => reply.code(status).send({ error: { code, message, details } });
export const address = z.object({ city: z.string().min(1).max(150), street: z.string().min(1).max(200), house: z.string().min(1).max(30), apartment: z.string().max(30).optional(), postalCode: z.string().regex(/^\d{6}$/).optional() });
export const item = z.object({ variantId: z.string().uuid(), quantity: z.number().int().min(1).max(100) });
export const orderInput = z.object({ customerName: z.string().min(2).max(150), phone: z.string().regex(/^\+?[0-9 ()-]{10,25}$/), email: z.string().email().optional(), address, deliveryMethod: z.literal('manual_delivery'), paymentMethod: z.enum(['on_delivery', 'manual_confirmation']), comment: z.string().max(2000).optional(), personalDataConsent: z.literal(true) });
export const productInput = z.object({ slug: z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/), name: z.string().min(1), description: z.string().default(''), style: z.string(), color: z.string(), colorCode: z.string().nullable().optional(), countryCode: z.string().regex(/^[A-Z]{2}$/).nullable().optional(), images: z.array(z.object({ url: z.string().url(), alt: z.string().min(1).max(200) })).max(20).default([]), badge: z.string().nullable().optional(), isActive: z.boolean().default(true), popularity: z.number().int().min(0).default(0) });

export function outProduct(p: any, detail = false) {
  const variants = (p.variants || []).filter((v: any) => v.isActive && v.stockQuantity > 0);
  return { id: p.id, slug: p.slug, name: p.name, description: p.description, style: p.style, color: p.color, colorCode: p.colorCode, countryCode: p.countryCode, images: p.images, badge: p.badge, isActive: p.isActive, priceFrom: variants.length ? Math.min(...variants.map((v: any) => v.price)) : null, currency: 'RUB', ...(detail ? { variants } : {}) };
}
export async function auth(req: FastifyRequest, reply: FastifyReply) {
  const value = req.headers.authorization;
  if (!value?.startsWith('Bearer ')) return fail(reply, 401, 'UNAUTHORIZED', 'Необходим токен корзины');
  const cart = await db.cart.findUnique({ where: { tokenHash: hash(value.slice(7)) } });
  if (!cart || cart.expiresAt <= new Date()) return fail(reply, 401, 'TOKEN_EXPIRED', 'Токен неизвестен или истёк');
  (req as any).cart = cart;
}
export async function cartOut(cartId: string) {
  const cart = await db.cart.findUnique({ where: { id: cartId }, include: { items: { include: { variant: { include: { product: true } } } } } });
  if (!cart) return null;
  const items = cart.items.map(i => ({ id: i.id, variantId: i.variantId, productSlug: i.variant.product.slug, name: i.variant.product.name, sizeLabel: i.variant.sizeLabel, image: (i.variant.product.images as any[])?.[0]?.url || null, unitPrice: i.variant.price, quantity: i.quantity, lineTotal: i.variant.price * i.quantity, priceChanged: i.unitPrice !== i.variant.price, available: i.variant.isActive && i.variant.product.isActive ? i.variant.stockQuantity : 0 }));
  const subtotal = items.reduce((sum, i) => sum + i.lineTotal, 0);
  const delivery = subtotal >= threshold() ? 0 : fee();
  return { items, currency: 'RUB', subtotal, delivery, total: subtotal + delivery, freeDeliveryThreshold: threshold(), amountToFreeDelivery: Math.max(0, threshold() - subtotal) };
}
export async function admin(req: FastifyRequest, reply: FastifyReply) {
  const value = req.headers.authorization;
  if (!value?.startsWith('Basic ')) return fail(reply, 401, 'UNAUTHORIZED', 'Требуется авторизация администратора');
  const [username, password] = Buffer.from(value.slice(6), 'base64').toString().split(':');
  if (username !== process.env.ADMIN_USERNAME || !process.env.ADMIN_PASSWORD_HASH || !bcrypt.compareSync(password, process.env.ADMIN_PASSWORD_HASH)) return fail(reply, 401, 'UNAUTHORIZED', 'Неверные учетные данные');
}
