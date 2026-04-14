const state = {
  token: localStorage.getItem('expai_token') || '',
  refreshToken: localStorage.getItem('expai_refresh_token') || '',
  companyId: localStorage.getItem('expai_company_id') || '',
  accessControlEnabled: true,
  defaultCompanyName: '',
  defaultCompanyDescription: '',
  pendingApprovalTotal: 0,
  profile: null,
  taxonomies: {
    areas: [],
    categorias: [],
  },
};

let selectedTaxonomyArea = '';
let authRefreshPromise = null;
let sessionExpiredMessageShown = false;

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
const brandSubtitle = document.getElementById('brandSubtitle');
const loginMsg = document.getElementById('loginMsg');
const createMsg = document.getElementById('createMsg');
const publishMsg = document.getElementById('publishMsg');
const taxonomyMsg = document.getElementById('taxonomyMsg');
const sessionButtons = Array.from(document.querySelectorAll('.menu-item[data-session]'));
const toastContainer = document.getElementById('toastContainer');
const docsList = document.getElementById('docsList');
const refreshDocsButton = document.getElementById('refreshDocs');
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
const filterArea = document.getElementById('filterArea');
const filterCategoria = document.getElementById('filterCategoria');
const userAdminMenuItem = document.getElementById('userAdminMenuItem');
const userAreaAccessMenuItem = document.getElementById('userAreaAccessMenuItem');
const userAdminSession = document.getElementById('userAdminSession');
const userAreaAccessSession = document.getElementById('userAreaAccessSession');
const usersList = document.getElementById('usersList');
const addUserForm = document.getElementById('addUserForm');
const newUserName = document.getElementById('newUserName');
const newUserEmail = document.getElementById('newUserEmail');
const newUserPassword = document.getElementById('newUserPassword');
const newUserRole = document.getElementById('newUserRole');
const newUserRestrictionTrigger = document.getElementById('newUserRestrictionTrigger');
const newUserRestrictionTriggerLabel = document.getElementById('newUserRestrictionTriggerLabel');
const newUserRestrictionDropdown = document.getElementById('newUserRestrictionDropdown');
const userAdminMsg = document.getElementById('userAdminMsg');
const userAccessStatusFilter = document.getElementById('userAccessStatusFilter');
const userAccessSearch = document.getElementById('userAccessSearch');
const userAccessSort = document.getElementById('userAccessSort');
const userAuditList = document.getElementById('userAuditList');
const userAuditExportButton = document.getElementById('userAuditExport');
const userAuditPrevButton = document.getElementById('userAuditPrev');
const userAuditNextButton = document.getElementById('userAuditNext');
const userAuditPagerInfo = document.getElementById('userAuditPagerInfo');
const usersPrevButton = document.getElementById('usersPrev');
const usersNextButton = document.getElementById('usersNext');
const usersPagerInfo = document.getElementById('usersPagerInfo');
const areaAccessUserSelect = document.getElementById('areaAccessUserSelect');
const areaAccessMode = document.getElementById('areaAccessMode');
const areaAccessChecklist = document.getElementById('areaAccessChecklist');
const areaAccessProfilesList = document.getElementById('areaAccessProfilesList');
const saveAreaAccessBtn = document.getElementById('saveAreaAccessBtn');
const areaAccessMsg = document.getElementById('areaAccessMsg');
const createAreaRestrictionProfileForm = document.getElementById('createAreaRestrictionProfileForm');
const areaRestrictionProfileName = document.getElementById('areaRestrictionProfileName');
const areaRestrictionProfileDescription = document.getElementById('areaRestrictionProfileDescription');
const areaRestrictionProfileChecklist = document.getElementById('areaRestrictionProfileChecklist');
const areaRestrictionProfileMsg = document.getElementById('areaRestrictionProfileMsg');
const userAccessModal = document.getElementById('userAccessModal');
const userAccessModalOverlay = document.getElementById('userAccessModalOverlay');
const userAccessModalCloseBtn = document.getElementById('userAccessModalCloseBtn');
const userAccessModalTitle = document.getElementById('userAccessModalTitle');
const userAccessModalMeta = document.getElementById('userAccessModalMeta');
const userAccessModalName = document.getElementById('userAccessModalName');
const userAccessModalEmail = document.getElementById('userAccessModalEmail');
const userAccessModalRoles = document.getElementById('userAccessModalRoles');
const userAccessModalRestrictionTrigger = document.getElementById('userAccessModalRestrictionTrigger');
const userAccessModalRestrictionTriggerLabel = document.getElementById('userAccessModalRestrictionTriggerLabel');
const userAccessModalRestrictionDropdown = document.getElementById('userAccessModalRestrictionDropdown');
const userAccessModalPassword = document.getElementById('userAccessModalPassword');
const userAccessModalScope = document.getElementById('userAccessModalScope');
const userAccessModalRestrictionProfiles = document.getElementById('userAccessModalRestrictionProfiles');
const userAccessModalPasswordFlag = document.getElementById('userAccessModalPasswordFlag');
const userAccessModalOpenAreas = document.getElementById('userAccessModalOpenAreas');
const userAccessModalRevoke = document.getElementById('userAccessModalRevoke');
const userAccessModalSave = document.getElementById('userAccessModalSave');
const userAccessModalMsg = document.getElementById('userAccessModalMsg');
const forcePasswordModal = document.getElementById('forcePasswordModal');
const forcePasswordNew = document.getElementById('forcePasswordNew');
const forcePasswordConfirm = document.getElementById('forcePasswordConfirm');
const forcePasswordSave = document.getElementById('forcePasswordSave');
const forcePasswordMsg = document.getElementById('forcePasswordMsg');
const editHistorySession = document.getElementById('editHistorySession');
const editVersionsList = document.getElementById('editVersionsList');
const editHistoryHint = document.getElementById('editHistoryHint');
const attachmentsSection = document.getElementById('attachmentsSection');
const attachmentsList = document.getElementById('attachmentsList');
const attachmentsHint = document.getElementById('attachmentsHint');
const versionPreviewSession = document.getElementById('versionPreviewSession');
const versionPreviewInfo = document.getElementById('versionPreviewInfo');
const versionPreviewContent = document.getElementById('versionPreviewContent');
const versionPublishToggle = document.getElementById('versionPublishToggle');
const publishToggleInfo = document.getElementById('publishToggleInfo');
const logoutBtn = document.getElementById('userLogoutMenuItem');
const docAreaSelect = docArea;
const docCategoriaSelect = docCategoria;
const categoriaAreaSelect = document.getElementById('categoriaAreaSelect');
const docSlugInput = document.getElementById('docSlug');
const docTitleInput = document.getElementById('docTitle');
const docContentInput = document.getElementById('docContent');
const docAiPromptInput = document.getElementById('docAiPrompt');
const docValidityInput = document.getElementById('docValidity');
const docTagsInput = document.getElementById('docTags');
const docTagBadges = document.getElementById('docTagBadges');
const docsPrevButton = document.getElementById('docsPrev');
const docsNextButton = document.getElementById('docsNext');
const docsPagerInfo = document.getElementById('docsPagerInfo');

let selectedDocument = null;
let editingDocumentKey = null;
let editingDocumentContext = null;
let editingHistoryVersions = [];
let selectedHistoryVersion = null;
let importProgressTimer = null;
let taxonomyLoading = false;
let isSlugAutoSuggestionEnabled = true;
let createSessionTags = [];
const titleMaxChars = 256;
const FALLBACK_AREA = 'sem-area';
const FALLBACK_CATEGORIA = 'sem-categoria';
const pagination = {
  page: 1,
  limit: 10,
  total: 0,
};
let docsSearchDebounceTimer = null;
const ACCESS_ROLE_OPTIONS = ['admin', 'editor', 'aprovador'];
let companyUsersCache = [];
let companyUserAuditCache = [];
let areaAccessState = {
  availableAreas: [],
  selectedAreas: [],
  profiles: [],
  assignedProfileIds: [],
  effectiveScope: { mode: 'all', areas: [] },
};
let areaRestrictionProfilesCatalog = [];
let newUserAssignedRestrictionProfileIds = [];
let selectedUserAccessRecord = null;
let selectedUserAccessRestrictionState = {
  defaultScope: { mode: 'all', areas: [] },
  assignedProfileIds: [],
  profiles: [],
};
const usersPagination = {
  page: 1,
  limit: 10,
  total: 0,
};
const userAuditPagination = {
  page: 1,
  limit: 10,
  total: 0,
};

const USER_ROLE_WEIGHT = {
  admin: 3,
  editor: 2,
  aprovador: 1,
};

function docTitleOf(doc) {
  return doc?.titulo || doc?.title || '';
}

function normalizeTextTitle(value) {
  return String(value || '').trim();
}

function truncateForCard(value, maxChars = titleMaxChars) {
  const normalized = normalizeTextTitle(value);
  if (normalized.length <= maxChars) {
    return normalized;
  }
  return `${normalized.slice(0, maxChars)}...`;
}

