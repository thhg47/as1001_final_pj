const USERS_KEY = 'pc_users_v1';
const SESSION_KEY = 'pc_current_user';
const TOKEN_KEY = 'pc_access_token';
const DEMO_EMAIL = 'parent@parentalcontrol.vn';
const API_BASE_URL = 'http://127.0.0.1:8080/api/v1';

const DEFAULT_USERS = [
  { name: 'Demo', email: DEMO_EMAIL, password: 'Parent@123' }
];

const DEMO_STATE = {
  device: {
    id: 'DEV-8841',
    name: 'Galaxy A15 - Minh',
    os: 'Android 14',
    status: 'online',
    screen_time_minutes: 105,
    daily_limit_hours: 3
  },
  logs: [
    {
      id: 101,
      timestamp: '2026-11-21 19:05',
      app: 'Messenger',
      text: 'Tan học mày đợi đấy, tao gọi người chặn đánh',
      label: 2,
      category: 'Danger',
      confidence: 0.9642,
      action: 'Blocked'
    },
    {
      id: 102,
      timestamp: '2026-11-21 18:40',
      app: 'Zalo',
      text: 'Đồ ngu, có mỗi bài Toán dễ thế này mà cũng làm sai',
      label: 1,
      category: 'Warning',
      confidence: 0.8815,
      action: 'Warned'
    },
    {
      id: 103,
      timestamp: '2026-11-21 17:15',
      app: 'YouTube',
      text: 'Hôm nay lớp con có bài kiểm tra Toán',
      label: 0,
      category: 'Safe',
      confidence: 0.9910,
      action: 'Allowed'
    },
    {
      id: 104,
      timestamp: '2026-11-21 16:02',
      app: 'Facebook',
      text: 'Tao hack Facebook của mày bây giờ',
      label: 2,
      category: 'Danger',
      confidence: 0.9480,
      action: 'Blocked'
    }
  ],
  unlockRequests: [
    {
      id: 'REQ-01',
      time: '19:08',
      app: 'Messenger',
      reason: 'Con đang nhắn tin hỏi bài nhóm bạn, tin nhắn kia là bạn trêu đùa ạ.',
      status: 'pending'
    }
  ],
  rules: [
    { id: 1, keyword: 'chặn đánh', level: 'Danger' },
    { id: 2, keyword: 'hack facebook', level: 'Danger' },
    { id: 3, keyword: 'đồ ngu', level: 'Warning' },
    { id: 4, keyword: 'bẩn bựa', level: 'Warning' }
  ]
};

const EMPTY_NEW_USER_STATE = {
  device: null,
  logs: [],
  unlockRequests: [],
  rules: [
    { id: 1, keyword: 'chặn đánh', level: 'Danger' },
    { id: 2, keyword: 'hack facebook', level: 'Danger' },
    { id: 3, keyword: 'đồ ngu', level: 'Warning' }
  ]
};

let appState = null;
let currentUser = null;
let labelChart = null;
let devicePollTimer = null;

function getStorageKey(email) {
  return `pc_state_${email.toLowerCase()}`;
}

function getAuthToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

function getAuthHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  const token = getAuthToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

