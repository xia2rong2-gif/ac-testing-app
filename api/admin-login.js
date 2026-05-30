import { kv } from '@vercel/kv';

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ success: false, message: 'Method not allowed' });

  const { password } = req.body || {};
  if (!password || password !== process.env.ADMIN_PASSWORD) {
    return res.status(401).json({ success: false, message: '密码错误' });
  }

  const { randomBytes } = await import('node:crypto');
  const token = randomBytes(32).toString('hex');

  await kv.set(`admin:session:${token}`, JSON.stringify({ created_at: Date.now() }), { ex: 86400 });

  return res.status(200).json({ success: true, token });
}
