import { kv } from '@vercel/kv';

export default async function handler(req, res) {
  const authHeader = req.headers.authorization || '';
  const token = authHeader.replace('Bearer ', '').trim();

  if (!token) return res.status(401).json({ success: false, message: '未授权' });
  const session = await kv.get(`admin:session:${token}`);
  if (!session) return res.status(401).json({ success: false, message: '会话已过期' });

  const users = await kv.lrange('registered_users', 0, -1);
  const list = users.map(u => typeof u === 'string' ? JSON.parse(u) : u);

  return res.status(200).json({ success: true, users: list });
}
