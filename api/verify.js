import { kv } from '@vercel/kv';

export default async function handler(req, res) {
  const token = req.query.token || '';
  if (!token) return res.status(200).json({ valid: false });

  const session = await kv.get(`session:${token}`);
  return res.status(200).json({ valid: !!session });
}