function formatFileSize(bytesValue) {
  const bytes = Number(bytesValue || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '';
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function normalizeTagValue(value) {
  return String(value || '')
    .trim()
    .toLowerCase();
}

function normalizeTagValues(values) {
  if (!values) {
    return [];
  }
  if (Array.isArray(values)) {
    return values
      .map((item) => normalizeTagValue(item))
      .filter((item, index, list) => item && list.indexOf(item) === index);
  }
  if (typeof values === 'string') {
    return values
      .split(',')
      .map((item) => normalizeTagValue(item))
      .filter((item, index, list) => item && list.indexOf(item) === index);
  }
  return [];
}

function docPublishedVersionOf(doc) {
  return doc?.published_version || doc?.versao_publicada || doc?.version || '';
}

function docIsPublished(doc) {
  if (doc?.published !== undefined) {
    return Boolean(doc.published);
  }
  if (doc?.published_version || doc?.versao_publicada) {
    return true;
  }
  return false;
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

function normalizeDocumentError(errorValue) {
  if (!errorValue) {
    return 'Processamento interrompido.';
  }
  if (typeof errorValue !== 'string') {
    return String(errorValue);
  }
  const raw = errorValue.trim();
  if (!raw) {
    return 'Processamento interrompido.';
  }
  if ((raw.startsWith('{') && raw.endsWith('}')) || (raw.startsWith('[') && raw.endsWith(']'))) {
    try {
      const parsed = JSON.parse(raw);
      if (typeof parsed === 'string' && parsed.trim()) {
        return parsed.trim();
      }
      if (Array.isArray(parsed)) {
        const firstText = parsed.find((item) => typeof item === 'string' && item.trim());
        if (firstText) {
          return firstText.trim();
        }
      }
      if (parsed && typeof parsed === 'object') {
        const candidates = [parsed.error, parsed.message, parsed.detail, parsed.stderr, parsed.stdout];
        const firstCandidate = candidates.find((item) => typeof item === 'string' && item.trim());
        if (firstCandidate) {
          return firstCandidate.trim();
        }
      }
    } catch (_error) {
      return raw;
    }
  }
  return raw;
}

function canDeleteDocumentCard() {
  return !isAccessControlEnabled() || isAdminProfile() || hasRole('editor');
}

function canViewUploadQueue(profile = state.profile) {
  return !isAccessControlEnabled() || hasRole('editor', profile);
}

function canCreateNewDocument(profile = state.profile) {
  return !isAccessControlEnabled() || hasRole('editor', profile);
}

function normalizedRolesOf(profile = state.profile) {
  const rawRoles = Array.isArray(profile?.roles) && profile.roles.length ? profile.roles : [profile?.role || ''];
  return rawRoles
    .map((item) => String(item || '').trim().toLowerCase())
    .filter((item, index, list) => item && list.indexOf(item) === index);
}

function hasRole(role, profile = state.profile) {
  const target = String(role || '').trim().toLowerCase();
  const roles = normalizedRolesOf(profile);
  return roles.includes('admin') || roles.includes(target);
}

function canPublishDocument(profile = state.profile) {
  return !isAccessControlEnabled() || hasRole('aprovador', profile);
}

function isPendingApprovalVersion(payload = {}) {
  return Boolean(payload?.pending_approval);
}

function updateDashboardApprovalStatus() {
  if (!state.profile) {
    setPanelStatusText();
    return;
  }
  const pendingTotal = Number(state.pendingApprovalTotal || 0);
  if (canPublishDocument()) {
    setStatus(
      pendingTotal > 0
        ? `${pendingTotal} pendente(s) de aprovação`
        : 'Nenhuma pendência de aprovação',
    );
    return;
  }
  setStatus('Sem pendências de aprovação');
}

function formatRoleLabel(profile = state.profile) {
  const roles = normalizedRolesOf(profile);
  if (!roles.length) {
    return profile?.role || 'sem perfil';
  }
  return roles.join(', ');
}

function setUserAdminMessage(message = '', type = '') {
  if (!userAdminMsg) {
    return;
  }
  userAdminMsg.textContent = message;
  userAdminMsg.className = type ? `helper ${type}` : 'helper';
}

function setAreaAccessMessage(message = '', type = '') {
  if (!areaAccessMsg) {
    return;
  }
  areaAccessMsg.textContent = message;
  areaAccessMsg.className = type ? `helper ${type}` : 'helper';
}

function setAreaRestrictionProfileMessage(message = '', type = '') {
  if (!areaRestrictionProfileMsg) {
    return;
  }
  areaRestrictionProfileMsg.textContent = message;
  areaRestrictionProfileMsg.className = type ? `helper ${type}` : 'helper';
}

function setUserAccessModalMessage(message = '', type = '') {
  if (!userAccessModalMsg) {
    return;
  }
  userAccessModalMsg.textContent = message;
  userAccessModalMsg.className = type ? `helper ${type}` : 'helper';
}

function setForcePasswordMessage(message = '', type = '') {
  if (!forcePasswordMsg) {
    return;
  }
  forcePasswordMsg.textContent = message;
  forcePasswordMsg.className = type ? `helper ${type}` : 'helper';
}

function updateCreateDocumentButtonAvailability() {
  if (!refreshDocsButton) {
    return;
  }
  const allowed = canCreateNewDocument();
  refreshDocsButton.disabled = !allowed;
  refreshDocsButton.title = allowed
    ? 'Publicar novo documento'
    : 'Somente editores ou administradores podem criar novos documentos.';
}

function closeUserAccessRestrictionDropdown() {
  if (!userAccessModalRestrictionDropdown) {
    return;
  }
  userAccessModalRestrictionDropdown.classList.add('hidden-view');
  userAccessModalRestrictionTrigger?.setAttribute('aria-expanded', 'false');
}

function closeNewUserRestrictionDropdown() {
  if (!newUserRestrictionDropdown) {
    return;
  }
  newUserRestrictionDropdown.classList.add('hidden-view');
  newUserRestrictionTrigger?.setAttribute('aria-expanded', 'false');
}

function findAssignedRestrictionProfiles(profiles = [], assignedIds = []) {
  return profiles.filter((profile) => assignedIds.includes(Number(profile.id)));
}

function updateRestrictionTriggerLabel(labelElement, profiles = [], assignedIds = [], emptyLabel = 'Nenhum perfil de restrição') {
  if (!labelElement) {
    return;
  }
  const assignedProfiles = findAssignedRestrictionProfiles(profiles, assignedIds);
  if (!assignedProfiles.length) {
    labelElement.textContent = emptyLabel;
    return;
  }
  labelElement.textContent = assignedProfiles.map((profile) => profile.name || `perfil ${profile.id}`).join(', ');
}

function updateUserAccessRestrictionTriggerLabel() {
  updateRestrictionTriggerLabel(
    userAccessModalRestrictionTriggerLabel,
    selectedUserAccessRestrictionState.profiles || [],
    selectedUserAccessRestrictionState.assignedProfileIds || [],
  );
}

function updateNewUserRestrictionTriggerLabel() {
  updateRestrictionTriggerLabel(
    newUserRestrictionTriggerLabel,
    areaRestrictionProfilesCatalog,
    newUserAssignedRestrictionProfileIds,
    'Nenhum perfil de restrição',
  );
}

function renderRestrictionDropdown(dropdownElement, profiles = [], assignedIds = []) {
  if (!dropdownElement) {
    return;
  }
  if (!profiles.length) {
    dropdownElement.innerHTML = '<span class="helper">Nenhum perfil reutilizável disponível.</span>';
    return;
  }
  dropdownElement.innerHTML = '';
  profiles.forEach((profile) => {
    const label = document.createElement('label');
    label.className = 'multi-combobox__option';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = String(profile.id || '');
    input.checked = assignedIds.includes(Number(profile.id));
    const textWrap = document.createElement('span');
    textWrap.className = 'multi-combobox__option-text';
    const title = document.createElement('strong');
    title.textContent = profile.name || `perfil ${profile.id}`;
    const meta = document.createElement('small');
    meta.textContent = (profile.areas || []).length ? (profile.areas || []).join(', ') : 'sem áreas';
    textWrap.appendChild(title);
    if (profile.description) {
      const desc = document.createElement('small');
      desc.textContent = profile.description;
      textWrap.appendChild(desc);
    }
    textWrap.appendChild(meta);
    label.appendChild(input);
    label.appendChild(textWrap);
    dropdownElement.appendChild(label);
  });
}

function renderUserAccessRestrictionDropdown() {
  renderRestrictionDropdown(
    userAccessModalRestrictionDropdown,
    selectedUserAccessRestrictionState.profiles || [],
    selectedUserAccessRestrictionState.assignedProfileIds || [],
  );
  if (userAccessModalRestrictionTrigger) {
    userAccessModalRestrictionTrigger.disabled = (selectedUserAccessRestrictionState.profiles || []).length === 0;
  }
  updateUserAccessRestrictionTriggerLabel();
}

function renderNewUserRestrictionDropdown() {
  renderRestrictionDropdown(newUserRestrictionDropdown, areaRestrictionProfilesCatalog, newUserAssignedRestrictionProfileIds);
  updateNewUserRestrictionTriggerLabel();
  if (newUserRestrictionTrigger) {
    newUserRestrictionTrigger.disabled = areaRestrictionProfilesCatalog.length === 0;
  }
}

function collectUserAccessRestrictionProfileIds() {
  if (!userAccessModalRestrictionDropdown) {
    return [];
  }
  return Array.from(userAccessModalRestrictionDropdown.querySelectorAll('input[type="checkbox"]:checked'))
    .map((input) => Number(input.value || 0))
    .filter((value) => Number.isFinite(value) && value > 0);
}

function collectNewUserRestrictionProfileIds() {
  if (!newUserRestrictionDropdown) {
    return [];
  }
  return Array.from(newUserRestrictionDropdown.querySelectorAll('input[type="checkbox"]:checked'))
    .map((input) => Number(input.value || 0))
    .filter((value) => Number.isFinite(value) && value > 0);
}

async function handleDeleteDocument(doc) {
  const area = doc?.area || FALLBACK_AREA;
  const categoria = doc?.categoria || FALLBACK_CATEGORIA;
  const slug = doc?.slug || '';
  const title = doc?.title || doc?.titulo || doc?.file_name || slug || 'documento';
  if (!slug) {
    showToast('Não foi possível identificar o slug do documento para exclusão.', 'error');
    return;
  }
  const confirmed = window.confirm(`Excluir "${title}"? Esta ação remove o documento da listagem.`);
  if (!confirmed) {
    return;
  }
  await apiFetch(`/api/v1/empresas/${state.companyId}/documentos/${encodeURIComponent(area)}/${encodeURIComponent(categoria)}/${encodeURIComponent(slug)}`, {
    method: 'DELETE',
  });
  if (docModal?.classList.contains('open') && selectedDocument?.slug === slug) {
    closeDocModal();
  }
  showToast('Documento excluído com sucesso.');
  await loadPublishedDocs();
}

function openDocumentEditorFromCard(doc) {
  if (!doc || !doc.area || !doc.categoria || !doc.slug) {
    showToast('Documento sem contexto suficiente para edição.', 'error');
    return;
  }
  selectedDocument = {
    ...doc,
    title: docTitleOf(doc) || doc.slug,
  };
  openCreateForSelectedDocument();
}

function setTaxonomySelectOptions() {
  if (!docArea || !docCategoria) {
    return;
  }
  const previousArea = (docArea.value || '').trim();
  const previousCategoria = (docCategoria.value || '').trim();
  const availableAreas = state.taxonomies.areas.map((name) => String(name || '').trim()).filter(Boolean);
  const areaList = [...new Set(
    [
      ...availableAreas,
      ...previousArea ? [previousArea] : [],
    ].filter(Boolean),
  )];
  const categoriaList = state.taxonomies.categorias.map((item) => (
    typeof item === 'string' ? { name: item, area: '' } : {
      name: item?.name || item?.categoria || '',
      area: item?.area || item?.parent_area || '',
    }
  )).filter((item) => item.name);

  docArea.innerHTML = '<option value="" selected>Sem área (opcional)</option>';
  areaList.forEach((name) => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    docArea.appendChild(option);
  });
  if ([...docArea.options].some((option) => option.value === previousArea)) {
    docArea.value = previousArea;
  }

  docCategoria.innerHTML = '<option value="" selected>Sem categoria (opcional)</option>';
  const currentArea = docArea.value || '';
  const normalizedCurrentArea = (currentArea || '').trim();
  const categoriesToRender = normalizedCurrentArea
    ? categoriaList.filter((item) => item.area === normalizedCurrentArea)
    : categoriaList;
  const finalCategoriasToRender = categoriesToRender;

  const allowedCategorias = new Set(['', ...finalCategoriasToRender.map((item) => item.name)]);
  finalCategoriasToRender.forEach((item) => {
    const option = document.createElement('option');
    option.value = item.name;
    option.textContent = item.area ? `${item.name} (${item.area})` : item.name;
    option.dataset.area = item.area || '';
    docCategoria.appendChild(option);
  });
  if (allowedCategorias.has(previousCategoria)) {
    docCategoria.value = previousCategoria;
  } else {
    docCategoria.value = '';
  }

  if (categoriaAreaSelect) {
    const currentCategoriaArea = categoriaAreaSelect.value || '';
    categoriaAreaSelect.innerHTML = '<option value="">Selecione uma área</option>';
    areaList.forEach((name) => {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      categoriaAreaSelect.appendChild(option);
    });
    if ([...categoriaAreaSelect.options].some((option) => option.value === currentCategoriaArea)) {
      categoriaAreaSelect.value = currentCategoriaArea;
    }
  }
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
  items.forEach((item) => {
    const name = typeof item === 'string' ? item : item?.name || '';
    if (!name) {
      return;
    }
    const area = typeof item === 'string' ? '' : item?.area || item?.parent_area || '';
    const li = document.createElement('li');
    li.className = 'taxonomy-item';
    li.dataset.kind = kind;
    li.dataset.name = name;
    if (kind === 'areas' && name === selectedTaxonomyArea) {
      li.classList.add('taxonomy-item--active');
    }
    li.innerHTML = `
      <span class="taxonomy-name">${name}${area ? ` <span class="taxonomy-area-pill">${area}</span>` : ''}</span>
      <button type="button" class="taxonomy-remove" data-kind="${kind}" data-name="${name}" ${area ? `data-area="${area}"` : ''}>Remover</button>
    `;
    listElement.appendChild(li);
  });
}

function renderTaxonomies() {
  const availableAreas = (state.taxonomies.areas || []).map((item) => String(item || '').trim()).filter(Boolean);
  if (selectedTaxonomyArea && !availableAreas.includes(selectedTaxonomyArea)) {
    selectedTaxonomyArea = '';
    if (categoriaAreaSelect) {
      categoriaAreaSelect.value = '';
    }
  }

  renderTaxonomyList(areasList, availableAreas, 'areas');
  const categoryItems = state.taxonomies.categorias.filter((item) => (
    !selectedTaxonomyArea || (item?.area || item?.parent_area || '') === selectedTaxonomyArea
  ));
  renderTaxonomyList(categoriasList, categoryItems, 'categorias');
  setTaxonomySelectOptions();
  if (filterArea) {
    const currentArea = filterArea.value;
    filterArea.innerHTML = '<option value="">Todas as áreas</option>';
    state.taxonomies.areas.forEach((name) => {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      filterArea.appendChild(option);
    });
    if ([...filterArea.options].some((option) => option.value === currentArea)) {
      filterArea.value = currentArea;
    }
  }
  updateFilterCategoriaOptions();
}

function updateFilterCategoriaOptions() {
  if (!filterCategoria) {
    return;
  }
  const currentCategoria = filterCategoria.value;
  const selectedArea = (filterArea?.value || '').trim();
  const categoriaNames = state.taxonomies.categorias
    .filter((item) => !selectedArea || (item?.area || item?.parent_area || '') === selectedArea)
    .map((item) => (typeof item === 'string' ? item?.trim() : `${item?.name || ''}`))
    .filter(Boolean)
    .filter((value, index, list) => list.indexOf(value) === index)
    .sort();
  filterCategoria.innerHTML = '<option value="">Todas as categorias</option>';
  categoriaNames.forEach((name) => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    filterCategoria.appendChild(option);
  });
  if ([...filterCategoria.options].some((option) => option.value === currentCategoria)) {
    filterCategoria.value = currentCategoria;
  } else {
    filterCategoria.value = '';
  }
}

function renderTaxonomyError(message) {
  if (!taxonomyMsg) return;
  taxonomyMsg.textContent = message;
  taxonomyMsg.className = message ? 'helper error' : 'helper';
}

function isAdminProfile(profile = state.profile) {
  return hasRole('admin', profile);
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
    roles: ['anônimo'],
    company_id: companyId || 0,
    company_name: state.defaultCompanyName || (companyId ? `empresa ${companyId}` : 'empresa'),
    company_description: state.defaultCompanyDescription || '',
  };
  renderProfileToUi(state.profile);
  setPanelStatusText();
  updatePublishControls();
}

