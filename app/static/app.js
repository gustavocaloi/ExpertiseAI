const state = {
  token: localStorage.getItem('expai_token') || '',
  companyId: localStorage.getItem('expai_company_id') || '',
  accessControlEnabled: true,
  profile: null,
  taxonomies: {
    areas: [],
    categorias: [],
  },
};

const queryParams = new URLSearchParams(window.location.search);
const DEBUG_MENU = queryParams.has('debug') || queryParams.has('trace') || localStorage.getItem('expai_debug') === '1';

if (queryParams.get('debug') === '1' && localStorage.getItem('expai_debug') !== '1') {
  localStorage.setItem('expai_debug', '1');
}

function debugMenuLog(...args) {
  if (!DEBUG_MENU && !state.token) {
    return;
  }
  // eslint-disable-next-line no-console
  console.log('[Expertise.AI][Menu]', ...args);
}

const loginPanel = document.getElementById('loginPanel');
const dashboardPanel = document.getElementById('dashboardPanel');
const workspaceNav = document.getElementById('workspaceNav');
const userMenu = document.getElementById('userMenu');
const userMenuBtn = document.getElementById('userMenuBtn');
const userMenuDropdown = document.getElementById('userMenuDropdown');
const statusChip = document.getElementById('statusChip');
const brandHomeLink = document.getElementById('brandHomeLink');
const brandHomeWrap = document.querySelector('.brand-wrap');
const loginMsg = document.getElementById('loginMsg');
const createMsg = document.getElementById('createMsg');
const publishMsg = document.getElementById('publishMsg');
const taxonomyMsg = document.getElementById('taxonomyMsg');
const sessionButtons = Array.from(document.querySelectorAll('.menu-item[data-session]'));
const toastContainer = document.getElementById('toastContainer');
const docsList = document.getElementById('docsList');
const createSession = document.getElementById('createSession');
const docModal = document.getElementById('docViewerModal');
const docModalOverlay = document.getElementById('docModalOverlay');
const docModalCloseBtn = document.getElementById('docModalCloseBtn');
const docModalEditBtn = document.getElementById('docModalEditBtn');
const docModalTitle = document.getElementById('docModalTitle');
const docModalMeta = document.getElementById('docModalMeta');
const docModalContent = document.getElementById('docModalContent');
const profileName = document.getElementById('profileName');
const profileEmail = document.getElementById('profileEmail');
const profileRole = document.getElementById('profileRole');
const profileCompany = document.getElementById('profileCompany');
const userAvatar = document.getElementById('userAvatar');
const userProfileMenuItem = document.getElementById('userProfileMenuItem');
const userLogoutMenuItem = document.getElementById('userLogoutMenuItem');
const importProgressOverlay = document.getElementById('importProgressOverlay');
const importProgressMessage = document.getElementById('importProgressMessage');
const importProgressBar = document.getElementById('importProgressBar');
const modalVersionPublishToggle = document.getElementById('modalVersionPublishToggle');
const modalPublishToggleInfo = document.getElementById('modalPublishToggleInfo');
const modalPublishToggleWrap = document.getElementById('modalPublishToggleWrap');
const taxonomySession = document.getElementById('taxonomySession');
const areasList = document.getElementById('areasList');
const categoriasList = document.getElementById('categoriasList');
const areaInput = document.getElementById('areaInput');
const categoriaInput = document.getElementById('categoriaInput');
const addAreaForm = document.getElementById('addAreaForm');
const addCategoriaForm = document.getElementById('addCategoriaForm');
const docArea = document.getElementById('docArea');
const docCategoria = document.getElementById('docCategoria');
const userAdminMenuItem = document.getElementById('userAdminMenuItem');
const userAdminSession = document.getElementById('userAdminSession');
const usersList = document.getElementById('usersList');
const addUserForm = document.getElementById('addUserForm');
const newUserName = document.getElementById('newUserName');
const newUserEmail = document.getElementById('newUserEmail');
const newUserPassword = document.getElementById('newUserPassword');
const newUserRole = document.getElementById('newUserRole');
const userAdminMsg = document.getElementById('userAdminMsg');
const editHistorySession = document.getElementById('editHistorySession');
const editVersionsList = document.getElementById('editVersionsList');
const editHistoryHint = document.getElementById('editHistoryHint');
const versionPreviewSession = document.getElementById('versionPreviewSession');
const versionPreviewInfo = document.getElementById('versionPreviewInfo');
const versionPreviewContent = document.getElementById('versionPreviewContent');
const versionPublishToggle = document.getElementById('versionPublishToggle');
const publishToggleInfo = document.getElementById('publishToggleInfo');
const logoutBtn = document.getElementById('userLogoutMenuItem');
const docAreaSelect = docArea;
const docCategoriaSelect = docCategoria;
const docSlugInput = document.getElementById('docSlug');
const docTitleInput = document.getElementById('docTitle');
const docContentInput = document.getElementById('docContent');

let selectedDocument = null;
let editingDocumentKey = null;
let editingDocumentContext = null;
let editingHistoryVersions = [];
let selectedHistoryVersion = null;
let importProgressTimer = null;
let taxonomyLoading = false;
let isSlugAutoSuggestionEnabled = true;
const FALLBACK_AREA = 'sem-area';
const FALLBACK_CATEGORIA = 'sem-categoria';

function docTitleOf(doc) {
  return doc?.titulo || doc?.title || '';
}

function docPublishedVersionOf(doc) {
  return doc?.published_version || doc?.versao_publicada || doc?.version || '';
}

function contentVersionOf(payload) {
  return payload?.version || payload?.versao || payload?.content_version || payload?.conteudo_versao || '';
}

function contentPublishedOf(payload) {
  if (payload?.published !== undefined) {
    return Boolean(payload.published);
  }
  if (payload?.publicado !== undefined) {
    return Boolean(payload.publicado);
  }
  if (payload?.content_published !== undefined) {
    return Boolean(payload.content_published);
  }
  if (payload?.conteudo_publicado !== undefined) {
    return Boolean(payload.conteudo_publicado);
  }
  return false;
}

function setTaxonomySelectOptions() {
  if (!docArea || !docCategoria) {
    return;
  }
  const areaList = state.taxonomies.areas;
  const categoriaList = state.taxonomies.categorias;

  docArea.innerHTML = '<option value="" selected>Sem área (opcional)</option>';
  areaList.forEach((name) => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    docArea.appendChild(option);
  });

  docCategoria.innerHTML = '<option value="" selected>Sem categoria (opcional)</option>';
  categoriaList.forEach((name) => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    docCategoria.appendChild(option);
  });
}

function setFormSelectValue(select, value) {
  if (!select || value == null) {
    return;
  }
  const target = String(value);
  const existing = [...select.options].some((option) => option.value === target);
  if (!existing) {
    const option = document.createElement('option');
    option.value = target;
    option.textContent = target;
    select.appendChild(option);
  }
  select.value = target;
}

function renderTaxonomyList(listElement, items = [], kind) {
  if (!listElement) {
    return;
  }
  if (!items.length) {
    listElement.innerHTML = '<li>Nenhum item cadastrado.</li>';
    return;
  }
  listElement.innerHTML = '';
  items.forEach((name) => {
    const li = document.createElement('li');
    li.className = 'taxonomy-item';
    li.innerHTML = `
      <span class="taxonomy-name">${name}</span>
      <button type="button" class="taxonomy-remove" data-kind="${kind}" data-name="${name}">Remover</button>
    `;
    listElement.appendChild(li);
  });
}

function renderTaxonomies() {
  renderTaxonomyList(areasList, state.taxonomies.areas, 'areas');
  renderTaxonomyList(categoriasList, state.taxonomies.categorias, 'categorias');
  setTaxonomySelectOptions();
}

function renderTaxonomyError(message) {
  if (!taxonomyMsg) return;
  taxonomyMsg.textContent = message;
  taxonomyMsg.className = message ? 'helper error' : 'helper';
}

