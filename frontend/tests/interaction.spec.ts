import {test,expect} from '@playwright/test';
test('interactive iteration: selection metrics corrections editor review and reload',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const w=await (await page.request.post('/api/workspaces',{data:{interest:'交互离线演示',role:'Agent开发工程师'}})).json();
 await page.addInitScript(id=>localStorage.setItem('repocareer.workspace',id),w.id);await page.goto('/?view=admin');
 await page.getByRole('button',{name:'当前信息',exact:true}).click();
 await page.getByLabel('改进标题',{exact:true}).fill('保留角色隔离的统一执行器');await page.getByLabel('建议方案',{exact:true}).fill('先验证独立上下文，再复用执行代码');await page.getByRole('button',{name:'添加改进点',exact:true}).click();
 const card=page.getByTestId('improvement-card');await expect(card).toHaveCount(1);await card.getByRole('button',{name:'采用',exact:true}).click();await expect(card).toContainText('已采用 · 未开始');await card.getByRole('button',{name:'报告已完成',exact:true}).click();await expect(card).toContainText('用户报告完成，未核查源码');
 await page.getByLabel('指标名称',{exact:true}).fill('幻觉率下降');await page.getByLabel('指标数值',{exact:true}).fill('70');await page.getByLabel('变化类型',{exact:true}).selectOption('relative_decrease');await page.getByRole('button',{name:'添加指标',exact:true}).click();await expect(page.getByTestId('metric-card')).toContainText('70%');
 await page.getByRole('button',{name:'讨论区',exact:true}).click();await page.getByLabel('项目讨论',{exact:true}).fill('把幻觉率下降改成80%');await page.getByRole('button',{name:'发送讨论',exact:true}).click();await expect(page.getByText('把幻觉率下降改成80%',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'当前信息',exact:true}).click();await expect(page.getByTestId('metric-card')).toHaveCount(1);await expect(page.getByTestId('metric-card')).toContainText('70%');await page.getByTestId('metric-card').getByRole('button',{name:'编辑指标',exact:true}).click();await page.getByLabel('指标数值',{exact:true}).fill('80');await page.getByRole('button',{name:'保存指标更正',exact:true}).click();await expect(page.getByTestId('metric-card')).toContainText('80%');await expect(page.getByTestId('metric-card')).toContainText('v2');
 await page.getByLabel('当前 JD',{exact:true}).fill('Agent编排与上下文隔离');await page.getByRole('button',{name:'保存当前 JD',exact:true}).click();
 await page.getByRole('button',{name:'项目经历编辑器',exact:true}).click();await page.getByText('高级生成设置',{exact:true}).click();await page.getByLabel('迭代生成方式',{exact:true}).selectOption('reference');await page.getByRole('button',{name:'生成项目参考建议',exact:true}).click();await expect(page.getByRole('button',{name:'接受建议并保存新版本',exact:true})).toBeVisible();await expect(page.getByLabel('项目经历正文')).toHaveValue('');await page.getByRole('button',{name:'接受建议并保存新版本',exact:true}).click();await expect(page.getByLabel('项目经历正文')).not.toHaveValue('');
 await page.getByLabel('项目经历正文').fill('人工文本：快照恢复');await page.getByRole('button',{name:'保存手动修改',exact:true}).click();await expect(page.getByText(/正文已保存/)).toBeVisible();
 await page.getByLabel('项目经历正文').fill('人工文本：任务级断点续跑');await page.getByRole('button',{name:'分析当前文本',exact:true}).click();await expect(page.getByText(/^事实\/指标\/归属：离线模拟：请核对新增能力/)).toBeVisible();await expect(page.getByLabel('项目经历正文')).toHaveValue('人工文本：任务级断点续跑');await page.getByRole('button',{name:'拒绝建议',exact:true}).click();await expect(page.getByLabel('项目经历正文')).toHaveValue('人工文本：任务级断点续跑');
 await page.reload();await page.getByRole('button',{name:'项目经历编辑器',exact:true}).click();await expect(page.getByLabel('项目经历正文')).toHaveValue('人工文本：任务级断点续跑');await expect(page.getByText(/有未保存修改/)).toBeVisible();
 await page.getByText('版本记录与恢复',{exact:true}).click();await page.getByRole('button',{name:'恢复 v3 为新版本',exact:true}).click();await expect(page.getByLabel('项目经历正文')).toHaveValue('人工文本：快照恢复');
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);expect(errors).toEqual([]);
});