function renderUsersList(users = []) {
  if (!usersList) {
    return;
  }
  const statusFilter = userAccessStatusFilter?.value || 'all';
  const searchTerm = String(userAccessSearch?.value || '').trim().toLowerCase();
  const sortMode = userAccessSort?.value || 'name_asc';
  const filteredUsers = users.filter((item) => {
    if (statusFilter === 'active') {
      if (!item.active) return false;
    }
    if (statusFilter === 'inactive') {
      if (item.active) return false;
    }
    if (!searchTerm) {
      return true;
    }
    const haystack = [
      item.full_name || item.nome || '',
      item.email || '',
      ...(Array.isArray(item.roles) ? item.roles : []),
      item.role || '',
      item.area_scope_summary || '',
      ...((item.area_scope_profiles || []).map((profile) => profile?.name || '')),
      ...((item.area_scope?.areas || [])),
    ].join(' ').toLowerCase();
    return haystack.includes(searchTerm);
  });
  filteredUsers.sort((a, b) => {
    const nameA = String(a.full_name || a.nome || '').toLowerCase();
    const nameB = String(b.full_name || b.nome || '').toLowerCase();
    const roleA = USER_ROLE_WEIGHT[String(a.role || '').toLowerCase()] || 0;
    const roleB = USER_ROLE_WEIGHT[String(b.role || '').toLowerCase()] || 0;
    const activeA = a.active ? 1 : 0;
    const activeB = b.active ? 1 : 0;
    if (sortMode === 'name_desc') {
      return nameB.localeCompare(nameA);
    }
    if (sortMode === 'status_active_first') {
      if (activeA !== activeB) return activeB - activeA;
      return nameA.localeCompare(nameB);
    }
    if (sortMode === 'status_inactive_first') {
      if (activeA !== activeB) return activeA - activeB;
      return nameA.localeCompare(nameB);
    }
    if (sortMode === 'role_desc') {
      if (roleA !== roleB) return roleB - roleA;
      return nameA.localeCompare(nameB);
    }
    return nameA.localeCompare(nameB);
  });
  usersPagination.total = filteredUsers.length;
  const totalPages = Math.max(1, Math.ceil(usersPagination.total / usersPagination.limit));
  usersPagination.page = Math.min(Math.max(1, usersPagination.page), totalPages);
  const startIndex = (usersPagination.page - 1) * usersPagination.limit;
  const pagedUsers = filteredUsers.slice(startIndex, startIndex + usersPagination.limit);
  if (usersPagerInfo) {
    if (!usersPagination.total) {
      usersPagerInfo.textContent = 'Página 1 de 1 — 0 usuário(s)';
    } else {
      usersPagerInfo.textContent = `Página ${usersPagination.page} de ${totalPages} — ${startIndex + 1} a ${Math.min(startIndex + pagedUsers.length, usersPagination.total)} de ${usersPagination.total} usuário(s)`;
    }
  }
  if (usersPrevButton) {
    usersPrevButton.disabled = usersPagination.page <= 1 || usersPagination.total <= 0;
  }
  if (usersNextButton) {
    usersNextButton.disabled = usersPagination.page >= totalPages || usersPagination.total <= 0;
  }
  if (!pagedUsers.length) {
    usersList.innerHTML = '<li>Nenhum usuário encontrado.</li>';
    return;
  }
  usersList.innerHTML = '';
  pagedUsers.forEach((item) => {
    const li = document.createElement('li');
    li.className = 'items-list-item user-access-list-item';
    li.dataset.userId = String(item.id || '');
    const effectiveRole = item.role || formatRoleLabel(item) || '-';
    li.innerHTML = `
      <div class="user-access-list-item__summary">
        <strong>${item.full_name || item.nome || '-'}</strong>
        <small>${effectiveRole}</small>
      </div>
    `;
    usersList.appendChild(li);
  });
}

function formatAuditActionLabel(item = {}) {
  const action = String(item.action || '').trim().toLowerCase();
  if (action === 'grant') return 'Acesso concedido';
  if (action === 'update') return 'Acesso atualizado';
  if (action === 'revoke') return 'Acesso removido';
  if (action === 'scope') return 'Escopo de áreas atualizado';
  if (action === 'scope-profile') return 'Perfil de restrição alterado';
  return action || 'Alteração de acesso';
}

function escapeCsvValue(value) {
  const text = String(value ?? '');
  if (/[",\n;]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function downloadTextFile(filename, content, mimeType = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function renderUserAuditList(items = []) {
  if (!userAuditList) {
    return;
  }
  if (!items.length) {
    userAuditList.innerHTML = '<li>Nenhum evento de auditoria encontrado.</li>';
    return;
  }
  userAuditList.innerHTML = '';
  items.forEach((item) => {
    const li = document.createElement('li');
    li.className = 'items-list-item user-audit-item';
    const rolesLabel = Array.isArray(item.roles) && item.roles.length ? item.roles.join(', ') : 'sem perfis';
    li.innerHTML = `
      <div class="user-audit-item__content">
        <strong>${formatAuditActionLabel(item)}</strong>
        <span>${item.target_name || '-'} · ${item.target_email || '-'}</span>
        <small>Por ${item.actor_name || '-'} · ${item.created_at || '-'} · ${rolesLabel}</small>
        ${item.note ? `<small>${item.note}</small>` : ''}
      </div>
    `;
    userAuditList.appendChild(li);
  });
}

function updateUserAuditPager() {
  const totalPages = Math.max(1, Math.ceil(userAuditPagination.total / userAuditPagination.limit));
  userAuditPagination.page = Math.min(Math.max(1, userAuditPagination.page), totalPages);
  const startIndex = (userAuditPagination.page - 1) * userAuditPagination.limit;
  const endIndex = userAuditPagination.total > 0
    ? Math.min(startIndex + userAuditPagination.limit, userAuditPagination.total)
    : 0;

  if (userAuditPagerInfo) {
    if (!userAuditPagination.total) {
      userAuditPagerInfo.textContent = 'Página 1 de 1 — 0 registro(s)';
    } else {
      userAuditPagerInfo.textContent = `Página ${userAuditPagination.page} de ${totalPages} — ${startIndex + 1} a ${endIndex} de ${userAuditPagination.total} registro(s)`;
    }
  }
  if (userAuditPrevButton) {
    userAuditPrevButton.disabled = userAuditPagination.page <= 1 || userAuditPagination.total <= 0;
  }
  if (userAuditNextButton) {
    userAuditNextButton.disabled = userAuditPagination.page >= totalPages || userAuditPagination.total <= 0;
  }
}

function resetUserAuditPagination() {
  userAuditPagination.page = 1;
}

function getUserByIdFromCache(userId) {
  return (companyUsersCache || []).find((item) => Number(item.id) === Number(userId)) || null;
}

async function openUserAccessModal(userId) {
  const user = getUserByIdFromCache(userId);
  if (!user || !userAccessModal) {
    return;
  }
  selectedUserAccessRecord = user;
  const activeRoles = normalizedRolesOf(user);
  if (userAccessModalTitle) {
    userAccessModalTitle.textContent = user.full_name || user.email || 'Usuário';
  }
  if (userAccessModalMeta) {
    userAccessModalMeta.textContent = `${user.active ? 'Acesso ativo' : 'Sem acesso ativo'} · Perfil efetivo: ${user.role || '-'}`;
  }
  if (userAccessModalName) {
    userAccessModalName.value = user.full_name || '';
  }
  if (userAccessModalEmail) {
    userAccessModalEmail.value = user.email || '';
  }
  if (userAccessModalPassword) {
    userAccessModalPassword.value = '';
  }
  if (userAccessModalRoles) {
    userAccessModalRoles.innerHTML = '';
    ACCESS_ROLE_OPTIONS.forEach((role) => {
      const label = document.createElement('label');
      label.className = 'user-access-role';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.value = role;
      input.checked = activeRoles.includes(role);
      const span = document.createElement('span');
      span.textContent = role;
      label.appendChild(input);
      label.appendChild(span);
      userAccessModalRoles.appendChild(label);
    });
  }
  if (userAccessModalScope) {
    userAccessModalScope.textContent = user.area_scope_summary || 'todas as áreas';
  }
  if (userAccessModalRestrictionProfiles) {
    const names = (user.area_scope_profiles || []).map((profile) => profile?.name || '').filter(Boolean);
    userAccessModalRestrictionProfiles.textContent = names.length ? names.join(', ') : 'nenhum';
  }
  if (userAccessModalPasswordFlag) {
    userAccessModalPasswordFlag.textContent = user.require_password_change ? 'troca pendente no próximo acesso' : 'ok';
  }
  setUserAccessModalMessage('');
  closeUserAccessRestrictionDropdown();
  try {
    const payload = await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios/${user.id}/areas-acesso`);
    selectedUserAccessRestrictionState = {
      defaultScope: payload?.scope || { mode: 'all', areas: [] },
      assignedProfileIds: (payload?.assigned_profile_ids || []).map((item) => Number(item)),
      profiles: (payload?.profiles || []).length ? (payload?.profiles || []) : areaRestrictionProfilesCatalog,
    };
  } catch (_error) {
    selectedUserAccessRestrictionState = {
      defaultScope: user.area_scope_default || { mode: 'all', areas: [] },
      assignedProfileIds: ((user.area_scope_profiles || []).map((profile) => Number(profile.id))).filter((value) => Number.isFinite(value)),
      profiles: areaRestrictionProfilesCatalog,
    };
  }
  renderUserAccessRestrictionDropdown();
  userAccessModal.setAttribute('aria-hidden', 'false');
  userAccessModal.classList.add('open');
}

function closeUserAccessModal() {
  if (!userAccessModal) {
    return;
  }
  userAccessModal.classList.remove('open');
  userAccessModal.setAttribute('aria-hidden', 'true');
  closeUserAccessRestrictionDropdown();
  selectedUserAccessRecord = null;
}

async function openSelectedUserAreaRestrictions() {
  const user = selectedUserAccessRecord;
  if (!user) {
    return;
  }
  closeUserAccessModal();
  await openAreaAccessSession(user.id);
}

function collectUserAccessModalRoles() {
  if (!userAccessModalRoles) {
    return [];
  }
  return Array.from(userAccessModalRoles.querySelectorAll('input[type="checkbox"]:checked'))
    .map((input) => input.value || '')
    .filter(Boolean);
}

async function saveSelectedUserAccess() {
  const user = selectedUserAccessRecord;
  if (!user || !state.companyId) {
    setUserAccessModalMessage('Usuário não selecionado.', 'error');
    return;
  }
  const roles = collectUserAccessModalRoles();
  const profileIds = collectUserAccessRestrictionProfileIds();
  const fullName = userAccessModalName?.value?.trim() || '';
  const password = userAccessModalPassword?.value || '';
  if (!roles.length) {
    setUserAccessModalMessage('Selecione ao menos um perfil ou use revogar acesso.', 'error');
    return;
  }
  if (!fullName) {
    setUserAccessModalMessage('Informe um nome válido.', 'error');
    return;
  }
  try {
    await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios/${user.id}/acessos`, {
      method: 'PUT',
      body: JSON.stringify({
        roles,
        full_name: fullName,
        password,
      }),
    });
    await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios/${user.id}/areas-acesso`, {
      method: 'PUT',
      body: JSON.stringify({
        mode: selectedUserAccessRestrictionState.defaultScope?.mode || 'all',
        areas: selectedUserAccessRestrictionState.defaultScope?.areas || [],
        profile_ids: profileIds,
      }),
    });
    setUserAccessModalMessage('Usuário atualizado com sucesso.', 'success');
    await refreshAdminSessionAfterAccessChange(user.id);
    await loadUsersForCompany();
    resetUserAuditPagination();
    await loadUserAccessAudit();
    await openUserAccessModal(user.id);
  } catch (error) {
    setUserAccessModalMessage(error.message, 'error');
  }
}

async function revokeSelectedUserAccess() {
  const user = selectedUserAccessRecord;
  if (!user || !state.companyId) {
    setUserAccessModalMessage('Usuário não selecionado.', 'error');
    return;
  }
  const confirmed = window.confirm('Revogar o acesso deste usuário à empresa?');
  if (!confirmed) {
    return;
  }
  try {
    await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios/${user.id}/acessos`, {
      method: 'DELETE',
    });
    closeUserAccessModal();
    setUserAdminMessage('Acesso revogado com sucesso.', 'success');
    await refreshAdminSessionAfterAccessChange(user.id);
    await loadUsersForCompany();
    resetUserAuditPagination();
    await loadUserAccessAudit();
  } catch (error) {
    setUserAccessModalMessage(error.message, 'error');
  }
}

function openForcePasswordModal() {
  if (!forcePasswordModal) {
    return;
  }
  if (forcePasswordNew) forcePasswordNew.value = '';
  if (forcePasswordConfirm) forcePasswordConfirm.value = '';
  setForcePasswordMessage('');
  forcePasswordModal.setAttribute('aria-hidden', 'false');
  forcePasswordModal.classList.add('open');
}

function closeForcePasswordModal() {
  if (!forcePasswordModal) {
    return;
  }
  forcePasswordModal.classList.remove('open');
  forcePasswordModal.setAttribute('aria-hidden', 'true');
}

async function submitForcedPasswordChange() {
  const newPassword = forcePasswordNew?.value || '';
  const confirmPassword = forcePasswordConfirm?.value || '';
  if (!newPassword || newPassword.length < 8) {
    setForcePasswordMessage('A nova senha deve ter pelo menos 8 caracteres.', 'error');
    return;
  }
  if (newPassword !== confirmPassword) {
    setForcePasswordMessage('A confirmação da senha não confere.', 'error');
    return;
  }
  try {
    await apiFetch('/api/v1/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword }),
    });
    await loadUserSession(true);
    closeForcePasswordModal();
    showToast('Senha alterada com sucesso.');
  } catch (error) {
    setForcePasswordMessage(error.message, 'error');
  }
}

