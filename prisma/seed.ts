import { PrismaClient } from '@prisma/client';
const db = new PrismaClient();
async function main() { console.log('Seed is intentionally empty until the real lib/products.ts is provided.'); }
main().finally(() => db.$disconnect());
