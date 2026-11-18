/* Run after check_monitoria.cjs on an isolated test server. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
(async () => {
 const browser = await chromium.launch({headless:true, channel:'chrome'});
 const page = await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[]; page.on('pageerror',e=>errors.push(e.message));
 const base=process.env.MONITORIA_TEST_URL||'http://127.0.0.1:8766';
 const password=process.env.MONITORIA_TEST_PASSWORD||'MonitoriaQA@123';
 try {
  await page.goto(base); await page.locator('#email').fill('admin@expertise.ai.local'); await page.locator('#password').fill(password); await page.locator('#loginForm button[type=submit]').click();
  await page.locator('#dashboardPanel.active').waitFor();
  const token=await page.evaluate(()=>localStorage.getItem('expai_token'));
  const headers={Authorization:`Bearer ${token}`};
  // Use the browser's actual token storage key if the legacy key is absent.
  const login=await page.request.post(base+'/api/v1/auth/login',{data:{email:'admin@expertise.ai.local',password,company_id:1}}); assert.equal(login.status(),200);
  headers.Authorization=`Bearer ${(await login.json()).access_token}`;
  for (const area of ['suporte','financeiro']) await page.request.post(base+'/api/v1/empresas/1/areas',{headers,data:{name:area}});
  await page.request.post(base+'/api/v1/empresas/1/categorias',{headers,data:{name:'duvidas',area:'suporte'}});
  await page.locator('#userMenuBtn').click(); await page.locator('#userAdminMenuItem').click();
  const email=`monitoria-${Date.now()}@qa.local`;
  await page.locator('#newUserName').fill('Analista de Monitoria QA'); await page.locator('#newUserEmail').fill(email); await page.locator('#newUserPassword').fill(password); await page.locator('#newUserRole').selectOption('editor');
  await page.locator('#newUserModules input[value=conteudo]').uncheck(); await page.locator('#newUserModules input[value=monitoria]').check();
  const created=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/usuarios'));
  await page.locator('#newUserName').locator('xpath=ancestor::form').locator('button[type=submit]').click();
  const response=await created;assert.equal(response.status(),200); const uid=(await response.json()).usuario_id;
  const users=await(await page.request.get(base+'/api/v1/empresas/1/usuarios',{headers})).json();assert.deepEqual(users.find(u=>u.id===uid).modules,['monitoria']);
  await page.request.put(base+`/api/v1/empresas/1/usuarios/${uid}/areas-acesso`,{headers,data:{mode:'selected',areas:['suporte'],profile_ids:[]}});
  // Edit modal must expose and persist both module switches.
  await page.locator(`#usersList li[data-user-id="${uid}"] button`).click();
  await page.locator('#userAccessModal.open').waitFor();
  assert(await page.locator('#userAccessModalModules input[value=monitoria]').isChecked());
  assert(!(await page.locator('#userAccessModalModules input[value=conteudo]').isChecked()));
  await page.locator('#userAccessModalMonitoriaRole').selectOption('monitoria_supervisor'); const saved=page.waitForResponse(r=>r.request().method()==='PUT'&&r.url().endsWith(`/${uid}/areas-acesso`)); await page.locator('#userAccessModalSave').click(); assert.equal((await saved).status(),200); await page.waitForFunction(()=>!document.querySelector('#userAccessModalSave').disabled);
  await page.locator('#userAccessModalCloseBtn').click();
  await page.locator('[data-session=monitoriaSession]').click(); await page.locator('[data-monitoria-tab=org]').click();
  assert.match(await page.locator('#monitoriaCentralsList').textContent(),/suporte/);
  assert.equal(await page.locator('#monitoriaCentralForm').count(),0);
  for(const width of [390,1440]) { await page.setViewportSize({width,height:1000});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)); }
  await page.locator('#userMenuBtn').click(); await page.locator('#userLogoutMenuItem').click();
  await page.locator('#email').fill(email); await page.locator('#password').fill(password); await page.locator('#loginForm button[type=submit]').click();
  await page.locator('#dashboardPanel.active').waitFor();
  if(await page.locator('#forcePasswordModal.open').count()) {
   await page.locator('#forcePasswordModal input[type=password]').first().fill('MonitoriaQA@456');
   const inputs=page.locator('#forcePasswordModal input[type=password]');if(await inputs.count()>1)await inputs.nth(1).fill('MonitoriaQA@456');
   await page.locator('#forcePasswordSave').click(); await page.locator('#forcePasswordModal.open').waitFor({state:'hidden'});
  }
  await page.locator('#monitoriaSession.active-session').waitFor();
  assert(!(await page.locator('[data-session=dashboardSession]').isVisible()));assert(!(await page.locator('[data-session=taxonomySession]').isVisible()));
  await page.locator('[data-monitoria-tab=upload]').click();
  await page.locator('#monitoriaAudioFile').setInputFiles({name:'scope.wav',mimeType:'audio/wav',buffer:Buffer.from('RIFF....WAVE')});
  await page.locator('.monitoria-batch-file details summary').click();
  const area=page.locator('[data-batch-field=area]');await area.selectOption('suporte');
  await page.locator('[data-batch-field=categoria]').selectOption('duvidas');
  assert(!(await area.locator('option[value=financeiro]').count()));
  await page.locator('#monitoriaUploadForm button[type=submit]').click();
  await page.waitForFunction(()=>document.querySelector('#monitoriaBatchStatus').textContent.includes('1/1 finalizados'));
  assert.match(await page.locator('#monitoriaBatchResults').textContent(),/Concluída/);
  require('node:fs').mkdirSync('/tmp/expertise-monitoria-screens',{recursive:true}); await page.screenshot({path:'/tmp/expertise-monitoria-screens/module-access-upload.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log('PASS: module grant/create/edit, monitoria-only navigation, shared areas/categories, scoped batch upload, mobile layout.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