function renderAreaAccessUserOptions() {
  if (!areaAccessUserSelect) {
    return;
  }
  const previousValue = areaAccessUserSelect.value;
  areaAccessUserSelect.innerHTML = '<option value="">Selecione um usuário</option>';
  (companyUsersCache || []).forEach((user) => {
    const option = document.createElement('option');
    option.value = String(user.id || '');
    option.textContent = `${user.full_name || user.email || 'usuário'} · ${user.email || '-'}`;
    areaAccessUserSelect.appendChild(option);
  });
  const fallbackValue = previousValue || String(companyUsersCache?.[0]?.id || '');
  if ([...areaAccessUserSelect.options].some((option) => option.value === fallbackValue)) {
    areaAccessUserSelect.value = fallbackValue;
  }
}

function renderAreaAccessChecklist() {
  if (!areaAccessChecklist) {
    return;
  }
  const selectedUser = getUserByIdFromCache(areaAccessUserSelect?.value);
  const isAdminTarget = hasRole('admin', selectedUser);
  const mode = areaAccessMode?.value || 'all';
  const disabled = isAdminTarget || mode !== 'selected';
  const areas = Array.isArray(areaAccessState.availableAreas) ? areaAccessState.availableAreas : [];
  if (!areas.length) {
    areaAccessChecklist.innerHTML = '<span class="helper">Nenhuma área disponível para configurar.</span>';
    return;
  }
  areaAccessChecklist.innerHTML = '';
  areas.forEach((area) => {
    const label = document.createElement('label');
    label.className = 'user-access-role';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = area;
    input.checked = areaAccessState.selectedAreas.includes(area);
    input.disabled = disabled;
    const span = document.createElement('span');
    span.textContent = area === FALLBACK_AREA ? 'sem-area' : area;
    label.appendChild(input);
    label.appendChild(span);
    areaAccessChecklist.appendChild(label);
  });
  if (isAdminTarget) {
    setAreaAccessMessage('Administradores sempre possuem acesso total às áreas.', 'success');
  }
}

function renderAreaRestrictionProfileChecklist() {
  if (!areaRestrictionProfileChecklist) {
    return;
  }
  const areas = Array.isArray(areaAccessState.availableAreas) ? areaAccessState.availableAreas : [];
  if (!areas.length) {
    areaRestrictionProfileChecklist.innerHTML = '<span class="helper">Nenhuma área disponível para perfis.</span>';
    return;
  }
  areaRestrictionProfileChecklist.innerHTML = '';
  areas.forEach((area) => {
    const label = document.createElement('label');
    label.className = 'user-access-role';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = area;
    const span = document.createElement('span');
    span.textContent = area === FALLBACK_AREA ? 'sem-area' : area;
    label.appendChild(input);
    label.appendChild(span);
    areaRestrictionProfileChecklist.appendChild(label);
  });
}

function renderAreaAccessProfiles() {
  if (!areaAccessProfilesList) {
    return;
  }
  const selectedUser = getUserByIdFromCache(areaAccessUserSelect?.value);
  const isAdminTarget = hasRole('admin', selectedUser);
  const profiles = Array.isArray(areaAccessState.profiles) ? areaAccessState.profiles : [];
  if (!profiles.length) {
    areaAccessProfilesList.innerHTML = '<span class="helper">Nenhum perfil reutilizável cadastrado.</span>';
    return;
  }
  areaAccessProfilesList.innerHTML = '';
  profiles.forEach((profile) => {
    const label = document.createElement('label');
    label.className = 'area-profile-card';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = String(profile.id || '');
    input.checked = (areaAccessState.assignedProfileIds || []).includes(Number(profile.id));
    input.disabled = isAdminTarget;
    const content = document.createElement('div');
    content.className = 'area-profile-card__content';
    const title = document.createElement('strong');
    title.textContent = profile.name || `perfil ${profile.id}`;
    const meta = document.createElement('small');
    meta.textContent = (profile.areas || []).length ? (profile.areas || []).join(', ') : 'sem áreas';
    content.appendChild(title);
    if (profile.description) {
      const desc = document.createElement('small');
      desc.textContent = profile.description;
      content.appendChild(desc);
    }
    content.appendChild(meta);
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'ghost area-profile-remove';
    removeBtn.dataset.profileId = String(profile.id || '');
    removeBtn.textContent = 'Excluir perfil';
    label.appendChild(input);
    label.appendChild(content);
    label.appendChild(removeBtn);
    areaAccessProfilesList.appendChild(label);
  });
}

function collectAreaAccessSelection() {
  if (!areaAccessChecklist) {
    return [];
  }
  return Array.from(areaAccessChecklist.querySelectorAll('input[type="checkbox"]:checked'))
    .map((input) => input.value || '')
    .filter(Boolean);
}

function collectAssignedAreaProfileIds() {
  if (!areaAccessProfilesList) {
    return [];
  }
  return Array.from(areaAccessProfilesList.querySelectorAll('input[type="checkbox"]:checked'))
    .map((input) => Number(input.value || 0))
    .filter((value) => Number.isFinite(value) && value > 0);
}

function collectAreaRestrictionProfileAreas() {
  if (!areaRestrictionProfileChecklist) {
    return [];
  }
  return Array.from(areaRestrictionProfileChecklist.querySelectorAll('input[type="checkbox"]:checked'))
    .map((input) => input.value || '')
    .filter(Boolean);
}

async function loadSelectedUserAreaScope() {
  const userId = Number(areaAccessUserSelect?.value || 0);
  if (!userId || !state.companyId) {
    areaAccessState = {
      availableAreas: [],
      selectedAreas: [],
      profiles: [],
      assignedProfileIds: [],
      effectiveScope: { mode: 'all', areas: [] },
    };
    renderAreaAccessChecklist();
    renderAreaAccessProfiles();
    renderAreaRestrictionProfileChecklist();
    return;
  }
  try {
    const payload = await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios/${userId}/areas-acesso`);
    areaAccessState = {
      availableAreas: payload?.available_areas || [],
      selectedAreas: payload?.scope?.areas || [],
      profiles: payload?.profiles || [],
      assignedProfileIds: (payload?.assigned_profile_ids || []).map((item) => Number(item)),
      effectiveScope: payload?.effective_scope || { mode: 'all', areas: [] },
    };
    if (areaAccessMode) {
      areaAccessMode.value = payload?.scope?.mode || 'all';
    }
    if (!hasRole('admin', getUserByIdFromCache(userId))) {
      setAreaAccessMessage('');
    }
    renderAreaAccessChecklist();
    renderAreaAccessProfiles();
    renderAreaRestrictionProfileChecklist();
  } catch (error) {
    areaAccessState = { availableAreas: [], selectedAreas: [], profiles: [], assignedProfileIds: [], effectiveScope: { mode: 'all', areas: [] } };
    renderAreaAccessChecklist();
    renderAreaAccessProfiles();
    renderAreaRestrictionProfileChecklist();
    setAreaAccessMessage(error.message, 'error');
  }
}

async function openAreaAccessSession(preferredUserId = null) {
  showSession('userAreaAccessSession');
  setAreaAccessMessage('');
  setAreaRestrictionProfileMessage('');
  await loadUsersForCompany();
  renderAreaAccessUserOptions();
  if (preferredUserId && areaAccessUserSelect) {
    const preferred = String(preferredUserId);
    if ([...areaAccessUserSelect.options].some((option) => option.value === preferred)) {
      areaAccessUserSelect.value = preferred;
    }
  }
  await loadSelectedUserAreaScope();
  hideUserMenu();
}

async function saveAreaAccessScope() {
  const userId = Number(areaAccessUserSelect?.value || 0);
  if (!userId || !state.companyId) {
    setAreaAccessMessage('Selecione um usuário para configurar o acesso.', 'error');
    return;
  }
  const targetUser = getUserByIdFromCache(userId);
  if (hasRole('admin', targetUser)) {
    setAreaAccessMessage('Administradores não podem ter restrição de área.', 'error');
    return;
  }
  const mode = areaAccessMode?.value || 'all';
  const selectedAreas = collectAreaAccessSelection();
  const profileIds = collectAssignedAreaProfileIds();
  if (mode === 'selected' && !selectedAreas.length) {
    setAreaAccessMessage('Selecione ao menos uma área quando o modo for restrito.', 'error');
    return;
  }
  try {
    await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios/${userId}/areas-acesso`, {
      method: 'PUT',
      body: JSON.stringify({ mode, areas: selectedAreas, profile_ids: profileIds }),
    });
    setAreaAccessMessage('Restrição de áreas atualizada com sucesso.', 'success');
    resetUserAuditPagination();
    await loadUserAccessAudit();
    await loadSelectedUserAreaScope();
  } catch (error) {
    setAreaAccessMessage(error.message, 'error');
  }
}

async function createAreaRestrictionProfile(event) {
  event.preventDefault();
  if (!state.companyId) {
    setAreaRestrictionProfileMessage('Empresa não identificada.', 'error');
    return;
  }
  const name = areaRestrictionProfileName?.value?.trim() || '';
  const description = areaRestrictionProfileDescription?.value?.trim() || '';
  const areas = collectAreaRestrictionProfileAreas();
  if (!name) {
    setAreaRestrictionProfileMessage('Informe um nome para o perfil.', 'error');
    return;
  }
  if (!areas.length) {
    setAreaRestrictionProfileMessage('Selecione ao menos uma área para o perfil.', 'error');
    return;
  }
  try {
    await apiFetch(`/api/v1/empresas/${state.companyId}/perfis-restricao-areas`, {
      method: 'POST',
      body: JSON.stringify({ name, description, areas }),
    });
    if (areaRestrictionProfileName) areaRestrictionProfileName.value = '';
    if (areaRestrictionProfileDescription) areaRestrictionProfileDescription.value = '';
    areaRestrictionProfileChecklist?.querySelectorAll('input[type="checkbox"]').forEach((input) => {
      input.checked = false;
    });
    setAreaRestrictionProfileMessage('Perfil de restrição criado com sucesso.', 'success');
    await loadSelectedUserAreaScope();
    resetUserAuditPagination();
    await loadUserAccessAudit();
    await loadUsersForCompany();
  } catch (error) {
    setAreaRestrictionProfileMessage(error.message, 'error');
  }
}

async function deleteAreaRestrictionProfile(profileId) {
  if (!state.companyId || !profileId) {
    return;
  }
  const confirmed = window.confirm('Excluir este perfil reutilizável de restrição?');
  if (!confirmed) {
    return;
  }
  try {
    await apiFetch(`/api/v1/empresas/${state.companyId}/perfis-restricao-areas/${profileId}`, {
      method: 'DELETE',
    });
    setAreaAccessMessage('Perfil reutilizável removido com sucesso.', 'success');
    await loadSelectedUserAreaScope();
    resetUserAuditPagination();
    await loadUserAccessAudit();
    await loadUsersForCompany();
  } catch (error) {
    setAreaAccessMessage(error.message, 'error');
  }
}

function exportUserAuditCsv() {
  const items = Array.isArray(companyUserAuditCache) ? companyUserAuditCache : [];
  if (!items.length) {
    showToast('Não há auditoria para exportar.', 'error');
    return;
  }
  const lines = [
    ['acao', 'alvo_nome', 'alvo_email', 'ator_nome', 'ator_email', 'perfis', 'observacao', 'criado_em']
      .map(escapeCsvValue)
      .join(','),
  ];
  items.forEach((item) => {
    lines.push([
      formatAuditActionLabel(item),
      item.target_name || '',
      item.target_email || '',
      item.actor_name || '',
      item.actor_email || '',
      Array.isArray(item.roles) ? item.roles.join('; ') : '',
      item.note || '',
      item.created_at || '',
    ].map(escapeCsvValue).join(','));
  });
  const companyLabel = String(state.companyId || 'empresa');
  downloadTextFile(`auditoria-acessos-empresa-${companyLabel}.csv`, `${lines.join('\n')}\n`, 'text/csv;charset=utf-8');
}

async function loadAreaRestrictionProfilesCatalog() {
  if (!isAccessControlEnabled() || !state.companyId || !isAdminProfile()) {
    areaRestrictionProfilesCatalog = [];
    newUserAssignedRestrictionProfileIds = [];
    renderNewUserRestrictionDropdown();
    return;
  }
  try {
    const payload = await apiFetch(`/api/v1/empresas/${state.companyId}/perfis-restricao-areas`);
    areaRestrictionProfilesCatalog = Array.isArray(payload?.items) ? payload.items : [];
    newUserAssignedRestrictionProfileIds = newUserAssignedRestrictionProfileIds
      .filter((profileId) => areaRestrictionProfilesCatalog.some((profile) => Number(profile.id) === Number(profileId)));
    renderNewUserRestrictionDropdown();
  } catch (_error) {
    areaRestrictionProfilesCatalog = [];
    newUserAssignedRestrictionProfileIds = [];
    renderNewUserRestrictionDropdown();
  }
}