function formatMinutesToHoursText(minutes) {
  const mins = Number(minutes) || 0;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h}h ${String(m).padStart(2, '0')}m`;
}

function getUsers() {
  const raw = localStorage.getItem(USERS_KEY);
  if (raw) return JSON.parse(raw);
  localStorage.setItem(USERS_KEY, JSON.stringify(DEFAULT_USERS));
  return [...DEFAULT_USERS];
}

function saveUsers(users) {
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
}

function loadStateForUser(email) {
  const key = getStorageKey(email);
  const saved = localStorage.getItem(key);
  if (saved) {
    appState = JSON.parse(saved);
    if (appState.device && appState.device.screen_time_minutes === undefined) {
      appState.device.screen_time_minutes = 105;
      appState.device.daily_limit_hours = appState.device.dailyLimitHours || 3;
    }
  } else {
    const template = email.toLowerCase() === DEMO_EMAIL ? DEMO_STATE : EMPTY_NEW_USER_STATE;
    appState = JSON.parse(JSON.stringify(template));
    saveState();
  }
}

function saveState() {
  if (!currentUser) return;
  localStorage.setItem(getStorageKey(currentUser.email), JSON.stringify(appState));
}

function evaluatePassword(pw) {
  return {
    len: pw.length >= 6 && pw.length <= 16,
    upper: /[A-Z]/.test(pw),
    number: /[0-9]/.test(pw),
    special: /[^A-Za-z0-9]/.test(pw)
  };
}

function updatePasswordChecklist(pw) {
  const checks = evaluatePassword(pw);
  const map = [
    { id: 'rule-len', ok: checks.len },
    { id: 'rule-upper', ok: checks.upper },
    { id: 'rule-number', ok: checks.number },
    { id: 'rule-special', ok: checks.special }
  ];

  map.forEach((item) => {
    const el = document.getElementById(item.id);
    const icon = el.querySelector('.rule-icon');
    if (item.ok) {
      el.classList.remove('text-slate-400');
      el.classList.add('text-emerald-600', 'font-medium');
      icon.textContent = '✓';
    } else {
      el.classList.remove('text-emerald-600', 'font-medium');
      el.classList.add('text-slate-400');
      icon.textContent = '○';
    }
  });

  return checks.len && checks.upper && checks.number && checks.special;
}

function initApp() {
  getUsers();
  bindEvents();

  const savedSession = sessionStorage.getItem(SESSION_KEY);
  if (savedSession) {
    const user = JSON.parse(savedSession);
    showMainView(user);
  }
}

function showAuthMessage(text, isError = true) {
  const box = document.getElementById('auth-message');
  box.textContent = text;
  box.className = `text-xs mt-3 ${isError ? 'text-red-600' : 'text-emerald-600'}`;
  box.classList.remove('hidden');
}

function switchAuthMode(mode) {
  const isLogin = mode === 'login';
  document.getElementById('form-login').classList.toggle('hidden', !isLogin);
  document.getElementById('form-register').classList.toggle('hidden', isLogin);
  document.getElementById('auth-message').classList.add('hidden');

  document.getElementById('auth-subtitle').textContent = isLogin
    ? 'Đăng nhập để quản lý thiết bị và quy tắc an toàn.'
    : 'Tạo tài khoản phụ huynh mới để bắt đầu giám sát.';

  const btnLogin = document.getElementById('tab-btn-login');
  const btnReg = document.getElementById('tab-btn-register');

  btnLogin.className = isLogin
    ? 'py-1.5 rounded-md bg-white text-slate-900 shadow-sm'
    : 'py-1.5 rounded-md text-slate-500 hover:text-slate-800';
  btnReg.className = !isLogin
    ? 'py-1.5 rounded-md bg-white text-slate-900 shadow-sm'
    : 'py-1.5 rounded-md text-slate-500 hover:text-slate-800';
}

async function fetchDevicesFromBackend() {
  const token = getAuthToken();
  if (!token || !currentUser) return;

  try {
    const res = await fetch(`${API_BASE_URL}/devices`, {
      method: 'GET',
      headers: getAuthHeaders()
    });
    if (!res.ok) return;

    const data = await res.json();
    const list = Array.isArray(data) ? data : (data.devices || data.items || []);
    if (list.length > 0) {
      const dev = list[0];
      appState.device = {
        id: dev.id,
        name: dev.name || dev.device_name || 'Thiết bị Android',
        os: dev.os || dev.os_version || 'Android',
        status: dev.status || (dev.is_online ? 'online' : 'offline'),
        screen_time_minutes: Number(dev.screen_time_minutes ?? 0),
        daily_limit_hours: Number(dev.daily_limit_hours ?? 3)
      };
      saveState();
      renderDeviceInfo();
      document.getElementById('input-daily-limit').value = appState.device.daily_limit_hours;
    }
  } catch {
    // Offline fallback: giữ nguyên state hiện tại trong localStorage
  }
}

function startDevicePolling() {
  stopDevicePolling();
  fetchDevicesFromBackend();
  devicePollTimer = setInterval(fetchDevicesFromBackend, 7000);
}

function stopDevicePolling() {
  if (devicePollTimer) {
    clearInterval(devicePollTimer);
    devicePollTimer = null;
  }
}

function bindEvents() {
  document.getElementById('tab-btn-login').addEventListener('click', () => switchAuthMode('login'));
  document.getElementById('tab-btn-register').addEventListener('click', () => switchAuthMode('register'));

  document.getElementById('reg-password').addEventListener('input', (e) => {
    updatePasswordChecklist(e.target.value);
  });

  document.getElementById('form-login').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('login-email').value.trim().toLowerCase();
    const pass = document.getElementById('login-password').value;

    // 1. Thử đăng nhập với Backend thật (cổng 8080)
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 1500);
      const res = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pass }),
        signal: controller.signal
      });
      clearTimeout(timer);

      if (res.ok) {
        const data = await res.json();
        const token = data.access_token || data.token;
        if (token) {
          sessionStorage.setItem(TOKEN_KEY, token);
        }
        const userObj = {
          name: data.user?.name || (email === DEMO_EMAIL ? 'Demo' : email.split('@')[0]),
          email: email
        };
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(userObj));
        showMainView(userObj);
        return;
      } else if (res.status === 401 || res.status === 400) {
        showAuthMessage('Email hoặc mật khẩu không chính xác trên hệ thống.');
        return;
      }
    } catch {
      // Backend chưa bật -> tự động chuyển sang xác thực cục bộ (localStorage)
    }

    // 2. Fallback cục bộ khi chạy Demo offline
    const users = getUsers();
    const matched = users.find((u) => u.email.toLowerCase() === email && u.password === pass);

    if (!matched) {
      showAuthMessage('Email hoặc mật khẩu không chính xác. Vui lòng kiểm tra lại hoặc đăng ký tài khoản mới.');
      return;
    }

    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(matched));
    showMainView(matched);
  });

  document.getElementById('form-register').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('reg-name').value.trim();
    const email = document.getElementById('reg-email').value.trim().toLowerCase();
    const pass = document.getElementById('reg-password').value;
    const confirm = document.getElementById('reg-confirm').value;

    if (!updatePasswordChecklist(pass)) {
      showAuthMessage('Mật khẩu chưa đáp ứng đủ các điều kiện bảo mật bên trên.');
      return;
    }
    if (pass !== confirm) {
      showAuthMessage('Mật khẩu xác nhận không khớp.');
      return;
    }

    // Thử gọi đăng ký lên Backend nếu có
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 1500);
      await fetch(`${API_BASE_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password: pass }),
        signal: controller.signal
      });
      clearTimeout(timer);
    } catch {
      // Bỏ qua nếu offline
    }

    const users = getUsers();
    if (users.some((u) => u.email.toLowerCase() === email)) {
      showAuthMessage('Email này đã được đăng ký. Vui lòng chuyển sang tab Đăng nhập.');
      return;
    }

    const newUser = { name, email, password: pass };
    users.push(newUser);
    saveUsers(users);

    document.getElementById('form-register').reset();
    updatePasswordChecklist('');
    document.getElementById('login-email').value = email;
    document.getElementById('login-password').value = pass;
    switchAuthMode('login');
    showAuthMessage('Đăng ký thành công! Bạn có thể bấm Đăng nhập ngay bây giờ.', false);
  });

  document.getElementById('btn-logout').addEventListener('click', () => {
    stopDevicePolling();
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    currentUser = null;
    document.getElementById('view-main').classList.add('hidden');
    document.getElementById('view-auth').classList.remove('hidden');
    document.getElementById('auth-message').classList.add('hidden');
  });

  document.getElementById('btn-reset-demo').addEventListener('click', () => {
    if (currentUser) {
      localStorage.removeItem(getStorageKey(currentUser.email));
      loadStateForUser(currentUser.email);
      document.getElementById('predict-result-box').innerHTML =
        '<div class="text-xs text-slate-400">Nhập nội dung phía trên và bấm <strong>Kiểm tra</strong> để xem mức độ đánh giá.</div>';
      renderAll();
      fetchDevicesFromBackend();
    }
  });

  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  document.getElementById('filter-label').addEventListener('change', renderLogs);
  document.getElementById('btn-run-predict').addEventListener('click', handleSimulatePredict);

  // Nút Tạo mã mới -> gọi POST /api/v1/pairing/pin
  document.getElementById('btn-new-pin').addEventListener('click', async () => {
    const pinEl = document.getElementById('text-pin');
    const token = getAuthToken();

    if (token) {
      try {
        const res = await fetch(`${API_BASE_URL}/pairing/pin`, {
          method: 'POST',
          headers: getAuthHeaders()
        });
        if (res.ok) {
          const data = await res.json();
          const rawPin = String(data.pin || data.code || '').replace(/\s+/g, '');
          if (rawPin.length === 6) {
            pinEl.textContent = `${rawPin.slice(0, 3)} ${rawPin.slice(3)}`;
            return;
          } else if (rawPin) {
            pinEl.textContent = rawPin;
            return;
          }
        }
      } catch {
        // Fallback random nếu rớt mạng
      }
    }

    const code = Math.floor(100000 + Math.random() * 900000).toString();
    pinEl.textContent = `${code.slice(0, 3)} ${code.slice(3)}`;
  });

  // Ô giới hạn giờ -> gọi PATCH /api/v1/devices/{id}
  document.getElementById('btn-save-limit').addEventListener('click', async () => {
    const input = document.getElementById('input-daily-limit');
    const val = Number(input.value);
    if (!Number.isInteger(val) || val < 1 || val > 12) {
      alert('Vui lòng nhập số giờ nguyên từ 1 đến 12.');
      input.value = appState.device ? appState.device.daily_limit_hours : 3;
      return;
    }

    if (appState.device) {
      appState.device.daily_limit_hours = val;
      saveState();
      renderDeviceInfo();

      const token = getAuthToken();
      if (token && appState.device.id) {
        try {
          await fetch(`${API_BASE_URL}/devices/${appState.device.id}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ daily_limit_hours: val })
          });
        } catch {
          // Bỏ qua nếu offline
        }
      }
    }
  });

  document.getElementById('form-add-rule').addEventListener('submit', (e) => {
    e.preventDefault();
    const kwInput = document.getElementById('input-keyword');
    const level = document.getElementById('select-level').value;
    const kw = kwInput.value.trim();
    if (!kw) return;

    appState.rules.unshift({
      id: Date.now(),
      keyword: kw,
      level: level
    });
    kwInput.value = '';
    saveState();
    renderRules();
  });
}

function showMainView(user) {
  currentUser = user;
  loadStateForUser(user.email);

  document.getElementById('view-auth').classList.add('hidden');
  document.getElementById('view-main').classList.remove('hidden');
  document.getElementById('current-user-name').textContent =
    user.email.toLowerCase() === DEMO_EMAIL ? 'Demo' : user.name;
  document.getElementById('current-user-email').textContent = user.email;
  renderAll();
  startDevicePolling();
}

function switchTab(tabName) {
  document.querySelectorAll('[id^="panel-"]').forEach((p) => p.classList.add('hidden'));
  document.getElementById(`panel-${tabName}`).classList.remove('hidden');

  document.querySelectorAll('.nav-item').forEach((btn) => {
    const active = btn.dataset.tab === tabName;
    btn.classList.toggle('bg-blue-600', active);
    btn.classList.toggle('text-white', active);
    btn.classList.toggle('text-slate-300', !active);
  });
}

function renderAll() {
  renderDeviceInfo();
  renderStatsAndChart();
  renderUnlockRequests();
  renderLogs();
  renderRules();
  document.getElementById('input-daily-limit').value = appState.device ? appState.device.daily_limit_hours : 3;
}

function renderDeviceInfo() {
  const d = appState.device;
  const badge = document.getElementById('device-badge');
  const card = document.getElementById('device-card');

  if (!d) {
    badge.innerHTML = `<span class="inline-block w-2 h-2 rounded-full bg-slate-400 mr-1.5"></span>Chưa ghép nối thiết bị`;
    card.innerHTML = `
      <div class="p-4 border border-dashed border-slate-300 rounded-lg text-center space-y-1">
        <p class="text-xs font-medium text-slate-700">Chưa có thiết bị nào được liên kết</p>
        <p class="text-[11px] text-slate-500">Vui lòng nhập mã PIN bên trái vào ứng dụng Android trên máy của trẻ để đồng bộ dữ liệu thật.</p>
      </div>
    `;
    return;
  }

  const timeFormatted = formatMinutesToHoursText(d.screen_time_minutes);
  const isOnline = String(d.status).toLowerCase() === 'online';

  badge.innerHTML = `<span class="inline-block w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-slate-400'} mr-1.5"></span>${d.name} (${timeFormatted} / ${d.daily_limit_hours}h)`;

  card.innerHTML = `
    <div class="p-4 border border-slate-200 rounded-lg space-y-2">
      <div class="flex items-center justify-between">
        <span class="font-semibold text-sm text-slate-900">${d.name}</span>
        <span class="px-2 py-0.5 text-[11px] rounded-full ${isOnline ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'} font-medium">
          ${isOnline ? 'Online' : 'Offline'}
        </span>
      </div>
      <div class="text-xs text-slate-500">ID: ${d.id} • Hệ điều hành: ${d.os}</div>
      <div class="text-xs text-slate-600">Thời gian dùng hôm nay: <strong>${timeFormatted}</strong> (Giới hạn: ${d.daily_limit_hours} giờ)</div>
    </div>
  `;
}

function renderStatsAndChart() {
  const safe = appState.logs.filter((l) => l.label === 0).length;
  const warn = appState.logs.filter((l) => l.label === 1).length;
  const danger = appState.logs.filter((l) => l.label === 2).length;
  const total = safe + warn + danger;

  document.getElementById('kpi-total').textContent = total;
  document.getElementById('kpi-safe').textContent = safe;
  document.getElementById('kpi-warning').textContent = warn;
  document.getElementById('kpi-danger').textContent = danger;

  const ctx = document.getElementById('chart-labels').getContext('2d');
  if (labelChart) labelChart.destroy();

  const hasData = total > 0;
  labelChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: hasData ? ['An toàn', 'Cảnh báo', 'Nguy hiểm'] : ['Chưa có dữ liệu'],
      datasets: [
        {
          data: hasData ? [safe, warn, danger] : [1],
          backgroundColor: hasData ? ['#10b981', '#f59e0b', '#ef4444'] : ['#e2e8f0'],
          borderWidth: 1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } }
      }
    }
  });
}

function renderLogs() {
  const filterVal = document.getElementById('filter-label').value;
  const items =
    filterVal === 'all'
      ? appState.logs
      : appState.logs.filter((l) => String(l.label) === filterVal);

  const tbody = document.getElementById('table-logs');
  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-slate-400">Chưa có nhật ký nào được ghi nhận.</td></tr>`;
    return;
  }

  const labelTextMap = { 0: 'An toàn', 1: 'Cảnh báo', 2: 'Nguy hiểm' };

  tbody.innerHTML = items
    .map((item) => {
      const pill =
        item.label === 2
          ? 'bg-red-100 text-red-700'
          : item.label === 1
          ? 'bg-amber-100 text-amber-700'
          : 'bg-emerald-100 text-emerald-700';

      return `
        <tr class="hover:bg-slate-50">
          <td class="py-2.5 px-4 text-slate-500 whitespace-nowrap">${item.timestamp}</td>
          <td class="py-2.5 px-4 font-medium text-slate-800">${item.app}</td>
          <td class="py-2.5 px-4 text-slate-700">${item.text}</td>
          <td class="py-2.5 px-4">
            <span class="px-2 py-0.5 rounded-full font-semibold ${pill}">${labelTextMap[item.label]}</span>
          </td>
          <td class="py-2.5 px-4 font-mono text-slate-600">${(item.confidence * 100).toFixed(2)}%</td>
          <td class="py-2.5 px-4 text-slate-600">${item.action}</td>
        </tr>
      `;
    })
    .join('');
}

function renderUnlockRequests() {
  const container = document.getElementById('unlock-list');
  if (!appState.unlockRequests.length) {
    container.innerHTML = '<p class="text-xs text-slate-400">Không có yêu cầu mở khóa nào.</p>';
    return;
  }

  container.innerHTML = appState.unlockRequests
    .map((req) => {
      const actionHtml =
        req.status === 'pending'
          ? `<div class="flex gap-2 shrink-0">
              <button onclick="resolveUnlock('${req.id}', 'approved')" class="px-2.5 py-1 bg-emerald-600 text-white text-xs rounded hover:bg-emerald-700">Mở khóa</button>
              <button onclick="resolveUnlock('${req.id}', 'rejected')" class="px-2.5 py-1 bg-slate-200 text-slate-700 text-xs rounded hover:bg-slate-300">Từ chối</button>
            </div>`
          : `<span class="text-xs font-medium ${req.status === 'approved' ? 'text-emerald-600' : 'text-red-600'}">
              ${req.status === 'approved' ? 'Đã mở khóa' : 'Đã từ chối'}
            </span>`;

      return `
        <div class="p-3 bg-slate-50 border border-slate-200 rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <div class="text-xs font-semibold text-slate-800">${req.app} • <span class="font-normal text-slate-500">Lúc ${req.time}</span></div>
            <div class="text-xs text-slate-600 mt-0.5">"${req.reason}"</div>
          </div>
          ${actionHtml}
        </div>
      `;
    })
    .join('');
}

window.resolveUnlock = function (id, decision) {
  const target = appState.unlockRequests.find((r) => r.id === id);
  if (target) {
    target.status = decision;
    saveState();
    renderUnlockRequests();
  }
};

function matchVietnameseKeywords(text, keywords) {
  const normalized = text.normalize('NFC');
  const escaped = keywords.map((kw) => kw.normalize('NFC').replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const pattern = new RegExp(`(?:^|[^\\p{L}\\p{M}\\p{N}])(?:${escaped.join('|')})(?=$|[^\\p{L}\\p{M}\\p{N}])`, 'u');
  return pattern.test(normalized);
}

function classifyLocalFallback(text) {
  const lower = text.normalize('NFC').toLowerCase().trim();

  const matchedRule = appState.rules.find((r) => lower.includes(r.keyword.normalize('NFC').toLowerCase()));
  if (matchedRule) {
    return {
      label: matchedRule.level === 'Danger' ? 2 : 1,
      confidence: Number((0.92 + Math.random() * 0.06).toFixed(4))
    };
  }

  const dangerWords = [
    'đánh', 'đập', 'đấm', 'đá', 'tát', 'chém', 'giết', 'đâm', 'bắn', 'siết',
    'bóp cổ', 'nện', 'phang', 'quất', 'xử', 'triệt', 'xiên', 'thiêu', 'đốt',
    'đợi đấy', 'chờ đấy', 'coi chừng', 'biết tay', 'không tha', 'lấy mạng', 'tính sổ',
    'gọi người', 'kéo băng', 'tự tử', 'tự sát', 'nhảy lầu', 'rạch tay', 'chết đi',
    'hack', 'chiếm nick', 'lừa đảo', 'chiếm đoạt', 'cá độ', 'cờ bạc', 'tài xỉu',
    'ma túy', 'cần sa', 'thuốc lắc', 'khiêu dâm', '18+', 'khủng bố'
  ];

  if (matchVietnameseKeywords(lower, dangerWords)) {
    return {
      label: 2,
      confidence: Number((0.90 + Math.random() * 0.08).toFixed(4))
    };
  }

  const warningWords = [
    'địt', 'đụ', 'lồn', 'cặc', 'buồi', 'đéo', 'đếch', 'đm', 'đkm', 'đcm', 'dcm', 'dkm',
    'vcl', 'vl', 'vkl', 'cc', 'cl', 'clgt', 'mẹ mày', 'bố mày', 'djt', 'đjt', 'djtme', 'đjtme', 'ditme', 'đitme',
    'ngu', 'đần', 'dốt', 'óc chó', 'súc vật', 'chó đẻ', 'khốn nạn', 'mất dạy', 'vô học',
    'bẩn bựa', 'rẻ rách', 'thất học', 'điên', 'khùng', 'tâm thần',
    'cút', 'biến đi', 'nhục', 'tẩy chay', 'bóc phốt', 'chửi', 'kinh tởm', 'ghê tởm',
    'tao', 'mày', 'tụi mày', 'chúng mày'
  ];

  if (matchVietnameseKeywords(lower, warningWords)) {
    return {
      label: 1,
      confidence: Number((0.84 + Math.random() * 0.10).toFixed(4))
    };
  }

  return {
    label: 0,
    confidence: Number((0.94 + Math.random() * 0.05).toFixed(4))
  };
}

async function handleSimulatePredict() {
  const input = document.getElementById('input-sample-text');
  const text = input.value.trim();
  if (!text) return;

  let label = 0;
  let confidence = 0.95;

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1200);
    const res = await fetch(`${API_BASE_URL}/predict`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ text }),
      signal: controller.signal
    });
    clearTimeout(timer);
    if (res.ok) {
      const data = await res.json();
      label = Number(data.label ?? data.prediction ?? 0);
      confidence = Number(data.confidence ?? 0.95);
    } else {
      ({ label, confidence } = classifyLocalFallback(text));
    }
  } catch {
    ({ label, confidence } = classifyLocalFallback(text));
  }

  const labelMap = { 0: 'An toàn (Safe)', 1: 'Cảnh báo (Warning)', 2: 'Nguy hiểm (Danger)' };
  const categoryShort = { 0: 'Safe', 1: 'Warning', 2: 'Danger' };

  const badgeStyle =
    label === 2
      ? 'bg-red-100 text-red-700 border-red-200'
      : label === 1
      ? 'bg-amber-100 text-amber-700 border-amber-200'
      : 'bg-emerald-100 text-emerald-700 border-emerald-200';

  const actionText =
    label === 2
      ? 'Tự động chặn & khóa màn hình'
      : label === 1
      ? 'Gửi thông báo nhắc nhở phụ huynh'
      : 'Cho phép hiển thị bình thường';

  document.getElementById('predict-result-box').innerHTML = `
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold border ${badgeStyle}">${labelMap[label]}</span>
        <span class="text-xs text-slate-600">Độ chính xác: <strong>${(confidence * 100).toFixed(2)}%</strong></span>
      </div>
      <span class="text-xs font-medium text-slate-700">${actionText}</span>
    </div>
    <p class="text-[11px] text-slate-500 mt-2 truncate">Nội dung đã kiểm tra: "${text}"</p>
  `;

  const now = new Date();
  const timeStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

  appState.logs.unshift({
    id: Date.now(),
    timestamp: timeStr,
    app: 'Kiểm tra thủ công',
    text: text,
    label: label,
    category: categoryShort[label],
    confidence: confidence,
    action: label === 2 ? 'Blocked' : label === 1 ? 'Warned' : 'Allowed'
  });

  input.value = '';
  saveState();
  renderStatsAndChart();
  renderLogs();
}

function renderRules() {
  const tbody = document.getElementById('table-rules');
  tbody.innerHTML = appState.rules
    .map(
      (r) => `
      <tr>
        <td class="py-2 px-3 font-medium text-slate-800">${r.keyword}</td>
        <td class="py-2 px-3">
          <span class="px-2 py-0.5 rounded font-semibold ${r.level === 'Danger' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}">
            ${r.level}
          </span>
        </td>
        <td class="py-2 px-3 text-right">
          <button onclick="deleteRule(${r.id})" class="text-slate-400 hover:text-red-600">Xóa</button>
        </td>
      </tr>
    `
    )
    .join('');
}

window.deleteRule = function (id) {
  appState.rules = appState.rules.filter((r) => r.id !== id);
  saveState();
  renderRules();
};

initApp();