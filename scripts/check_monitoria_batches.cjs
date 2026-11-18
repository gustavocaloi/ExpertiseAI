/* Run after check_monitoria.cjs against the same isolated server. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  try {
    await page.goto(process.env.MONITORIA_TEST_URL || 'http://127.0.0.1:8766/');
    await page.locator('#email').fill('admin@expertise.ai.local');
    await page.locator('#password').fill(process.env.MONITORIA_TEST_PASSWORD || 'MonitoriaQA@123');
    await page.locator('#loginForm button[type="submit"]').click();
    await page.locator('#dashboardPanel.active').waitFor();
    await page.locator('#docsList[aria-busy="false"]').waitFor();
    await page.locator('[data-session="monitoriaSession"]').click();
    await page.locator('[data-monitoria-tab="upload"]').click();
    const files = ['primeiro.wav', 'segundo.wav', 'vazio.wav', 'remover.wav'].map((name) => ({ name, mimeType: 'audio/wav', buffer: name === 'vazio.wav' ? Buffer.alloc(0) : Buffer.from('RIFF....WAVE') }));
    await page.locator('#monitoriaAudioFile').setInputFiles(files);
    assert.equal(await page.locator('.monitoria-batch-file').count(), 4);
    await page.locator('[data-remove-file]').last().click();
    assert.equal(await page.locator('.monitoria-batch-file').count(), 3);
    await page.locator('.monitoria-upload-defaults summary').click();
    await page.locator('#monitoriaCliente').fill('Cliente padrão');
    await page.locator('.monitoria-batch-file').nth(0).locator('[data-batch-field="ticket_id"]').fill('LOTE-1');
    await page.locator('.monitoria-batch-file').nth(1).locator('[data-batch-field="ticket_id"]').fill('LOTE-2');
    await page.locator('.monitoria-batch-file').nth(1).locator('[data-batch-field="cliente"]').fill('Cliente específico');
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Draft overflow at ${width}`);
    }
    const received = page.waitForResponse((r) => r.url().includes('/conversas/upload-lote') && r.request().method() === 'POST');
    await page.locator('#monitoriaUploadForm button[type="submit"]').click();
    const response = await received;
    assert.equal(response.status(), 202);
    const batch = await response.json();
    assert.equal(batch.total, 3);
    assert.equal(batch.counts.rejected, 1);
    assert.match(await page.locator('#monitoriaUploadMsg').textContent(), /Lote recebido/);
    await page.waitForFunction(() => document.querySelector('#monitoriaBatchStatus').textContent.includes('3/3 finalizados'));
    assert.match(await page.locator('#monitoriaBatchResults').textContent(), /Cliente padrão/);
    assert.match(await page.locator('#monitoriaBatchResults').textContent(), /Cliente específico/);
    assert.match(await page.locator('#monitoriaBatchResults').textContent(), /Arquivo vazio/);
    assert.equal(await page.locator('#monitoriaBatchResults [data-batch-conversation]').count(), 2);
    // Recover persisted batch history after a full browser refresh.
    await page.reload();
    await page.locator('#dashboardPanel.active').waitFor();
    await page.locator('[data-session="monitoriaSession"]').click();
    await page.locator('[data-monitoria-tab="upload"]').click();
    await page.waitForFunction((id) => document.querySelector('#monitoriaBatchSelect').value === id, batch.batch_id);
    await page.waitForFunction(() => document.querySelectorAll('#monitoriaBatchResults li').length === 3);
    require('node:fs').mkdirSync('/tmp/expertise-monitoria-screens', { recursive: true });
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Results overflow at ${width}`);
      if ([390, 1440].includes(width)) await page.screenshot({ path: `/tmp/expertise-monitoria-screens/lotes-${width}.png`, fullPage: true });
    }
    await page.locator('#monitoriaBatchResults [data-batch-conversation]').nth(1).click();
    await page.waitForFunction(() => document.querySelector('#monitoriaDetailTitle').textContent === 'LOTE-2');
    assert.equal(await page.locator('#monitoriaChat .monitoria-bubble').count(), 8);
    assert.deepEqual(errors, []);
    console.log('PASS: multi-select, remove, shared/per-file metadata, asynchronous partial results, reload recovery, conversation navigation, 320–1440px; no JS errors.');
  } finally { await browser.close(); }
})().catch((e) => { console.error(e); process.exitCode = 1; });