function isAdminProfile(profile = state.profile) {
  return (profile?.role || '').toLowerCase() === 'admin';
}

function toBooleanValue(value, fallback = true) {
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    return value !== 0;
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    return ['1', 'true', 'yes', 'on'].includes(normalized);
  }
  return fallback;
}

function isAccessControlEnabled() {
  return state.accessControlEnabled !== false;
}

function canAccessPlatform() {
  return isAccessControlEnabled() ? Boolean(state.token && state.companyId) : Boolean(state.companyId);
}

function ensureAnonymousProfile() {
  const companyId = state.companyId ? Number(state.companyId) : null;
  state.profile = {
    user_id: 0,
    full_name: 'Anônimo',
    email: 'anônimo',
    role: 'anônimo',
    company_id: companyId || 0,
    company_name: companyId ? `empresa ${companyId}` : 'empresa',
  };
  renderProfileToUi(state.profile);
  setPanelStatusText();
}

function renderUsersList(users = []) {
  if (!usersList) {
    return;
  }
  if (!users.length) {
    usersList.innerHTML = '<li>Nenhum usuário encontrado.</li>';
    return;
  }
  usersList.innerHTML = '';
  users.forEach((item) => {
    const li = document.createElement('li');
    li.className = 'items-list-item';
    li.innerHTML = `
      <span>${item.full_name || item.nome || '-'} · ${item.email || '-'}</span>
      <strong>${item.role || '-'}</strong>
    `;
    usersList.appendChild(li);
  });
}

function toggleAdminMenuVisibility() {
  if (!isAccessControlEnabled()) {
    if (userAdminMenuItem) {
      userAdminMenuItem.classList.add('hidden-view');
      userAdminMenuItem.setAttribute('aria-hidden', 'true');
    }
    if (userAdminSession && userAdminSession.classList.contains('active-session')) {
      showSession('dashboardSession');
    }
    return;
  }
  if (userAdminMenuItem) {
    userAdminMenuItem.classList.toggle('hidden-view', !isAdminProfile());
    userAdminMenuItem.setAttribute('aria-hidden', String(!isAdminProfile()));
  }
  if (userAdminSession && !isAdminProfile() && userAdminSession.classList.contains('active-session')) {
    showSession('dashboardSession');
  }
}