test('simple user navigation is visible, preserves edits and separates diagnostics',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const w=await (await page.request.post('/api/workspaces',{data:{interest:'简洁界面回归',role:'AI应用开发'}})).json();
 await page.addInitScript(()=>localStorage.removeItem('repocareer.workspace'));
 await page.goto('/');
 await expect(page.getByLabel('选择项目')).toHaveValue(w.id); // newest project is restored even without browser storage
 for(const name of ['讨论区','当前信息'])await expect(page.getByRole('button',{name,exact:true})).toHaveCount(0);
 for(const name of ['项目设置','优化大方向','项目经历编辑器'])await expect(page.getByRole('button',{name,exact:true})).toBeInViewport();
 await expect(page.getByText('历史生成与证据工具（兼容入口）',{exact:true})).toHaveCount(0);
 await expect(page.getByText('执行记录与中间材料',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'项目经历编辑器',exact:true}).click();
 await page.getByLabel('项目经历正文').fill('跨区域切换不能丢失的手动文本');
 await page.getByRole('button',{name:'项目设置',exact:true}).click();
 await page.getByRole('button',{name:'优化大方向',exact:true}).click();
 await page.getByRole('button',{name:'项目经历编辑器',exact:true}).click();
 await expect(page.getByLabel('项目经历正文')).toHaveValue('跨区域切换不能丢失的手动文本');
 await page.screenshot({path:test.info().outputPath('simple-editor.png'),fullPage:true});
 await page.goto('/?view=admin');await expect(page.getByRole('heading',{name:'项目过程后台',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'执行记录与中间材料',exact:true})).toBeVisible();
 await page.goto('/');await page.getByRole('button',{name:'项目经历编辑器',exact:true}).click();await expect(page.getByLabel('项目经历正文')).toHaveValue('跨区域切换不能丢失的手动文本');
 await page.setViewportSize({width:390,height:844});await expect(page.getByRole('button',{name:'优化大方向',exact:true})).toBeInViewport();expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);expect(errors).toEqual([]);
});

test('empty project still explains where discussion and editor are',async({page})=>{
 await page.route('**/api/workspaces',r=>r.fulfill({json:[]}));await page.goto('/');
 await page.getByRole('button',{name:'优化大方向',exact:true}).click();await expect(page.getByText('先保存一个 GitHub 仓库链接，或在顶部选择已有项目。',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'项目经历编辑器',exact:true}).click();await expect(page.getByRole('heading',{name:'项目经历编辑器',exact:true})).toBeVisible();
});

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
 await page.addInitScript(id=>localStorage.setItem('repocareer.workspace',id),w.id);await page.goto('/?view=admin');await page.getByRole('button',{name:'讨论区',exact:true}).click();
 await page.getByLabel('项目讨论',{exact:true}).fill('约束：只考虑本地部署');await page.getByRole('button',{name:'发送讨论',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('请先完成项目Wiki分析');
 await page.getByText('已保存约束与讨论笔记',{exact:true}).click();await expect(page.getByText('只考虑本地部署',{exact:true})).toBeVisible();
 await page.reload();await page.getByRole('button',{name:'讨论区',exact:true}).click();await page.getByText('已保存约束与讨论笔记',{exact:true}).click();await expect(page.getByText('只考虑本地部署',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'更正笔记',exact:true}).click();await page.getByLabel('更正讨论笔记').fill('允许云端但需要成本上限');await page.getByRole('button',{name:'保存更正',exact:true}).click();await expect(page.getByText('允许云端但需要成本上限',{exact:true})).toBeVisible();
 page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'删除会话',exact:true}).click();await expect(page.getByText('允许云端但需要成本上限',{exact:true})).toHaveCount(0);
 await page.reload();await page.getByRole('button',{name:'讨论区',exact:true}).click();await expect(page.getByText('约束：只考虑本地部署',{exact:true})).toHaveCount(0);
 const after=await (await page.request.get('/api/workspaces/'+w.id)).json();expect(after.contributions).toEqual([]);expect(after.artifacts).toEqual([]);expect(after.jd_versions).toEqual([]);
});
