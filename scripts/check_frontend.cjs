/* Frontend regression checks. API fixtures are intercepted; no real writes occur.
 * Requires Playwright. Run against a static server rooted in app/:
 * FRONTEND_URL=http://127.0.0.1:8765/static/index.html node scripts/check_frontend.cjs
 * Optional: UI_SCREENSHOTS=/tmp/expertise-ui for visual review artifacts.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const url = process.env.FRONTEND_URL || 'http://127.0.0.1:8765/static/index.html';
const output = process.env.UI_SCREENSHOTS;
if (output) fs.mkdirSync(output, { recursive: true });
const titles = ['Guia de integração de novos colaboradores', 'Política de segurança da informação', 'Manual de atendimento ao cliente', 'Processo de aprovação de despesas', 'Boas práticas de documentação', 'Plano de continuidade operacional', 'Checklist de fechamento mensal', 'Padrões de qualidade', 'Guia de fornecedores', 'Procedimentos de suporte', 'Plano de treinamento', 'Processo de compras'];
const documents = titles.map((title, i) => ({
  title, slug: `documento-${i}`, document_uuid: `fixture-${i}`, area: i % 2 ? 'Operações' : 'Pessoas',
  categoria: i % 2 ? 'Processos' : 'Integração', tags: ['essencial', 'equipe'],
  published: i !== 3, published_version: i !== 3 ? '1.0' : '', version: '1.0',
  pending_approval: i === 3, updated_at: '2026-10-20T10:00:00',
}));

(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const errors = [];
  const unknown = [];
  const mutations = [];
  let role = 'admin', failure = false, queue = false, maintenance = false, noDocuments = false;
  page.on('pageerror', (e) => errors.push(e.message));
  await context.route('**/api/**', async (route) => {
    const req = route.request();
    const parsed = new URL(req.url());
    const pathname = parsed.pathname;
    const q = parsed.searchParams;
    const send = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    if (req.method() !== 'GET') {
      mutations.push({ pathname, method: req.method() });
      if (pathname.endsWith('/auth/login')) return send({ access_token: 'fixture-token', refresh_token: 'fixture-refresh' });
      return send({ version: '1.0', published: false, slug: 'novo-documento', area: 'Pessoas', categoria: 'Integração' });
    }
    if (pathname.endsWith('/config')) return send({ access_control_enabled: true, default_company_name: 'Equipe Expertise', default_company_id: 1 });
    if (pathname.endsWith('/auth/me')) return send({ id: 1, full_name: 'Marina Costa', email: 'marina@example.test', company_id: 1, company_name: 'Equipe Expertise', role, roles: [role], modules: ['conteudo'] });
    if (pathname.endsWith('/areas')) return send({ items: ['Pessoas', 'Operações'] });
    if (pathname.endsWith('/categorias')) return send({ items: [{ name: 'Integração', area: 'Pessoas' }, { name: 'Processos', area: 'Operações' }] });
    if (pathname.endsWith('/kb-status')) return send(maintenance ? { running: true, phase: 'rebuilding_index', total: 12, indexed: 0, processed: 2 } : { index_ready: true });
    if (pathname.endsWith('/documentos/processando')) return send({ documentos: queue ? [{ title: q.get('status') === 'failed' ? 'Arquivo com falha na importação' : 'Documento em processamento', slug: 'importacao', area: 'Pessoas', categoria: 'Integração', created_at: '2026-10-20', error: 'Falha simulada na conversão', job_id: 'fixture-job' }] : [] });
    if (pathname.endsWith('/documentos')) {
      if (failure) return send({ detail: 'Falha de conexão simulada.' }, 503);
      let list = noDocuments ? [] : documents.filter((d) => (!q.get('busca') || d.title.toLowerCase().includes(q.get('busca').toLowerCase())) && (!q.get('area') || d.area === q.get('area')) && (!q.get('categoria') || d.categoria === q.get('categoria')) && (!q.get('tag') || d.tags.includes(q.get('tag'))));
      if (q.get('busca') === 'Guia') await new Promise((r) => setTimeout(r, 450));
      if (maintenance) await new Promise((r) => setTimeout(r, 400));
      return send({ documentos: list.slice(Number(q.get('offset')), Number(q.get('offset')) + Number(q.get('limit'))), total: list.length, pending_total: list.filter((d) => d.pending_approval).length });
    }
    if (pathname.endsWith('/conteudo')) return send({ ...documents[0], content: '# Guia de integração\n\nConheça os processos, as pessoas e as ferramentas da equipe.\n\n' + 'Conteúdo de exemplo para testar a leitura.\n'.repeat(12) });
    if (/\/documentos\/[^/]+\/[^/]+\/[^/]+$/.test(pathname)) return send({ ...documents[0], versions: [{ version: '1.0', published: true, created_at: '2026-10-20' }] });
    if (pathname.endsWith('/usuarios')) return send([{ id: 1, full_name: 'Marina Costa', email: 'marina@example.test', role: 'admin', roles: ['admin'], active: true }]);
    if (pathname.endsWith('/usuarios/auditoria')) return send({ items: [], total: 0 });
    if (pathname.endsWith('/perfis-restricao-areas')) return send({ items: [] });
    if (pathname.endsWith('/areas-acesso')) return send({ mode: 'all', areas: [], available_areas: ['Pessoas', 'Operações'], profiles: [] });
    unknown.push(pathname);
    return send({});
  });
  const screenshot = async (name) => {
    if (output) await page.screenshot({ path: path.join(output, name + '.png'), fullPage: !(await page.locator('.doc-modal.open').count()) });
    if (process.env.UI_A11Y === '1') {
      const { default: AxeBuilder } = require('@axe-core/playwright');
      const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
      assert.deepEqual(result.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => ({ target: n.target, summary: n.failureSummary })) })), [], `Accessibility: ${name}`);
    }
  };
  const settle = () => page.waitForFunction(() => document.querySelector('#docsList').getAttribute('aria-busy') === 'false');
  const noOverflow = async (label) => {
    const dimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: innerWidth }));
    assert(dimensions.scroll <= dimensions.viewport + 1, `${label}: horizontal overflow ${JSON.stringify(dimensions)}`);
  };
  const gotoHome = async () => { await page.locator('.menu-item[data-session="dashboardSession"]').click(); await settle(); };
  const openMenu = async (id) => { await page.locator('#userMenuBtn').click(); await page.locator(id).click(); };
  try {
    await page.goto(url);
    await page.locator('#loginPanel.active').waitFor();
    await screenshot('login-desktop');
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await noOverflow(`login ${width}`);
      if (width === 390) await screenshot('login-mobile');
    }
    await page.locator('#email').fill('marina@example.test');
    await page.locator('#password').fill('fixture-password');
    await page.locator('#loginForm button[type="submit"]').click();
    await page.locator('#dashboardPanel.active').waitFor();
    await settle();
    assert.equal(await page.locator('#docsList .doc-item').count(), 10);
    assert.equal(await page.locator('#docsCount').textContent(), '12');
    await screenshot('library-desktop');
    await page.locator('#docsNext').click(); await settle();
    assert.equal(await page.locator('#docsList .doc-item').count(), 2);
    await page.locator('#docsPrev').click(); await settle();
    await page.locator('#filterBusca').fill('sem resultado');
    await page.getByText('Nenhum documento encontrado', { exact: true }).waitFor();
    await page.locator('#clearDocFilters').click(); await settle();
    assert.equal(await page.locator('#docsList .doc-item').count(), 10);
    await page.locator('#filterArea').selectOption('Pessoas'); await settle();
    assert.equal(await page.locator('#docsCount').textContent(), '6');
    await page.locator('#clearDocFilters').click(); await settle();
    // Search races must not replace a newer result with an older response.
    await page.locator('#filterBusca').fill('Guia');
    await page.waitForRequest((r) => new URL(r.url()).searchParams.get('busca') === 'Guia');
    await page.locator('#filterBusca').fill('Política');
    await page.waitForResponse((r) => new URL(r.url()).searchParams.get('busca') === 'Política');
    await settle();
    await page.waitForResponse((r) => new URL(r.url()).searchParams.get('busca') === 'Guia');
    assert.equal(await page.locator('#docsCount').textContent(), '1');
    assert.match(await page.locator('.doc-open').textContent(), /Política/);
    await page.locator('#clearDocFilters').click(); await settle();
    // Keyboard document opening, modal focus containment and focus restoration.
    await page.locator('.doc-open').first().focus(); await page.keyboard.press('Enter');
    await page.locator('#docViewerModal.open').waitFor();
    await screenshot('document-desktop');
    await page.locator('#docModalCloseBtn').focus(); await page.keyboard.press('Shift+Tab');
    assert(await page.evaluate(() => document.querySelector('#docViewerModal').contains(document.activeElement)));
    await page.keyboard.press('Escape');
    assert(await page.locator('.doc-open').first().evaluate((el) => el === document.activeElement));
    // Menu can close on the second tap/click and works with arrow keys.
    await page.locator('#userMenuBtn').click(); await page.locator('#userMenuDropdown.is-open').waitFor();
    await page.locator('#userMenuBtn').click();
    assert.equal(await page.locator('#userMenuBtn').getAttribute('aria-expanded'), 'false');
    await page.locator('#userMenuBtn').focus(); await page.keyboard.press('ArrowDown');
    assert.equal(await page.locator('#userProfileMenuItem').evaluate((el) => el === document.activeElement), true);
    await page.keyboard.press('Escape');
    await page.locator('#refreshDocs').click();
    await page.locator('#docTitle').fill('Novo documento');
    await page.locator('#docContent').fill('# Teste de interface');
    await screenshot('editor-desktop');
    await page.locator('#cancelDocument').click();
    assert(await page.locator('#dashboardSession').evaluate((el) => el.classList.contains('active-session')));
    // Responsive navigation through every primary screen.
    for (const width of [320, 390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await gotoHome(); await noOverflow(`library ${width}`);
      if (width === 390) await screenshot('library-mobile');
      await page.locator('#refreshDocs').click(); await noOverflow(`editor ${width}`);
      if (width === 390) await screenshot('editor-mobile');
      await page.locator('#backToDocuments').click();
      await page.locator('[data-session="taxonomySession"]').click(); await noOverflow(`structure ${width}`);
      if (width === 390 || width === 1440) await screenshot(`structure-${width}`);
      await openMenu('#userAdminMenuItem'); await page.locator('#usersList .user-access-list-item').waitFor();
      await noOverflow(`users ${width}`);
      await page.locator('#usersList .user-access-list-item').click();
      await page.locator('#userAccessModal.open').waitFor(); await noOverflow(`user modal ${width}`);
      assert(await page.locator('#userAccessModalSave').isVisible());
      if (width === 390) await screenshot('user-modal-mobile');
      await page.keyboard.press('Escape');
      await openMenu('#userAreaAccessMenuItem'); await noOverflow(`access ${width}`);
      await openMenu('#userProfileMenuItem'); await noOverflow(`profile ${width}`);
    }
    failure = true; await gotoHome();
    await page.getByText('Não foi possível carregar os documentos', { exact: true }).waitFor();
    assert(await page.locator('#docsNext').isDisabled());
    failure = false; await page.getByRole('button', { name: 'Tentar novamente', exact: true }).click(); await settle();
    queue = true; await gotoHome();
    assert.equal(await page.locator('.doc-item-processing').count(), 1);
    await page.locator('button.status-tag-failed').click(); await page.locator('#docViewerModal.open').waitFor();
    await page.keyboard.press('Escape');
    queue = false; noDocuments = true; maintenance = true;
    await page.locator('.menu-item[data-session="dashboardSession"]').click();
    await page.waitForFunction(() => document.querySelector('#docsPagerInfo')?.textContent === 'Atualizando documentos... 2 de 12');
    await settle();
    assert(await page.locator('#kbStatusAlert').isVisible());
    await page.getByText('Preparando sua biblioteca', { exact: true }).waitFor();
    maintenance = false; await gotoHome();
    await page.getByText('Seu conhecimento começa aqui', { exact: true }).waitFor();
    noDocuments = false;
    for (role of ['aprovador', 'editor']) {
      await page.reload(); await settle();
      assert.equal(await page.locator('#refreshDocs').isDisabled(), role === 'aprovador');
      await page.locator('#userMenuBtn').click();
      assert.equal(await page.locator('#userAdminMenuItem').isVisible(), false);
      await page.keyboard.press('Escape');
    }
    assert.deepEqual(errors, [], 'Browser runtime errors');
    assert.deepEqual(unknown, [], 'Unexpected API fixtures');
    assert.deepEqual(mutations, [{ pathname: '/api/v1/auth/login', method: 'POST' }], 'No unintended document/user writes');
    console.log('PASS: login, pagination, search race, filters/reset, keyboard/modal focus, menu, editor return, responsive primary screens (320–1440px), error/retry, import states, maintenance/empty states, approver/editor permissions. No runtime errors or unintended writes.');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