async function loadUsersForCompany() {
  if (!isAccessControlEnabled()) {
    if (usersList) {
      usersList.innerHTML = 'Acesso a usuários indisponível no modo sem autenticação.';
    }
    return;
  }
  if (!state.companyId || !isAdminProfile()) {
    if (usersList) {
      usersList.innerHTML = '<li>Sem permissão para visualizar usuários.</li>';
    }
    return;
  }
  try {
    const users = await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios`);
    renderUsersList(users || []);
    if (userAdminMsg) {
      userAdminMsg.textContent = '';
      userAdminMsg.className = 'helper';
    }
  } catch (error) {
    if (usersList) {
      usersList.innerHTML = `<li>${error.message}</li>`;
    }
  }
}

async function loadTaxonomies() {
  if (!state.companyId) {
    state.taxonomies.areas = [];
    state.taxonomies.categorias = [];
    renderTaxonomies();
    return;
  }
  if (taxonomyLoading) {
    return;
  }

  taxonomyLoading = true;
  try {
    const [areasData, categoriasData] = await Promise.all([
      apiFetch(`/api/v1/empresas/${state.companyId}/areas`),
      apiFetch(`/api/v1/empresas/${state.companyId}/categorias`),
    ]);
    state.taxonomies.areas = areasData?.items || [];
    state.taxonomies.categorias = categoriasData?.items || [];
    renderTaxonomies();
    renderTaxonomyError('');
  } catch (error) {
    state.taxonomies = { areas: [], categorias: [] };
    renderTaxonomies();
    renderTaxonomyError(error.message);
  } finally {
    taxonomyLoading = false;
  }
}

async function loadPlatformConfig() {
  try {
    const config = await apiFetch('/api/v1/config');
    state.accessControlEnabled = toBooleanValue(config?.access_control_enabled, true);

    if (!isAccessControlEnabled()) {
      const defaultCompanyId = config?.default_company_id;
      if (!state.companyId && defaultCompanyId) {
        state.companyId = String(defaultCompanyId);
        localStorage.setItem('expai_company_id', state.companyId);
      }
      if (!state.companyId && !defaultCompanyId) {
        state.companyId = '1';
        localStorage.setItem('expai_company_id', state.companyId);
      }
      if (!state.companyId) {
        state.companyId = '1';
        localStorage.setItem('expai_company_id', state.companyId);
      }
      ensureAnonymousProfile();
    }
  } catch {
    state.accessControlEnabled = false;
    if (!state.companyId) {
      state.companyId = localStorage.getItem('expai_company_id') || '1';
      localStorage.setItem('expai_company_id', state.companyId);
    }
    ensureAnonymousProfile();
  }
}

function normalizeVersion(value) {
  if (value === undefined || value === null) {
    return '';
  }
  return String(value).trim();
}

function parseVersionParts(value) {
  const version = normalizeVersion(value);
  const match = /^\s*(\d+)(?:\.(\d+))?\s*$/.exec(version);
  if (!match) {
    return [0, 0];
  }
  return [Number(match[1]), Number(match[2] || 0)];
}

function compareVersions(a, b) {
  const [aMajor, aMinor] = parseVersionParts(a);
  const [bMajor, bMinor] = parseVersionParts(b);
  if (aMajor !== bMajor) {
    return aMajor - bMajor;
  }
  return aMinor - bMinor;
}

const sessions = {
  dashboardSession: document.getElementById('dashboardSession'),
  createSession: document.getElementById('createSession'),
  profileSession: document.getElementById('profileSession'),
  taxonomySession: document.getElementById('taxonomySession'),
  userAdminSession: document.getElementById('userAdminSession'),
  publishSession: document.getElementById('publishSession'),
};

function showInlineCreateSession(show = true) {
  if (!createSession) {
    return;
  }

  if (show) {
    if (state.companyId && (!state.taxonomies.areas.length || !state.taxonomies.categorias.length)) {
      void loadTaxonomies();
    }
    showSession('createSession');
    createSession.classList.remove('hidden-view');
    return;
  }

  showSession('dashboardSession');
  createSession.classList.add('hidden-view');
}

function showSession(sessionId) {
  if (sessionId === 'userAdminSession' && !isAdminProfile()) {
    showToast('Somente administradores podem acessar a sessão de usuários.', 'error');
    sessionId = 'dashboardSession';
  }

  Object.entries(sessions).forEach(([id, el]) => {
    if (!el) return;
    el.classList.toggle('active-session', id === sessionId);
  });

  sessionButtons.forEach((button) => {
    const selected = button.dataset.session === sessionId;
    button.classList.toggle('active', selected);
  });
}

function setStatus(text, ok = true) {
  statusChip.textContent = text;
  statusChip.style.color = ok ? 'var(--ink-soft)' : '#8c342f';
}

function formatProfileLabel(profile) {
  const name = profile?.full_name || profile?.email || 'usuário';
  const role = profile?.role || 'sem perfil';
  const company = profile?.company_name || `empresa ${state.companyId || '-'}`;
  return `${name} · ${role} · ${company}`;
}

function getInitials(profile) {
  const fallback = String(profile?.email || profile?.full_name || profile?.role || 'U').trim();
  if (!fallback) {
    return 'U';
  }
  const source = (profile?.full_name || '').trim();
  if (!source) {
    return fallback.charAt(0).toUpperCase();
  }
  const parts = source.split(/\s+/).filter(Boolean);
  if (!parts.length) {
    return source.charAt(0).toUpperCase();
  }
  if (parts.length === 1) {
    return parts[0].charAt(0).toUpperCase();
  }
  return `${parts[0].charAt(0)}${parts[1].charAt(0)}`.toUpperCase();
}

function renderProfileToUi(profile = null) {
  const data = profile || {};
  if (profileName) {
    profileName.textContent = data.full_name || data.email || '-';
  }
  if (profileEmail) {
    profileEmail.textContent = data.email || '-';
  }
  if (profileRole) {
    profileRole.textContent = data.role || '-';
  }
  if (profileCompany) {
    profileCompany.textContent = data.company_name || '-';
  }
  if (userAvatar) {
    userAvatar.textContent = getInitials(data);
  }
}

function setPanelStatusText() {
  if (state.profile) {
    setStatus(formatProfileLabel(state.profile));
    renderProfileToUi(state.profile);
    return;
  }
  setStatus('sem sessão de usuário');
}

function clearImportProgressTimer() {
  if (importProgressTimer) {
    window.clearInterval(importProgressTimer);
    importProgressTimer = null;
  }
}

function updateImportProgress(percent, message) {
  if (importProgressBar) {
    importProgressBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  }
  if (message && importProgressMessage) {
    importProgressMessage.textContent = message;
  }
}

function showImportProgress(message = 'Processando arquivo...') {
  if (importProgressOverlay) {
    importProgressOverlay.classList.remove('hidden-view');
  }
  if (importProgressBar) {
    importProgressBar.style.width = '0%';
  }
  clearImportProgressTimer();
  let progress = 6;
  updateImportProgress(progress, message);
  importProgressTimer = window.setInterval(() => {
    const step = Math.floor(Math.random() * 6) + 2;
    progress = Math.min(88, progress + step);
    updateImportProgress(progress, importProgressMessage?.textContent || message);
  }, 180);
}

function hideImportProgress(message = null) {
  clearImportProgressTimer();
  if (message) {
    updateImportProgress(100, message);
  }
  window.setTimeout(() => {
    if (importProgressOverlay) {
      importProgressOverlay.classList.add('hidden-view');
    }
    if (importProgressBar) {
      importProgressBar.style.width = '0%';
    }
  }, 250);
}

function setPanel(authenticated) {
  debugMenuLog('setPanel', { authenticated, token: Boolean(state.token), companyId: state.companyId, hasProfile: Boolean(state.profile), accessControlEnabled: isAccessControlEnabled() });
  if (authenticated) {
    loginPanel.classList.add('hidden-view');
    loginPanel.classList.remove('active');
    dashboardPanel.classList.add('active');
    workspaceNav.style.display = 'flex';
    if (userMenu) {
      userMenu.style.display = 'block';
    }
    debugMenuLog('setPanel.auth', {
      userMenuExists: Boolean(userMenu),
      dropdownExists: Boolean(userMenuDropdown),
      admin: isAdminProfile(),
    });
    loadTaxonomies();
    toggleAdminMenuVisibility();
    showSession('dashboardSession');
    setPanelStatusText();
    hideUserMenu();
    loadPublishedDocs();
  } else {
    loginPanel.classList.remove('hidden-view');
    loginPanel.classList.add('active');
    dashboardPanel.classList.remove('active');
    workspaceNav.style.display = 'none';
    if (userMenu) {
      userMenu.style.display = 'none';
      hideUserMenu();
    }
    hideEditHistory();
    selectedDocument = null;
    showInlineCreateSession(false);
    state.taxonomies = { areas: [], categorias: [] };
    renderTaxonomies();
    state.profile = null;
    renderProfileToUi({ full_name: '-', email: '-', role: '-', company_name: '-' });
    toggleAdminMenuVisibility();
    if (usersList) {
      usersList.innerHTML = '<li>Sem permissão para visualizar usuários.</li>';
    }
    setStatus('sem autenticação');
  }
}

function closeDocumentModal() {
  docModal.classList.remove('open');
  docModal.setAttribute('aria-hidden', 'true');
  if (modalVersionPublishToggle) {
    modalVersionPublishToggle.checked = false;
    modalVersionPublishToggle.disabled = true;
  }
  if (modalPublishToggleInfo) {
    modalPublishToggleInfo.textContent = 'Publicar esta versão';
  }
}

function hideUserMenu() {
  setUserMenuOpen(false);
}

function toggleUserMenu() {
  if (!userMenuDropdown || !userMenuBtn) {
    return;
  }
  const isOpen = userMenuDropdown.classList.contains('is-open');
  setUserMenuOpen(!isOpen);
}

function setUserMenuOpen(open = false) {
  if (!userMenuDropdown || !userMenuBtn) {
    debugMenuLog('setUserMenuOpen.blocked', { open, hasMenu: Boolean(userMenu), hasDropdown: Boolean(userMenuDropdown), hasBtn: Boolean(userMenuBtn) });
    return;
  }
  if (open) {
    if (userMenu) {
      userMenu.classList.add('is-open');
    }
    userMenuDropdown.classList.add('is-open');
    userMenuDropdown.style.display = 'grid';
    userMenuDropdown.style.visibility = 'visible';
    userMenuDropdown.style.pointerEvents = 'auto';
    userMenuDropdown.setAttribute('aria-hidden', 'false');
    userMenuBtn.setAttribute('aria-expanded', 'true');

    const rect = userMenuDropdown.getBoundingClientRect();
    const itemLabels = Array.from(userMenuDropdown.children).map((item) => item?.textContent?.trim()).filter(Boolean);
    debugMenuLog('setUserMenuOpen.opened', {
      open,
      display: userMenuDropdown.style.display,
      visibility: userMenuDropdown.style.visibility,
      pointerEvents: userMenuDropdown.style.pointerEvents,
      rect,
      hasItems: userMenuDropdown.children.length,
      itemLabels,
    });

    if (!userMenuDropdown.children.length) {
      debugMenuLog('setUserMenuOpen.warning', { issue: 'dropdown_without_items' });
    }
    return;
  }

  if (userMenu) {
    userMenu.classList.remove('is-open');
  }
  userMenuDropdown.classList.remove('is-open');
  userMenuDropdown.style.display = 'none';
  userMenuDropdown.style.visibility = 'hidden';
  userMenuDropdown.style.pointerEvents = 'none';
  userMenuDropdown.setAttribute('aria-hidden', 'true');
  userMenuBtn.setAttribute('aria-expanded', 'false');
  debugMenuLog('setUserMenuOpen.closed', {
    open,
    display: userMenuDropdown.style.display,
    visibility: userMenuDropdown.style.visibility,
    pointerEvents: userMenuDropdown.style.pointerEvents,
  });
}

function doLogout() {
  state.token = '';
    localStorage.removeItem('expai_token');
  if (isAccessControlEnabled()) {
    localStorage.removeItem('expai_company_id');
  }
  state.profile = null;
  if (isAccessControlEnabled()) {
    state.companyId = '';
  }
  renderProfileToUi({ full_name: '-', email: '-', role: '-', company_name: '-' });
  hideImportProgress();
  if (!isAccessControlEnabled() && state.companyId) {
    setPanel(true);
    ensureAnonymousProfile();
  } else {
    setPanel(false);
  }
  hideUserMenu();
  if (loginMsg) {
    loginMsg.textContent = '';
  }
  if (createMsg) {
    createMsg.textContent = '';
  }
}

async function loadUserSession(force = false) {
  if (!isAccessControlEnabled()) {
    ensureAnonymousProfile();
    return state.profile;
  }
  if (!state.token) {
    state.profile = null;
    renderProfileToUi({ full_name: '-', email: '-', role: '-', company_name: '-' });
    setPanelStatusText();
    return null;
  }
  if (!force && state.profile) {
    setPanelStatusText();
    return state.profile;
  }

  try {
    const payload = await apiFetch('/api/v1/auth/me');
    state.profile = payload;
    if (payload.company_id) {
      state.companyId = String(payload.company_id);
      localStorage.setItem('expai_company_id', state.companyId);
    }
    renderProfileToUi(payload);
    setPanelStatusText();
    toggleAdminMenuVisibility();
    return payload;
  } catch (error) {
    state.profile = null;
    renderProfileToUi({ full_name: '-', email: '-', role: '-', company_name: '-' });
    setStatus(error.message, false);
    toggleAdminMenuVisibility();
    return null;
  }
}

function hideEditHistory() {
  if (!editHistorySession || !editVersionsList) {
    return;
  }

  editHistorySession.classList.add('hidden-view');
  editVersionsList.innerHTML = '';
  if (editHistoryHint) {
    editHistoryHint.textContent = 'Selecione um documento publicado para visualizar o histórico.';
  }
  if (versionPreviewSession) {
    versionPreviewSession.classList.add('hidden-view');
  }
  if (versionPreviewInfo) {
    versionPreviewInfo.textContent = 'Selecione uma versão acima para exibir o conteúdo.';
  }
  if (versionPreviewContent) {
    versionPreviewContent.textContent = 'Nenhuma versão selecionada.';
  }
  if (versionPublishToggle) {
    versionPublishToggle.checked = false;
    versionPublishToggle.disabled = true;
  }
  if (publishToggleInfo) {
    publishToggleInfo.textContent = 'Publicar esta versão';
  }
  editingDocumentKey = null;
  editingDocumentContext = null;
  editingHistoryVersions = [];
  selectedHistoryVersion = null;
}

function getHistoryVersion(version) {
  const target = normalizeVersion(version);
  return (editingHistoryVersions || []).find((item) => normalizeVersion(item.version) === target);
}

function setTimelineActiveVersion(version) {
  if (!editVersionsList) {
    return;
  }

  const target = normalizeVersion(version);
  const items = editVersionsList.querySelectorAll('.timeline-item');
  items.forEach((item) => {
    item.classList.toggle('active', normalizeVersion(item.dataset.version) === target);
  });
}

function renderEditHistory(meta) {
  if (!editHistorySession || !editVersionsList) {
    return;
  }

  const versions = Array.isArray(meta?.versions) ? [...meta.versions] : [];
  if (!versions.length) {
    editVersionsList.innerHTML = '<li>Nenhuma versão registrada.</li>';
    editHistorySession.classList.remove('hidden-view');
    return;
  }

  versions.sort((a, b) => compareVersions(a.version, b.version));
  versions.reverse();
  editingHistoryVersions = versions;
  editVersionsList.innerHTML = '';

  for (const item of versions) {
    const publishedTag = item.published ? 'PUBLICADA' : '';
    const publishedLabel = item.published_at ? `Publicado em ${item.published_at}` : '';
    const title = `v${item.version}`;
    const metaLine = [
      item.author || 'autor não informado',
      item.created_at || '',
      publishedLabel,
    ].join(' · ');

    const li = document.createElement('li');
    li.className = `timeline-item ${item.published ? 'is-published' : ''}`;
    li.tabIndex = 0;
    li.dataset.version = item.version;
    li.addEventListener('click', () => {
      loadVersionForEdit(item.version);
    });
    li.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        loadVersionForEdit(item.version);
      }
    });
    li.innerHTML = `
      <div class="timeline-main">
        <div class="timeline-main-row">
          <strong>${title}</strong>
          ${publishedTag ? `<span class="timeline-badge">${publishedTag}</span>` : '<span class="timeline-badge timeline-badge--draft">RASCUNHO</span>'}
        </div>
        <span class="timeline-meta">${metaLine}</span>
      </div>
    `;
    editVersionsList.appendChild(li);
  }

  editHistorySession.classList.remove('hidden-view');
  if (editHistoryHint) {
    editHistoryHint.textContent = `Histórico completo de "${docTitleOf(meta) || ''}".`;
  }
}

function renderVersionPreview(version, payload) {
  if (!versionPreviewSession || !versionPreviewContent || !versionPreviewInfo || !versionPublishToggle || !publishToggleInfo) {
    return;
  }

  selectedHistoryVersion = normalizeVersion(version);
  setTimelineActiveVersion(version);
  versionPreviewSession.classList.remove('hidden-view');
  versionPreviewInfo.textContent = `Visualização da versão v${version}`;
  versionPreviewContent.textContent = payload?.content || 'Não foi possível carregar o conteúdo desta versão.';

  const selected = getHistoryVersion(version);
  const isPublished = selected?.published === true || contentPublishedOf(payload);
  versionPublishToggle.checked = isPublished;
  versionPublishToggle.disabled = false;
  publishToggleInfo.textContent = `Publicar versão v${version}`;
}

function loadVersionForEdit(version) {
  if (!editingDocumentContext) {
    return;
  }
  const { area, categoria, slug } = editingDocumentContext;
  selectedHistoryVersion = normalizeVersion(version);
  setTimelineActiveVersion(version);
  openDocumentModalFromPublished(
    {
      area,
      categoria,
      slug,
      title: docTitleOf(editingDocumentContext) || '',
      updated_at: editingDocumentContext.updated_at || '',
      published_version: selectedHistoryVersion,
    },
    selectedHistoryVersion,
    true,
  );
}

async function publishVersionFromToggle(version) {
  if (!editingDocumentContext) {
    return;
  }
  const targetVersion = normalizeVersion(version);
  if (!targetVersion) {
    showToast('Selecione uma versão válida para publicar.', 'error');
    return;
  }

  try {
    await apiFetch(`/api/v1/empresas/${state.companyId}/documentos/${encodeURIComponent(editingDocumentContext.area)}/${encodeURIComponent(editingDocumentContext.categoria)}/${encodeURIComponent(editingDocumentContext.slug)}/publicar`, {
      method: 'PUT',
      body: JSON.stringify({ version: targetVersion }),
    });
    showToast(`Versão v${targetVersion} publicada com sucesso.`);
    if (versionPublishToggle) {
      versionPublishToggle.disabled = false;
    }
    const docMeta = {
      area: editingDocumentContext.area,
      categoria: editingDocumentContext.categoria,
      slug: editingDocumentContext.slug,
      title: docTitleOf(editingDocumentContext) || '',
    };
    editingDocumentKey = null;
    await loadDocumentHistory(docMeta, true);
      loadVersionForEdit(targetVersion);
  } catch (error) {
    showToast(error.message, 'error');
    versionPublishToggle.checked = false;
    versionPublishToggle.disabled = false;
  }
}

async function loadDocumentHistory(document, forceReload = false) {
  const key = `${document.area}::${document.categoria}::${document.slug}`;
  if (!forceReload && editingDocumentKey === key) {
    return;
  }

  if (!editHistorySession || !editVersionsList) {
    return;
  }

  editVersionsList.innerHTML = '<li>Carregando histórico...</li>';
  editHistorySession.classList.remove('hidden-view');
  if (editHistoryHint) {
    editHistoryHint.textContent = `Carregando histórico de "${document.slug}".`;
  }
  editingDocumentContext = {
    area: document.area,
    categoria: document.categoria,
    slug: document.slug,
    title: docTitleOf(document) || '',
  };
  selectedHistoryVersion = null;
  setTimelineActiveVersion(null);
  versionPreviewSession?.classList.add('hidden-view');

  try {
    const payload = await apiFetch(`/api/v1/empresas/${state.companyId}/documentos/${encodeURIComponent(document.area)}/${encodeURIComponent(document.categoria)}/${encodeURIComponent(document.slug)}`);
    editingDocumentKey = key;
    renderEditHistory(payload.documento || payload);
  } catch (error) {
    editingDocumentKey = null;
    editVersionsList.innerHTML = `<li>${error.message}</li>`;
  }
}

function openDocumentModalFromPublished(doc, version = null, showPublishControls = false) {
  const targetVersion = version != null
    ? normalizeVersion(version)
    : normalizeVersion(docPublishedVersionOf(doc) || doc.version || '');
  const fromHistory = Boolean(showPublishControls);
  selectedDocument = doc;
  selectedDocument = { ...selectedDocument, fromHistoryEdit: fromHistory };
  selectedDocument.version = targetVersion || null;
  const shouldShowPublish = Boolean(showPublishControls);
  const versionLabel = targetVersion ? `v${targetVersion}` : '-';
  docModalTitle.textContent = docTitleOf(doc) || doc.slug;
  docModalMeta.textContent = `${doc.area} / ${doc.categoria} · ${versionLabel} · ${doc.updated_at || ''}`;
  docModalContent.textContent = 'Carregando conteúdo...';
  docModal.setAttribute('aria-hidden', 'false');
  docModal.classList.add('open');

  if (modalPublishToggleWrap) {
    modalPublishToggleWrap.classList.toggle('hidden-view', !shouldShowPublish);
  }
  if (modalVersionPublishToggle) {
    modalVersionPublishToggle.disabled = !shouldShowPublish;
    modalVersionPublishToggle.checked = false;
  }
  if (modalPublishToggleInfo) {
    modalPublishToggleInfo.textContent = targetVersion ? `Publicar versão v${targetVersion}` : 'Publicar esta versão';
  }

  const query = new URLSearchParams();
  if (targetVersion) {
    query.set('version', String(targetVersion));
  }
  const url = `/api/v1/empresas/${state.companyId}/documentos/${encodeURIComponent(doc.area)}/${encodeURIComponent(doc.categoria)}/${encodeURIComponent(doc.slug)}/conteudo${query.toString() ? `?${query}` : ''}`;

  apiFetch(url)
    .then((payload) => {
      docModalContent.textContent = payload?.content || 'Não foi possível carregar o conteúdo.';
      const payloadVersion = contentVersionOf(payload);
      const payloadPublished = contentPublishedOf(payload);
      if (payloadVersion) {
        selectedDocument = { ...selectedDocument, version: payloadVersion, published: payloadPublished };
        docModalMeta.textContent = `${doc.area} / ${doc.categoria} · v${payloadVersion} · ${payload.updated_at || doc.updated_at || ''}`;
        if (modalVersionPublishToggle) {
          modalVersionPublishToggle.checked = payloadPublished;
          modalVersionPublishToggle.disabled = !shouldShowPublish;
        }
        if (modalPublishToggleInfo) {
          modalPublishToggleInfo.textContent = `Publicar versão v${payloadVersion}`;
        }
      }
      const payloadTitle = docTitleOf(payload);
      if (payloadTitle) {
        selectedDocument = { ...selectedDocument, title: payloadTitle };
      }
      if (payload?.tags) {
        selectedDocument = { ...selectedDocument, tags: payload.tags };
      }
    })
    .catch((error) => {
      docModalContent.textContent = error.message;
      if (modalVersionPublishToggle) {
        modalVersionPublishToggle.checked = false;
        modalVersionPublishToggle.disabled = true;
      }
      if (modalPublishToggleInfo) {
        modalPublishToggleInfo.textContent = 'Publicar esta versão';
      }
    });
}

function getPublishContext() {
  if (editingDocumentContext) {
    return editingDocumentContext;
  }
  if (selectedDocument && selectedDocument.area && selectedDocument.categoria && selectedDocument.slug) {
    return {
      area: selectedDocument.area,
      categoria: selectedDocument.categoria,
      slug: selectedDocument.slug,
      title: docTitleOf(selectedDocument) || '',
    };
  }
  return null;
}

async function publishVersionFromContext(version) {
  const context = getPublishContext();
  if (!context) {
    showToast('Não há contexto do documento para publicar.', 'error');
    return;
  }
  if (!version) {
    showToast('Selecione uma versão válida para publicar.', 'error');
    return;
  }

  await apiFetch(`/api/v1/empresas/${state.companyId}/documentos/${encodeURIComponent(context.area)}/${encodeURIComponent(context.categoria)}/${encodeURIComponent(context.slug)}/publicar`, {
    method: 'PUT',
    body: JSON.stringify({ version }),
  });

  showToast(`Versão v${version} publicada com sucesso.`);
  if (modalVersionPublishToggle) {
    modalVersionPublishToggle.disabled = false;
    modalVersionPublishToggle.checked = true;
  }

  const hasHistoryCtx = Boolean(editingDocumentContext);
  if (hasHistoryCtx && context.area && context.categoria && context.slug) {
    await loadDocumentHistory({
      area: context.area,
      categoria: context.categoria,
      slug: context.slug,
      title: docTitleOf(context) || '',
    },
    true,
    );
    loadVersionForEdit(version);
  } else {
    await loadPublishedDocs();
    if (docModal && docModal.classList.contains('open')) {
      openDocumentModalFromPublished(selectedDocument, version);
    }
  }
}

function openCreateForSelectedDocument() {
  if (!selectedDocument) {
    showToast('Selecione um documento publicado antes de atualizar.', 'error');
    return;
  }
  isSlugAutoSuggestionEnabled = false;

  const selectedVersion = normalizeVersion(selectedDocument.version) || null;
  const targetVersion = selectedVersion || normalizeVersion(selectedDocument.published_version || docPublishedVersionOf(selectedDocument)) || null;
  showToast(selectedVersion ? `Carregando versão ${selectedVersion} para edição...` : 'Carregando versão publicada para edição...');

  const query = new URLSearchParams();
  if (targetVersion) {
    query.set('version', targetVersion);
  }
  const url = `/api/v1/empresas/${state.companyId}/documentos/${encodeURIComponent(selectedDocument.area)}/${encodeURIComponent(selectedDocument.categoria)}/${encodeURIComponent(selectedDocument.slug)}/conteudo${query.toString() ? `?${query}` : ''}`;

  closeDocumentModal();
  showInlineCreateSession(true);
  if (createSession) {
    createSession.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  const contentTarget = document.getElementById('docContent');
  contentTarget.value = '';
  setFormSelectValue(docArea, selectedDocument.area || '');
  setFormSelectValue(docCategoria, selectedDocument.categoria || '');
  document.getElementById('docSlug').value = selectedDocument.slug || '';
  document.getElementById('docTitle').value = docTitleOf(selectedDocument) || selectedDocument.slug || '';
  document.getElementById('docTags').value = (selectedDocument.tags || []).join(', ');
  const fileInput = document.getElementById('docFile');
  if (fileInput) {
    fileInput.value = '';
  }

  apiFetch(url)
    .then((payload) => {
      contentTarget.value = payload?.content || 'Não foi possível carregar o conteúdo desta versão.';
      const payloadTitle = docTitleOf(payload);
      if (payloadTitle) {
        document.getElementById('docTitle').value = payloadTitle;
      }
      if (payload?.tags) {
        document.getElementById('docTags').value = payload.tags.join(', ');
      }
      const selectedVersion = contentVersionOf(payload);
      if (selectedVersion) {
        selectedDocument = { ...selectedDocument, version: selectedVersion };
      }
      loadDocumentHistory({
        area: payload?.area || selectedDocument.area || '',
        categoria: payload?.categoria || selectedDocument.categoria || '',
        slug: payload?.slug || selectedDocument.slug || '',
        title: docTitleOf(payload) || docTitleOf(selectedDocument) || selectedDocument.slug || '',
      });
      showToast('Documento carregado para edição com sucesso. Você pode substituir o arquivo para gerar nova versão.');
    })
    .catch((error) => {
      showToast(error.message, 'error');
      loadDocumentHistory({
        area: selectedDocument.area || '',
        categoria: selectedDocument.categoria || '',
        slug: selectedDocument.slug || '',
        title: docTitleOf(selectedDocument) || selectedDocument.slug || '',
      });
    });
}

function showToast(message, type = 'success') {
  if (!toastContainer) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add('show'));
  window.setTimeout(() => {
    toast.classList.remove('show');
    window.setTimeout(() => toast.remove(), 250);
  }, 2800);
}

function parseTags(value) {
  return value
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
}

function collectTaxonomyFields() {
  return {
    area: (docAreaSelect?.value || '').trim(),
    categoria: (docCategoriaSelect?.value || '').trim(),
  };
}

function slugifyText(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function maybeFillSlugFromTitle() {
  if (!docSlugInput || !docTitleInput) {
    return;
  }
  if (!isSlugAutoSuggestionEnabled) {
    return;
  }
  docSlugInput.value = slugifyText(docTitleInput.value);
}

function handleSlugManualEdit() {
  if (!docSlugInput || !docTitleInput) {
    return;
  }
  const currentAuto = slugifyText(docTitleInput.value);
  const currentSlug = (docSlugInput.value || '').trim();
  isSlugAutoSuggestionEnabled = !currentSlug || currentSlug === currentAuto;
  if (isSlugAutoSuggestionEnabled) {
    docSlugInput.value = currentAuto;
  }
}

docTitleInput?.addEventListener('input', () => {
  maybeFillSlugFromTitle();
});
docSlugInput?.addEventListener('input', handleSlugManualEdit);

async function apiFetch(path, options = {}) {
  const headers = options.headers || {};
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data?.detail || `Erro ${response.status}`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return data;
}

document.getElementById('loginForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = {
    email: document.getElementById('email').value,
    password: document.getElementById('password').value,
    company_id: Number(document.getElementById('companyId').value),
  };

  try {
    const data = await apiFetch('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    state.token = data.access_token;
    state.companyId = String(payload.company_id);
    localStorage.setItem('expai_token', state.token);
    localStorage.setItem('expai_company_id', state.companyId);
    loginMsg.textContent = 'Login efetuado com sucesso.';
    loginMsg.className = 'helper success';
    await loadUserSession(true);
    if (state.profile) {
      setPanel(true);
    } else {
      state.token = '';
      localStorage.removeItem('expai_token');
      setPanel(false);
    }
  } catch (error) {
    loginMsg.textContent = error.message;
    loginMsg.className = 'helper error';
  }
});

if (logoutBtn) {
  logoutBtn.addEventListener('click', () => {
    doLogout();
  });
}

if (userProfileMenuItem) {
  userProfileMenuItem.addEventListener('click', async () => {
    showSession('profileSession');
    await loadUserSession();
    hideUserMenu();
  });
}

async function handleUserMenuButton(event) {
  event.preventDefault();
  event.stopPropagation();
  debugMenuLog('userMenuBtn.click', {
    hasToken: Boolean(state.token),
    hasProfile: Boolean(state.profile),
    dropdownClass: userMenuDropdown ? userMenuDropdown.className : null,
  });
  if (isAccessControlEnabled() && !state.token) {
    return;
  }
  if (!state.profile) {
    debugMenuLog('userMenuBtn.loadUserSession.start');
    await loadUserSession(true);
    if (!state.profile) {
      renderProfileToUi({ full_name: '-', email: '-', role: '-', company_name: '-' });
      toggleAdminMenuVisibility();
      debugMenuLog('userMenuBtn.loadUserSession.failed');
    }
  }
  debugMenuLog('userMenuBtn.clientRect', userMenuBtn.getBoundingClientRect());
  if (!state.token) {
    return;
  }
  debugMenuLog('userMenuBtn.toggleAfterLoad', {
    token: Boolean(state.token),
    role: state.profile?.role,
    dropdownBeforeOpen: userMenuDropdown?.className,
  });
  debugMenuLog('userMenuBtn.dropdownComputed', window.getComputedStyle(userMenuDropdown));
  toggleUserMenu();
  window.requestAnimationFrame(() => {
    const styles = window.getComputedStyle(userMenuDropdown);
    const visible = styles.display !== 'none' && styles.visibility !== 'hidden' && userMenuDropdown.classList.contains('is-open');
    if (!visible) {
      debugMenuLog('userMenuBtn.fallbackOpen', {
        display: styles.display,
        visibility: styles.visibility,
        className: userMenuDropdown.className,
      });
      userMenuDropdown.style.display = 'grid';
      userMenuDropdown.style.visibility = 'visible';
      userMenuDropdown.style.pointerEvents = 'auto';
      userMenuDropdown.classList.add('is-open');
      userMenuDropdown.setAttribute('aria-hidden', 'false');
      userMenuBtn.setAttribute('aria-expanded', 'true');
      if (userMenu) {
        userMenu.classList.add('is-open');
      }
    }
  });
}

if (userMenuBtn) {
  userMenuBtn.addEventListener('click', handleUserMenuButton, { passive: false });
  userMenuBtn.addEventListener('touchend', handleUserMenuButton, { passive: false });
}

sessionButtons.forEach((button) => {
  button.addEventListener('click', (event) => {
    const target = event.currentTarget.dataset.session;
    if (!target) {
      return;
    }
    showSession(target);
  if (target === 'dashboardSession') {
      loadPublishedDocs();
      hideEditHistory();
      return;
    }
    if (target === 'taxonomySession') {
      loadTaxonomies();
    }
  });
});

if (userAdminMenuItem) {
  userAdminMenuItem.addEventListener('click', async () => {
    if (!isAccessControlEnabled()) {
      showToast('Sessão de usuários desativada no modo sem autenticação.', 'error');
      hideUserMenu();
      return;
    }
    if (!isAdminProfile()) {
      showToast('Acesso restrito a administradores.', 'error');
      return;
    }
    showSession('userAdminSession');
    await loadUsersForCompany();
    hideUserMenu();
  });
}

async function loadPublishedDocs() {
  const area = document.getElementById('filterArea').value;
  const categoria = document.getElementById('filterCategoria').value;
  const tag = document.getElementById('filterTag').value;
  const busca = document.getElementById('filterBusca').value;

  const query = new URLSearchParams();
  if (area) query.set('area', area);
  if (categoria) query.set('categoria', categoria);
  if (tag) query.set('tag', tag);
  if (busca) query.set('busca', busca);
  query.set('include_content', 'true');

  try {
    const data = await apiFetch(`/api/v1/empresas/${state.companyId}/documentos/publicados?${query.toString()}`);
    docsList.innerHTML = '';

    if (!data.documentos?.length) {
      docsList.innerHTML = '<li>Nenhum documento publicado encontrado para essa busca.</li>';
      return;
    }

    for (const doc of data.documentos) {
      const item = document.createElement('li');
      item.className = 'doc-item';
      item.tabIndex = 0;
      item.addEventListener('click', () => openDocumentModalFromPublished(doc));
      item.addEventListener('keypress', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          openDocumentModalFromPublished(doc);
        }
      });
      item.innerHTML = `
        <div>
          <strong>${docTitleOf(doc) || doc.slug}</strong>
          <div class="meta">${doc.area} / ${doc.categoria}</div>
        </div>
        <span class="meta">v${docPublishedVersionOf(doc) || ''} · ${doc.updated_at || ''}</span>
      `;
      docsList.appendChild(item);
    }
  } catch (error) {
    docsList.innerHTML = `<li>${error.message}</li>`;
  }
}

function showDashboardCreateFlow() {
  selectedDocument = null;
  editingDocumentContext = null;
  editingHistoryVersions = [];
  selectedHistoryVersion = null;
  hideEditHistory();
  isSlugAutoSuggestionEnabled = true;
  createMsg.textContent = '';
  createMsg.className = 'helper';

  const docSlug = document.getElementById('docSlug');
  const docTitle = document.getElementById('docTitle');
  const docTags = document.getElementById('docTags');
  const docContent = document.getElementById('docContent');
  const docPublish = document.getElementById('docPublish');
  const docFile = document.getElementById('docFile');

  if (docArea) docArea.value = '';
  if (docCategoria) docCategoria.value = '';
  if (docSlug) docSlug.value = '';
  if (docTitle) docTitle.value = '';
  if (docTags) docTags.value = '';
  if (docFile) docFile.value = '';
  if (docContent) docContent.value = '';
  if (docPublish) docPublish.checked = true;

  showInlineCreateSession(true);
  if (createSession) {
    createSession.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  showToast('Preencha os campos para publicar um novo documento.');
}

document.getElementById('refreshDocs').addEventListener('click', showDashboardCreateFlow);

document.getElementById('createDocForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const docSlug = document.getElementById('docSlug');
  const docTitle = document.getElementById('docTitle');
  const docTags = document.getElementById('docTags');
  const docPublish = document.getElementById('docPublish');
  const docFile = document.getElementById('docFile');
  const docContent = document.getElementById('docContent');

  const file = docFile?.files?.[0];
  const content = docContent?.value || '';

  if (!file && !content.trim()) {
    createMsg.textContent = 'Informe conteúdo no campo de texto ou anexe um arquivo PDF/DOCX.';
    createMsg.className = 'helper error';
    return;
  }
  if (file) {
    showImportProgress('Enviando arquivo para processamento...');
  } else {
    showImportProgress('Salvando documento...');
  }

  const { area, categoria } = collectTaxonomyFields();
  const title = docTitle?.value || '';
  const generatedSlug = slugifyText(title);
  const slug = (docSlug?.value || '').trim() || generatedSlug;
  const tags = parseTags(docTags?.value || '');
  const publicar = Boolean(docPublish?.checked);
  const normalizedArea = area || FALLBACK_AREA;
  const normalizedCategoria = categoria || FALLBACK_CATEGORIA;

  if (docSlug && !docSlug.value.trim() && generatedSlug) {
    docSlug.value = generatedSlug;
  }

  const context = {
    area: normalizedArea,
    categoria: normalizedCategoria,
    slug,
    title,
  };

  const isFileUpload = Boolean(file);
  const requestTagString = tags.join(', ');

  try {
    let uploadedDoc;
    let uploadedVersion = null;

    if (isFileUpload) {
      const form = new FormData();
      form.set('area', normalizedArea);
      form.set('categoria', normalizedCategoria);
      if (slug) {
        form.set('slug', slug);
      }
      if (title) {
        form.set('title', title);
      }
      if (requestTagString) {
        form.set('tags', requestTagString);
      }
      form.set('file', file);

      const res = await fetch(`/api/v1/empresas/${state.companyId}/documentos/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${state.token}` },
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data?.detail || `Erro ${res.status}`);
      }

      uploadedDoc = data?.documento || {};
      uploadedVersion = uploadedDoc?.version;
    } else {
      const payload = {
        area: normalizedArea,
        categoria: normalizedCategoria,
        slug: slug || null,
        title,
        content,
        tags,
        publicar,
      };

      const data = await apiFetch(`/api/v1/empresas/${state.companyId}/documentos`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      uploadedDoc = data?.documento || {};
      uploadedVersion = uploadedDoc?.version;
    }

    const resolvedArea = uploadedDoc?.area || context.area;
    const resolvedCategoria = uploadedDoc?.categoria || context.categoria;
    const resolvedSlug = uploadedDoc?.slug || context.slug;
    context.area = resolvedArea;
    context.categoria = resolvedCategoria;
    context.slug = resolvedSlug;
    if (docArea) setFormSelectValue(docArea, resolvedArea);
    if (docCategoria) setFormSelectValue(docCategoria, resolvedCategoria);
    if (docSlug) docSlug.value = resolvedSlug || '';
    if (docTitle) docTitle.value = docTitleOf(uploadedDoc) || title;

    if (isFileUpload && docContent && uploadedVersion) {
      updateImportProgress(55, 'Baixando versão convertida...');
      const payload = await apiFetch(`/api/v1/empresas/${state.companyId}/documentos/${encodeURIComponent(resolvedArea)}/${encodeURIComponent(resolvedCategoria)}/${encodeURIComponent(resolvedSlug)}/conteudo?version=${encodeURIComponent(uploadedVersion)}`);
      if (payload?.content !== undefined) {
        docContent.value = payload.content;
      }
      updateImportProgress(72, 'Conteúdo carregado na edição...');
    }

    if (publicar && uploadedVersion) {
      if (isFileUpload) {
        updateImportProgress(80, 'Publicando documento...');
        await apiFetch(`/api/v1/empresas/${state.companyId}/documentos/${encodeURIComponent(context.area)}/${encodeURIComponent(context.categoria)}/${encodeURIComponent(context.slug)}/publicar`, {
          method: 'PUT',
          body: JSON.stringify({ version: String(uploadedVersion) }),
        });
      }
    }

    if (uploadedVersion) {
      updateImportProgress(95, 'Finalizando...');
      if (editingDocumentContext &&
        editingDocumentContext.area === context.area &&
        editingDocumentContext.categoria === context.categoria &&
        editingDocumentContext.slug === context.slug) {
        editingDocumentKey = null;
        await loadDocumentHistory(context, true);
      } else {
        await loadPublishedDocs();
      }

      createMsg.textContent = isFileUpload
        ? `Documento importado como versão ${uploadedVersion}. ${publicar ? 'Publicado.' : 'Rascunho criado.'}`
        : `Documento salvo como versão ${uploadedVersion}. ${publicar ? 'Publicado.' : 'Rascunho criado.'}`;
      createMsg.className = 'helper success';
      showToast(isFileUpload
        ? `Arquivo convertido e ${publicar ? 'publicado' : 'salvo como rascunho'} (v${uploadedVersion}).`
        : `Documento ${publicar ? 'publicado' : 'salvo como rascunho'} (v${uploadedVersion}).`,
      );
      showInlineCreateSession(false);
      showSession('dashboardSession');
      await loadPublishedDocs();
      hideImportProgress(isFileUpload ? 'Importação concluída.' : 'Documento salvo.');
      return;
    }

    throw new Error('Não foi possível identificar a versão criada.');
  } catch (error) {
    createMsg.textContent = error.message;
    createMsg.className = 'helper error';
    hideImportProgress('Falha no processamento.');
  }
});

if (addAreaForm) {
  addAreaForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const value = areaInput?.value || '';
    if (!value.trim()) {
      renderTaxonomyError('Informe o nome da área.');
      return;
    }
    try {
      await apiFetch(`/api/v1/empresas/${state.companyId}/areas`, {
        method: 'POST',
        body: JSON.stringify({ name: value.trim() }),
      });
      if (areaInput) {
        areaInput.value = '';
      }
      renderTaxonomyError('');
      await loadTaxonomies();
      showToast('Área adicionada.');
    } catch (error) {
      renderTaxonomyError(error.message);
    }
  });
}

if (addCategoriaForm) {
  addCategoriaForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const value = categoriaInput?.value || '';
    if (!value.trim()) {
      renderTaxonomyError('Informe o nome da categoria.');
      return;
    }
    try {
      await apiFetch(`/api/v1/empresas/${state.companyId}/categorias`, {
        method: 'POST',
        body: JSON.stringify({ name: value.trim() }),
      });
      if (categoriaInput) {
        categoriaInput.value = '';
      }
      renderTaxonomyError('');
      await loadTaxonomies();
      showToast('Categoria adicionada.');
    } catch (error) {
      renderTaxonomyError(error.message);
    }
  });
}

if (addUserForm) {
  addUserForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!isAccessControlEnabled()) {
      if (userAdminMsg) {
        userAdminMsg.textContent = 'Usuário anônimo não pode criar usuários nesse modo.';
        userAdminMsg.className = 'helper error';
      }
      return;
    }
    if (!isAdminProfile()) {
      if (userAdminMsg) {
        userAdminMsg.textContent = 'Apenas administradores podem cadastrar usuários.';
        userAdminMsg.className = 'helper error';
      }
      return;
    }

    const full_name = newUserName?.value?.trim() || '';
    const email = newUserEmail?.value?.trim() || '';
    const password = newUserPassword?.value || '';
    const role = newUserRole?.value || '';

    if (!full_name || !email || !password || !role) {
      if (userAdminMsg) {
        userAdminMsg.textContent = 'Preencha nome, e-mail, senha e perfil.';
        userAdminMsg.className = 'helper error';
      }
      return;
    }

    if (!state.companyId) {
      if (userAdminMsg) {
        userAdminMsg.textContent = 'Empresa não identificada.';
        userAdminMsg.className = 'helper error';
      }
      return;
    }

    try {
      await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios`, {
        method: 'POST',
        body: JSON.stringify({
          full_name,
          email,
          password,
          role,
        }),
      });
      if (newUserName) newUserName.value = '';
      if (newUserEmail) newUserEmail.value = '';
      if (newUserPassword) newUserPassword.value = '';
      if (newUserRole) newUserRole.value = '';
      if (userAdminMsg) {
        userAdminMsg.textContent = 'Usuário cadastrado com sucesso.';
        userAdminMsg.className = 'helper success';
      }
      await loadUsersForCompany();
    } catch (error) {
      if (userAdminMsg) {
        userAdminMsg.textContent = error.message;
        userAdminMsg.className = 'helper error';
      }
    }
  });
}

