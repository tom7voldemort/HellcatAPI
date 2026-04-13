const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('overlay');
const mainEl = document.getElementById('main');
const hamIcon = document.getElementById('hamburger-icon');
let sidebarOpen = window.innerWidth >= 900;

function setSidebar(open) {
    sidebarOpen = open;
    sidebar.classList.toggle('open', open);
    sidebar.classList.toggle('collapsed', !open);
    overlay.classList.toggle('open', open && window.innerWidth < 900);
    if (window.innerWidth >= 900) mainEl.classList.toggle('expanded', !open);
    hamIcon.className = open ? 'fa-solid fa-xmark' : 'fa-solid fa-bars';
}

document.getElementById('hamburger').addEventListener('click', () => setSidebar(!sidebarOpen));
overlay.addEventListener('click', () => setSidebar(false));
window.addEventListener('resize', () => {
    if (window.innerWidth >= 900) {
        overlay.classList.remove('open');
        if (!sidebar.classList.contains('collapsed')) { sidebar.classList.add('open'); mainEl.classList.remove('expanded'); }
    } else { if (sidebarOpen) overlay.classList.add('open'); }
});
setSidebar(window.innerWidth >= 900);

function goTo(page) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.sb-item').forEach(i => i.classList.remove('active'));
    const pg = document.getElementById('page-' + page);
    if (pg) pg.classList.add('active');
    const sb = document.querySelector('[data-page="' + page + '"]');
    if (sb) sb.classList.add('active');
    if (window.innerWidth < 900) setSidebar(false);
}
document.querySelectorAll('.sb-item').forEach(item => {
    item.addEventListener('click', () => goTo(item.dataset.page));
});

async function callApi(path) {
    const el = document.getElementById('output');
    el.className = ''; el.textContent = 'Sending request...';
    try {
        const r = await fetch(path);
        const d = await r.json();
        el.textContent = JSON.stringify(d, null, 2);
        el.className = 'ok';
    } catch (e) {
        el.textContent = 'Error: ' + e.message;
        el.className = 'err';
    }
}

async function postApi() {
    const el = document.getElementById('output');
    el.className = ''; el.textContent = 'Sending request...';
    try {
        const r = await fetch('/async-echo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ msg: 'hello', from: 'HellcatAPI Dashboard' })
        });
        const d = await r.json();
        el.textContent = JSON.stringify(d, null, 2);
        el.className = 'ok';
    } catch (e) {
        el.textContent = 'Error: ' + e.message;
        el.className = 'err';
    }
}

function clearOutput() {
    const el = document.getElementById('output');
    el.textContent = 'Waiting for request...'; el.className = '';
}

async function createUser() {
    const el = document.getElementById('output');
    el.className = ''; el.textContent = 'Creating user...';
    try {
        const r = await fetch('/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ Name: 'NewUser', Email: 'newuser@hellcat.dev', Role: 'user' })
        });
        const d = await r.json();
        el.textContent = JSON.stringify(d, null, 2);
        el.className = r.ok ? 'ok' : 'err';
        goTo('dashboard');
    } catch (e) { el.textContent = 'Error: ' + e.message; el.className = 'err'; goTo('dashboard'); }
}

async function deleteUser(id) {
    const el = document.getElementById('output');
    el.className = ''; el.textContent = `Deleting user ${id}...`;
    try {
        const r = await fetch(`/users/${id}`, { method: 'DELETE' });
        const d = await r.json();
        el.textContent = JSON.stringify(d, null, 2);
        el.className = r.ok ? 'ok' : 'err';
    } catch (e) { el.textContent = 'Error: ' + e.message; el.className = 'err'; }
}

async function createOrder() {
    const uid = parseInt(document.getElementById('order-uid').value);
    const pid = parseInt(document.getElementById('order-pid').value);
    const qty = parseInt(document.getElementById('order-qty').value);
    const el = document.getElementById('output');
    el.className = ''; el.textContent = 'Placing order...';
    try {
        const r = await fetch('/orders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ UserId: uid, ProductId: pid, Quantity: qty })
        });
        const d = await r.json();
        el.textContent = JSON.stringify(d, null, 2);
        el.className = r.ok ? 'ok' : 'err';
        goTo('dashboard');
    } catch (e) { el.textContent = 'Error: ' + e.message; el.className = 'err'; goTo('dashboard'); }
}

