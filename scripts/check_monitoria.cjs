/* Integration smoke test: run ONLY against an isolated test database.
 * Example server: EXPAI_DATA_DIR=/tmp/monitoria-qa EXPAI_MCP_ENABLED=false
 * EXPAI_DOCLING_ENABLED=false EXPAI_DOCLING_PREFETCH_MODELS=false
 * .venv/bin/python -m uvicorn app.main:app --port 8766
 * This script creates demo conversations and a pillar in that database.
 */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce' });
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
    await page.locator('#monitoriaCreateDemoBtn').click();
    await page.locator('#monitoriaTelemetryList .monitoria-track-canvas').waitFor();
    assert.equal(await page.locator('#monitoriaChat .monitoria-bubble').count(), 8);
    assert.equal(await page.locator('#monitoriaTelemetryList .monitoria-pillar-track').count(), 4);
    await page.locator('#monitoriaTelemetryList [data-turn="1"][data-pillar]').first().click();
    assert.equal(await page.locator('#monitoriaChat .is-highlighted').count(), 1);
    assert.match(await page.locator('#monitoriaEvidence').textContent(), /simulação/);
    await page.locator('#monitoriaLoadAudio').click();
    await page.waitForFunction(() => document.querySelector('#monitoriaAudio').readyState > 0);
    assert.equal(await page.locator('#monitoriaAudio').evaluate((a) => a.duration), 40);
    // Proportional segments: the 4-second first turn is 80% of the 5-second second turn.
    const widths = await page.locator('.monitoria-pillar-track').first().locator('button').evaluateAll((buttons) => buttons.slice(0, 2).map((b) => b.getBoundingClientRect().width));
    assert(Math.abs(widths[0] / widths[1] - 0.8) < 0.03, 'Time spans must be proportional');
    await page.locator('#monitoriaPlayPause').click();
    await page.waitForFunction(() => !document.querySelector('#monitoriaAudio').paused && document.querySelector('#monitoriaAudio').currentTime > 4.1);
    await page.locator('#monitoriaSpeed').selectOption('1.5');
    assert.equal(await page.locator('#monitoriaAudio').evaluate((a) => a.playbackRate), 1.5);
    await page.locator('#monitoriaAudio').evaluate((a) => { a.currentTime = 16; });
    await page.waitForFunction(() => document.querySelector('#monitoriaChat [data-turn="3"]').classList.contains('is-highlighted'));
    assert.match(await page.locator('#monitoriaPlaybackTime').textContent(), /00:16/);
    assert.match(await page.locator('#monitoriaTelemetryList').getAttribute('style'), /--play-position/);
    await page.locator('#monitoriaPlayPause').click();
    await page.locator('#monitoriaSeek').focus();
    await page.keyboard.press('Home');
    await page.waitForFunction(() => document.querySelector('#monitoriaAudio').currentTime < 0.5);
    await page.locator('#monitoriaChat [data-turn="5"]').click();
    await page.waitForFunction(() => Math.abs(document.querySelector('#monitoriaAudio').currentTime - 24) < 0.5);
    await page.locator('#monitoriaRewind').click();
    assert.equal(Math.floor(await page.locator('#monitoriaAudio').evaluate((a) => a.currentTime)), 14);
    const canvasWidth = await page.locator('.monitoria-track-canvas').evaluate((el) => el.getBoundingClientRect().width);
    await page.locator('#monitoriaZoom').selectOption('2');
    assert(await page.locator('.monitoria-track-canvas').evaluate((el) => el.getBoundingClientRect().width) > canvasWidth);
    await page.locator('#monitoriaZoom').selectOption('1');
    await page.locator('#monitoriaFiltersPanel > summary').click();
    await page.locator('#monitoriaFilterTipo').fill('Suporte');
    await page.waitForFunction(() => document.querySelector('#monitoriaPagerInfo').textContent.includes('1 conversas'));
    assert.equal(await page.locator('.monitoria-conversation').count(), 1);
    assert.equal(await page.locator('#monitoriaDetailContent').isVisible(), false);
    await page.locator('#monitoriaClearFilters').click();
    await page.waitForFunction(() => document.querySelector('#monitoriaPagerInfo').textContent.includes('3 conversas'));
    await page.locator('.monitoria-conversation').first().click();
    await page.locator('#monitoriaDetailContent:visible').waitFor();
    // An updated rubric must not hide conversations evaluated with previous versions.
    await page.locator('[data-monitoria-tab="pilares"]').click();
    await page.locator('#monitoriaPillarName').fill('Empatia');
    await page.locator('#monitoriaPillarPrompt').fill('Novo critério de empatia para análises futuras.');
    await page.locator('#monitoriaPillarForm button[type="submit"]').click();
    await page.waitForFunction(() => [...document.querySelectorAll('#monitoriaFilterPillar option')].some((o) => o.textContent.includes('Empatia · v2')));
    const empathyFamily = await page.locator('#monitoriaFilterPillar option').evaluateAll((options) => options.find((o) => o.textContent === 'Empatia · todas as versões').value);
    const empathyOld = await page.locator('#monitoriaFilterPillar option').evaluateAll((options) => options.find((o) => o.textContent.includes('Empatia · v1')).value);
    const empathyNew = await page.locator('#monitoriaFilterPillar option').evaluateAll((options) => options.find((o) => o.textContent.includes('Empatia · v2')).value);
    await page.locator('[data-monitoria-tab="conversas"]').click();
    for (const [value, count] of [[empathyNew, 0], [empathyOld, 3], [empathyFamily, 3]]) {
      const response = page.waitForResponse((r) => r.url().includes('/monitoria/conversas?') && r.request().method() === 'GET');
      await page.locator('#monitoriaFilterPillar').selectOption(value);
      await response;
      await page.waitForFunction((count) => document.querySelector('#monitoriaPagerInfo').textContent.includes(`${count} conversas`) && document.querySelector('#monitoriaConversasList').getAttribute('aria-busy') === 'false', count);
    }
    await page.locator('.monitoria-conversation').first().click();
    await page.locator('#monitoriaDetailContent:visible').waitFor();
    await page.getByText('Critérios usados nesta avaliação', { exact: true }).click();
    assert.match(await page.locator('#monitoriaCriteriaSnapshot').textContent(), /Reconhecer a necessidade/);
    assert.doesNotMatch(await page.locator('#monitoriaCriteriaSnapshot').textContent(), /Novo critério de empatia/);
    await page.getByText('Critérios usados nesta avaliação', { exact: true }).click();
    await page.locator('#monitoriaFiltersPanel > summary').click();
    await page.waitForFunction(() => document.querySelectorAll('.toast').length === 0);
    fs.mkdirSync('/tmp/expertise-monitoria-screens', { recursive: true });
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1100 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Horizontal overflow at ${width}`);
      if (width <= 1000) {
        assert.equal(await page.locator('.monitoria-list-pane').isVisible(), false);
        await page.locator('#monitoriaBackToList').click();
        assert.equal(await page.locator('.monitoria-list-pane').isVisible(), true);
        assert.equal(await page.locator('.monitoria-detail-pane').isVisible(), false);
        await page.locator('.monitoria-conversation').first().click();
        await page.locator('#monitoriaDetailContent:visible').waitFor();
      }
      if ([390, 1440].includes(width)) {
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: `/tmp/expertise-monitoria-screens/conversas-${width}.png`, fullPage: true });
      }
      for (const tab of ['upload', 'pilares', 'org', 'config']) {
        await page.locator(`[data-monitoria-tab="${tab}"]`).click();
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${tab} overflow at ${width}`);
      }
      await page.locator('[data-monitoria-tab="conversas"]').click();
    }
    await page.locator('[data-monitoria-tab="upload"]').click();
    await page.locator('#monitoriaAudioFile').setInputFiles({ name: 'teste.wav', mimeType: 'audio/wav', buffer: Buffer.from('RIFF....WAVE') });
    await page.locator('.monitoria-upload-defaults summary').click();
    await page.locator('#monitoriaTicketId').fill('QA-UPLOAD');
    await page.locator('#monitoriaCliente').fill('Cliente de teste');
    await page.locator('#monitoriaUploadForm button[type="submit"]').click();
    await page.waitForFunction(() => document.querySelector('#monitoriaBatchResults').textContent.includes('Concluída'));
    await page.locator('#monitoriaBatchResults [data-batch-conversation]').first().click();
    await page.waitForFunction(() => document.querySelector('#monitoriaDetailTitle').textContent.includes('QA-UPLOAD'));
    assert.equal(await page.locator('#monitoriaChat .monitoria-bubble').count(), 8);
    await page.locator('[data-monitoria-tab="pilares"]').click();
    await page.locator('#monitoriaPillarName').fill('Qualidade QA');
    await page.locator('#monitoriaPillarDescription').fill('Pilar criado pelo teste de integração');
    await page.locator('#monitoriaPillarPrompt').fill('Avalie a clareza do próximo passo.');
    await page.locator('#monitoriaPillarForm button[type="submit"]').click();
    await page.locator('#monitoriaPillarsList').getByText('Qualidade QA', { exact: true }).waitFor();
    assert.deepEqual(errors, [], 'Browser runtime errors');
    console.log('PASS: proportional timeline, playback synchronization, seek/rewind/speed/zoom, mobile list/detail, demo, transcript, evidence, audio, filters across rubric versions, immutable criteria, upload, pillars, all tabs at 320–1440px; no JS errors.');
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
