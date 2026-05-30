/**
 * 腾讯云函数 SCF Handler — 邀请码授权系统 API
 *
 * 部署方式：
 * 1. 腾讯云 → 云函数 → 新建（Node.js 18+）
 * 2. 环境变量设置：
 *    - ADMIN_PASSWORD: 管理员密码
 *    - COS_BUCKET: COS 存储桶名称
 *    - COS_REGION: COS 地区 (如 ap-guangzhou)
 * 3. 触发器 → API 网关 → 新建 API（启用 CORS）
 * 4. 本文件直接粘贴到函数代码中（零依赖，无需 npm）
 *
 * 数据存储:
 * - COS 上的 3 个 JSON 文件模拟 KV 存储
 * - kv/invite_codes.json: { "CODE": {created_at, max_uses, used_count, is_active} }
 * - kv/sessions.json: { "session:TOKEN": {code_used, created_at}, "admin:session:TOKEN": {...} }
 * - kv/registered_users.json: [{code_used, created_at, ip, user_agent}]
 */

const crypto = require('crypto');
const https = require('https');

/* ============================================================
 * Config
 * ============================================================ */
const BUCKET = process.env.COS_BUCKET || '';
const REGION = process.env.COS_REGION || '';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || '';

/* ============================================================
 * COS REST API — 零依赖实现
 * ============================================================ */
function getCosEndpoint() {
  return `${BUCKET}.cos.${REGION}.myqcloud.com`;
}

function getCosCredentials() {
  return {
    secretId: process.env.TENCENTCLOUD_SECRETID || '',
    secretKey: process.env.TENCENTCLOUD_SECRETKEY || '',
    token: process.env.TENCENTCLOUD_SESSIONTOKEN || '',
  };
}

function hmacSha1(key, data) {
  return crypto.createHmac('sha1', key).update(data, 'utf8').digest('hex');
}

function sha1Hex(str) {
  return crypto.createHash('sha1').update(str, 'utf8').digest('hex');
}

function buildCosAuth(method, path, creds, keyTime) {
  const headers = {
    'host': getCosEndpoint(),
    'x-cos-security-token': creds.token,
  };
  const signedHeaders = 'host;x-cos-security-token';

  const headerStr = 'host=' + headers['host'].toLowerCase() + '&x-cos-security-token=' + encodeURIComponent(headers['x-cos-security-token']);

  const httpString = method + '\n' + path + '\n\n' + headerStr + '\n' + signedHeaders + '\n';

  const signKey = hmacSha1(creds.secretKey, keyTime);
  const stringToSign = 'sha1\n' + keyTime + '\n' + sha1Hex(httpString) + '\n';
  const signature = hmacSha1(signKey, stringToSign);

  return {
    Authorization: 'q-sign-algorithm=sha1&q-ak=' + creds.secretId +
      '&q-sign-time=' + keyTime + '&q-key-time=' + keyTime +
      '&q-header-list=' + signedHeaders + '&q-url-param-list=&q-signature=' + signature,
    'x-cos-security-token': creds.token,
  };
}

function cosRequest(method, cosPath, body) {
  return new Promise((resolve, reject) => {
    const creds = getCosCredentials();
    const now = Math.floor(Date.now() / 1000);
    const keyTime = now + ';' + (now + 3600);
    const authHeaders = buildCosAuth(method, cosPath, creds, keyTime);

    const options = {
      hostname: getCosEndpoint(),
      path: cosPath,
      method: method,
      headers: {
        ...authHeaders,
      },
    };

    if (body) {
      options.headers['Content-Type'] = 'application/json';
      options.headers['Content-Length'] = Buffer.byteLength(body, 'utf8');
    }

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve({ status: res.statusCode, body: data });
        } else if (res.statusCode === 404) {
          resolve({ status: 404, body: data });
        } else {
          reject(new Error(`COS ${method} ${cosPath} failed: ${res.statusCode} ${data}`));
        }
      });
    });
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

async function cosGetJson(cosPath) {
  try {
    const res = await cosRequest('GET', cosPath);
    return JSON.parse(res.body);
  } catch (err) {
    if (err.message && err.message.includes('404')) return null;
    throw err;
  }
}

async function cosPutJson(cosPath, data) {
  const body = JSON.stringify(data);
  await cosRequest('PUT', cosPath, body);
}

/* ============================================================
 * KV Operations (backed by COS JSON files)
 * ============================================================ */
async function getInviteCodes() {
  const data = await cosGetJson('/kv/invite_codes.json');
  return data || {};
}

async function saveInviteCodes(codes) {
  await cosPutJson('/kv/invite_codes.json', codes);
}

async function getSessions() {
  const data = await cosGetJson('/kv/sessions.json');
  return data || {};
}

async function saveSessions(sessions) {
  await cosPutJson('/kv/sessions.json', sessions);
}

async function getRegisteredUsers() {
  const data = await cosGetJson('/kv/registered_users.json');
  return data || [];
}

async function saveRegisteredUsers(users) {
  await cosPutJson('/kv/registered_users.json', users);
}

/* ============================================================
 * CORS Headers
 * ============================================================ */
const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  'Content-Type': 'application/json; charset=utf-8',
};

function corsResponse(statusCode, body) {
  return {
    isBase64Encoded: false,
    statusCode,
    headers: CORS_HEADERS,
    body: JSON.stringify(body),
  };
}

/* ============================================================
 * Handlers
 * ============================================================ */

