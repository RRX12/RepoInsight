import {test,expect} from '@playwright/test';

test('repository precedes JD and header editor preserves JD history without analyzing',async({page})=>{
 const w=await (await page.request.post('/api/workspaces',{data:{interest:'分步设置测试',role:'待填写'}})).json();
 await page.addInitScript(id=>localStorage.setItem('repocareer.workspace',id),w.id);await page.goto('/');
 await expect(page.getByRole('heading',{name:'GitHub 代码仓库',exact:true})).toBeVisible();
 await expect(page.getByLabel('岗位JD',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('link',{name:'过程后台 ↗'})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'修改岗位JD',exact:true})).toBeDisabled();
 await page.getByLabel('GitHub仓库链接').fill('https://github.com/example/workflow');await page.getByRole('button',{name:'保存仓库链接',exact:true}).click();
 await expect(page.getByRole('heading',{name:'上传岗位JD（可选）',exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'GitHub 代码仓库',exact:true})).toHaveCount(0);
 const header=page.locator('header');await expect(header.getByRole('button',{name:'修改岗位JD',exact:true})).toBeEnabled();
 await header.getByRole('button',{name:'修改岗位JD',exact:true}).click();const dialog=page.getByRole('dialog',{name:'修改岗位JD'});
 await dialog.getByLabel('修改岗位名称').fill('后端开发工程师');await dialog.getByLabel('修改岗位JD内容').fill('Python API、取消与幂等');await dialog.getByRole('button',{name:'保存岗位JD'}).click();
 await expect(dialog).toHaveCount(0);await expect(page.getByLabel('岗位名称',{exact:true})).toHaveValue('后端开发工程师');await expect(page.getByLabel('岗位JD',{exact:true})).toHaveValue('Python API、取消与幂等');
 let state=await (await page.request.get('/api/workspaces/'+w.id)).json();expect(state.jd_versions).toHaveLength(1);expect(state.runs).toHaveLength(0);
 await page.reload();await expect(page.getByLabel('岗位JD',{exact:true})).toHaveValue('Python API、取消与幂等');
 await header.getByRole('button',{name:'修改岗位JD',exact:true}).click();await dialog.getByLabel('修改岗位JD内容').fill('版本校验和故障恢复');await dialog.getByRole('button',{name:'保存岗位JD'}).click();await expect(dialog).toHaveCount(0);
 state=await (await page.request.get('/api/workspaces/'+w.id)).json();expect(state.jd_versions).toHaveLength(2);expect(state.jd_versions[1].supersedes_id).toBe(state.jd_versions[0].id);expect(state.runs).toHaveLength(0);
 await page.getByRole('button',{name:'01 · 上传仓库'}).click();await expect(page.getByLabel('GitHub仓库链接')).toHaveValue('https://github.com/example/workflow');
 await page.getByRole('button',{name:'02 · 上传岗位JD（可选）'}).click();await expect(page.getByLabel('岗位JD',{exact:true})).toHaveValue('版本校验和故障恢复');
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test('skip clears old JD before analysis and regular analysis submits edited JD',async({page})=>{
 const w=await (await page.request.post('/api/workspaces',{data:{interest:'跳过和分析测试',role:'旧岗位'}})).json();
 const repository=await page.request.post('/api/workspaces/'+w.id+'/repository-link',{data:{url:'https://github.com/example/workflow'}});expect(repository.ok(),await repository.text()).toBeTruthy();
 const target=await page.request.post('/api/workspaces/'+w.id+'/target',{data:{role:'旧岗位',jd:'旧岗位要求'}});expect(target.ok(),await target.text()).toBeTruthy();
 await page.addInitScript(id=>localStorage.setItem('repocareer.workspace',id),w.id);
 const targets:any[]=[],runs:any[]=[];
 await page.route('**/api/workspaces/'+w.id+'/target',async r=>{targets.push(r.request().postDataJSON());const response=await r.fetch();await r.fulfill({response});});
 await page.route('**/api/workspaces/'+w.id+'/architecture-runs',r=>{runs.push(r.request().postDataJSON());return r.fulfill({json:{id:'offline-no-model-run'}});});
 await page.goto('/');await page.getByRole('button',{name:'跳过',exact:true}).click();await expect.poll(()=>runs.length).toBe(1);expect(targets[0]).toEqual({role:'项目工程优化',jd:''});
 const state=await (await page.request.get('/api/workspaces/'+w.id)).json();expect(state.jd_versions.at(-1).raw_text).toBe('');expect(state.jd_versions[0].raw_text).toBe('旧岗位要求');
 await expect(page.getByLabel('岗位JD',{exact:true})).toHaveValue('');await page.getByLabel('岗位名称',{exact:true}).fill('AI应用开发');await page.getByLabel('岗位JD',{exact:true}).fill('上下文隔离与模型工具治理');await page.getByRole('button',{name:'分析项目全貌与优化方向 →'}).click();await expect.poll(()=>runs.length).toBe(2);expect(targets[1]).toEqual({role:'AI应用开发',jd:'上下文隔离与模型工具治理'});
});
