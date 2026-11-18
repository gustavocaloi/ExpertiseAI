/* Focused review checks. Run after check_monitoria.cjs on the same isolated server.
 * No persisted writes: edge cases below override GET responses in the browser only.
 */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  try {
    await page.goto(process.env.MONITORIA_TEST_URL || 'http://127.0.0.1:8766/');
    await page.locator('#email').fill('admin@expertise.ai.local');
    await page.locator('#password').fill(process.env.MONITORIA_TEST_PASSWORD || 'MonitoriaQA@123');
    await page.locator('#loginForm button[type="submit"]').click();
    await page.locator('#dashboardPanel.active').waitFor();
    await page.locator('#docsList[aria-busy="false"]').waitFor();
    await page.locator('[data-session="monitoriaSession"]').click();
    const demo = page.locator('.monitoria-conversation').filter({ hasText: 'DEMO-003' });
    await demo.click();
    await page.locator('.monitoria-track-canvas').waitFor();
    const uuid = await demo.getAttribute('data-uuid');
    const detailPattern = `**/monitoria/conversas/${uuid}`;
    const audioPattern = `**/monitoria/conversas/${uuid}/audio`;
    const load = async () => {
      await page.locator('#monitoriaLoadAudio').click();
      await page.waitForFunction(() => document.querySelector('#monitoriaAudio').readyState > 0);
    };
    await page.route(audioPattern, (route) => route.fulfill({ status: 503, body: 'Test unavailable' }));
    await page.locator('#monitoriaLoadAudio').click();
    await page.waitForFunction(() => document.querySelector('#monitoriaAudioStatus').textContent.includes('Não foi possível carregar'));
    assert.equal(await page.locator('#monitoriaLoadAudio').isEnabled(), true);
    await page.unroute(audioPattern);
    await load();
    // Playback advances without moving the surrounding document. Follow can be disabled.
    await page.locator('#monitoriaFollow').uncheck();
    await page.locator('#monitoriaChat').evaluate((el) => { el.scrollTop = 0; });
    await page.locator('#monitoriaAudio').evaluate((a) => { a.currentTime = 34; });
    await page.waitForFunction(() => document.querySelector('#monitoriaChat [data-turn="7"]').classList.contains('is-highlighted'));
    assert.equal(await page.locator('#monitoriaChat').evaluate((el) => el.scrollTop), 0);
    await page.locator('#monitoriaFollow').check();
    assert(await page.locator('#monitoriaChat').evaluate((el) => el.scrollTop) > 0);
    await page.setViewportSize({ width: 390, height: 900 });
    await page.locator('#monitoriaZoom').selectOption('2');
    await page.locator('#monitoriaPlayPause').click();
    await page.waitForFunction(() => document.querySelector('#monitoriaAudio').currentTime > 34.1 && document.querySelector('#monitoriaTelemetryList').scrollLeft > 0);
    const initialScroll = await page.evaluate(() => scrollY);
    await page.waitForFunction(() => document.querySelector('#monitoriaAudio').currentTime > 35);
    assert.equal(await page.evaluate(() => scrollY), initialScroll, 'Playback must not scroll the document');
    const sticky = await page.evaluate(() => {
      const player = document.querySelector('.monitoria-player').getBoundingClientRect();
      const header = document.querySelector('.topbar').getBoundingClientRect();
      return player.top >= header.bottom && player.bottom < innerHeight;
    });
    assert(sticky, 'Player is visible below the mobile header');
    await page.locator('#monitoriaBackToList').click();
    assert.equal(await page.locator('#monitoriaAudio').evaluate((a) => a.paused), true);
    // Mobile loading/failure must always offer a way back.
    await page.route(detailPattern, (route) => route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Falha de teste"}' }));
    await demo.click();
    await page.waitForFunction(() => document.querySelector('#monitoriaDetailEmpty').textContent.includes('Não foi possível abrir'));
    assert.equal(await page.locator('#monitoriaBackToList').isVisible(), true);
    await page.locator('#monitoriaBackToList').click();
    await page.unroute(detailPattern);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await demo.click();
    await page.locator('.monitoria-track-canvas').waitFor();
    // An audio response that arrives after selecting another conversation is discarded.
    let release, intercepted;
    const gate = new Promise((resolve) => { release = resolve; });
    const ready = new Promise((resolve) => { intercepted = resolve; });
    await page.route(audioPattern, async (route) => {
      const response = await route.fetch(); intercepted(); await gate; await route.fulfill({ response });
    });
    await page.locator('#monitoriaLoadAudio').click();
    await ready;
    await page.locator('.monitoria-conversation').filter({ hasText: 'DEMO-002' }).click();
    await page.waitForFunction(() => document.querySelector('#monitoriaDetailTitle').textContent === 'DEMO-002');
    const late = page.waitForResponse((r) => r.url().endsWith(`/${uuid}/audio`));
    release(); await late;
    await page.unroute(audioPattern);
    assert.equal(await page.locator('#monitoriaAudio').getAttribute('src'), null);
    assert.equal(await page.locator('#monitoriaLoadAudio').isEnabled(), true);
    // Synthetic timestamps include a gap and an overlap, without changing the database.
    await page.route(detailPattern, async (route) => {
      const response = await route.fetch(); const detail = await response.json();
      detail.turns[0].t_end = 2; // Gap [2,4).
      detail.turns[1].t_end = 10; // Overlap with turn 2 [9,10).
      await route.fulfill({ response, json: detail });
    });
    await demo.click();
    await page.waitForFunction(() => document.querySelector('#monitoriaDetailTitle').textContent === 'DEMO-003' && !document.querySelector('#monitoriaDetailContent').classList.contains('hidden-view'));
    await page.locator('#monitoriaSeek').evaluate((el) => { el.value = 3; el.dispatchEvent(new Event('input', { bubbles: true })); });
    assert.equal(await page.locator('#monitoriaChat .is-highlighted').count(), 0);
    await page.locator('#monitoriaSeek').evaluate((el) => { el.value = 9.5; el.dispatchEvent(new Event('input', { bubbles: true })); });
    assert.equal(await page.locator('#monitoriaChat .is-highlighted').count(), 2);
    await page.unroute(detailPattern);
    // The intentionally invalid WAV uploaded by the smoke test gets a readable decode error.
    await page.locator('.monitoria-conversation').filter({ hasText: 'QA-UPLOAD' }).click();
    await page.waitForFunction(() => document.querySelector('#monitoriaDetailTitle').textContent === 'QA-UPLOAD' && !document.querySelector('#monitoriaDetailContent').classList.contains('hidden-view'));
    await page.locator('#monitoriaLoadAudio').click();
    await page.waitForFunction(() => document.querySelector('#monitoriaAudioStatus').textContent.includes('Não foi possível reproduzir'));
    assert.equal(await page.locator('#monitoriaLoadAudio').isVisible(), true);
    assert.equal(await page.locator('#monitoriaChat .monitoria-bubble').count(), 8);
    await demo.click();
    await page.locator('.monitoria-track-canvas').waitFor();
    const score = page.locator('.monitoria-score-cell[data-turn="3"]').first();
    await score.focus(); await page.keyboard.press('Enter');
    const selectedLabel = await score.getAttribute('aria-label');
    await page.locator('#monitoriaZoom').selectOption('2');
    assert.equal(await page.locator('.monitoria-score-cell[aria-pressed="true"]').getAttribute('aria-label'), selectedLabel);
    await page.locator('#monitoriaZoom').selectOption('1');
    await page.waitForFunction(() => document.querySelectorAll('.toast').length === 0);
    require('node:fs').mkdirSync('/tmp/expertise-monitoria-screens', { recursive: true });
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Review overflow at ${width}`);
      if ([390, 1440].includes(width)) {
        await page.waitForFunction(() => document.querySelector('#monitoriaMsg').textContent === '');
        await page.evaluate(() => scrollTo(0, 0));
        await page.screenshot({ path: `/tmp/expertise-monitoria-screens/conversas-${width}.png`, fullPage: true });
      }
    }
    assert.deepEqual(errors, []);
    console.log('PASS: audio failure/retry, stale audio response, decode error, mobile failure/back, sticky player, timeline follow, optional transcript follow, gaps/overlaps; no JS errors.');
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