if (areasList) {
  areasList.addEventListener('click', async (event) => {
    const button = event.target.closest('.taxonomy-remove');
    if (!button) {
      return;
    }
    const name = button.dataset.name;
    if (!name) return;
    try {
      await apiFetch(`/api/v1/empresas/${state.companyId}/areas?name=${encodeURIComponent(name)}`, {
        method: 'DELETE',
      });
      await loadTaxonomies();
      showToast('Área removida.');
    } catch (error) {
      renderTaxonomyError(error.message);
    }
  });
}

if (categoriasList) {
  categoriasList.addEventListener('click', async (event) => {
    const button = event.target.closest('.taxonomy-remove');
    if (!button) {
      return;
    }
    const name = button.dataset.name;
    if (!name) return;
    try {
      await apiFetch(`/api/v1/empresas/${state.companyId}/categorias?name=${encodeURIComponent(name)}`, {
        method: 'DELETE',
      });
      await loadTaxonomies();
      showToast('Categoria removida.');
    } catch (error) {
      renderTaxonomyError(error.message);
    }
  });
}

document.getElementById('publishForm').addEventListener('submit', async (event) => {
  event.preventDefault();

  try {
    await apiFetch(`/api/v1/empresas/${state.companyId}/documentos/${encodeURIComponent(document.getElementById('pubArea').value)}/${encodeURIComponent(document.getElementById('pubCategoria').value)}/${encodeURIComponent(document.getElementById('pubSlug').value)}/publicar`, {
      method: 'PUT',
      body: JSON.stringify({ version: String(document.getElementById('pubVersion').value).trim() }),
    });
    publishMsg.textContent = 'Versão publicada com sucesso.';
    publishMsg.className = 'helper success';
    loadPublishedDocs();
  } catch (error) {
    publishMsg.textContent = error.message;
    publishMsg.className = 'helper error';
  }
});

