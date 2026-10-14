import {test,expect} from '@playwright/test';
test('optimization directions can be saved selected edited deleted and restored on reload',async({page})=>{
 const w=await (await page.request.post('/api/workspaces',{data:{interest:'优化方向交互',role:'AI开发'}})).json();
 await page.addInitScript(id=>localStorage.setItem('repocareer.workspace',id),w.id);await page.goto('/');
 await page.getByRole('button',{name:'优化大方向',exact:true}).click();
 await page.getByRole('button',{name:'保存优化方向',exact:true}).click();await expect(page.getByRole('alert')).toContainText('请填写方向名称');
 for(const title of ['任务编排优化','记忆优化']){
  await page.getByLabel('优化方向名称').fill(title);await page.getByLabel('优化方向内容').fill('计划增加版本校验；尚未实施，需要比较冲突处理方案');
  await page.getByRole('button',{name:'保存优化方向',exact:true}).click();await expect(page.getByLabel('选择方向：'+title)).toBeVisible();
  await page.getByLabel('选择方向：'+title).click();await expect(page.getByLabel('选择方向：'+title)).toBeChecked();
 }
 await page.reload();await page.getByRole('button',{name:'优化大方向',exact:true}).click();
 await expect(page.getByLabel('选择方向：任务编排优化')).toBeChecked();await expect(page.getByLabel('选择方向：记忆优化')).toBeChecked();
 const first=page.getByTestId('direction-option').filter({hasText:'任务编排优化'});
 await first.getByRole('button',{name:'编辑方向',exact:true}).click();await page.getByLabel('优化方向内容').fill('改为优先复用已有调度机制，暂未实施');await page.getByRole('button',{name:'保存优化方向',exact:true}).click();await expect(first).toContainText('优先复用');
 await first.getByRole('button',{name:'删除方向',exact:true}).click();await expect(first).toHaveCount(0);
 await expect(page.getByLabel('选择方向：记忆优化')).toBeChecked();
});

test('discussion constraints persist, can be corrected and deleted without business changes',async({page})=>{
 const w=await (await page.request.post('/api/workspaces',{data:{interest:'持久讨论测试',role:'开发'}})).json();
 await page.addInitScript(id=>localStorage.setItem('repocareer.workspace',id),w.id);await page.goto('/');await page.getByRole('button',{name:'优化大方向',exact:true}).click();
 await page.getByLabel('项目讨论',{exact:true}).fill('约束：只考虑本地部署');await page.getByRole('button',{name:'发送讨论',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('请先完成项目Wiki分析');
 await page.getByText('已保存约束与讨论笔记',{exact:true}).click();await expect(page.getByText('只考虑本地部署',{exact:true})).toBeVisible();
 await page.reload();await page.getByRole('button',{name:'优化大方向',exact:true}).click();await page.getByText('已保存约束与讨论笔记',{exact:true}).click();await expect(page.getByText('只考虑本地部署',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'更正笔记',exact:true}).click();await page.getByLabel('更正讨论笔记').fill('允许云端但需要成本上限');await page.getByRole('button',{name:'保存更正',exact:true}).click();await expect(page.getByText('允许云端但需要成本上限',{exact:true})).toBeVisible();
 page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'删除会话',exact:true}).click();await expect(page.getByText('允许云端但需要成本上限',{exact:true})).toHaveCount(0);
 await page.reload();await page.getByRole('button',{name:'优化大方向',exact:true}).click();await expect(page.getByText('约束：只考虑本地部署',{exact:true})).toHaveCount(0);
 const after=await (await page.request.get('/api/workspaces/'+w.id)).json();expect(after.contributions).toEqual([]);expect(after.artifacts).toEqual([]);expect(after.jd_versions).toEqual([]);
});
