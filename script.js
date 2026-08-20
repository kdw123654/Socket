const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const screens = {
  auth: $('#authScreen'),
  connect: $('#connectScreen'),
  app: $('#appScreen'),
};

const config = window.PRAIN_CONFIG || {};
const API_BASE = (config.apiBaseUrl ?? '').replace(/\/$/, '');
const DEMO_ON_ERROR = config.demoModeOnApiError !== false;
const tokenKey = 'prain_access_token';
const userKey = 'prain_user';
const communityKey = 'prain_community_posts';
const seededCommunityIds = new Set(['community-1', 'community-2']);
const savedCommunityPosts = safeJson(localStorage.getItem(communityKey));
const initialCommunityPosts = Array.isArray(savedCommunityPosts)
  ? savedCommunityPosts
    .filter((post) => !seededCommunityIds.has(post.id))
    .map((post) => ({ ...post, owned: post.owned ?? true }))
  : [];

const state = {
  token: localStorage.getItem(tokenKey) || '',
  user: safeJson(localStorage.getItem(userKey)),
  authMode: 'signup',
  meetings: [],
  notes: [],
  layout: null,
  figma: { connected: false, username: '' },
  notion: { connected: false, workspace: '', pages: [] },
  github: { connected: false, username: '', repos: [] },
  meetingAudio: { file: null, url: '' },
  apiConnected: false,
  dashboardSummary: '',
  communityPosts: initialCommunityPosts,
  communityFilter: '전체',
  editingCommunityPostId: '',
  selectedCommunityPostId: '',
  usingDemo: false,
};

if (Array.isArray(savedCommunityPosts) && savedCommunityPosts.length !== initialCommunityPosts.length) {
  localStorage.setItem(communityKey, JSON.stringify(initialCommunityPosts));
}