document.getElementById('filterArea').addEventListener('change', loadPublishedDocs);
document.getElementById('filterCategoria').addEventListener('change', loadPublishedDocs);
document.getElementById('filterTag').addEventListener('change', loadPublishedDocs);
document.getElementById('filterBusca').addEventListener('change', loadPublishedDocs);

docModalCloseBtn.addEventListener('click', closeDocumentModal);
docModalOverlay.addEventListener('click', closeDocumentModal);
if (docModalEditBtn) {
  docModalEditBtn.addEventListener('click', openCreateForSelectedDocument);
}
if (brandHomeWrap || brandHomeLink) {
  const homeTrigger = brandHomeWrap || brandHomeLink;
  const navigateHome = async () => {
    showSession('dashboardSession');
    if (!state.companyId) {
      await loadPlatformConfig();
    }
    await loadPublishedDocs();
    hideEditHistory();
    showInlineCreateSession(false);
    hideUserMenu();
  };

  homeTrigger.addEventListener('click', (event) => {
    event.preventDefault();
    void navigateHome();
  });
  homeTrigger.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      void navigateHome();
    }
  });
}
window.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && docModal.classList.contains('open')) {
    closeDocumentModal();
    return;
  }
  if (event.key === 'Escape') {
    hideUserMenu();
  }
});