let jwtToken = null;

async function doLogin() {
    const email = document.getElementById('login-email').value;
    const out = document.getElementById('auth-output');
    out.style.color = 'var(--text-3)'; out.textContent = 'Logging in...';
    try {
        const r = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ Email: email })
        });
        const d = await r.json();
        out.textContent = JSON.stringify(d, null, 2);
        out.style.color = r.ok ? 'var(--teal-light)' : '#fca5a5';
        if (r.ok && d.Token) {
            jwtToken = d.Token;
            document.getElementById('token-panel').style.display = '';
            document.getElementById('token-display').textContent = d.Token;
        }
    } catch (e) { out.textContent = 'Error: ' + e.message; out.style.color = '#fca5a5'; }
}

async function doMe() {
    const out = document.getElementById('auth-output');
    if (!jwtToken) { out.textContent = 'Login first to get a token.'; out.style.color = '#fca5a5'; return; }
    out.style.color = 'var(--text-3)'; out.textContent = 'Fetching /auth/me...';
    try {
        const r = await fetch('/auth/me', { headers: { 'Authorization': 'Bearer ' + jwtToken } });
        const d = await r.json();
        out.textContent = JSON.stringify(d, null, 2);
        out.style.color = r.ok ? 'var(--teal-light)' : '#fca5a5';
    } catch (e) { out.textContent = 'Error: ' + e.message; out.style.color = '#fca5a5'; }
}

async function doLogout() {
    const out = document.getElementById('auth-output');
    out.style.color = 'var(--text-3)'; out.textContent = 'Logging out...';
    try {
        const r = await fetch('/auth/logout', { method: 'POST' });
        const d = await r.json();
        out.textContent = JSON.stringify(d, null, 2);
        out.style.color = 'var(--teal-light)';
        jwtToken = null;
        document.getElementById('token-panel').style.display = 'none';
    } catch (e) { out.textContent = 'Error: ' + e.message; out.style.color = '#fca5a5'; }
}

function clearAuthOutput() {
    document.getElementById('auth-output').textContent = 'Login to see response...';
    document.getElementById('auth-output').style.color = 'var(--text-3)';
}

let evtSource = null;

function startStream() {
    const count = parseInt(document.getElementById('stream-count').value) || 5;
    const out = document.getElementById('stream-output');
    out.innerHTML = '<span style="color:var(--text-3)">Connecting to /stream?count=' + count + '...</span>\n';
    if (evtSource) evtSource.close();
    evtSource = new EventSource('/stream?count=' + count);
    evtSource.onmessage = function (e) {
        try {
            const d = JSON.parse(e.data);
            if (d.Event === 'done') {
                out.innerHTML += '<span class="stream-done">✔ Stream complete.</span>\n';
                evtSource.close(); evtSource = null;
            } else {
                out.innerHTML += '<span class="stream-event">► Event ' + d.Event + '</span>  value=' + d.Value + '  ts=' + d.Ts + '\n';
                out.scrollTop = out.scrollHeight;
            }
        } catch (err) {
            out.innerHTML += '<span style="color:#fca5a5">Parse error: ' + err.message + '</span>\n';
        }
    };
    evtSource.onerror = function () {
        out.innerHTML += '<span style="color:#fca5a5">Connection error.</span>\n';
        if (evtSource) { evtSource.close(); evtSource = null; }
    };
}

function clearStream() {
    if (evtSource) { evtSource.close(); evtSource = null; }
    document.getElementById('stream-output').textContent = 'Press Start to begin receiving events...';
}