function safeJson(value) {
  try {
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

function markDemoResponse(data) {
  if (data && typeof data === 'object') {
    Object.defineProperty(data, '__demo', { value: true });
  }
  return data;
}

function isDemoResponse(data) {
  return Boolean(data?.__demo);
}

function showScreen(name) {
  Object.values(screens).forEach((screen) => screen.classList.remove('active'));
  screens[name].classList.add('active');
  if (name === 'app') refreshAppData();
  if (name === 'connect') {
    loadDiscordStatus();
    loadFigmaStatus();
    loadNotionStatus();
    loadGithubStatus();
  }
}

window.showPrainScreen = showScreen;

function setStatus(group, label, ok = true) {
  const node = $(`[data-api-status="${group}"]`);
  if (!node) return;
  node.textContent = label;
  node.classList.toggle('ok', ok);
  node.classList.toggle('warn', !ok);
}

function setApiMode(message, demo = state.usingDemo) {
  state.usingDemo = demo;
  $('#apiMode').textContent = message;
  $('#authApiState').textContent = demo ? '데모 데이터 사용 중' : 'API 연결 준비';
  $('#authApiBase').textContent = API_BASE || '같은 도메인';
  renderApiConnectionState();
}

function renderApiConnectionState() {
  const grid = $('#apiGrid');
  const empty = $('#apiEmptyState');
  if (!grid || !empty) return;
  grid.classList.toggle('hidden', !state.apiConnected);
  empty.classList.toggle('hidden', state.apiConnected);
  renderDashboardSummary();
}

function renderDashboardSummary() {
  const panel = $('#dashboardInsight');
  const label = $('#dashboardSummaryLabel');
  const summary = $('#dashboardSummary');
  if (!panel || !label || !summary) return;
  const hasSummary = Boolean(state.dashboardSummary);
  panel.classList.toggle('empty-summary', !hasSummary);
  panel.classList.toggle('has-summary', hasSummary);
  label.textContent = hasSummary ? 'AI 요약' : '요약 없음';
  summary.textContent = hasSummary ? state.dashboardSummary : '아직 생성된 AI 요약이 없습니다.';
}

function setDashboardSummary(text) {
  state.dashboardSummary = (text || '').replace(/[#*\-[\]]/g, '').replace(/\s+/g, ' ').trim();
  renderDashboardSummary();
}

function updateUserUi(user = state.user) {
  if (!user) return;
  $('#userNickname').textContent = user.nickname || 'Prain';
  $('#userEmail').textContent = user.email || '온라인';
}

async function apiRequest(path, options = {}) {
  const method = options.method || 'GET';
  const headers = new Headers(options.headers || {});
  let body = options.body;

  if (body && !(body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
    body = JSON.stringify(body);
  }

  if (state.token && options.auth !== false) {
    headers.set('Authorization', `Bearer ${state.token}`);
  }

  try {
    const response = await fetch(`${API_BASE}${path}`, { method, headers, body });
    if (!response.ok) {
      const message = await response.text();
      const error = new Error(message || `${response.status} ${response.statusText}`);
      error.status = response.status;
      throw error;
    }
    state.apiConnected = true;
    setApiMode('API 연결됨', false);
    if (response.status === 204) return null;
    return response.json();
  } catch (error) {
    if (options.fallbackPath && !options._fallbackAttempted) {
      return apiRequest(options.fallbackPath, { ...options, fallbackPath: null, _fallbackAttempted: true });
    }
    if (!DEMO_ON_ERROR) throw error;
    setApiMode(state.apiConnected ? '일부 API 대기 중' : '백엔드 대기 중 · 데모 데이터 표시', !state.apiConnected);
    return markDemoResponse(demoResponse(path, options));
  }
}

function demoResponse(path, options = {}) {
  const body = options.body instanceof FormData ? {} : options.body || {};
  if (path === '/auth/login') {
    return {
      access_token: 'demo-access-token',
      token_type: 'bearer',
      user: { id: 'demo-user', email: body.email || 'user@example.com', nickname: state.user?.nickname || '사용자' },
    };
  }
  if (path === '/auth/signup') {
    return { id: 'demo-user', email: body.email || 'user@example.com', nickname: body.nickname || '사용자', created_at: new Date().toISOString() };
  }
  if (path === '/auth/me') {
    return state.user || { id: 'demo-user', email: 'user@example.com', nickname: '사용자', created_at: new Date().toISOString() };
  }
  if (path === '/ai/chat') {
    return { reply: '80% 완료됐어요. 인증, AI 회의록, 메모, Discord 상태, 워크스페이스 저장 호출이 프론트에 연결되어 있습니다.' };
  }
  if (path === '/ai/summarize-text') {
    return {
      id: `meeting-${Date.now()}`,
      title: body.title || '기획 회의',
      summary_markdown: '### 핵심 요약\n- 입력한 회의 내용을 바탕으로 주요 논의와 결정 사항을 정리했습니다.\n\n### 액션 아이템\n- [ ] 후속 작업을 확인해 주세요.\n\n### 타임라인\n- 입력된 스크립트 기준으로 정리됩니다.',
      created_at: new Date().toISOString(),
    };
  }
  if (path === '/ai/summarize') {
    return {
      id: `audio-${Date.now()}`,
      title: '업로드 회의 음성',
      summary_markdown: '음성 파일 업로드 요청이 준비되었습니다. 백엔드가 켜지면 STT 결과와 회의록 요약이 이 영역에 표시됩니다.',
      created_at: new Date().toISOString(),
    };
  }
  if (path === '/ai/meetings') {
    return state.meetings;
  }
  if (path === '/notes' && options.method === 'POST') {
    return { id: `note-${Date.now()}`, title: body.title, content: body.content, created_at: new Date().toISOString() };
  }
  if (path === '/notes') {
    return state.notes;
  }
  if (path === '/integrations/discord/status') {
    return { connected: true, provider: 'discord', username: 'kdw_prain#1234' };
  }
  if (path === '/integrations/discord/authorize') {
    return { authorize_url: buildDiscordAuthorizeUrl() || 'https://discord.com/oauth2/authorize' };
  }
  if (path.includes('/integrations/notion/authorize')) {
    return { authorize_url: '' };
  }
  if (path.includes('/integrations/notion/status')) {
    return { connected: false, workspace_name: '' };
  }
  if (path.includes('/integrations/notion/pages/') && path.endsWith('/blocks')) {
    return { blocks: [] };
  }
  if (path.includes('/integrations/notion/pages')) {
    return { pages: [] };
  }
  if (path.endsWith('/integrations/notion') && options.method === 'DELETE') {
    return { message: 'Notion 연동 해제 요청이 준비되었습니다.' };
  }
  if (path.includes('/integrations/github/authorize')) {
    return { authorize_url: '' };
  }
  if (path.includes('/integrations/github/status')) {
    return { connected: false, username: '' };
  }
  if (path.includes('/integrations/github/repos/') && path.endsWith('/issues')) {
    return { issues: [] };
  }
  if (path.includes('/integrations/github/repos/') && path.endsWith('/commits')) {
    return { commits: [] };
  }
  if (path.includes('/integrations/github/repos/') && path.endsWith('/pulls')) {
    return { pulls: [] };
  }
  if (path.includes('/integrations/github/repos')) {
    return { repos: [] };
  }
  if (path.endsWith('/integrations/github') && options.method === 'DELETE') {
    return { message: 'GitHub 연동 해제 요청이 준비되었습니다.' };
  }
  if (path === '/integrations/figma/save-pat') {
    state.figma = { connected: true, username: 'Prain Figma' };
    return { message: 'Figma PAT가 저장되었습니다.', username: state.figma.username };
  }
  if (path === '/integrations/figma/pat-status') {
    return { connected: state.figma.connected, username: state.figma.username };
  }
  if (path === '/integrations/figma/pat' && options.method === 'DELETE') {
    state.figma = { connected: false, username: '' };
    return { message: 'Figma 연동이 해제되었습니다.' };
  }
  if (path === '/integrations/figma/frames') {
    return {
      frames: [
        { id: '92:36', name: '회의 기록', page: 'Page 1', thumbnail: '' },
        { id: '92:235', name: '커뮤니티', page: 'Page 1', thumbnail: '' },
      ],
    };
  }
  if (path === '/integrations/figma/file-comments') {
    return {
      comments: [
        { id: 'comment-1', message: '회의 기록 첫 화면은 빈 상태 안내가 필요합니다.', user: '디자이너', created_at: new Date().toISOString(), resolved_at: null },
      ],
    };
  }
  if (path === '/integrations/figma/summarize') {
    return { summary: '### Figma 요약\n- 파일의 주요 프레임과 최근 댓글을 기반으로 변경 포인트를 정리합니다.\n- 프레임별 구현 우선순위를 확인할 수 있습니다.' };
  }
  if (path === '/integrations/figma/analyze') {
    return {
      frame_name: body.frame_name || '선택한 프레임',
      image_url: '',
      analysis: '레이아웃, 색상, 여백, 컴포넌트 구조를 기준으로 프론트 구현 가이드를 생성합니다.',
    };
  }
  if (path === '/workspace/layout' && options.method === 'PUT') {
    return { id: 'layout-1234', user_id: state.user?.id || 'demo-user', layout_data: body.layout_data || body };
  }
  if (path === '/workspace/layout') {
    return state.layout || {
      id: 'layout-1234',
      user_id: state.user?.id || 'demo-user',
      layout_data: {
        split_type: 'vertical_2',
        panels: [
          { id: 'p1', type: 'meeting_notes' },
          { id: 'p2', type: 'browser', url: 'https://github.com' },
        ],
      },
    };
  }
  return {};
}

function buildDiscordAuthorizeUrl() {
  const clientId = config.discordClientId;
  if (!clientId || clientId === 'YOUR_DISCORD_APPLICATION_ID') return '';
  const params = new URLSearchParams({
    client_id: clientId,
    scope: 'bot applications.commands',
    permissions: '84992',
    integration_type: '0',
  });
  return `https://discord.com/oauth2/authorize?${params}`;
}

function persistSession(loginResponse) {
  if (!loginResponse?.access_token) return;
  const previousUser = state.user || {};
  state.token = loginResponse.access_token;
  state.user = { ...previousUser, ...(loginResponse.user || {}) };
  if ($('#rememberLogin').checked) {
    localStorage.setItem(tokenKey, state.token);
    localStorage.setItem(userKey, JSON.stringify(state.user));
  }
  updateUserUi();
}

function setAuthMode(mode) {
  state.authMode = mode;
  $$('[data-auth-mode]').forEach((button) => button.classList.toggle('active', button.dataset.authMode === mode));
  $('#authNickname').classList.toggle('hidden', mode === 'login');
  $('#authSubmit').textContent = mode === 'signup' ? '회원가입하고 시작하기' : '로그인하고 시작하기';
  $('.corner-label').textContent = mode === 'signup' ? '회원가입' : '로그인';
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  const email = $('#authEmail').value.trim();
  const password = $('#authPassword').value.trim();
  const nickname = $('#authNickname').value.trim();
  if (!email || !password || (state.authMode === 'signup' && !nickname)) {
    $('#installMessage').textContent = '이메일, 비밀번호, 닉네임을 입력해 주세요.';
    return;
  }

  $('#authSubmit').disabled = true;
  $('#authSubmit').textContent = '처리 중';
  try {
    if (state.authMode === 'signup') {
      const signupUser = await apiRequest('/auth/signup', { method: 'POST', auth: false, body: { email, password, nickname } });
      state.user = { ...(state.user || {}), ...(signupUser || {}), email, nickname: signupUser.nickname || nickname };
    }
    const loginResponse = await apiRequest('/auth/login', { method: 'POST', auth: false, body: { email, password } });
    persistSession(loginResponse);
    setStatus('auth', isDemoResponse(loginResponse) ? '대기' : '연결됨', !isDemoResponse(loginResponse));
    showScreen('app');
  } finally {
    $('#authSubmit').disabled = false;
    $('#authSubmit').textContent = state.authMode === 'signup' ? '회원가입하고 시작하기' : '로그인하고 시작하기';
  }
}

async function continueWithDiscord() {
  const message = $('#installMessage');
  if (state.token) {
    const data = await apiRequest('/integrations/discord/authorize');
    if (data.authorize_url) {
      window.open(data.authorize_url, '_blank', 'noopener,noreferrer');
      message.textContent = 'Discord 승인 창을 열었습니다. 승인 후 대시보드에서 상태를 새로고침해 주세요.';
      setStatus('integrations', 'OAuth 열림');
      return;
    }
  }

  const directUrl = buildDiscordAuthorizeUrl();
  if (directUrl) {
    window.open(directUrl, '_blank', 'noopener,noreferrer');
    message.textContent = 'Discord 승인 창을 열었습니다.';
    return;
  }

  message.textContent = '미리보기 모드로 대시보드를 엽니다.';
  showScreen('app');
}

async function refreshAppData() {
  state.apiConnected = false;
  $$('[data-api-status]').forEach((node) => {
    node.textContent = '대기';
    node.classList.remove('ok');
    node.classList.add('warn');
  });
  setApiMode('API 연결 확인 중', false);
  updateUserUi();
  await Promise.allSettled([
    loadCurrentUser(),
    loadMeetings(),
    loadNotes(),
    loadDiscordStatus(),
    loadFigmaStatus(),
    loadNotionStatus(),
    loadGithubStatus(),
    loadWorkspaceLayout(),
  ]);
  $('#lastSync').textContent = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

async function loadCurrentUser() {
  const user = await apiRequest('/auth/me');
  state.user = user;
  updateUserUi(user);
  setStatus('auth', isDemoResponse(user) ? '대기' : '연결됨', !isDemoResponse(user));
}

async function loadDiscordStatus() {
  const status = await apiRequest('/integrations/discord/status');
  const label = status.connected ? `${status.username || 'Discord'} 연결됨` : '연결 필요';
  $('#discordStatusText').textContent = label;
  const isLive = !isDemoResponse(status);
  setStatus('integrations', isLive && status.connected ? '연결됨' : '대기', isLive && status.connected);
}

async function loadFigmaStatus() {
  const status = await apiRequest('/integrations/figma/pat-status');
  state.figma = {
    connected: Boolean(status.connected),
    username: status.username || '',
  };
  renderFigmaStatus();
  const isLive = !isDemoResponse(status);
  setStatus('figmaIntegration', isLive && state.figma.connected ? '연결됨' : '대기', isLive && state.figma.connected);
}

function renderFigmaStatus() {
  const label = state.figma.connected ? `${state.figma.username || 'Figma'} 연결됨` : 'PAT 등록 필요';
  const statusText = $('#figmaStatusText');
  const message = $('#figmaPatMessage');
  if (statusText) statusText.textContent = label;
  if (message) message.textContent = state.figma.connected ? `${label} · 파일 조회 API를 사용할 수 있습니다.` : 'PAT는 백엔드 보안 저장소에만 저장됩니다.';
  $('#figmaTool')?.classList.toggle('connected', state.figma.connected);
}

async function handleFigmaPatSubmit(event) {
  event.preventDefault();
  const input = $('#figmaPatInput');
  const message = $('#figmaPatMessage');
  const figmaPat = input.value.trim();
  if (!figmaPat) {
    message.textContent = 'Figma PAT를 입력해 주세요.';
    return;
  }

  const button = $('button[type="submit"]', event.currentTarget);
  button.disabled = true;
  button.textContent = '저장 중';
  try {
    const data = await apiRequest('/integrations/figma/save-pat', {
      method: 'POST',
      body: { figma_pat: figmaPat },
    });
    if (isDemoResponse(data)) {
      state.figma = { connected: false, username: '' };
      renderFigmaStatus();
      setStatus('figmaIntegration', '대기', false);
      message.textContent = '아직 백엔드가 연결되지 않아 PAT를 저장할 수 없습니다.';
      return;
    }
    state.figma = { connected: true, username: data.username || 'Figma' };
    input.value = '';
    renderFigmaStatus();
    setStatus('figmaIntegration', '연결됨');
    message.textContent = data.message || 'Figma PAT가 저장되었습니다.';
  } finally {
    button.disabled = false;
    button.textContent = 'PAT 저장';
  }
}

async function handleFigmaDisconnect() {
  const message = $('#figmaPatMessage');
  const button = $('#disconnectFigmaPat');
  button.disabled = true;
  button.textContent = '해제 중';
  try {
    const data = await apiRequest('/integrations/figma/pat', { method: 'DELETE' });
    state.figma = { connected: false, username: '' };
    renderFigmaStatus();
    setStatus('figmaIntegration', '대기', false);
    message.textContent = isDemoResponse(data) ? '아직 백엔드가 연결되지 않았습니다.' : data.message || 'Figma 연동이 해제되었습니다.';
  } finally {
    button.disabled = false;
    button.textContent = '연동 해제';
  }
}

function pickAuthorizeUrl(data) {
  return data?.authorize_url || data?.authorization_url || data?.oauth_url || data?.url || '';
}

function arrayPayload(data, keys) {
  if (Array.isArray(data)) return data;
  for (const key of [...keys, 'data']) {
    if (Array.isArray(data?.[key])) return data[key];
  }
  return [];
}

function readableJson(value) {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function setIntegrationResult(message, empty = true) {
  const root = $('#integrationResult');
  if (!root) return;
  root.innerHTML = '';
  root.classList.toggle('empty-state', empty);
  root.textContent = message;
}

function renderIntegrationCards(title, items, emptyText, toViewModel) {
  const root = $('#integrationResult');
  if (!root) return;
  root.innerHTML = '';
  root.classList.remove('empty-state');

  if (!items.length) {
    setIntegrationResult(emptyText);
    return;
  }

  const heading = document.createElement('b');
  heading.textContent = title;
  root.append(heading);

  items.slice(0, 10).forEach((item) => {
    const view = toViewModel(item);
    const card = document.createElement('article');
    card.className = 'integration-result-card';
    card.innerHTML = '<b></b><small></small><p></p>';
    $('b', card).textContent = view.title || '제목 없음';
    $('small', card).textContent = view.meta || '';
    $('p', card).textContent = view.text || '';
    root.append(card);
  });
}

async function openIntegrationOAuth(provider) {
  const label = provider === 'notion' ? 'Notion' : 'GitHub';
  const data = await apiRequest(`/api/v1/integrations/${provider}/authorize`, {
    fallbackPath: `/integrations/${provider}/authorize`,
  });
  const authorizeUrl = pickAuthorizeUrl(data);

  if (isDemoResponse(data) || !authorizeUrl) {
    const message = `아직 백엔드가 연결되지 않아 ${label} OAuth URL을 받을 수 없습니다.`;
    $('#installMessage').textContent = message;
    $('#externalApiStatus').textContent = `${label} OAuth 대기`;
    setIntegrationResult(message);
    setStatus(provider, '대기', false);
    return;
  }

  window.open(authorizeUrl, '_blank', 'noopener,noreferrer');
  $('#installMessage').textContent = `${label} 승인 창을 열었습니다. 승인 후 새로고침하면 상태가 반영됩니다.`;
  $('#externalApiStatus').textContent = `${label} OAuth 진행 중`;
  setStatus(provider, 'OAuth 열림', false);
}

function continueWithNotion() {
  return openIntegrationOAuth('notion');
}

function continueWithGithub() {
  return openIntegrationOAuth('github');
}

function renderNotionStatus() {
  const label = state.notion.connected
    ? `${state.notion.workspace || 'Notion'} 연결됨`
    : 'OAuth 연결 필요';
  $('#notionStatusText').textContent = label;
  $('#notionWorkspaceStatus').textContent = label;
  $('#notionTool')?.classList.toggle('connected', state.notion.connected);
  $('#notionSummaryItem')?.classList.toggle('muted', !state.notion.connected);
}

function renderGithubStatus() {
  const label = state.github.connected
    ? `${state.github.username || 'GitHub'} 연결됨`
    : 'OAuth 연결 필요';
  $('#githubStatusText').textContent = label;
  $('#githubAccountStatus').textContent = label;
  $('#githubTool')?.classList.toggle('connected', state.github.connected);
  $('#githubSummaryItem')?.classList.toggle('muted', !state.github.connected);
}

async function loadNotionStatus() {
  const status = await apiRequest('/api/v1/integrations/notion/status', {
    fallbackPath: '/integrations/notion/status',
  });
  state.notion = {
    ...state.notion,
    connected: Boolean(status?.connected),
    workspace: status?.workspace_name || status?.workspace || status?.workspace_id || status?.username || '',
  };
  renderNotionStatus();
  const isLive = !isDemoResponse(status);
  setStatus('notion', isLive && state.notion.connected ? '연결됨' : '대기', isLive && state.notion.connected);
}

async function loadGithubStatus() {
  const status = await apiRequest('/api/v1/integrations/github/status', {
    fallbackPath: '/integrations/github/status',
  });
  state.github = {
    ...state.github,
    connected: Boolean(status?.connected),
    username: status?.username || status?.login || status?.name || '',
  };
  renderGithubStatus();
  const isLive = !isDemoResponse(status);
  setStatus('github', isLive && state.github.connected ? '연결됨' : '대기', isLive && state.github.connected);
}

function notionPageId(page) {
  return page.id || page.page_id || page.pageId || '';
}

function notionPageTitle(page) {
  const notionTitle = page.properties?.title?.title?.[0]?.plain_text
    || page.properties?.Name?.title?.[0]?.plain_text
    || page.properties?.이름?.title?.[0]?.plain_text;
  return page.title || page.name || notionTitle || '제목 없는 페이지';
}

function renderNotionPageOptions(pages) {
  const select = $('#notionPageSelect');
  if (!select) return;
  select.innerHTML = '';
  if (!pages.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = '조회된 페이지 없음';
    select.append(option);
    return;
  }
  pages.forEach((page) => {
    const option = document.createElement('option');
    option.value = notionPageId(page);
    option.textContent = notionPageTitle(page);
    select.append(option);
  });
}

async function loadNotionPages() {
  $('#externalApiStatus').textContent = 'Notion 페이지 조회 중';
  const data = await apiRequest('/api/v1/integrations/notion/pages', {
    fallbackPath: '/integrations/notion/pages',
  });
  const pages = arrayPayload(data, ['pages', 'results', 'items']);
  state.notion.pages = pages;
  renderNotionPageOptions(pages);

  if (isDemoResponse(data)) {
    setStatus('notion', '대기', false);
    $('#externalApiStatus').textContent = 'Notion 대기';
    setIntegrationResult('아직 백엔드가 연결되지 않아 Notion 페이지를 불러올 수 없습니다.');
    return;
  }

  renderIntegrationCards('Notion 페이지', pages, '조회된 Notion 페이지가 없습니다.', (page) => ({
    title: notionPageTitle(page),
    meta: notionPageId(page),
    text: page.url || page.workspace_name || '',
  }));
  $('#externalApiStatus').textContent = 'Notion 페이지 조회 완료';
  setStatus('notion', '조회됨');
}

async function loadNotionBlocks() {
  const pageId = $('#notionPageSelect').value;
  if (!pageId) {
    setIntegrationResult('먼저 Notion 페이지를 조회하고 페이지를 선택해 주세요.');
    return;
  }

  $('#externalApiStatus').textContent = 'Notion 블록 조회 중';
  const path = `/api/v1/integrations/notion/pages/${encodeURIComponent(pageId)}/blocks`;
  const data = await apiRequest(path, {
    fallbackPath: `/integrations/notion/pages/${encodeURIComponent(pageId)}/blocks`,
  });
  const blocks = arrayPayload(data, ['blocks', 'results', 'items']);

  if (isDemoResponse(data)) {
    setStatus('notion', '대기', false);
    $('#externalApiStatus').textContent = 'Notion 대기';
    setIntegrationResult('아직 백엔드가 연결되지 않아 Notion 블록을 불러올 수 없습니다.');
    return;
  }

  renderIntegrationCards('Notion 블록', blocks, '조회된 Notion 블록이 없습니다.', (block) => ({
    title: block.type || block.name || block.id || '블록',
    meta: block.id || '',
    text: block.plain_text || block.text || block.content || readableJson(block),
  }));

  const promptText = data?.prompt || data?.markdown || data?.summary;
  if (promptText) {
    const card = document.createElement('article');
    card.className = 'integration-result-card';
    card.innerHTML = '<b>프롬프트용 텍스트</b><pre></pre>';
    $('pre', card).textContent = promptText;
    $('#integrationResult').append(card);
  }

  $('#externalApiStatus').textContent = 'Notion 블록 조회 완료';
  setStatus('notion', '조회됨');
}

function githubRepoName(repo) {
  return repo.full_name || [repo.owner?.login || repo.owner, repo.name || repo.repo].filter(Boolean).join('/') || '저장소';
}

function fillGithubRepoInputs(repo) {
  const fullName = githubRepoName(repo);
  const [owner, name] = fullName.split('/');
  if (owner && name) {
    $('#githubOwnerInput').value = owner;
    $('#githubRepoInput').value = name;
  }
}

async function loadGithubRepos() {
  $('#externalApiStatus').textContent = 'GitHub Repository 조회 중';
  const data = await apiRequest('/api/v1/integrations/github/repos', {
    fallbackPath: '/integrations/github/repos',
  });
  const repos = arrayPayload(data, ['repos', 'repositories', 'results', 'items']);
  state.github.repos = repos;
  if (repos[0]) fillGithubRepoInputs(repos[0]);

  if (isDemoResponse(data)) {
    setStatus('github', '대기', false);
    $('#externalApiStatus').textContent = 'GitHub 대기';
    setIntegrationResult('아직 백엔드가 연결되지 않아 GitHub Repository를 불러올 수 없습니다.');
    return;
  }

  renderIntegrationCards('GitHub Repository', repos, '조회된 GitHub Repository가 없습니다.', (repo) => ({
    title: githubRepoName(repo),
    meta: repo.private ? 'private' : 'public',
    text: repo.description || repo.html_url || '',
  }));
  $('#externalApiStatus').textContent = 'GitHub Repository 조회 완료';
  setStatus('github', '조회됨');
}

function githubResourceTitle(kind) {
  return {
    issues: 'Issue',
    commits: 'Commit',
    pulls: 'Pull Request',
  }[kind] || 'GitHub 데이터';
}

async function loadGithubResource(kind) {
  const owner = $('#githubOwnerInput').value.trim();
  const repo = $('#githubRepoInput').value.trim();
  if (!owner || !repo) {
    setIntegrationResult('Repository 조회를 먼저 하거나 owner와 repo를 직접 입력해 주세요.');
    return;
  }

  const label = githubResourceTitle(kind);
  $('#externalApiStatus').textContent = `GitHub ${label} 조회 중`;
  const path = `/api/v1/integrations/github/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/${kind}`;
  const data = await apiRequest(path, {
    fallbackPath: `/integrations/github/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/${kind}`,
  });
  const items = arrayPayload(data, [kind, 'results', 'items']);

  if (isDemoResponse(data)) {
    setStatus('github', '대기', false);
    $('#externalApiStatus').textContent = 'GitHub 대기';
    setIntegrationResult(`아직 백엔드가 연결되지 않아 GitHub ${label}를 불러올 수 없습니다.`);
    return;
  }

  renderIntegrationCards(`GitHub ${label}`, items, `조회된 GitHub ${label}가 없습니다.`, (item) => ({
    title: item.title || item.commit?.message?.split('\n')[0] || item.name || item.sha || `${label} 항목`,
    meta: item.number ? `#${item.number} · ${item.state || ''}` : item.sha || item.author?.login || item.commit?.author?.name || '',
    text: item.body || item.html_url || item.commit?.message || readableJson(item),
  }));
  $('#externalApiStatus').textContent = `GitHub ${label} 조회 완료`;
  setStatus('github', '조회됨');
}

async function disconnectIntegration(provider) {
  const label = provider === 'notion' ? 'Notion' : 'GitHub';
  const data = await apiRequest(`/api/v1/integrations/${provider}`, {
    method: 'DELETE',
    fallbackPath: `/integrations/${provider}`,
  });

  if (provider === 'notion') {
    state.notion = { connected: false, workspace: '', pages: [] };
    renderNotionStatus();
    renderNotionPageOptions([]);
  } else {
    state.github = { connected: false, username: '', repos: [] };
    renderGithubStatus();
  }

  setStatus(provider, '대기', false);
  setIntegrationResult(isDemoResponse(data) ? `아직 백엔드가 연결되지 않아 ${label} 연동 해제를 확인할 수 없습니다.` : data?.message || `${label} 연동을 해제했습니다.`);
  $('#externalApiStatus').textContent = `${label} 연동 대기`;
}

async function loadMeetings() {
  const meetings = await apiRequest('/ai/meetings');
  state.meetings = meetings;
  renderMeetings(meetings);
  setStatus('meetings', isDemoResponse(meetings) ? '대기' : '연결됨', !isDemoResponse(meetings));
}

function renderMeetings(meetings) {
  const list = $('#meetingList');
  const latestMeeting = $('#latestMeeting');
  if (!list) {
    if (latestMeeting) latestMeeting.textContent = meetings[0]?.title || '아직 저장된 회의록이 없습니다.';
    renderWorkspacePreview();
    return;
  }
  list.innerHTML = '';
  if (!meetings.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = '아직 저장된 회의록이 없습니다.';
    list.append(empty);
    if (latestMeeting) latestMeeting.textContent = '아직 저장된 회의록이 없습니다.';
    renderWorkspacePreview();
    return;
  }
  meetings.forEach((meeting) => {
    const item = document.createElement('article');
    item.innerHTML = '<b></b><small></small><p></p>';
    $('b', item).textContent = meeting.title;
    $('small', item).textContent = formatDate(meeting.created_at);
    $('p', item).textContent = meeting.summary_preview || meeting.summary_markdown || '요약 내용이 없습니다.';
    list.append(item);
  });
  if (latestMeeting) latestMeeting.textContent = meetings[0]?.title || '아직 저장된 회의록이 없습니다.';
  renderWorkspacePreview();
}

async function loadNotes() {
  const notes = await apiRequest('/notes');
  state.notes = notes;
  renderNotes(notes);
  setStatus('notes', isDemoResponse(notes) ? '대기' : '연결됨', !isDemoResponse(notes));
}

function renderNotes(notes) {
  const list = $('#noteList');
  list.innerHTML = '';
  if (!notes.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = '아직 작성된 메모가 없습니다.';
    list.append(empty);
    renderWorkspacePreview();
    return;
  }
  notes.forEach((note) => {
    const item = document.createElement('article');
    item.innerHTML = '<b></b><small></small><p></p>';
    $('b', item).textContent = note.title;
    $('small', item).textContent = formatDate(note.created_at);
    $('p', item).textContent = note.content;
    list.append(item);
  });
  renderWorkspacePreview();
}

async function loadWorkspaceLayout() {
  const layout = await apiRequest('/workspace/layout');
  state.layout = layout;
  renderLayout(layout);
  setStatus('workspace', isDemoResponse(layout) ? '대기' : '연결됨', !isDemoResponse(layout));
}

function renderLayout(layout) {
  const data = { ...(layout.layout_data || layout), split_type: 'vertical_2' };
  $('#splitType').value = 'vertical_2';
  $('#panelOneType').value = data.panels?.[0]?.type || 'meeting_notes';
  $('#panelTwoType').value = data.panels?.[1]?.type || 'browser';
  $('#panelTwoUrl').value = data.panels?.[1]?.url || 'https://github.com';
  state.layout = { ...layout, layout_data: data };
  renderWorkspacePreview(data);
}

function getCurrentLayoutData() {
  const rightPanel = { id: 'p2', type: $('#panelTwoType').value };
  if (rightPanel.type === 'browser') rightPanel.url = $('#panelTwoUrl').value.trim();
  return {
    split_type: 'vertical_2',
    panels: [
      { id: 'p1', type: $('#panelOneType').value },
      rightPanel,
    ],
  };
}

function panelTitle(type) {
  return {
    meeting_notes: '회의록',
    notes: '메모',
    browser: '브라우저',
    ai_chat: 'AI 채팅',
  }[type] || '패널';
}

function normalizedUrl(value) {
  const raw = (value || '').trim();
  if (!raw) return '';
  try {
    return new URL(raw.startsWith('http') ? raw : `https://${raw}`).href;
  } catch {
    return '';
  }
}

function renderWorkspacePreview(data = state.layout?.layout_data || getCurrentLayoutData()) {
  const workspace = $('#splitWorkspace');
  if (!workspace) return;
  const verticalData = { ...data, split_type: 'vertical_2' };
  workspace.classList.remove('horizontal');
  renderWorkspacePane($('#workspacePaneOne'), verticalData.panels?.[0] || { type: 'meeting_notes' });
  renderWorkspacePane($('#workspacePaneTwo'), verticalData.panels?.[1] || { type: 'browser', url: $('#panelTwoUrl').value.trim() });
}

function renderWorkspacePane(target, panel) {
  target.innerHTML = '<header><small></small><b></b></header><div class="pane-body"></div>';
  $('small', target).textContent = 'Panel';
  $('b', target).textContent = panelTitle(panel.type);
  const body = $('.pane-body', target);

  if (panel.type === 'meeting_notes') {
    renderPaneList(body, state.meetings, '저장된 회의록이 없습니다.', (meeting) => ({
      title: meeting.title,
      meta: formatDate(meeting.created_at),
      text: meeting.summary_preview || meeting.summary_markdown || '',
    }));
    return;
  }

  if (panel.type === 'notes') {
    renderPaneList(body, state.notes, '작성된 메모가 없습니다.', (note) => ({
      title: note.title,
      meta: formatDate(note.created_at),
      text: note.content,
    }));
    return;
  }

  if (panel.type === 'ai_chat') {
    body.innerHTML = '<p class="pane-empty">AI 채팅 화면에서 대화를 시작하면 이 패널과 함께 보며 작업할 수 있습니다.</p><button type="button" class="pane-link">AI 채팅 열기</button>';
    $('.pane-link', body).addEventListener('click', () => showView('ai'));
    return;
  }

  const url = normalizedUrl(panel.url || $('#panelTwoUrl').value);
  if (!url) {
    body.innerHTML = '<p class="pane-empty">브라우저 URL을 입력해 주세요.</p>';
    return;
  }
  body.innerHTML = '<div class="browser-frame"><div class="browser-url"></div><iframe title="브라우저 패널"></iframe></div><a class="pane-link" target="_blank" rel="noopener noreferrer">새 탭에서 열기</a>';
  $('.browser-url', body).textContent = url;
  $('iframe', body).src = url;
  $('.pane-link', body).href = url;
}

function renderPaneList(target, items, emptyText, toViewModel) {
  if (!items.length) {
    target.innerHTML = '<p class="pane-empty"></p>';
    $('.pane-empty', target).textContent = emptyText;
    return;
  }
  const list = document.createElement('div');
  list.className = 'pane-list';
  items.slice(0, 4).forEach((item) => {
    const view = toViewModel(item);
    const article = document.createElement('article');
    article.innerHTML = '<b></b><small></small><p></p>';
    $('b', article).textContent = view.title || '제목 없음';
    $('small', article).textContent = view.meta || '';
    $('p', article).textContent = view.text || '';
    list.append(article);
  });
  target.append(list);
}

function parseFigmaFileKey(value) {
  const raw = value.trim();
  const match = raw.match(/figma\.com\/(?:file|design|proto)\/([^/?#]+)/i);
  return match ? decodeURIComponent(match[1]) : raw;
}

function setFigmaFileStatus(message) {
  const status = $('#figmaFileStatus');
  if (status) status.textContent = message;
}

function setFigmaButtonsDisabled(disabled) {
  $$('#figmaFileForm button').forEach((button) => {
    button.disabled = disabled;
  });
}

async function handleFigmaFileSubmit(event) {
  event.preventDefault();
  const action = event.submitter?.dataset.figmaAction || 'frames';
  const fileKey = parseFigmaFileKey($('#figmaFileKey').value);
  const nodeId = $('#figmaNodeId').value.trim();
  const frameName = $('#figmaFrameName').value.trim();
  const actions = {
    frames: { path: '/integrations/figma/frames', label: '프레임 조회' },
    comments: { path: '/integrations/figma/file-comments', label: '댓글 조회' },
    summarize: { path: '/integrations/figma/summarize', label: 'AI 요약' },
    analyze: { path: '/integrations/figma/analyze', label: '프레임 분석' },
  };

  if (!fileKey) {
    renderFigmaEmpty('Figma 파일 키 또는 URL을 입력해 주세요.');
    return;
  }

  if (action === 'analyze' && !nodeId) {
    renderFigmaEmpty('프레임 분석은 node_id를 함께 입력해 주세요.');
    return;
  }

  const body = { file_key: fileKey };
  if (action === 'analyze') {
    body.node_id = nodeId;
    body.frame_name = frameName || '선택한 프레임';
  }

  setFigmaButtonsDisabled(true);
  setFigmaFileStatus(`${actions[action].label} 중`);
  try {
    const data = await apiRequest(actions[action].path, { method: 'POST', body });
    if (isDemoResponse(data)) {
      renderFigmaEmpty('아직 백엔드가 연결되지 않아 Figma 파일을 조회할 수 없습니다.');
      setStatus('figmaFile', '대기', false);
      setFigmaFileStatus('백엔드 연결 대기');
      return;
    }
    renderFigmaResult(action, data);
    setStatus('figmaFile', '호출됨');
    setFigmaFileStatus(`${actions[action].label} 완료`);
  } catch {
    renderFigmaEmpty('Figma API 호출 중 문제가 생겼습니다. 백엔드 연결과 PAT 상태를 확인해 주세요.');
    setStatus('figmaFile', '오류', false);
    setFigmaFileStatus('호출 실패');
  } finally {
    setFigmaButtonsDisabled(false);
  }
}

function renderFigmaEmpty(message) {
  const result = $('#figmaResult');
  result.className = 'figma-result empty-state';
  result.textContent = message;
}

function renderFigmaResult(action, data) {
  const result = $('#figmaResult');
  result.className = 'figma-result';
  result.innerHTML = '';

  if (action === 'frames') {
    const frames = data.frames || [];
    if (!frames.length) {
      renderFigmaEmpty('조회된 프레임이 없습니다.');
      return;
    }
    frames.forEach((frame) => appendFigmaResultCard(result, {
      title: frame.name,
      meta: [frame.page, frame.id].filter(Boolean).join(' · '),
      text: '프레임 목록과 썸네일 조회 결과입니다.',
      imageUrl: frame.thumbnail,
    }));
    return;
  }

  if (action === 'comments') {
    const comments = data.comments || [];
    if (!comments.length) {
      renderFigmaEmpty('최근 댓글이 없습니다.');
      return;
    }
    comments.forEach((comment) => appendFigmaResultCard(result, {
      title: comment.user || '댓글',
      meta: [formatDate(comment.created_at), comment.resolved_at ? '해결됨' : '미해결'].filter(Boolean).join(' · '),
      text: comment.message,
    }));
    return;
  }

  if (action === 'summarize') {
    appendFigmaTextResult(result, 'AI 요약 결과', data.summary || '요약 결과가 비어 있습니다.');
    setDashboardSummary(data.summary);
    return;
  }

  appendFigmaResultCard(result, {
    title: data.frame_name || '프레임 분석 결과',
    meta: '구현 가이드',
    text: data.analysis || '분석 결과가 비어 있습니다.',
    imageUrl: data.image_url,
  });
}

function appendFigmaResultCard(root, { title, meta, text, imageUrl }) {
  const article = document.createElement('article');
  article.className = 'figma-result-card';
  article.innerHTML = '<div><b></b><small></small><p></p></div>';
  $('b', article).textContent = title || '제목 없음';
  $('small', article).textContent = meta || '';
  $('p', article).textContent = text || '';

  if (imageUrl) {
    const image = document.createElement('img');
    image.src = imageUrl;
    image.alt = `${title || 'Figma 프레임'} 썸네일`;
    article.prepend(image);
  }

  root.append(article);
}

function appendFigmaTextResult(root, title, text) {
  const article = document.createElement('article');
  article.className = 'figma-result-card figma-text-result';
  article.innerHTML = '<b></b><pre></pre>';
  $('b', article).textContent = title;
  $('pre', article).textContent = text;
  root.append(article);
}

function formatDate(value) {
  if (!value) return '방금 전';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes)) return '';
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function handleMeetingAudioSelect(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (state.meetingAudio.url) URL.revokeObjectURL(state.meetingAudio.url);
  state.meetingAudio.file = file;
  state.meetingAudio.url = URL.createObjectURL(file);

  $('#meetingUploadPanel').classList.remove('hidden');
  $('#meetingFileName').textContent = file.name;
  $('#meetingFileMeta').textContent = [file.type || 'audio', formatFileSize(file.size)].filter(Boolean).join(' · ');
  $('#meetingUploadHelp').textContent = '파일을 확인한 뒤 AI 요약 요청을 누르면 백엔드로 전송됩니다.';
  $('#sendMeetingAudioSummary').disabled = false;
  $('#sendMeetingAudioSummary').textContent = 'AI 요약 요청';
  $('#meetingUploadButton').textContent = '파일 변경';

  const preview = $('#meetingAudioPreview');
  preview.src = state.meetingAudio.url;
  preview.classList.remove('hidden');
}

async function handleMeetingAudioSummary() {
  const file = state.meetingAudio.file;
  if (!file) {
    $('#meetingAudioUpload').click();
    return;
  }

  const button = $('#sendMeetingAudioSummary');
  button.disabled = true;
  button.textContent = '요약 요청 중';
  $('#meetingUploadHelp').textContent = '녹음 파일을 백엔드로 보내는 중입니다.';

  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', file.name.replace(/\.[^.]+$/, ''));
    const summary = await apiRequest('/ai/summarize', { method: 'POST', body: formData });

    if (isDemoResponse(summary)) {
      $('#meetingUploadHelp').textContent = '아직 백엔드가 연결되지 않아 AI 요약을 만들 수 없습니다. 파일 선택은 정상입니다.';
      setStatus('ai', '대기', false);
      setStatus('meetings', '대기', false);
      return;
    }

    renderMeetingSummaryResult(summary);
    setDashboardSummary(summary.summary_markdown);
    state.meetings = [toMeetingPreview(summary), ...state.meetings.filter((meeting) => meeting.id !== summary.id)];
    renderMeetings(state.meetings);
    $('#meetingUploadHelp').textContent = 'AI 요약이 완료되었습니다.';
    setStatus('ai', '연결됨');
    setStatus('meetings', '저장됨');
  } finally {
    button.disabled = false;
    button.textContent = 'AI 요약 요청';
  }
}

function renderMeetingSummaryResult(summary) {
  const card = $('#meetingEmptyCard');
  card.className = 'meeting-summary-card';
  card.innerHTML = '<small>AI 요약 결과</small><pre></pre>';
  $('pre', card).textContent = summary.summary_markdown || '요약 결과가 비어 있습니다.';
}

function appendBubble(kind, text, meta = '') {
  $('#chatEmpty')?.remove();
  const bubble = document.createElement('div');
  bubble.className = `bubble ${kind}`;
  bubble.textContent = text;
  if (meta) {
    const small = document.createElement('small');
    small.textContent = meta;
    bubble.append(small);
  }
  $('#chatList').append(bubble);
  bubble.scrollIntoView({ block: 'nearest' });
  return bubble;
}

async function handleChatSubmit(event) {
  event.preventDefault();
  const input = $('#chatInput');
  const message = input.value.trim();
  if (!message) return;
  appendBubble('user', message);
  input.value = '';
  const pending = appendBubble('ai', '답변을 생성하는 중입니다.', '/ai/chat');
  const response = await apiRequest('/ai/chat', { method: 'POST', body: { message } });
  pending.textContent = response.reply || '답변을 가져오지 못했습니다.';
  const small = document.createElement('small');
  small.textContent = '/ai/chat';
  pending.append(small);
  if (!isDemoResponse(response)) setDashboardSummary(response.reply);
  setStatus('ai', isDemoResponse(response) ? '대기' : '연결됨', !isDemoResponse(response));
}

async function handleSummarySubmit(event) {
  event.preventDefault();
  const title = $('#meetingTitle').value.trim();
  const transcript = $('#meetingTranscript').value.trim();
  if (!title || !transcript) return;
  const summary = await apiRequest('/ai/summarize-text', {
    method: 'POST',
    body: { title, transcript },
    fallbackPath: '/ai/summarize_text',
  });
  renderSummary(summary);
  state.meetings = [toMeetingPreview(summary), ...state.meetings.filter((meeting) => meeting.id !== summary.id)];
  renderMeetings(state.meetings);
  const isLive = !isDemoResponse(summary);
  if (isLive) setDashboardSummary(summary.summary_markdown);
  setStatus('ai', isLive ? '연결됨' : '대기', isLive);
  setStatus('meetings', isLive ? '저장됨' : '대기', isLive);
}

async function handleAudioSummary(event) {
  event.preventDefault();
  const file = $('#audioFile').files[0];
  if (!file) {
    $('#audioResult').textContent = '업로드할 음성 파일을 선택해 주세요.';
    return;
  }
  const formData = new FormData();
  formData.append('file', file);
  formData.append('title', file.name.replace(/\.[^.]+$/, ''));
  const summary = await apiRequest('/ai/summarize', { method: 'POST', body: formData });
  $('#audioResult').textContent = `${summary.title || file.name} 요약 요청이 완료되었습니다.`;
  renderSummary(summary);
  if (!isDemoResponse(summary)) setDashboardSummary(summary.summary_markdown);
  setStatus('ai', isDemoResponse(summary) ? '대기' : '연결됨', !isDemoResponse(summary));
}

function renderSummary(summary) {
  $('#summaryOutput').innerHTML = '<h4>AI 요약 결과</h4><pre></pre>';
  $('pre', $('#summaryOutput')).textContent = summary.summary_markdown || '요약 결과가 비어 있습니다.';
}

function toMeetingPreview(summary) {
  const preview = (summary.summary_markdown || '').replace(/[#*\-[\]]/g, '').replace(/\s+/g, ' ').trim();
  return {
    id: summary.id,
    title: summary.title,
    summary_preview: preview.slice(0, 90),
    created_at: summary.created_at || new Date().toISOString(),
  };
}

async function handleNoteSubmit(event) {
  event.preventDefault();
  const title = $('#noteTitle').value.trim();
  const content = $('#noteContent').value.trim();
  if (!title || !content) return;
  const note = await apiRequest('/notes', { method: 'POST', body: { title, content } });
  state.notes = [note, ...state.notes.filter((item) => item.id !== note.id)];
  renderNotes(state.notes);
  setStatus('notes', isDemoResponse(note) ? '대기' : '저장됨', !isDemoResponse(note));
}

async function handleLayoutSubmit(event) {
  event.preventDefault();
  const layoutData = getCurrentLayoutData();
  const layout = await apiRequest('/workspace/layout', { method: 'PUT', body: { layout_data: layoutData } });
  state.layout = layout;
  renderLayout(layout);
  setStatus('workspace', isDemoResponse(layout) ? '대기' : '저장됨', !isDemoResponse(layout));
}

function renderCommunityPosts() {
  const list = $('#communityPosts');
  list.innerHTML = '';
  const posts = state.communityFilter === '전체'
    ? state.communityPosts
    : state.communityPosts.filter((post) => post.category === state.communityFilter);

  if (!posts.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = '게시글이 없습니다.';
    list.append(empty);
    return;
  }

  posts.forEach((post) => {
    const article = document.createElement('article');
    article.dataset.postId = post.id;
    article.tabIndex = 0;
    article.setAttribute('role', 'button');
    article.innerHTML = '<div class="post-row"><b></b><div class="post-actions"></div></div><small></small><p></p>';
    $('b', article).textContent = post.title;
    $('small', article).textContent = `${post.category} · ${post.time} · 댓글 ${getCommunityComments(post).length}`;
    $('p', article).textContent = post.content || '';
    $('p', article).classList.toggle('hidden', !post.content);
    if (post.owned) {
      const actions = $('.post-actions', article);
      actions.innerHTML = '<button type="button" data-post-action="edit">수정</button><button type="button" data-post-action="delete">삭제</button>';
      $$('button', actions).forEach((button) => {
        button.dataset.postId = post.id;
      });
    }
    list.append(article);
  });
}

function getCommunityComments(post) {
  return Array.isArray(post?.comments) ? post.comments : [];
}

function getCurrentCommentAuthor() {
  return state.user?.nickname?.trim() || $('#authNickname')?.value.trim() || '나';
}

function saveCommunityPosts() {
  localStorage.setItem(communityKey, JSON.stringify(state.communityPosts));
}

function openPostComposer(post = null) {
  state.editingCommunityPostId = post?.id || '';
  $('#postTitle').value = post?.title || '';
  $('#postCategory').value = post?.category || (state.communityFilter === '전체' ? '자유게시판' : state.communityFilter);
  $('#postContent').value = post?.content || '';
  $('#savePostButton').textContent = post ? '수정' : '등록';
  $('#postComposer').classList.remove('hidden');
  $('#openPostComposer').classList.add('hidden');
  $('#postTitle').focus();
}

function closePostComposer() {
  $('#postComposer').reset();
  state.editingCommunityPostId = '';
  $('#savePostButton').textContent = '등록';
  $('#postComposer').classList.add('hidden');
  $('#openPostComposer').classList.remove('hidden');
}

function openCommunityDetail(postId) {
  state.selectedCommunityPostId = postId;
  closePostComposer();
  $('.filters').classList.add('hidden');
  $('#communityPosts').classList.add('hidden');
  $('#openPostComposer').classList.add('hidden');
  $('#communityDetail').classList.remove('hidden');
  renderCommunityDetail();
}

function closeCommunityDetail() {
  state.selectedCommunityPostId = '';
  $('#communityDetail').classList.add('hidden');
  $('.filters').classList.remove('hidden');
  $('#communityPosts').classList.remove('hidden');
  $('#openPostComposer').classList.remove('hidden');
  renderCommunityPosts();
}

function renderCommunityDetail() {
  const post = state.communityPosts.find((item) => item.id === state.selectedCommunityPostId);
  if (!post) {
    closeCommunityDetail();
    return;
  }

  const comments = getCommunityComments(post);
  $('#detailTitle').textContent = post.title;
  $('#detailMeta').textContent = `${post.category} · ${post.time} · 댓글 ${comments.length}`;
  $('#detailContent').textContent = post.content || '내용이 없습니다.';
  $('#detailContent').classList.toggle('empty-content', !post.content);

  const actions = $('#detailActions');
  actions.innerHTML = '';
  if (post.owned) {
    actions.innerHTML = '<button type="button" data-post-action="edit">수정</button><button type="button" data-post-action="delete">삭제</button>';
    $$('button', actions).forEach((button) => {
      button.dataset.postId = post.id;
    });
  }

  const list = $('#commentList');
  list.innerHTML = '';
  if (!comments.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = '아직 댓글이 없습니다.';
    list.append(empty);
    return;
  }

  comments.forEach((comment) => {
    const item = document.createElement('article');
    item.innerHTML = '<b></b><small></small><p></p>';
    $('b', item).textContent = comment.author || '나';
    $('small', item).textContent = comment.time || '방금 전';
    $('p', item).textContent = comment.content;
    list.append(item);
  });
}

function handlePostSubmit(event) {
  event.preventDefault();
  const title = $('#postTitle').value.trim();
  const category = $('#postCategory').value;
  const content = $('#postContent').value.trim();
  if (!title) return;

  if (state.editingCommunityPostId) {
    state.communityPosts = state.communityPosts.map((post) => post.id === state.editingCommunityPostId
      ? { ...post, title, category, content, time: '수정됨', owned: true, comments: getCommunityComments(post) }
      : post);
    saveCommunityPosts();
    renderCommunityPosts();
    if (state.selectedCommunityPostId) renderCommunityDetail();
    closePostComposer();
    return;
  }

  const post = {
    id: `community-${Date.now()}`,
    title,
    category,
    time: '방금 전',
    comments: [],
    content,
    owned: true,
  };
  state.communityPosts = [post, ...state.communityPosts];
  saveCommunityPosts();
  renderCommunityPosts();
  closePostComposer();
}

function setCommunityFilter(filter) {
  state.communityFilter = filter;
  $$('[data-community-filter]').forEach((button) => {
    button.classList.toggle('active', button.dataset.communityFilter === filter);
  });
  if (state.selectedCommunityPostId) closeCommunityDetail();
  closePostComposer();
  renderCommunityPosts();
}

function handleCommunityPostAction(event) {
  const button = event.target.closest('[data-post-action]');
  if (!button) {
    const card = event.target.closest('[data-post-id]');
    if (card) openCommunityDetail(card.dataset.postId);
    return;
  }

  event.stopPropagation();
  const post = state.communityPosts.find((item) => item.id === button.dataset.postId);
  if (!post || !post.owned) return;
  if (button.dataset.postAction === 'edit') {
    if (state.selectedCommunityPostId) closeCommunityDetail();
    openPostComposer(post);
    return;
  }

  state.communityPosts = state.communityPosts.filter((item) => item.id !== post.id);
  saveCommunityPosts();
  if (state.selectedCommunityPostId === post.id) closeCommunityDetail();
  renderCommunityPosts();
}

function handleCommunityPostKeydown(event) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  const card = event.target.closest('[data-post-id]');
  if (!card) return;
  event.preventDefault();
  openCommunityDetail(card.dataset.postId);
}

function handleCommentSubmit(event) {
  event.preventDefault();
  const input = $('#commentInput');
  const content = input.value.trim();
  if (!content || !state.selectedCommunityPostId) return;

  state.communityPosts = state.communityPosts.map((post) => {
    if (post.id !== state.selectedCommunityPostId) return post;
    const comments = [
      ...getCommunityComments(post),
      {
        id: `comment-${Date.now()}`,
        author: getCurrentCommentAuthor(),
        content,
        time: '방금 전',
      },
    ];
    return { ...post, comments };
  });
  input.value = '';
  saveCommunityPosts();
  renderCommunityDetail();
}

const names = {
  dashboard: '아이디어 보드',
  ai: 'AI 채팅',
  meeting: '회의 기록',
  community: '커뮤니티',
  workspace: '2분할 작업창',
};

function showView(name) {
  $$('.view').forEach((view) => view.classList.toggle('active', view.id === `${name}View`));
  $$('.side-link').forEach((button) => button.classList.toggle('active', button.dataset.view === name));
  $('#viewTitle').textContent = names[name];
  if (name === 'workspace') renderWorkspacePreview();
}

$('#signupForm').addEventListener('submit', handleAuthSubmit);
$$('[data-auth-mode]').forEach((button) => button.addEventListener('click', () => setAuthMode(button.dataset.authMode)));
$$('[data-next]').forEach((button) => button.addEventListener('click', () => showScreen('app')));
$('#installDiscordBot').addEventListener('click', continueWithDiscord);
$('#discordConnect').addEventListener('click', continueWithDiscord);
$('#enterDashboard').addEventListener('click', () => showScreen('app'));
$('#openProjectSetup').addEventListener('click', () => showScreen('connect'));
$('#showFigmaGuide').addEventListener('click', () => $('#figmaGuide').scrollIntoView({ behavior: 'smooth', block: 'center' }));
$('#figmaPatForm').addEventListener('submit', handleFigmaPatSubmit);
$('#disconnectFigmaPat').addEventListener('click', handleFigmaDisconnect);
$$('.link-btn,.channel-btn').forEach((button) => {
  if (['showFigmaGuide', 'githubConnect', 'notionConnect', 'discordConnect'].includes(button.id)) return;
  button.addEventListener('click', () => button.closest('.tool')?.classList.add('connected'));
});
$$('[data-view]').forEach((button) => button.addEventListener('click', () => showView(button.dataset.view)));
$$('[data-jump]').forEach((button) => button.addEventListener('click', () => showView(button.dataset.jump)));
$('#refreshData').addEventListener('click', refreshAppData);
$('#chatForm').addEventListener('submit', handleChatSubmit);
$('#summaryForm')?.addEventListener('submit', handleSummarySubmit);
$('#audioSummaryForm')?.addEventListener('submit', handleAudioSummary);
$('#noteForm').addEventListener('submit', handleNoteSubmit);
$('#layoutForm').addEventListener('submit', handleLayoutSubmit);
$('#figmaFileForm').addEventListener('submit', handleFigmaFileSubmit);
$('#notionConnect').addEventListener('click', continueWithNotion);
$('#notionAuthorizeButton').addEventListener('click', continueWithNotion);
$('#notionDisconnectButton').addEventListener('click', () => disconnectIntegration('notion'));
$('#loadNotionPagesButton').addEventListener('click', loadNotionPages);
$('#loadNotionBlocksButton').addEventListener('click', loadNotionBlocks);
$('#githubConnect').addEventListener('click', continueWithGithub);
$('#githubAuthorizeButton').addEventListener('click', continueWithGithub);
$('#githubDisconnectButton').addEventListener('click', () => disconnectIntegration('github'));
$('#loadGithubReposButton').addEventListener('click', loadGithubRepos);
$$('[data-github-resource]').forEach((button) => {
  button.addEventListener('click', () => loadGithubResource(button.dataset.githubResource));
});
['#panelOneType', '#panelTwoType', '#panelTwoUrl'].forEach((selector) => {
  $(selector).addEventListener('input', () => {
    const data = getCurrentLayoutData();
    state.layout = { id: state.layout?.id || 'layout-preview', layout_data: data };
    renderWorkspacePreview(data);
  });
});
$('#openPostComposer').addEventListener('click', () => openPostComposer());
$('#cancelPostComposer').addEventListener('click', closePostComposer);
$('#postComposer').addEventListener('submit', handlePostSubmit);
$('#communityPosts').addEventListener('click', handleCommunityPostAction);
$('#communityPosts').addEventListener('keydown', handleCommunityPostKeydown);
$('#communityDetail').addEventListener('click', handleCommunityPostAction);
$('#backToCommunityList').addEventListener('click', closeCommunityDetail);
$('#commentForm').addEventListener('submit', handleCommentSubmit);
$('#meetingDiscordButton')?.addEventListener('click', continueWithDiscord);
$('#meetingUploadButton')?.addEventListener('click', () => $('#meetingAudioUpload')?.click());
$('#changeMeetingAudio')?.addEventListener('click', () => $('#meetingAudioUpload')?.click());
$('#meetingAudioUpload')?.addEventListener('change', handleMeetingAudioSelect);
$('#sendMeetingAudioSummary')?.addEventListener('click', handleMeetingAudioSummary);
$$('[data-community-filter]').forEach((button) => {
  button.addEventListener('click', () => setCommunityFilter(button.dataset.communityFilter));
});

setAuthMode('signup');
setApiMode('API 연결 준비', false);
updateUserUi();
renderDashboardSummary();
renderNotionStatus();
renderGithubStatus();
renderNotionPageOptions([]);
renderWorkspacePreview();
renderCommunityPosts();
if (state.token) refreshAppData();
