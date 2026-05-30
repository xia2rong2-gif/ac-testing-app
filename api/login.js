import { kv } from '@vercel/kv';

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ success: false, message: 'Method not allowed' });

  const { code } = req.body || {};
  if (!code || typeof code !== 'string') return res.status(400).json({ success: false, message: '请输入邀请码' });

  const key = code.trim().toUpperCase();
  const record = await kv.hget('invite_codes', key);

  if (!record) return res.status(401).json({ success: false, message: '邀请码无效' });

  const codeData = typeof record === 'string' ? JSON.parse(record) : record;
  if (!codeData.is_active) return res.status(401).json({ success: false, message: '邀请码已失效' });
  if (codeData.used_count >= codeData.max_uses) return res.status(401).json({ success: false, message: '邀请码使用次数已达上限' });

  // Create session token
  const { randomBytes } = await import('node:crypto');
  const token = randomBytes(32).toString('hex');
  const session = { code_used: key, created_at: Date.now(), ip: req.headers['x-forwarded-for'] || req.socket.remoteAddress, user_agent: req.headers['user-agent'] || '' };

  await Promise.all([
    kv.set(`session:${token}`, JSON.stringify(session)),
    kv.hset('invite_codes', { [key]: JSON.stringify({ ...codeData, used_count: codeData.used_count + 1 }) }),
    kv.lpush('registered_users', JSON.stringify(session)),
  ]);

  return res.status(200).json({ success: true, token });
}
