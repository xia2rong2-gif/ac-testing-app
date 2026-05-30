'use strict';

/**
 * Tencent Cloud SCF handler for AC Testing API
 *
 * Deployment: Copy this entire file into SCF console editor
 * Environment variables to set:
 *   COS_BUCKET     - Your COS bucket name (e.g., ac-testing-1234567890)
 *   COS_REGION     - COS region (e.g., ap-guangzhou)
 *   COS_SECRET_ID  - Tencent Cloud API SecretId
 *   COS_SECRET_KEY - Tencent Cloud API SecretKey
 *   ADMIN_PASSWORD - Admin panel password (default: 4a1f026e8dd940b7)
 */

const crypto = require('crypto');
const https = require('https');

// ===== CONFIG =====
const CFG = {
  cosBucket:    process.env.COS_BUCKET || '',
  cosRegion:    process.env.COS_REGION || 'ap-guangzhou',
  cosSecretId:  process.env.COS_SECRET_ID || '',
  cosSecretKey: process.env.COS_SECRET_KEY || '',
  adminPw:      process.env.ADMIN_PASSWORD || '4a1f026e8dd940b7',
};

const COS_PATHS = {
  codes:  'kv/invite_codes.json',
  sess:   'kv/sessions.json',
  users:  'kv/registered_users.json',
};

// ===== HTTPS HELPER =====
function request(method, host, path, headers, body) {
  return new Promise((resolve, reject) => {
    const opts = {
      hostname: host, path, method,
      headers,
      timeout: 10000,
    };
    const req = https.request(opts, res => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve({ status: res.statusCode, body: data }));
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    if (body != null) req.write(body);
    req.end();
  });
}

// ===== COS HMAC-SHA1 SIGNING =====
function sign(method, cosPath, headers) {
  const now = Math.floor(Date.now() / 1000);
  const keyTime = `${now};${now + 86400}`;
  const signKey = crypto.createHmac('sha1', CFG.cosSecretKey).update(keyTime).digest('hex');

  const sortedKeys = Object.keys(headers).sort();
  const hdrList = sortedKeys.join(';').toLowerCase();
  const hdrStr = sortedKeys.map(k =>
    `${k.toLowerCase()}=${encodeURIComponent(headers[k])}`
  ).join('&');

  const httpStr = `${method.toLowerCase()}\n/${cosPath}\n\n${hdrStr}\n`;
  const hash = crypto.createHash('sha1').update(httpStr).digest('hex');
  const stringToSign = `sha1\n${keyTime}\n${hash}\n`;
  const sig = crypto.createHmac('sha1', signKey).update(stringToSign).digest('hex');

  return `q-sign-algorithm=sha1&q-ak=${CFG.cosSecretId}&q-sign-time=${keyTime}&q-key-time=${keyTime}&q-header-list=${hdrList}&q-url-param-list=&q-signature=${sig}`;
}

async function cosRead(cosPath) {
  const host = `${CFG.cosBucket}.cos.${CFG.cosRegion}.myqcloud.com`;
  const headers = { Host: host };
  const auth = sign('GET', cosPath, headers);
  const res = await request('GET', host, '/' + cosPath, { Authorization: auth });
  if (res.status === 404) return null;
  if (res.status !== 200) throw new Error(`COS GET ${cosPath} → ${res.status}`);
  return JSON.parse(res.body);
}

async function cosWrite(cosPath, data) {
  const host = `${CFG.cosBucket}.cos.${CFG.cosRegion}.myqcloud.com`;
  const body = JSON.stringify(data);
  const headers = {
    Host: host,
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body).toString(),
  };
  const auth = sign('PUT', cosPath, headers);
  const res = await request('PUT', host, '/' + cosPath, { ...headers, Authorization: auth }, body);
  if (res.status !== 200) throw new Error(`COS PUT ${cosPath} → ${res.status}`);
}

// ===== DATA ACCESS (read/write COS) =====
const getCodes = () => cosRead(COS_PATHS.codes).then(d => d || {});
const setCodes = d => cosWrite(COS_PATHS.codes, d);
const getSessions = () => cosRead(COS_PATHS.sess).then(d => d || {});
const setSessions = d => cosWrite(COS_PATHS.sess, d);
const getUsers = () => cosRead(COS_PATHS.users).then(d => d || []);
const setUsers = d => cosWrite(COS_PATHS.users, d);

// ===== ROUTE HANDLERS =====