function toggleAdminMenuVisibility() {
  if (!isAccessControlEnabled()) {
    if (userAdminMenuItem) {
      userAdminMenuItem.classList.add('hidden-view');
      userAdminMenuItem.setAttribute('aria-hidden', 'true');
    }
    if (userAreaAccessMenuItem) {
      userAreaAccessMenuItem.classList.add('hidden-view');
      userAreaAccessMenuItem.setAttribute('aria-hidden', 'true');
    }
    if (userAdminSession && userAdminSession.classList.contains('active-session')) {
      showSession('dashboardSession');
    }
    if (userAreaAccessSession && userAreaAccessSession.classList.contains('active-session')) {
      showSession('dashboardSession');
    }
    return;
  }
  if (userAdminMenuItem) {
    userAdminMenuItem.classList.toggle('hidden-view', !isAdminProfile());
    userAdminMenuItem.setAttribute('aria-hidden', String(!isAdminProfile()));
  }
  if (userAreaAccessMenuItem) {
    userAreaAccessMenuItem.classList.toggle('hidden-view', !isAdminProfile());
    userAreaAccessMenuItem.setAttribute('aria-hidden', String(!isAdminProfile()));
  }
  if (userAdminSession && !isAdminProfile() && userAdminSession.classList.contains('active-session')) {
    showSession('dashboardSession');
  }
  if (userAreaAccessSession && !isAdminProfile() && userAreaAccessSession.classList.contains('active-session')) {
    showSession('dashboardSession');
  }
}

async function loadUsersForCompany() {
  if (!isAccessControlEnabled()) {
    if (usersList) {
      usersList.innerHTML = 'Acesso a usuários indisponível no modo sem autenticação.';
    }
    areaRestrictionProfilesCatalog = [];
    newUserAssignedRestrictionProfileIds = [];
    renderNewUserRestrictionDropdown();
    return;
  }
  if (!state.companyId || !isAdminProfile()) {
    if (usersList) {
      usersList.innerHTML = '<li>Sem permissão para visualizar usuários.</li>';
    }
    areaRestrictionProfilesCatalog = [];
    newUserAssignedRestrictionProfileIds = [];
    renderNewUserRestrictionDropdown();
    return;
  }
  try {
    const users = await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios`);
    companyUsersCache = users || [];
    usersPagination.page = 1;
    renderUsersList(companyUsersCache);
  } catch (error) {
    if (usersList) {
      usersList.innerHTML = `<li>${error.message}</li>`;
    }
  } finally {
    await loadAreaRestrictionProfilesCatalog();
  }
}

async function loadUserAccessAudit() {
  if (!isAccessControlEnabled() || !state.companyId || !isAdminProfile()) {
    if (userAuditList) {
      userAuditList.innerHTML = '<li>Sem permissão para visualizar auditoria.</li>';
    }
    companyUserAuditCache = [];
    userAuditPagination.total = 0;
    updateUserAuditPager();
    return;
  }
  try {
    const offset = (Math.max(1, userAuditPagination.page) - 1) * userAuditPagination.limit;
    const payload = await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios/auditoria?limit=${userAuditPagination.limit}&offset=${offset}`);
    companyUserAuditCache = Array.isArray(payload?.items) ? payload.items : [];
    userAuditPagination.total = Number.isFinite(Number(payload?.total)) ? Number(payload.total) : companyUserAuditCache.length;
    renderUserAuditList(companyUserAuditCache);
    updateUserAuditPager();
  } catch (error) {
    if (userAuditList) {
      userAuditList.innerHTML = `<li>${error.message}</li>`;
    }
    companyUserAuditCache = [];
    userAuditPagination.total = 0;
    updateUserAuditPager();
  }
}

function getRolesFromUserCard(card) {
  return Array.from(card.querySelectorAll('input[type="checkbox"][data-role]:checked'))
    .map((input) => input.dataset.role || '')
    .filter(Boolean);
}

function setUserCardBusy(card, busy = true) {
  if (!card) {
    return;
  }
  card.classList.toggle('is-busy', busy);
  const controls = card.querySelectorAll('input, button');
  controls.forEach((control) => {
    control.disabled = busy;
  });
}

async function refreshAdminSessionAfterAccessChange(targetUserId) {
  if (!state.profile || Number(targetUserId) !== Number(state.profile.user_id)) {
    return;
  }
  await loadUserSession(true);
  if (!isAdminProfile()) {
    showSession('dashboardSession');
  }
}

