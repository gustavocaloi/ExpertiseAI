/* Isolated backup UI checks. All APIs are mocked; no platform data is modified. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  let admin = true, exportFailure = false, restoreFailure = true, restoreCalls = 0;
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const send = (data, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    if (path.endsWith('/auth/login')) return send({ access_token: 'fixture-token', refresh_token: 'fixture-refresh' });
    if (path.endsWith('/config')) return send({ access_control_enabled: true, default_company_id: 1, default_company_name: 'Teste' });
    if (path.endsWith('/auth/me')) return send({ user_id: 1, full_name: 'Admin Teste', email: 'admin@example.test', company_id: 1, company_name: 'Teste', role: admin ? 'admin' : 'editor', roles: [admin ? 'admin' : 'editor'], modules: ['conteudo'], can_manage_backup: admin });
    if (path.endsWith('/backup/status')) return send({ max_bytes: 512 * 1024 * 1024 });
    if (path.endsWith('/backup/export')) return exportFailure ? send({ detail: 'Há operações em andamento. Aguarde e tente novamente.' }, 409) : send({ format: 'expertise-ai-platform-backup', version: 1 });
    if (path.endsWith('/backup/restore')) {
      restoreCalls++;
      assert(route.request().postData().includes('RESTAURAR'));
      return restoreFailure ? send({ detail: 'Arquivo JSON inválido ou corrompido.' }, 422) : send({ status: 'restored', login_required: true });
    }
    if (path.endsWith('/documentos')) return send({ documentos: [], total: 0, pending_total: 0 });
    if (path.endsWith('/documentos/processando')) return send({ documentos: [] });
    if (path.endsWith('/kb-status')) return send({ index_ready: true });
    return send({ items: [] });
  });
  const login = async () => {
    await page.locator('#email').fill('admin@example.test');
    await page.locator('#password').fill('secret');
    await page.locator('#loginForm button[type=submit]').click();
    await page.locator('#dashboardPanel.active').waitFor();
  };
  await page.goto(process.env.FRONTEND_URL || 'http://127.0.0.1:8766/static/index.html');
  await login();
  await page.locator('#userMenuBtn').click();
  await page.locator('#backupMenuItem').click();
  await page.locator('#backupExportBtn:not([disabled])').waitFor();
  assert(await page.locator('#backupSession').evaluate(el => el.classList.contains('active-session')));
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#backupExportBtn').click()]);
  assert(download.suggestedFilename().endsWith('.json'));
  await page.locator('#backupExportBtn:not([disabled])').waitFor();
  exportFailure = true;
  await page.locator('#backupExportBtn').click();
  await page.waitForFunction(() => document.querySelector('#backupStatus').textContent.includes('operações em andamento'));
  await page.locator('#backupFile').setInputFiles({ name: 'backup.json', mimeType: 'application/json', buffer: Buffer.from('{}') });
  await page.locator('#backupConfirmation').fill('errado');
  await page.locator('#backupRestoreBtn').click();
  assert.equal(restoreCalls, 0);
  await page.locator('#backupConfirmation').fill('RESTAURAR');
  await page.locator('#backupRestoreBtn').click();
  await page.waitForFunction(() => document.querySelector('#backupStatus').textContent.includes('corrompido'));
  assert.equal(restoreCalls, 1);
  assert.equal(await page.locator('#backupFile').evaluate(el => el.files.length), 1);
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}`);
  }
  await page.screenshot({ path: '/tmp/expertise-backup-ui/backup-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 900 });
  await page.screenshot({ path: '/tmp/expertise-backup-ui/backup-mobile.png', fullPage: true });
  restoreFailure = false;
  await page.locator('#backupRestoreBtn').click();
  await page.locator('#loginPanel.active').waitFor();
  assert((await page.locator('#loginMsg').textContent()).includes('Restauração concluída'));
  assert.equal(await page.evaluate(() => localStorage.getItem('expai_token')), null);
  admin = false;
  await login();
  await page.locator('#userMenuBtn').click();
  assert(!(await page.locator('#backupMenuItem').isVisible()));
  assert.deepEqual(errors, []);
  await browser.close();
  console.log('Backup UI: download, errors, confirmation, restore, logout, permissions and responsive layout passed.');
})().catch(error => { console.error(error); process.exit(1); });
