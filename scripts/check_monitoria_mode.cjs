/* UI flag checks against an isolated server; creates demo data and changes AI settings.
 * MONITORIA_EXPECT_REAL=true|false must match the server environment flag.
 */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
(async () => {
  const real = process.env.MONITORIA_EXPECT_REAL === 'true';
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  try {
    await page.goto(process.env.MONITORIA_TEST_URL || 'http://127.0.0.1:8766/');
    await page.locator('#email').fill('admin@expertise.ai.local');
    await page.locator('#password').fill(process.env.MONITORIA_TEST_PASSWORD || 'Admin@123');
    await page.locator('#loginForm button[type="submit"]').click();
    await page.locator('#dashboardPanel.active').waitFor();
    await page.locator('#docsList[aria-busy="false"]').waitFor();
    if (await page.locator('#forcePasswordModal.open').count()) {
      await page.locator('#forcePasswordNew').fill('MonitoriaQA@123');
      await page.locator('#forcePasswordConfirm').fill('MonitoriaQA@123');
      await page.locator('#forcePasswordSave').click();
      await page.locator('#forcePasswordModal.open').waitFor({ state: 'hidden' });
    }
    await page.locator('[data-session="monitoriaSession"]').click();
    await page.locator('#monitoriaCreateDemoBtn:visible').waitFor();
    assert.match(await page.locator('#monitoriaModeLabel').textContent(), real ? /Modo IA real/ : /Modo simulado/);
    await page.locator('[data-monitoria-tab="config"]').click();
    assert.equal(await page.locator('#monitoriaProvider').isEnabled(), real);
    if (real) {
      await page.locator('#monitoriaProvider').selectOption('openai');
      await page.locator('#monitoriaSettingsForm button[type="submit"]').click();
      await page.waitForFunction(() => document.querySelector('#monitoriaRuntimeStatus').textContent.includes("'openai' ainda não implementado"));
      assert.match(await page.locator('#monitoriaModeDescription').textContent(), /não implementado/);
    } else {
      assert.match(await page.locator('#monitoriaRuntimeStatus').textContent(), /Provedor efetivo: mock/);
    }
    await page.locator('#monitoriaCreateDemoBtn').click();
    await page.locator('#monitoriaTelemetryList .monitoria-track-canvas').waitFor();
    assert.match(await page.locator('#monitoriaDetailStatus').textContent(), /Simulação/);
    if (real) {
      await page.locator('[data-monitoria-tab="upload"]').click();
      await page.locator('#monitoriaAudioFile').setInputFiles({ name: 'test.wav', mimeType: 'audio/wav', buffer: Buffer.from('RIFF....WAVE') });
      const response = page.waitForResponse((r) => r.url().includes('/conversas/upload'));
      await page.locator('#monitoriaUploadForm button[type="submit"]').click();
      assert.equal((await response).status(), 409);
      await page.waitForFunction(() => document.querySelector('#monitoriaMsg').textContent.includes('não implementado'));
    }
    await page.locator('[data-monitoria-tab="config"]').click();
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Overflow at ${width}`);
    }
    assert.deepEqual(errors, []);
    console.log(`PASS: server flag ${real}, mode indicator, provider controls, demo mock, real upload blocking, responsive settings; no JS errors.`);
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