async function saveUserAccessFromCard(card) {
  const userId = Number(card?.dataset?.userId || 0);
  if (!userId || !state.companyId) {
    showToast('Não foi possível identificar o usuário.', 'error');
    return;
  }
  const roles = getRolesFromUserCard(card);
  const fullName = card.querySelector('.user-access-name')?.value?.trim() || '';
  const password = card.querySelector('.user-access-password')?.value || '';
  if (!roles.length) {
    setUserAdminMessage('Selecione ao menos um perfil ou use "Remover acesso".', 'error');
    return;
  }
  if (!fullName) {
    setUserAdminMessage('Informe um nome válido para o usuário.', 'error');
    return;
  }

  setUserCardBusy(card, true);
  try {
    await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios/${userId}/acessos`, {
      method: 'PUT',
      body: JSON.stringify({
        roles,
        full_name: fullName,
        password,
      }),
    });
    setUserAdminMessage('Acessos atualizados com sucesso.', 'success');
    await refreshAdminSessionAfterAccessChange(userId);
    await loadUsersForCompany();
    resetUserAuditPagination();
    await loadUserAccessAudit();
  } catch (error) {
    setUserAdminMessage(error.message, 'error');
  } finally {
    const passwordInput = card.querySelector('.user-access-password');
    if (passwordInput) {
      passwordInput.value = '';
    }
    setUserCardBusy(card, false);
  }
}

async function revokeUserAccessFromCard(card) {
  const userId = Number(card?.dataset?.userId || 0);
  if (!userId || !state.companyId) {
    showToast('Não foi possível identificar o usuário.', 'error');
    return;
  }

  setUserCardBusy(card, true);
  try {
    const confirmed = window.confirm('Remover o acesso deste usuário à empresa?');
    if (!confirmed) {
      return;
    }
    await apiFetch(`/api/v1/empresas/${state.companyId}/usuarios/${userId}/acessos`, {
      method: 'DELETE',
    });
    setUserAdminMessage('Acesso removido com sucesso.', 'success');
    await refreshAdminSessionAfterAccessChange(userId);
    await loadUsersForCompany();
    resetUserAuditPagination();
    await loadUserAccessAudit();
  } catch (error) {
    setUserAdminMessage(error.message, 'error');
  } finally {
    setUserCardBusy(card, false);
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
    state.taxonomies.categorias = (categoriasData?.items || []).map((item) => (
      typeof item === 'string'
        ? { name: item, area: '' }
        : {
          name: item?.name || '',
          area: item?.area || item?.parent_area || '',
        }
    )).filter((item) => item.name);
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
    state.defaultCompanyName = config?.default_company_name || '';
    state.defaultCompanyDescription = config?.default_company_description || '';

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
      if (brandSubtitle) {
        brandSubtitle.textContent = state.defaultCompanyName || state.defaultCompanyDescription || 'Expertise.AI';
      }
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
  userAreaAccessSession: document.getElementById('userAreaAccessSession'),
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
  if ((sessionId === 'userAdminSession' || sessionId === 'userAreaAccessSession') && !isAdminProfile()) {
    showToast('Somente administradores podem acessar a sessão de gestão de acessos.', 'error');
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
  const role = formatRoleLabel(profile);
  const company = profile?.company_name || state.defaultCompanyName || `empresa ${state.companyId || '-'}`;
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
    profileRole.textContent = formatRoleLabel(data);
  }
  if (profileCompany) {
    profileCompany.textContent = data.company_name || '-';
  }
  if (brandSubtitle) {
    brandSubtitle.textContent = data.company_name || state.defaultCompanyName || 'Expertise.AI';
  }
  if (userAvatar) {
    userAvatar.textContent = getInitials(data);
  }
}

function setPanelStatusText() {
  updateCreateDocumentButtonAvailability();
  if (state.profile) {
    updateDashboardApprovalStatus();
    renderProfileToUi(state.profile);
    return;
  }
  if (brandSubtitle) {
    brandSubtitle.textContent = state.defaultCompanyName || state.defaultCompanyDescription || 'Expertise.AI';
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
    closeUserAccessModal();
    closeForcePasswordModal();
    showInlineCreateSession(false);
    state.taxonomies = { areas: [], categorias: [] };
    renderTaxonomies();
    state.profile = null;
    renderProfileToUi({ full_name: '-', email: '-', role: '-', company_name: '-' });
    toggleAdminMenuVisibility();
    if (usersList) {
      usersList.innerHTML = '<li>Sem permissão para visualizar usuários.</li>';
    }
    if (userAuditList) {
      userAuditList.innerHTML = '<li>Sem permissão para visualizar auditoria.</li>';
    }
    setStatus('sem autenticação');
  }
}

function closeDocumentModal() {
  docModal.classList.remove('open');
  docModal.setAttribute('aria-hidden', 'true');
  if (docModalEditBtn) {
    docModalEditBtn.classList.remove('hidden-view');
  }
  if (docModalTitle) {
    docModalTitle.textContent = 'Visualizar documento';
  }
  if (docModalMeta) {
    docModalMeta.textContent = '';
  }
  if (docModalContent) {
    docModalContent.textContent = 'Selecione um documento para visualizar.';
  }
  if (modalVersionPublishToggle) {
    modalVersionPublishToggle.checked = false;
    modalVersionPublishToggle.disabled = true;
  }
  if (modalPublishToggleInfo) {
    modalPublishToggleInfo.textContent = 'Publicar esta versão';
  }
}

function openFailureDetailsModal(doc) {
  const displayError = normalizeDocumentError(doc?.error);
  selectedDocument = null;
  if (docModalTitle) {
    docModalTitle.textContent = 'Detalhes da falha';
  }
  if (docModalMeta) {
    docModalMeta.textContent = `${doc?.title || doc?.file_name || doc?.slug || 'Documento'} · ${doc?.area || 'sem-area'} / ${doc?.categoria || 'sem-categoria'}`;
  }
  if (docModalContent) {
    docModalContent.textContent = displayError;
  }
  if (docModalEditBtn) {
    docModalEditBtn.classList.add('hidden-view');
  }
  if (modalPublishToggleWrap) {
    modalPublishToggleWrap.classList.add('hidden-view');
  }
  docModal.setAttribute('aria-hidden', 'false');
  docModal.classList.add('open');
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

function persistAuthTokens(accessToken = '', refreshToken = '') {
  state.token = accessToken || '';
  state.refreshToken = refreshToken || '';
  if (state.token) {
    localStorage.setItem('expai_token', state.token);
  } else {
    localStorage.removeItem('expai_token');
  }
  if (state.refreshToken) {
    localStorage.setItem('expai_refresh_token', state.refreshToken);
  } else {
    localStorage.removeItem('expai_refresh_token');
  }
}

function doLogout(reason = '', notify = false) {
  state.token = '';
  state.refreshToken = '';
  localStorage.removeItem('expai_token');
  localStorage.removeItem('expai_refresh_token');
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
  if (notify && reason) {
    showToast(reason, 'error');
  } else if (reason && loginMsg) {
    loginMsg.textContent = reason;
    loginMsg.className = 'helper error';
  }
}

async function refreshAccessToken() {
  if (!isAccessControlEnabled()) {
    return false;
  }
  if (!state.refreshToken) {
    return false;
  }
  if (authRefreshPromise) {
    return authRefreshPromise;
  }

  authRefreshPromise = (async () => {
    const response = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: state.refreshToken }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = data?.detail || `Erro ${response.status}`;
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    if (!data?.access_token || !data?.refresh_token) {
      throw new Error('Resposta de refresh sem tokens válidos.');
    }
    persistAuthTokens(data.access_token, data.refresh_token);
    sessionExpiredMessageShown = false;
    return true;
  })();

  try {
    return await authRefreshPromise;
  } finally {
    authRefreshPromise = null;
  }
}

function handleAuthenticationFailure(message = 'Sua sessão expirou. Faça login novamente.') {
  const shouldNotify = !sessionExpiredMessageShown;
  sessionExpiredMessageShown = true;
  doLogout(message, shouldNotify);
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
    updatePublishControls();
    if (payload?.require_password_change) {
      openForcePasswordModal();
    } else {
      closeForcePasswordModal();
    }
    return payload;
  } catch (error) {
    state.profile = null;
    renderProfileToUi({ full_name: '-', email: '-', role: '-', company_name: '-' });
    setStatus(error.message, false);
    toggleAdminMenuVisibility();
    updatePublishControls();
    closeForcePasswordModal();
    return null;
  }
}

function hideEditHistory() {
  if (!editHistorySession || !editVersionsList) {
    return;
  }

  editHistorySession.classList.add('hidden-view');
  editVersionsList.innerHTML = '';
  if (attachmentsSection) {
    attachmentsSection.classList.add('hidden-view');
  }
  if (attachmentsList) {
    attachmentsList.innerHTML = '';
  }
  if (attachmentsHint) {
    attachmentsHint.textContent = 'Nenhum anexo disponível.';
  }
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

async function downloadAttachment(meta, attachment) {
  if (!meta || !attachment) {
    return;
  }
  if (!state.companyId) {
    showToast('Empresa não definida para baixar o anexo.', 'error');
    return;
  }
  if (!state.token && isAccessControlEnabled()) {
    showToast('Faça login para baixar o anexo.', 'error');
    return;
  }

  const query = new URLSearchParams();
  if (attachment.id) {
    query.set('attachment_id', attachment.id);
  }
  const url = `/api/v1/empresas/${state.companyId}/documentos/${encodeURIComponent(meta.area || FALLBACK_AREA)}/${encodeURIComponent(meta.categoria || FALLBACK_CATEGORIA)}/${encodeURIComponent(meta.slug || '')}/anexo${query.toString() ? `?${query}` : ''}`;
  try {
    const res = await fetch(url, {
      headers: state.token ? { Authorization: `Bearer ${state.token}` } : {},
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data?.detail || `Erro ${res.status}`);
    }
    const blob = await res.blob();
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = attachment.file_name || 'anexo';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(downloadUrl);
  } catch (error) {
    showToast(error.message || 'Não foi possível baixar o anexo.', 'error');
  }
}

function renderAttachments(meta) {
  if (!attachmentsSection || !attachmentsList) {
    return;
  }
  const attachments = Array.isArray(meta?.attachments) ? meta.attachments : [];
  attachmentsList.innerHTML = '';
  if (!attachments.length) {
    attachmentsSection.classList.add('hidden-view');
    if (attachmentsHint) {
      attachmentsHint.textContent = 'Nenhum anexo disponível.';
    }
    return;
  }

  attachmentsSection.classList.remove('hidden-view');
  if (attachmentsHint) {
    attachmentsHint.textContent = 'Clique para baixar os anexos do documento.';
  }
  attachments.forEach((attachment, index) => {
    const fileName = attachment?.file_name || `anexo-${index + 1}`;
    const sizeLabel = formatFileSize(attachment?.size_bytes);
    const uploadedAt = attachment?.uploaded_at || '';
    const metaLine = [sizeLabel, uploadedAt].filter(Boolean).join(' · ');

    const li = document.createElement('li');
    li.className = 'attachment-item';
    const name = document.createElement('span');
    name.className = 'attachment-name';
    name.textContent = fileName;
    const metaInfo = document.createElement('span');
    metaInfo.className = 'attachment-meta';
    metaInfo.textContent = metaLine;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'attachment-link';
    button.innerHTML = `
      <span class="attachment-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" role="presentation" focusable="false">
          <path d="M12 3a1 1 0 0 1 1 1v8.59l2.3-2.3a1 1 0 1 1 1.4 1.42l-4.01 4a1 1 0 0 1-1.4 0l-4.01-4a1 1 0 1 1 1.4-1.42l2.32 2.3V4a1 1 0 0 1 1-1zM5 19a1 1 0 0 1 1-1h12a1 1 0 0 1 0 2H6a1 1 0 0 1-1-1z"></path>
        </svg>
      </span>
      <span>Baixar</span>
    `;
    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      downloadAttachment(meta, attachment);
    });

    li.appendChild(name);
    if (metaLine) {
      li.appendChild(metaInfo);
    }
    li.appendChild(button);
    attachmentsList.appendChild(li);
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
    const pendingTag = !item.published && isPendingApprovalVersion(item) ? 'PENDENTE APROVACAO' : '';
    const publishedLabel = item.published_at ? `Publicado em ${item.published_at}` : '';
    const approvalLabel = item.approved_by
      ? `Aprovado por ${item.approved_by}${item.published_at ? ` em ${item.published_at}` : ''}`
      : '';
    const title = `v${item.version}`;
    const metaLine = [
      item.author || 'autor não informado',
      item.created_at || '',
      approvalLabel || publishedLabel,
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
          ${publishedTag
            ? `<span class="timeline-badge">${publishedTag}</span>`
            : pendingTag
              ? `<span class="timeline-badge timeline-badge--pending">${pendingTag}</span>`
              : '<span class="timeline-badge timeline-badge--draft">Rascunho</span>'}
        </div>
        <span class="timeline-meta">${metaLine}</span>
      </div>
    `;
    editVersionsList.appendChild(li);
  }

  renderAttachments(meta);
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
  const isPendingApproval = isPendingApprovalVersion(selected) || isPendingApprovalVersion(payload);
  versionPublishToggle.checked = isPublished;
  versionPublishToggle.disabled = false;
  publishToggleInfo.textContent = isPendingApproval
    ? `Publicar versão v${version} pendente de aprovação`
    : `Publicar versão v${version}`;
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
      document_uuid: editingDocumentContext.document_uuid || '',
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
    document_uuid: document.document_uuid || '',
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
  const pendingApproval = isPendingApprovalVersion(doc);
  const shouldShowPublish = canPublishDocument() && (Boolean(showPublishControls) || pendingApproval || !docIsPublished(doc));
  const versionLabel = targetVersion ? `v${targetVersion}` : '-';
  if (docModalEditBtn) {
    docModalEditBtn.classList.remove('hidden-view');
  }
  docModalTitle.textContent = truncateForCard(docTitleOf(doc) || doc.slug);
  docModalMeta.textContent = `${doc.area} / ${doc.categoria} · ${versionLabel} · ${doc.updated_at || ''}${formatValidityMeta(doc?.data_validade)}`;
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
        selectedDocument = {
          ...selectedDocument,
          version: payloadVersion,
          published: payloadPublished,
          pending_approval: isPendingApprovalVersion(payload),
        };
        docModalMeta.textContent = `${doc.area} / ${doc.categoria} · v${payloadVersion} · ${payload.updated_at || doc.updated_at || ''}${formatValidityMeta(payload?.data_validade || doc?.data_validade)}`;
        if (modalVersionPublishToggle) {
          modalVersionPublishToggle.checked = payloadPublished;
          modalVersionPublishToggle.disabled = !shouldShowPublish;
        }
        if (modalPublishToggleInfo) {
          modalPublishToggleInfo.textContent = isPendingApprovalVersion(payload)
            ? `Publicar versão v${payloadVersion} pendente de aprovação`
            : `Publicar versão v${payloadVersion}`;
        }
      }
      const payloadTitle = docTitleOf(payload);
      if (payloadTitle) {
        selectedDocument = { ...selectedDocument, title: payloadTitle };
        docModalTitle.textContent = truncateForCard(payloadTitle);
      }
      if (payload?.data_validade !== undefined) {
        selectedDocument = { ...selectedDocument, data_validade: payload.data_validade };
      }
      if (payload?.tags) {
        selectedDocument = { ...selectedDocument, tags: payload.tags };
      }
      if (payload?.ai_prompt) {
        selectedDocument = { ...selectedDocument, ai_prompt: payload.ai_prompt };
      }
      if (payload?.document_uuid) {
        selectedDocument = { ...selectedDocument, document_uuid: payload.document_uuid };
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
      document_uuid: selectedDocument.document_uuid || '',
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
      document_uuid: context.document_uuid || '',
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
  const promptTarget = document.getElementById('docAiPrompt');
  const validityTarget = document.getElementById('docValidity');
  contentTarget.value = '';
  setFormSelectValue(docArea, selectedDocument.area || '');
  setFormSelectValue(docCategoria, selectedDocument.categoria || '');
  setTaxonomySelectOptions();
  document.getElementById('docSlug').value = selectedDocument.slug || '';
  document.getElementById('docTitle').value = docTitleOf(selectedDocument) || selectedDocument.slug || '';
  setCreateSessionTags(selectedDocument.tags || []);
  if (promptTarget) {
    promptTarget.value = selectedDocument.ai_prompt || '';
  }
  if (validityTarget) {
    validityTarget.value = selectedDocument.data_validade || '';
  }
  updatePublishControls();
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
        setCreateSessionTags(payload.tags || []);
      }
      if (payload?.data_validade && validityTarget) {
        validityTarget.value = payload.data_validade;
      }
      const selectedVersion = contentVersionOf(payload);
      if (selectedVersion) {
        selectedDocument = { ...selectedDocument, version: selectedVersion };
      }
      loadDocumentHistory({
        document_uuid: payload?.document_uuid || selectedDocument.document_uuid || '',
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
        document_uuid: selectedDocument.document_uuid || '',
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

function updatePublishControls() {
  const docPublish = document.getElementById('docPublish');
  if (!docPublish) {
    return;
  }
  const allowed = canPublishDocument();
  docPublish.disabled = !allowed;
  if (!allowed) {
    docPublish.checked = false;
    docPublish.title = 'Somente aprovadores ou administradores podem publicar documentos.';
  } else {
    docPublish.title = 'Publicar documento';
  }
}

function parseTags(value) {
  return value
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
}

function parseDateOnly(value) {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const datePart = raw.split('T')[0];
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(datePart);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day);
}

function buildValidityBadge(dataValidade) {
  const parsed = parseDateOnly(dataValidade);
  if (!parsed) return '';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const warn = new Date(today);
  warn.setDate(today.getDate() + 1);
  if (today >= parsed) {
    return `<span class="status-tag status-tag-expired" title="Validade: ${dataValidade}">Expirado</span>`;
  }
  if (warn >= parsed) {
    return `<span class="status-tag status-tag-warning" title="Validade: ${dataValidade}">Prox. Expirar</span>`;
  }
  return '';
}

function formatValidityMeta(dataValidade) {
  if (!dataValidade) return '';
  return ` · validade: ${dataValidade}`;
}

function setCreateSessionTags(nextTags = [], pendingInput = '') {
  const normalized = normalizeTagValues(nextTags);
  createSessionTags = normalized;
  if (docTagBadges) {
    docTagBadges.innerHTML = '';
    normalized.forEach((tag) => {
      const badge = document.createElement('span');
      badge.className = 'tag-badge';
      badge.dataset.tag = tag;
      badge.textContent = tag;

      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'tag-badge__remove';
      remove.setAttribute('aria-label', `Remover tag ${tag}`);
      remove.innerHTML = '×';
      badge.appendChild(remove);
      docTagBadges.appendChild(badge);
    });
  }
  if (docTagsInput) {
    docTagsInput.value = pendingInput || '';
  }
}

function addCreateTagFromInput(rawValue) {
  const normalized = normalizeTagValues(parseTags(rawValue || ''));
  if (!normalized.length) {
    return;
  }
  const unique = new Set(createSessionTags);
  normalized.forEach((tag) => unique.add(tag));
  setCreateSessionTags([...unique]);
  if (docTagsInput) {
    docTagsInput.value = '';
  }
}

function removeCreateTag(tag) {
  const target = normalizeTagValue(tag);
  if (!target) {
    return;
  }
  const remaining = createSessionTags.filter((item) => item !== target);
  setCreateSessionTags(remaining);
}

function commitCreateTagInput(value = '') {
  const text = value || docTagsInput?.value || '';
  addCreateTagFromInput(text);
  if (docTagsInput) {
    docTagsInput.value = '';
  }
}

function collectCreateTags() {
  const pending = parseTags(docTagsInput?.value || '');
  return normalizeTagValues([...createSessionTags, ...pending]);
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
docTagsInput?.addEventListener('keydown', (event) => {
  if (event.key === ',') {
    event.preventDefault();
    commitCreateTagInput();
    return;
  }
  if (event.key === 'Enter') {
    event.preventDefault();
    commitCreateTagInput();
    return;
  }
  if (event.key === 'Backspace' && !docTagsInput.value && createSessionTags.length > 0) {
    event.preventDefault();
    setCreateSessionTags(createSessionTags.slice(0, -1));
  }
});
docTagsInput?.addEventListener('input', () => {
  const value = docTagsInput.value || '';
  if (!value.includes(',')) {
    return;
  }
  const parts = value.split(',');
  const trailing = parts.pop() || '';
  const toAdd = parts.join(', ');
  addCreateTagFromInput(toAdd);
  docTagsInput.value = trailing;
});
docTagsInput?.addEventListener('blur', () => {
  if (!docTagsInput.value) {
    return;
  }
  commitCreateTagInput();
});
docTagBadges?.addEventListener('click', (event) => {
  const removeBtn = event.target.closest('.tag-badge__remove');
  if (!removeBtn) {
    return;
  }
  const tag = removeBtn.parentNode?.dataset?.tag;
  removeCreateTag(tag);
});
docArea?.addEventListener('change', () => {
  setTaxonomySelectOptions();
});

async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token && !headers.Authorization) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const request = async () => {
    const response = await fetch(path, { ...options, headers: { ...headers } });
    const data = await response.json().catch(() => ({}));
    return { response, data };
  };

  let { response, data } = await request();
  const shouldTryRefresh = (
    response.status === 401
    && isAccessControlEnabled()
    && Boolean(state.refreshToken)
    && !options.skipAuthRefresh
    && path !== '/api/v1/auth/login'
    && path !== '/api/v1/auth/refresh'
  );

  if (shouldTryRefresh) {
    try {
      await refreshAccessToken();
      headers.Authorization = `Bearer ${state.token}`;
      ({ response, data } = await request());
    } catch (error) {
      handleAuthenticationFailure(error.message || 'Sua sessão expirou. Faça login novamente.');
      const authError = new Error(error.message || 'Sua sessão expirou. Faça login novamente.');
      authError.status = 401;
      throw authError;
    }
  }

  if (!response.ok) {
    const message = data?.detail || `Erro ${response.status}`;
    if (
      response.status === 401
      && isAccessControlEnabled()
      && (path === '/api/v1/auth/refresh' || !state.refreshToken || options.skipAuthRefresh)
    ) {
      handleAuthenticationFailure(typeof message === 'string' ? message : 'Sua sessão expirou. Faça login novamente.');
    }
    const error = new Error(typeof message === 'string' ? message : JSON.stringify(message));
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

async function waitForUploadJobCompletion(jobId, onProgress = null) {
  const maxAttempts = 1800;
  const delayMs = 1000;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    let payload = null;
    try {
      payload = await apiFetch(`/api/v1/empresas/${state.companyId}/documentos/upload/${encodeURIComponent(jobId)}`);
    } catch (error) {
      const status = error?.status;
      if (status === 404 || status === 410 || (status >= 400 && status < 500)) {
        throw error;
      }
      if (attempt + 1 >= maxAttempts) {
        throw error;
      }
      if (onProgress) {
        const percent = Math.min(60 + Math.floor((attempt / maxAttempts) * 30), 90);
        onProgress(
          {
            status: 'aguardando',
            error: error?.message || String(error),
          },
          percent,
          attempt + 1,
        );
      }
      await new Promise((resolve) => window.setTimeout(resolve, delayMs));
      continue;
    }

    const status = (payload?.status || '').toLowerCase();

    if (onProgress) {
      const percent = Math.min(60 + Math.floor((attempt / maxAttempts) * 30), 90);
      onProgress(payload, percent, attempt + 1);
    }

    if (status === 'done' && payload?.documento) {
      return payload;
    }

    if (status === 'failed') {
      throw new Error(payload?.error || 'Falha no processamento do documento.');
    }

    if (attempt + 1 >= maxAttempts) {
      throw new Error('Tempo de processamento excedeu o limite. Tente novamente em alguns minutos.');
    }

    await new Promise((resolve) => window.setTimeout(resolve, delayMs));
  }

  throw new Error('Tempo de processamento excedeu o limite. Tente novamente em alguns minutos.');
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
      skipAuthRefresh: true,
    });

    persistAuthTokens(data.access_token, data.refresh_token);
    state.companyId = String(payload.company_id);
    localStorage.setItem('expai_company_id', state.companyId);
    sessionExpiredMessageShown = false;
    loginMsg.textContent = 'Login efetuado com sucesso.';
    loginMsg.className = 'helper success';
    await loadUserSession(true);
    if (state.profile) {
      setPanel(true);
    } else {
      persistAuthTokens('', '');
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
    setUserAdminMessage('');
    await loadUsersForCompany();
    resetUserAuditPagination();
    await loadUserAccessAudit();
    hideUserMenu();
  });
}