document.addEventListener('click', (event) => {
  if (!userMenu || !userMenuDropdown || !userMenuDropdown.classList || !userMenuBtn) {
    debugMenuLog('docClick.menu.skip', {
      hasMenu: Boolean(userMenu),
      hasDropdown: Boolean(userMenuDropdown),
      hasBtn: Boolean(userMenuBtn),
    });
    return;
  }
  if (!userMenuDropdown.classList.contains('is-open')) {
    return;
  }
  if (!userMenu.contains(event.target)) {
    debugMenuLog('docClick.menu.hide', {
      open: userMenuDropdown.classList.contains('is-open'),
      targetTag: event.target?.tagName,
    });
    hideUserMenu();
  }
});

if (versionPublishToggle) {
  versionPublishToggle.addEventListener('change', async (event) => {
    const checked = event.currentTarget.checked;
    const selected = getHistoryVersion(selectedHistoryVersion);

    if (!selectedHistoryVersion || !selected) {
      showToast('Selecione uma versão para publicar.', 'error');
      versionPublishToggle.checked = false;
      return;
    }

    if (!checked) {
      if (selected.published) {
        showToast('A versão publicada não pode ser desmarcada aqui. Selecione outra versão e ative para trocar a publicação.', 'error');
        versionPublishToggle.checked = true;
        return;
      }
      showToast('Selecione a versão e ative para publicar.', 'error');
      return;
    }

    versionPublishToggle.disabled = true;
    await publishVersionFromToggle(selectedHistoryVersion);
    versionPublishToggle.disabled = false;
  });
}