async function testTimeout() {
    const wait = parseFloat(document.getElementById('td-wait').value) || 1;
    const limit = parseFloat(document.getElementById('td-limit').value) || 2;
    const out = document.getElementById('timeout-output');
    out.style.color = 'var(--text-3)'; out.textContent = 'Waiting...';
    try {
        const r = await fetch(`/timeout-demo?wait=${wait}&limit=${limit}`);
        const d = await r.json();
        out.textContent = JSON.stringify(d, null, 2);
        out.style.color = r.ok ? 'var(--teal-light)' : '#fca5a5';
    } catch (e) { out.textContent = 'Error: ' + e.message; out.style.color = '#fca5a5'; }
}

async function fetchLogs() {
    const limit = parseInt(document.getElementById('log-limit').value) || 10;
    const out = document.getElementById('logs-output');
    out.style.color = 'var(--text-3)'; out.textContent = 'Fetching...';
    try {
        const r = await fetch(`/logs?limit=${limit}`);
        const d = await r.json();
        out.textContent = JSON.stringify(d, null, 2);
        out.style.color = 'var(--teal-light)';
    } catch (e) { out.textContent = 'Error: ' + e.message; out.style.color = '#fca5a5'; }
}

function refreshLogs() { fetchLogs(); }

async function loadSummary() {
    try {
        const r = await fetch('/api/v1/summary');
        const d = await r.json();
        const usersEl = document.getElementById('stat-users');
        const productsEl = document.getElementById('stat-products');
        if (usersEl) usersEl.textContent = d.Users + ' registered';
        if (productsEl) productsEl.textContent = d.Products + ' in stock';
    } catch (e) {
        const u = document.getElementById('stat-users');
        const p = document.getElementById('stat-products');
        if (u) u.textContent = 'err';
        if (p) p.textContent = 'err';
    }
}

async function loadUsers() {
    const tbody = document.getElementById('users-tbody');
    const meta = document.getElementById('users-count');
    if (!tbody) return;
    try {
        const r = await fetch('/users?per=100');
        const d = await r.json();
        const rows = d.Data || [];
        if (meta) meta.textContent = rows.length + ' users';
        if (rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-3);font-size:12px;padding:14px">No users found.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(u => `
            <tr>
                <td class="mono">${u.id}</td>
                <td>${u.name}</td>
                <td><span class="role-badge ${u.role === 'admin' ? 'role-admin' : 'role-user'}">${u.role}</span></td>
                <td class="mono">${u.email}</td>
            </tr>
        `).join('');
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#fca5a5;font-size:12px;padding:14px">Failed to load users.</td></tr>';
        if (meta) meta.textContent = 'error';
    }
}

async function loadProducts() {
    const tbody = document.getElementById('products-tbody');
    const meta = document.getElementById('products-count');
    if (!tbody) return;
    try {
        const r = await fetch('/products?per=100');
        const d = await r.json();
        const rows = d.Data || [];
        if (meta) meta.textContent = rows.length + ' products';
        if (rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-3);font-size:12px;padding:14px">No products found.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(p => `
            <tr>
                <td class="mono">${p.id}</td>
                <td>${p.name}</td>
                <td class="mono">$${parseFloat(p.price).toFixed(2)}</td>
                <td class="mono">${p.stock}</td>
            </tr>
        `).join('');
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#fca5a5;font-size:12px;padding:14px">Failed to load products.</td></tr>';
        if (meta) meta.textContent = 'error';
    }
}

async function loadDbStats() {
    try {
        const r = await fetch('/db/stats');
        const d = await r.json();
        const pool = d.Stats && d.Stats.Pool ? d.Stats.Pool : {};
        const rs = await fetch('/api/v1/summary');
        const ds = await rs.json();
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        set('db-users', ds.Users ?? '—');
        set('db-products', ds.Products ?? '—');
        set('db-orders', ds.Orders ?? '—');
        set('db-pool', pool.PoolSize ?? '—');
        set('db-inuse', pool.InUse ?? '—');
        set('db-driver', d.Stats && d.Stats.Driver ? d.Stats.Driver : '—');
    } catch (e) {
        ['db-users', 'db-products', 'db-orders', 'db-pool', 'db-inuse', 'db-driver'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = 'err';
        });
    }
}

loadSummary();
loadUsers();
loadProducts();
loadDbStats();