if (userAreaAccessMenuItem) {
  userAreaAccessMenuItem.addEventListener('click', async () => {
    if (!isAccessControlEnabled()) {
      showToast('Sessão de áreas desativada no modo sem autenticação.', 'error');
      hideUserMenu();
      return;
    }
    if (!isAdminProfile()) {
      showToast('Acesso restrito a administradores.', 'error');
      return;
    }
    await openAreaAccessSession();
  });
}

userAccessModalOverlay?.addEventListener('click', closeUserAccessModal);
userAccessModalCloseBtn?.addEventListener('click', closeUserAccessModal);
newUserRestrictionTrigger?.addEventListener('click', () => {
  if (!newUserRestrictionDropdown || newUserRestrictionTrigger.disabled) {
    return;
  }
  closeUserAccessRestrictionDropdown();
  const nextOpen = newUserRestrictionDropdown.classList.contains('hidden-view');
  newUserRestrictionDropdown.classList.toggle('hidden-view', !nextOpen);
  newUserRestrictionTrigger.setAttribute('aria-expanded', String(nextOpen));
});
newUserRestrictionDropdown?.addEventListener('change', () => {
  newUserAssignedRestrictionProfileIds = collectNewUserRestrictionProfileIds();
  updateNewUserRestrictionTriggerLabel();
});
userAccessModalRestrictionTrigger?.addEventListener('click', () => {
  if (!userAccessModalRestrictionDropdown) {
    return;
  }
  closeNewUserRestrictionDropdown();
  const nextOpen = userAccessModalRestrictionDropdown.classList.contains('hidden-view');
  userAccessModalRestrictionDropdown.classList.toggle('hidden-view', !nextOpen);
  userAccessModalRestrictionTrigger.setAttribute('aria-expanded', String(nextOpen));
});
userAccessModalRestrictionDropdown?.addEventListener('change', () => {
  selectedUserAccessRestrictionState.assignedProfileIds = collectUserAccessRestrictionProfileIds();
  updateUserAccessRestrictionTriggerLabel();
});
userAccessModalSave?.addEventListener('click', () => {
  void saveSelectedUserAccess();
});
userAccessModalRevoke?.addEventListener('click', () => {
  void revokeSelectedUserAccess();
});
userAccessModalOpenAreas?.addEventListener('click', () => {
  void openSelectedUserAreaRestrictions();
});
document.addEventListener('click', (event) => {
  if (
    newUserRestrictionDropdown
    && newUserRestrictionTrigger
    && !newUserRestrictionDropdown.classList.contains('hidden-view')
    && !newUserRestrictionDropdown.contains(event.target)
    && !newUserRestrictionTrigger.contains(event.target)
  ) {
    closeNewUserRestrictionDropdown();
  }
  if (
    userAccessModalRestrictionDropdown
    && userAccessModalRestrictionTrigger
    && !userAccessModalRestrictionDropdown.classList.contains('hidden-view')
    && !userAccessModalRestrictionDropdown.contains(event.target)
    && !userAccessModalRestrictionTrigger.contains(event.target)
  ) {
    closeUserAccessRestrictionDropdown();
  }
});

if (userAccessStatusFilter) {
  userAccessStatusFilter.addEventListener('change', () => {
    usersPagination.page = 1;
    renderUsersList(companyUsersCache);
  });
}

if (userAccessSearch) {
  userAccessSearch.addEventListener('input', () => {
    usersPagination.page = 1;
    renderUsersList(companyUsersCache);
  });
}

if (userAccessSort) {
  userAccessSort.addEventListener('change', () => {
    usersPagination.page = 1;
    renderUsersList(companyUsersCache);
});
}

areaAccessUserSelect?.addEventListener('change', () => {
  void loadSelectedUserAreaScope();
});

areaAccessMode?.addEventListener('change', () => {
  renderAreaAccessChecklist();
});

saveAreaAccessBtn?.addEventListener('click', () => {
  void saveAreaAccessScope();
});

forcePasswordSave?.addEventListener('click', () => {
  void submitForcedPasswordChange();
});

createAreaRestrictionProfileForm?.addEventListener('submit', (event) => {
  void createAreaRestrictionProfile(event);
});

areaAccessProfilesList?.addEventListener('click', (event) => {
  const removeButton = event.target.closest('.area-profile-remove');
  if (!removeButton) {
    return;
  }
  const profileId = Number(removeButton.dataset.profileId || 0);
  void deleteAreaRestrictionProfile(profileId);
});

userAuditExportButton?.addEventListener('click', () => {
  exportUserAuditCsv();
});

userAuditPrevButton?.addEventListener('click', () => {
  if (userAuditPagination.page <= 1) {
    return;
  }
  userAuditPagination.page -= 1;
  void loadUserAccessAudit();
});

userAuditNextButton?.addEventListener('click', () => {
  const totalPages = Math.max(1, Math.ceil(userAuditPagination.total / userAuditPagination.limit));
  if (userAuditPagination.page >= totalPages) {
    return;
  }
  userAuditPagination.page += 1;
  void loadUserAccessAudit();
});

usersPrevButton?.addEventListener('click', () => {
  if (usersPagination.page <= 1) {
    return;
  }
  usersPagination.page -= 1;
  renderUsersList(companyUsersCache);
});

usersNextButton?.addEventListener('click', () => {
  const totalPages = Math.max(1, Math.ceil(usersPagination.total / usersPagination.limit));
  if (usersPagination.page >= totalPages) {
    return;
  }
  usersPagination.page += 1;
  renderUsersList(companyUsersCache);
});

