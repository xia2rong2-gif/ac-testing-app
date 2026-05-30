import { kv } from '@vercel/kv';

function auth(token) {
  if (!token) return false;
  // Token-based auth: verify admin session
  return token && token.startsWith('admin_');
  // Real auth happens through session checking in each handler
}

export default async function handler(req, res) {
  const authHeader = req.headers.authorization || '';
  const token = authHeader.replace('Bearer ', '').trim();

  if (!token) return res.status(401).json({ success: false, message: '未授权' });
  const session = await kv.get(`admin:session:${token}`);
  if (!session) return res.status(401).json({ success: false, message: '会话已过期' });

  if (req.method === 'GET') {
    const codes = await kv.hgetall('invite_codes') || {};
    const list = Object.entries(codes).map(([code, data]) => {
      const d = typeof data === 'string' ? JSON.parse(data) : data;
      return { code, ...d };
    });
    return res.status(200).json({ success: true, codes: list });
  }

  if (req.method === 'POST') {
    const { max_uses } = req.body || {};
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    let newCode = '';
    for (let i = 0; i < 8; i++) newCode += chars[Math.floor(Math.random() * chars.length)];

    const codeData = { created_at: Date.now(), max_uses: max_uses || 3, used_count: 0, is_active: true };
    await kv.hset('invite_codes', { [newCode]: JSON.stringify(codeData) });

    return res.status(200).json({ success: true, code: newCode, ...codeData });
  }

  if (req.method === 'DELETE') {
    const { code } = req.body || {};
    if (!code) return res.status(400).json({ success: false, message: '缺少邀请码' });

    const record = await kv.hget('invite_codes', code);
    if (!record) return res.status(404).json({ success: false, message: '邀请码不存在' });
    const data = typeof record === 'string' ? JSON.parse(record) : record;

    await kv.hset('invite_codes', { [code]: JSON.stringify({ ...data, is_active: false }) });
    return res.status(200).json({ success: true });
  }

  return res.status(405).json({ success: false, message: 'Method not allowed' });
}