if (modalVersionPublishToggle) {
  modalVersionPublishToggle.addEventListener('change', async (event) => {
    const checked = event.currentTarget.checked;
    const selected = normalizeVersion(selectedDocument?.version);

    if (!selected) {
      showToast('Selecione uma versão para publicar.', 'error');
      modalVersionPublishToggle.checked = false;
      return;
    }

    if (!checked) {
      if (selectedDocument?.published) {
        showToast('A versão publicada não pode ser desmarcada aqui. Selecione outra versão e ative para trocar a publicação.', 'error');
        modalVersionPublishToggle.checked = true;
        return;
      }
      showToast('Selecione a versão e ative para publicar.', 'error');
      return;
    }

    modalVersionPublishToggle.disabled = true;
    try {
      await publishVersionFromContext(selected);
    } catch (error) {
      showToast(error.message, 'error');
      modalVersionPublishToggle.checked = false;
    } finally {
      modalVersionPublishToggle.disabled = false;
    }
  });
}

window.__expaiMenu = {
  open: () => setUserMenuOpen(true),
  close: () => setUserMenuOpen(false),
  toggle: () => toggleUserMenu(),
  state: () => ({
    token: !!state.token,
    hasProfile: !!state.profile,
    menuOpen: userMenuDropdown?.classList?.contains('is-open') || false,
    dropdownDisplay: userMenuDropdown ? getComputedStyle(userMenuDropdown).display : null,
    dropdownVisibility: userMenuDropdown ? getComputedStyle(userMenuDropdown).visibility : null,
    menuItems: userMenuDropdown ? Array.from(userMenuDropdown.children).map((item) => item.textContent?.trim()) : [],
  }),
  forceLog: () => {
    // eslint-disable-next-line no-console
    console.log('[Expertise.AI][Menu] forceLog', {
      token: !!state.token,
      profile: state.profile,
      menuState: userMenuDropdown ? getComputedStyle(userMenuDropdown) : null,
    });
  },
};

(async () => {
  await loadPlatformConfig();
  if (!canAccessPlatform()) {
    setPanel(false);
    return;
  }

  if (isAccessControlEnabled()) {
    if (state.token && state.companyId) {
      await loadUserSession();
    }
    setPanel(Boolean(state.token && state.companyId));
    return;
  }

  await loadUserSession(true);
  setPanel(true);
})();
