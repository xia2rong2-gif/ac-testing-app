/**
 * Cloudflare Worker — 邀请码授权系统 API
 *
 * 使用 Workers KV 存储数据，零外部依赖。
 * 部署：wrangler deploy
 */

// KV namespace binding (在 wrangler.toml 中配置)
// 使用 KV 存储三个 key:
// - invite_codes: JSON { "CODE": {created_at, max_uses, used_count, is_active} }
// - sessions: JSON { "session:TOKEN": {...}, "admin:session:TOKEN": {...} }
// - registered_users: JSON [{code_used, created_at, ip}]

const ADMIN_PASSWORD = '4a1f026e8dd940b7';

const CORS_HEADERS = {
	'Access-Control-Allow-Origin': '*',
	'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
	'Access-Control-Allow-Headers': 'Content-Type, Authorization',
	'Content-Type': 'application/json; charset=utf-8',
};

function jsonResponse(status, data) {
	return new Response(JSON.stringify(data), {
		status,
		headers: CORS_HEADERS,
	});
}

export default {
	async fetch(request, env) {
		// CORS preflight
		if (request.method === 'OPTIONS') {
			return new Response('', { headers: CORS_HEADERS });
		}

		const url = new URL(request.url);
		const path = url.pathname;
		const method = request.method;
		const body = request.method !== 'GET' ? await request.json().catch(() => ({})) : {};
		const query = Object.fromEntries(url.searchParams.entries());
		const ip = request.headers.get('x-forwarded-for') || '';
		const userAgent = request.headers.get('user-agent') || '';

		try {
			// Extract auth from header
			const authHeader = request.headers.get('authorization') || '';

			// === Routes ===
			if (path === '/api/login' && method === 'POST') {
				return await handleLogin(body, ip, userAgent, env);
			}
			if (path === '/api/verify' && method === 'GET') {
				return await handleVerify(query, env);
			}
			if (path === '/api/admin-login' && method === 'POST') {
				return await handleAdminLogin(body, env);
			}
			if (path.startsWith('/api/admin/')) {
				return await handleAdminRoutes(path, method, body, authHeader, env);
			}

			return jsonResponse(404, { success: false, message: '接口不存在' });
		} catch (err) {
			console.error('Worker error:', err);
			return jsonResponse(500, { success: false, message: '服务器内部错误' });
		}
	},
};

// === Handlers ===

async function handleLogin(body, ip, userAgent, env) {
	const { code } = body || {};
	if (!code || typeof code !== 'string') {
		return jsonResponse(400, { success: false, message: '请输入邀请码' });
	}

	const key = code.trim().toUpperCase();
	const codesStr = await env.KV.get('invite_codes');
	const inviteCodes = codesStr ? JSON.parse(codesStr) : {};
	const record = inviteCodes[key];

	if (!record) return jsonResponse(401, { success: false, message: '邀请码无效' });
	if (!record.is_active) return jsonResponse(401, { success: false, message: '邀请码已失效' });
	if (record.used_count >= record.max_uses) {
		return jsonResponse(401, { success: false, message: '邀请码使用次数已达上限' });
	}

	const token = crypto.randomUUID().replace(/-/g, '') + crypto.randomUUID().replace(/-/g, '');
	const session = { code_used: key, created_at: Date.now(), ip, user_agent: userAgent };

	// Update invite code
	inviteCodes[key] = { ...record, used_count: record.used_count + 1 };

	// Save sessions
	const sessionsStr = await env.KV.get('sessions');
	const sessions = sessionsStr ? JSON.parse(sessionsStr) : {};
	sessions['session:' + token] = session;

	// Log user
	const usersStr = await env.KV.get('registered_users');
	const users = usersStr ? JSON.parse(usersStr) : [];
	users.push(session);

	// Write all in parallel
	await Promise.all([
		env.KV.put('invite_codes', JSON.stringify(inviteCodes)),
		env.KV.put('sessions', JSON.stringify(sessions)),
		env.KV.put('registered_users', JSON.stringify(users)),
	]);

	return jsonResponse(200, { success: true, token });
}

async function handleVerify(query, env) {
	const token = query?.token || '';
	if (!token) return jsonResponse(200, { valid: false });

	const sessionsStr = await env.KV.get('sessions');
	const sessions = sessionsStr ? JSON.parse(sessionsStr) : {};
	const valid = !!sessions['session:' + token];
	return jsonResponse(200, { valid });
}

async function handleAdminLogin(body, env) {
	const { password } = body || {};
	if (!password || password !== ADMIN_PASSWORD) {
		return jsonResponse(401, { success: false, message: '密码错误' });
	}

	const token = crypto.randomUUID().replace(/-/g, '') + crypto.randomUUID().replace(/-/g, '');
	const sessionsStr = await env.KV.get('sessions');
	const sessions = sessionsStr ? JSON.parse(sessionsStr) : {};
	sessions['admin:session:' + token] = { created_at: Date.now() };
	await env.KV.put('sessions', JSON.stringify(sessions));

	return jsonResponse(200, { success: true, token });
}

async function verifyAdmin(authHeader, env) {
	if (!authHeader) return false;
	const token = authHeader.replace('Bearer ', '').trim();
	if (!token) return false;
	const sessionsStr = await env.KV.get('sessions');
	const sessions = sessionsStr ? JSON.parse(sessionsStr) : {};
	return !!sessions['admin:session:' + token];
}

async function handleAdminRoutes(path, method, body, authHeader, env) {
	const auth = await verifyAdmin(authHeader, env);
	if (!auth) {
		return jsonResponse(401, { success: false, message: '未授权' });
	}

	if (path === '/api/admin/codes') {
		if (method === 'GET') {
			const codesStr = await env.KV.get('invite_codes');
			const inviteCodes = codesStr ? JSON.parse(codesStr) : {};
			const list = Object.entries(inviteCodes).map(([code, data]) => ({ code, ...data }));
			return jsonResponse(200, { success: true, codes: list });
		}

		if (method === 'POST') {
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
			const codesStr = await env.KV.get('invite_codes');
			const inviteCodes = codesStr ? JSON.parse(codesStr) : {};
			inviteCodes[newCode] = codeData;
			await env.KV.put('invite_codes', JSON.stringify(inviteCodes));
			return jsonResponse(200, { success: true, code: newCode, ...codeData });
		}

		if (method === 'DELETE') {
			const { code } = body || {};
			if (!code) return jsonResponse(400, { success: false, message: '缺少邀请码' });
			const codesStr = await env.KV.get('invite_codes');
			const inviteCodes = codesStr ? JSON.parse(codesStr) : {};
			if (!inviteCodes[code]) {
				return jsonResponse(404, { success: false, message: '邀请码不存在' });
			}
			inviteCodes[code] = { ...inviteCodes[code], is_active: false };
			await env.KV.put('invite_codes', JSON.stringify(inviteCodes));
			return jsonResponse(200, { success: true });
		}
	}

	if (path === '/api/admin/users' && method === 'GET') {
		const usersStr = await env.KV.get('registered_users');
		const users = usersStr ? JSON.parse(usersStr) : [];
		return jsonResponse(200, { success: true, users });
	}

	return jsonResponse(404, { success: false, message: '接口不存在' });
}