// POST /api/login
async function handleLogin(body) {
  const { code } = body || {};
  if (!code || typeof code !== 'string') {
    return corsResponse(400, { success: false, message: '请输入邀请码' });
  }

  const key = code.trim().toUpperCase();
  const inviteCodes = await getInviteCodes();
  const record = inviteCodes[key];

  if (!record) return corsResponse(401, { success: false, message: '邀请码无效' });

  if (!record.is_active) return corsResponse(401, { success: false, message: '邀请码已失效' });
  if (record.used_count >= record.max_uses) {
    return corsResponse(401, { success: false, message: '邀请码使用次数已达上限' });
  }

  const token = crypto.randomBytes(32).toString('hex');
  const session = {
    code_used: key,
    created_at: Date.now(),
    ip: body._sourceIp || '',
    user_agent: body._userAgent || '',
  };

  // Update used count
  inviteCodes[key] = { ...record, used_count: record.used_count + 1 };

  // Save session
  const sessions = await getSessions();
  sessions['session:' + token] = session;

  // Log user
  const users = await getRegisteredUsers();
  users.push(session);

  // All writes in parallel
  await Promise.all([
    saveInviteCodes(inviteCodes),
    saveSessions(sessions),
    saveRegisteredUsers(users),
  ]);

  return corsResponse(200, { success: true, token });
}

// GET /api/verify
async function handleVerify(query) {
  const token = (query && query.token) || '';
  if (!token) return corsResponse(200, { valid: false });

  const sessions = await getSessions();
  const session = sessions['session:' + token];
  return corsResponse(200, { valid: !!session });
}

// POST /api/admin-login
async function handleAdminLogin(body) {
  const { password } = body || {};
  if (!password || password !== ADMIN_PASSWORD) {
    return corsResponse(401, { success: false, message: '密码错误' });
  }

  const token = crypto.randomBytes(32).toString('hex');
  const sessions = await getSessions();
  sessions['admin:session:' + token] = { created_at: Date.now() };
  await saveSessions(sessions);

  return corsResponse(200, { success: true, token });
}

// Admin auth helper
async function verifyAdminSession(authHeader) {
  if (!authHeader) return false;
  const token = authHeader.replace('Bearer ', '').trim();
  if (!token) return false;
  const sessions = await getSessions();
  return !!sessions['admin:session:' + token];
}

// GET /api/admin/codes
async function handleListCodes() {
  const inviteCodes = await getInviteCodes();
  const list = Object.entries(inviteCodes).map(([code, data]) => ({
    code,
    ...data,
  }));
  return corsResponse(200, { success: true, codes: list });
}

// POST /api/admin/codes
async function handleCreateCode(body) {
  const { max_uses } = body || {};
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let newCode = '';
  for (let i = 0; i < 8; i++) {
    newCode += chars[Math.floor(Math.random() * chars.length)];
  }

  const codeData = {
    created_at: Date.now(),
    max_uses: max_uses || 3,
    used_count: 0,
    is_active: true,
  };

  const inviteCodes = await getInviteCodes();
  inviteCodes[newCode] = codeData;
  await saveInviteCodes(inviteCodes);

  return corsResponse(200, { success: true, code: newCode, ...codeData });
}

// DELETE /api/admin/codes
async function handleRevokeCode(body) {
  const { code } = body || {};
  if (!code) return corsResponse(400, { success: false, message: '缺少邀请码' });

  const inviteCodes = await getInviteCodes();
  if (!inviteCodes[code]) {
    return corsResponse(404, { success: false, message: '邀请码不存在' });
  }

  inviteCodes[code] = { ...inviteCodes[code], is_active: false };
  await saveInviteCodes(inviteCodes);

  return corsResponse(200, { success: true });
}

// GET /api/admin/users
async function handleListUsers() {
  const users = await getRegisteredUsers();
  return corsResponse(200, { success: true, users });
}

/* ============================================================
 * Main Handler
 * ============================================================ */
exports.main_handler = async (event) => {
  try {
    const path = event.path || '';
    const method = event.httpMethod || 'GET';
    const query = event.queryString || event.queryStringParameters || {};
    let body = {};

    if (event.body) {
      try {
        body = JSON.parse(event.body);
      } catch (_) {
        body = {};
      }
    }

    // Attach IP/UA from event
    const headers = event.headers || {};
    body._sourceIp = headers['x-forwarded-for'] || headers['x-real-ip'] || '';
    body._userAgent = headers['user-agent'] || '';

    // CORS preflight
    if (method === 'OPTIONS') {
      return {
        isBase64Encoded: false,
        statusCode: 200,
        headers: CORS_HEADERS,
        body: '',
      };
    }

    // Route matching
    if (path === '/api/login' && method === 'POST') {
      return await handleLogin(body);
    }
    if (path === '/api/verify' && method === 'GET') {
      return await handleVerify(query);
    }
    if (path === '/api/admin-login' && method === 'POST') {
      return await handleAdminLogin(body);
    }

    // Admin-only routes
    if (path.startsWith('/api/admin/')) {
      const isAdmin = await verifyAdminSession(headers.authorization || '');
      if (!isAdmin) {
        return corsResponse(401, { success: false, message: '未授权' });
      }

      if (path === '/api/admin/codes') {
        if (method === 'GET') return await handleListCodes();
        if (method === 'POST') return await handleCreateCode(body);
        if (method === 'DELETE') return await handleRevokeCode(body);
      }
      if (path === '/api/admin/users' && method === 'GET') {
        return await handleListUsers();
      }
    }

    return corsResponse(404, { success: false, message: '接口不存在' });
  } catch (err) {
    console.error('Handler error:', err);
    return corsResponse(500, { success: false, message: '服务器内部错误' });
  }
};