async function login(body) {
  const code = (body.code || '').toUpperCase().trim();
  if (!code) return { success: false, message: '请输入邀请码' };

  const codes = await getCodes();
  const invite = codes[code];
  if (!invite) return { success: false, message: '邀请码无效' };
  if (!invite.is_active) return { success: false, message: '邀请码已失效' };
  if (invite.used_count >= invite.max_uses) return { success: false, message: '邀请码已达最大使用次数' };

  // Generate permanent token
  const token = [...Array(64)].map(() => Math.random().toString(36)[2] || 0).join('');

  codes[code].used_count++;
  await setCodes(codes);

  const sessions = await getSessions();
  sessions[token] = { code_used: code, token, created_at: Date.now() };
  await setSessions(sessions);

  const users = await getUsers();
  users.push({ code_used: code, token, created_at: Date.now() });
  await setUsers(users);

  return { success: true, token };
}

async function verify(headers) {
  const token = (headers.Authorization || headers.authorization || '').replace('Bearer ', '');
  if (!token) return { success: false };
  const sessions = await getSessions();
  return { success: !!sessions[token] };
}

async function adminLogin(body) {
  if (body.password !== CFG.adminPw) return { success: false, message: '密码错误' };

  const token = [...Array(64)].map(() => Math.random().toString(36)[2] || 0).join('');
  const sessions = await getSessions();
  sessions[token] = { is_admin: true, token, created_at: Date.now() };
  await setSessions(sessions);

  return { success: true, token };
}

function getToken(headers) {
  return (headers.Authorization || headers.authorization || '').replace('Bearer ', '');
}

async function requireAdmin(headers) {
  const token = getToken(headers);
  if (!token) return false;
  const sessions = await getSessions();
  return sessions[token]?.is_admin === true;
}

async function listCodes(headers) {
  if (!await requireAdmin(headers)) return { success: false, message: '未授权' };
  const codes = await getCodes();
  return { success: true, codes: Object.values(codes) };
}

async function createCode(body, headers) {
  if (!await requireAdmin(headers)) return { success: false, message: '未授权' };

  const code = (body.code || genCode()).toUpperCase();
  const maxUses = body.max_uses || 3;

  const codes = await getCodes();
  if (codes[code]) return { success: false, message: '邀请码已存在' };

  codes[code] = { code, is_active: true, max_uses: maxUses, used_count: 0, created_at: Date.now() };
  await setCodes(codes);

  return { success: true, code };
}

async function revokeCode(body, headers) {
  if (!await requireAdmin(headers)) return { success: false, message: '未授权' };

  const code = (body.code || '').toUpperCase();
  if (!code) return { success: false, message: '请指定邀请码' };

  const codes = await getCodes();
  if (!codes[code]) return { success: false, message: '邀请码不存在' };

  codes[code].is_active = false;
  await setCodes(codes);

  return { success: true };
}

async function listUsers(headers) {
  if (!await requireAdmin(headers)) return { success: false, message: '未授权' };
  const users = await getUsers();
  return { success: true, users };
}

function genCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  return [...Array(8)].map(() => chars[Math.floor(Math.random() * chars.length)]).join('');
}

// ===== MAIN ENTRY POINT =====
exports.main_handler = async (event) => {
  const cors = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
  };

  // OPTIONS preflight
  if (event.httpMethod === 'OPTIONS') {
    return { isBase64Encoded: false, statusCode: 204, headers: cors, body: '' };
  }

  const path = event.path || '';
  const method = event.httpMethod || 'GET';
  const body = event.body ? JSON.parse(event.body) : {};
  const headers = event.headers || {};

  // Check config
  if (!CFG.cosBucket) {
    return {
      isBase64Encoded: false, statusCode: 500,
      headers: { ...cors, 'Content-Type': 'application/json' },
      body: JSON.stringify({ success: false, message: 'COS_BUCKET 未配置' }),
    };
  }

  let result;
  try {
    const route = method + ' ' + path;
    switch (route) {
      case 'POST /api/login':          result = await login(body); break;
      case 'GET /api/verify':          result = await verify(headers); break;
      case 'POST /api/admin-login':    result = await adminLogin(body); break;
      case 'GET /api/admin/codes':     result = await listCodes(headers); break;
      case 'POST /api/admin/codes':    result = await createCode(body, headers); break;
      case 'DELETE /api/admin/codes':  result = await revokeCode(body, headers); break;
      case 'GET /api/admin/users':     result = await listUsers(headers); break;
      default:
        result = { success: false, message: 'Not found: ' + route };
    }
  } catch (err) {
    return {
      isBase64Encoded: false, statusCode: 500,
      headers: { ...cors, 'Content-Type': 'application/json' },
      body: JSON.stringify({ success: false, message: '服务器错误: ' + err.message }),
    };
  }

  return {
    isBase64Encoded: false,
    statusCode: result.success ? 200 : 400,
    headers: { ...cors, 'Content-Type': 'application/json' },
    body: JSON.stringify(result),
  };
};