async function loadPublishedDocs() {
  const area = filterArea?.value || '';
  const categoria = filterCategoria?.value || '';
  const tag = document.getElementById('filterTag').value;
  const busca = document.getElementById('filterBusca').value;
  const sortBy = document.getElementById('sortDocs')?.value || 'created_desc';
  pagination.limit = 10;
  const clampedLimit = Math.max(1, Math.min(100, pagination.limit));
  const offset = (Math.max(1, pagination.page || 1) - 1) * clampedLimit;
  pagination.page = Math.max(1, pagination.page || 1);

  const query = new URLSearchParams();
  if (area) query.set('area', area);
  if (categoria) query.set('categoria', categoria);
  if (tag) query.set('tag', tag);
  if (busca) query.set('busca', busca);
  query.set('include_content', 'false');
  query.set('include_unpublished', 'true');
  query.set('limit', String(clampedLimit));
  query.set('offset', String(offset));
  query.set('sort', sortBy);
  const matchesDashboardFilters = (doc) => {
    const docArea = String(doc?.area || '').toLowerCase();
    const docCategoria = String(doc?.categoria || '').toLowerCase();
    const docTitle = String(doc?.title || doc?.titulo || doc?.file_name || doc?.slug || '').toLowerCase();
    const docError = String(doc?.error || '').toLowerCase();
    const rawTags = Array.isArray(doc?.tags) ? doc.tags : String(doc?.tags || '').split(',');
    const docTags = rawTags.map((item) => String(item || '').trim().toLowerCase()).filter(Boolean);
    const areaOk = !area || docArea === area.toLowerCase();
    const categoriaOk = !categoria || docCategoria === categoria.toLowerCase();
    const tagOk = !tag || docTags.some((item) => item.includes(tag.toLowerCase()));
    const docContent = String(doc?.content || '').toLowerCase();
    const buscaOk = !busca || docTitle.includes(busca.toLowerCase()) || docError.includes(busca.toLowerCase()) || docContent.includes(busca.toLowerCase());
    return areaOk && categoriaOk && tagOk && buscaOk;
  };

  try {
    const canLoadUploadQueue = canViewUploadQueue();
    const [data, processingData, failedData] = await Promise.all([
      apiFetch(`/api/v1/empresas/${state.companyId}/documentos?${query.toString()}`),
      canLoadUploadQueue
        ? apiFetch(`/api/v1/empresas/${state.companyId}/documentos/processando?status=processing`)
        : Promise.resolve({ documentos: [] }),
      canLoadUploadQueue
        ? apiFetch(`/api/v1/empresas/${state.companyId}/documentos/processando?status=failed`)
        : Promise.resolve({ documentos: [] }),
    ]);
    docsList.innerHTML = '';
    const processingDocs = (Array.isArray(processingData?.documentos) ? processingData.documentos : []).filter(matchesDashboardFilters);
    const failedDocs = (Array.isArray(failedData?.documentos) ? failedData.documentos : []).filter(matchesDashboardFilters);
    const listedDocs = Array.isArray(data?.documentos) ? data.documentos : [];
    state.pendingApprovalTotal = Number.isFinite(Number(data?.pending_total)) ? Number(data.pending_total) : 0;
    updateDashboardApprovalStatus();
    pagination.total = Number.isFinite(Number(data?.total)) ? Number(data.total) : listedDocs.length;
    const publishedOffset = Math.max(0, offset);
    const pageFromOffset = Math.floor(publishedOffset / clampedLimit) + 1;
    pagination.page = pageFromOffset;

    const allDocs = [
      ...processingDocs.map((doc) => ({ ...doc, _cardType: 'processing' })),
      ...failedDocs.map((doc) => ({ ...doc, _cardType: 'failed' })),
      ...listedDocs.map((doc) => ({ ...doc, _cardType: docIsPublished(doc) ? 'published' : 'draft' })),
    ];

    const totalDisplay = Number.isFinite(Number(pagination.total)) ? Number(pagination.total) : 0;
    const totalPages = Math.max(1, Math.ceil(totalDisplay / clampedLimit));
    if (pagination.page > totalPages) {
      pagination.page = totalPages;
      return loadPublishedDocs();
    }

    if (docsPrevButton) {
      docsPrevButton.disabled = pagination.page <= 1 || pagination.total <= 0;
    }
    if (docsNextButton) {
      docsNextButton.disabled = pagination.page >= totalPages || pagination.total <= 0;
    }

    const currentPage = Math.min(Math.max(1, pagination.page), totalPages);
    const start = totalDisplay > 0 ? (currentPage - 1) * clampedLimit + 1 : 0;
    const end = totalDisplay > 0 ? Math.min(currentPage * clampedLimit, totalDisplay) : 0;
    if (docsPagerInfo) {
      docsPagerInfo.textContent = `Página ${currentPage} de ${totalPages} — ${start} a ${end} de ${totalDisplay} documento(s)`;
    }

    if (!allDocs.length) {
      docsList.innerHTML = '<li>Nenhum documento encontrado para essa busca.</li>';
      return;
    }

    for (const doc of allDocs) {
      const normalizedTags = normalizeTagValues(doc?.tags);
      const tagChips = normalizedTags
        .slice(0, 4)
        .map((tagName) => `<span class="tag-chip">${tagName}</span>`)
        .join('');
      const tagsOverflow = normalizedTags.length > 4
        ? `<span class="tag-chip tag-chip--muted">+${normalizedTags.length - 4}</span>`
        : '';
      const validityBadge = doc?._cardType === 'published'
        ? buildValidityBadge(doc?.data_validade)
        : '';
      const draftBadge = doc?._cardType === 'draft'
        ? '<span class="status-tag status-tag-draft">Rascunho</span>'
        : '';
      const pendingBadge = isPendingApprovalVersion(doc)
        ? '<span class="status-tag status-tag-pending">Pendente aprovacao</span>'
        : '';
      const item = document.createElement('li');
      if (doc._cardType === 'processing') {
        item.className = 'doc-item doc-item-processing';
        item.innerHTML = `
          <div class="doc-item-body">
            <strong class="doc-title">${truncateForCard(doc?.title || doc?.file_name || doc?.slug || 'Documento')}</strong>
            <div class="meta doc-meta-tags">
              <span class="status-tag status-tag-neutral">${doc?.area || 'sem-area'}</span>
              <span class="status-tag status-tag-neutral">${doc?.categoria || 'sem-categoria'}</span>
              <span class="status-tag status-tag-processing">Processando</span>
              ${tagChips}${tagsOverflow}
            </div>
          </div>
          <span class="meta">${doc?.job_id || ''} · Início: ${doc?.created_at || ''}</span>
        `;
      } else if (doc._cardType === 'failed') {
        item.className = 'doc-item doc-item-failed';
        item.innerHTML = `
          <div class="doc-item-body">
            <strong class="doc-title">${truncateForCard(doc?.title || doc?.file_name || doc?.slug || 'Documento')}</strong>
            <div class="meta doc-meta-tags">
              <span class="status-tag status-tag-neutral">${doc?.area || 'sem-area'}</span>
              <span class="status-tag status-tag-neutral">${doc?.categoria || 'sem-categoria'}</span>
              ${tagChips}${tagsOverflow}
              <button type="button" class="status-tag status-tag-failed">Falha</button>
            </div>
          </div>
        `;
        const failedBadge = item.querySelector('.status-tag-failed');
        failedBadge?.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          openFailureDetailsModal(doc);
        });
      } else {
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
          <div class="doc-item-body">
            <strong class="doc-title">${truncateForCard(docTitleOf(doc) || doc.slug || 'Documento')}</strong>
            <div class="meta doc-meta-tags">
              <span class="status-tag status-tag-neutral">${doc?.area || 'sem-area'}</span>
              <span class="status-tag status-tag-neutral">${doc?.categoria || 'sem-categoria'}</span>
              ${validityBadge}
              ${draftBadge}
              ${pendingBadge}
              ${tagChips}${tagsOverflow}
            </div>
          </div>
          <span class="meta">v${docPublishedVersionOf(doc) || ''} · ${doc.updated_at || ''}</span>
        `;
      }
      const deleteWrap = document.createElement('div');
      deleteWrap.className = 'doc-card-actions';
      const editButton = document.createElement('button');
      editButton.type = 'button';
      editButton.className = 'doc-card-action';
      editButton.textContent = '✎';
      const editDisabled = doc._cardType !== 'published';
      editButton.disabled = editDisabled;
      if (editDisabled) {
        editButton.title = 'A edição está disponível apenas para documentos já publicados.';
      } else {
        editButton.title = 'Editar documento';
        editButton.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          openDocumentEditorFromCard(doc);
        });
      }
      deleteWrap.appendChild(editButton);
      const deleteButton = document.createElement('button');
      deleteButton.type = 'button';
      deleteButton.className = 'doc-card-action';
      deleteButton.textContent = '🗑';
      const deleteDisabled = doc._cardType === 'processing' || !doc?.slug || !canDeleteDocumentCard();
      deleteButton.disabled = deleteDisabled;
      if (doc._cardType === 'processing') {
        deleteButton.title = 'A exclusão não está disponível enquanto o documento estiver em processamento.';
      } else if (!doc?.slug) {
        deleteButton.title = 'Documento sem identificador para exclusão.';
      } else if (!canDeleteDocumentCard()) {
        deleteButton.title = 'Somente editores ou administradores podem excluir documentos.';
      } else {
        deleteButton.title = 'Excluir documento';
        deleteButton.addEventListener('click', async (event) => {
          event.preventDefault();
          event.stopPropagation();
          try {
            await handleDeleteDocument(doc);
          } catch (error) {
            showToast(error.message || 'Falha ao excluir documento.', 'error');
          }
        });
      }
      deleteWrap.appendChild(deleteButton);
      item.appendChild(deleteWrap);
      docsList.appendChild(item);
    }
  } catch (error) {
    state.pendingApprovalTotal = 0;
    updateDashboardApprovalStatus();
    docsList.innerHTML = `<li>${error.message}</li>`;
  }
}

function showDashboardCreateFlow() {
  if (!canCreateNewDocument()) {
    showToast('Somente editores ou administradores podem criar novos documentos.', 'error');
    showSession('dashboardSession');
    createSession?.classList.add('hidden-view');
    return;
  }
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
  const docAiPrompt = document.getElementById('docAiPrompt');
  const docValidity = document.getElementById('docValidity');
  const docContent = document.getElementById('docContent');
  const docPublish = document.getElementById('docPublish');
  const docFile = document.getElementById('docFile');

  if (docArea) docArea.value = '';
  if (docCategoria) docCategoria.value = '';
  if (docSlug) docSlug.value = '';
  if (docTitle) docTitle.value = '';
  if (docTags) setCreateSessionTags([]);
  if (docAiPrompt) docAiPrompt.value = '';
  if (docValidity) docValidity.value = '';
  if (docFile) docFile.value = '';
  if (docContent) docContent.value = '';
  if (docPublish) docPublish.checked = true;
  updatePublishControls();

  showInlineCreateSession(true);
  if (createSession) {
    createSession.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  showToast('Preencha os campos para publicar um novo documento.');
}

refreshDocsButton?.addEventListener('click', showDashboardCreateFlow);

document.getElementById('createDocForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const docSlug = document.getElementById('docSlug');
  const docTitle = document.getElementById('docTitle');
  const docTags = document.getElementById('docTags');
  const docPublish = document.getElementById('docPublish');
  const docFile = document.getElementById('docFile');
  const docContent = document.getElementById('docContent');
  const docAiPrompt = document.getElementById('docAiPrompt');
  const docValidity = document.getElementById('docValidity');

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
  const tags = collectCreateTags();
  const publicar = Boolean(docPublish?.checked);
  const normalizedArea = area || FALLBACK_AREA;
  const normalizedCategoria = categoria || FALLBACK_CATEGORIA;
  const baseVersion = normalizeVersion(selectedDocument?.version || selectedDocument?.published_version || selectedDocument?.versao_publicada || '');
  const aiPrompt = docAiPrompt?.value?.trim() || '';
  const dataValidade = (docValidity?.value || '').trim();

  if (docSlug && !docSlug.value.trim() && generatedSlug) {
    docSlug.value = generatedSlug;
  }

  const context = {
    document_uuid: selectedDocument?.document_uuid || editingDocumentContext?.document_uuid || null,
    area: normalizedArea,
    categoria: normalizedCategoria,
    slug,
    title,
    ai_prompt: aiPrompt,
    data_validade: dataValidade,
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
      if (context.document_uuid) {
        form.set('document_uuid', context.document_uuid);
      }
      if (slug) {
        form.set('slug', slug);
      }
      if (title) {
        form.set('title', title);
      }
      if (baseVersion) {
        form.set('base_version', baseVersion);
      }
      if (aiPrompt) {
        form.set('ai_prompt', aiPrompt);
      }
      form.set('data_validade', dataValidade);
      if (publicar) {
        form.set('publicar', 'true');
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

      if (data?.job_id) {
        createMsg.textContent = `Arquivo enviado. O documento será processado em segundo plano${publicar ? ' e publicado ao finalizar' : ''}.`;
        createMsg.className = 'helper success';
        showToast('Upload recebido. Acompanhe o status na página inicial.', 'success');
        showInlineCreateSession(false);
        showSession('dashboardSession');
        await loadPublishedDocs();
        hideImportProgress('Upload recebido.');
        return;
      }

      uploadedDoc = data?.documento || {};
      uploadedVersion = uploadedDoc?.version;
    } else {
      const payload = {
        document_uuid: context.document_uuid,
        area: normalizedArea,
        categoria: normalizedCategoria,
        slug: slug || null,
        title,
        content,
        tags,
        ai_prompt: aiPrompt,
        data_validade: dataValidade,
        ...(baseVersion ? { base_version: baseVersion } : {}),
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
    const resolvedDocumentUuid = uploadedDoc?.document_uuid || context.document_uuid || null;
    context.document_uuid = resolvedDocumentUuid;
    context.area = resolvedArea;
    context.categoria = resolvedCategoria;
    context.slug = resolvedSlug;
    if (resolvedDocumentUuid) {
      selectedDocument = { ...(selectedDocument || {}), ...uploadedDoc, document_uuid: resolvedDocumentUuid };
    }
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
        (
          (editingDocumentContext.document_uuid && context.document_uuid && editingDocumentContext.document_uuid === context.document_uuid)
          || (
            editingDocumentContext.area === context.area &&
            editingDocumentContext.categoria === context.categoria &&
            editingDocumentContext.slug === context.slug
          )
        )) {
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
    const area = categoriaAreaSelect?.value || '';
    if (!value.trim()) {
      renderTaxonomyError('Informe o nome da categoria.');
      return;
    }
    if (!area) {
      renderTaxonomyError('Selecione a área da categoria.');
      return;
    }
    try {
      await apiFetch(`/api/v1/empresas/${state.companyId}/categorias`, {
        method: 'POST',
        body: JSON.stringify({ name: value.trim(), area }),
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
      setUserAdminMessage('Usuário anônimo não pode criar usuários nesse modo.', 'error');
      return;
    }
    if (!isAdminProfile()) {
      setUserAdminMessage('Apenas administradores podem cadastrar usuários.', 'error');
      return;
    }

    const full_name = newUserName?.value?.trim() || '';
    const email = newUserEmail?.value?.trim() || '';
    const password = newUserPassword?.value || '';
    const role = newUserRole?.value || '';
    const profile_ids = collectNewUserRestrictionProfileIds();

    if (!full_name || !email || !role) {
      setUserAdminMessage('Preencha nome, e-mail e perfil.', 'error');
      return;
    }

    if (!state.companyId) {
      setUserAdminMessage('Empresa não identificada.', 'error');
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
          profile_ids,
        }),
      });
      if (newUserName) newUserName.value = '';
      if (newUserEmail) newUserEmail.value = '';
      if (newUserPassword) newUserPassword.value = '';
      if (newUserRole) newUserRole.value = '';
      newUserAssignedRestrictionProfileIds = [];
      closeNewUserRestrictionDropdown();
      renderNewUserRestrictionDropdown();
      setUserAdminMessage('Usuário criado ou vinculado com sucesso.', 'success');
      await loadUsersForCompany();
      resetUserAuditPagination();
      await loadUserAccessAudit();
    } catch (error) {
      setUserAdminMessage(error.message, 'error');
    }
  });
}

if (usersList) {
  usersList.addEventListener('click', async (event) => {
    const card = event.target.closest('.user-access-list-item');
    if (!card) {
      return;
    }
    await openUserAccessModal(card.dataset.userId);
  });
}

if (areasList) {
  areasList.addEventListener('click', async (event) => {
    const button = event.target.closest('.taxonomy-remove');
    if (!button) {
      const areaItem = event.target.closest('.taxonomy-item[data-kind="areas"]');
      if (!areaItem) {
        return;
      }
      const name = areaItem.dataset.name;
      if (!name) return;
      selectedTaxonomyArea = (selectedTaxonomyArea === name ? '' : name);
      if (categoriaAreaSelect) {
        setFormSelectValue(categoriaAreaSelect, selectedTaxonomyArea);
        if (selectedTaxonomyArea) {
          categoriaAreaSelect.value = selectedTaxonomyArea;
        }
      }
      if (categoriaAreaSelect && categoriaAreaSelect.value !== selectedTaxonomyArea) {
        categoriaAreaSelect.value = selectedTaxonomyArea;
      }
      renderTaxonomies();
      return;
    }
    const name = button.dataset.name;
    if (!name) return;
    try {
      await apiFetch(`/api/v1/empresas/${state.companyId}/areas?name=${encodeURIComponent(name)}`, {
        method: 'DELETE',
      });
      if (selectedTaxonomyArea === name) {
        selectedTaxonomyArea = '';
      }
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
    const area = button.dataset.area || '';
    const query = new URLSearchParams();
    if (area) {
      query.set('area', area);
    }
    try {
      await apiFetch(`/api/v1/empresas/${state.companyId}/categorias?${query.toString() ? `${query.toString()}&` : ''}name=${encodeURIComponent(name)}`, {
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

function resetPaginationAndLoadPublishedDocs() {
  pagination.page = 1;
  void loadPublishedDocs();
}

filterArea?.addEventListener('change', () => {
  updateFilterCategoriaOptions();
  resetPaginationAndLoadPublishedDocs();
});
filterCategoria?.addEventListener('change', resetPaginationAndLoadPublishedDocs);
document.getElementById('filterTag').addEventListener('change', resetPaginationAndLoadPublishedDocs);
document.getElementById('filterBusca').addEventListener('input', () => {
  pagination.page = 1;
  window.clearTimeout(docsSearchDebounceTimer);
  docsSearchDebounceTimer = window.setTimeout(() => {
    void loadPublishedDocs();
  }, 250);
});
document.getElementById('sortDocs').addEventListener('change', resetPaginationAndLoadPublishedDocs);
docsPrevButton?.addEventListener('click', () => {
  if (pagination.page <= 1) {
    return;
  }
  pagination.page -= 1;
  void loadPublishedDocs();
});
docsNextButton?.addEventListener('click', () => {
  const totalPages = Math.max(1, Math.ceil((pagination.total || 0) / pagination.limit));
  if (pagination.page >= totalPages) {
    return;
  }
  pagination.page += 1;
  void loadPublishedDocs();
});

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
