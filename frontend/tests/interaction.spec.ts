import {test,expect} from '@playwright/test';
test('interactive iteration: selection metrics corrections editor review and reload',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const w=await (await page.request.post('/api/workspaces',{data:{interest:'交互离线演示',role:'Agent开发工程师'}})).json();
 await page.addInitScript(id=>localStorage.setItem('repocareer.workspace',id),w.id);await page.goto('/');
 await page.getByRole('button',{name:'当前信息',exact:true}).click();
 await page.getByLabel('改进标题',{exact:true}).fill('保留角色隔离的统一执行器');await page.getByLabel('建议方案',{exact:true}).fill('先验证独立上下文，再复用执行代码');await page.getByRole('button',{name:'添加改进点',exact:true}).click();
 const card=page.getByTestId('improvement-card');await expect(card).toHaveCount(1);await card.getByRole('button',{name:'采用',exact:true}).click();await expect(card).toContainText('已采用 · 未开始');await card.getByRole('button',{name:'报告已完成',exact:true}).click();await expect(card).toContainText('用户报告完成，未核查源码');
 await page.getByLabel('指标名称',{exact:true}).fill('幻觉率下降');await page.getByLabel('指标数值',{exact:true}).fill('70');await page.getByLabel('变化类型',{exact:true}).selectOption('relative_decrease');await page.getByRole('button',{name:'添加指标',exact:true}).click();await expect(page.getByTestId('metric-card')).toContainText('70%');
 await page.getByRole('button',{name:'讨论区',exact:true}).click();await page.getByLabel('项目讨论',{exact:true}).fill('把幻觉率下降改成80%');await page.getByRole('button',{name:'发送讨论',exact:true}).click();await expect(page.getByText(/离线模拟返回/)).toBeVisible();
 await page.getByRole('button',{name:'当前信息',exact:true}).click();await expect(page.getByTestId('metric-card')).toHaveCount(1);await expect(page.getByTestId('metric-card')).toContainText('80%');await expect(page.getByTestId('metric-card')).toContainText('v2');
 await page.getByLabel('当前 JD',{exact:true}).fill('Agent编排与上下文隔离');await page.getByRole('button',{name:'保存当前 JD',exact:true}).click();
 await page.getByRole('button',{name:'项目经历编辑器',exact:true}).click();await page.getByLabel('迭代生成方式',{exact:true}).selectOption('reference');await page.getByRole('button',{name:'生成项目参考建议',exact:true}).click();await expect(page.getByRole('button',{name:'接受建议并保存新版本',exact:true})).toBeVisible();await expect(page.getByLabel('项目经历正文')).toHaveValue('');await page.getByRole('button',{name:'接受建议并保存新版本',exact:true}).click();await expect(page.getByLabel('项目经历正文')).not.toHaveValue('');
 await page.getByLabel('项目经历正文').fill('人工文本：快照恢复');await page.getByRole('button',{name:'保存手动修改',exact:true}).click();await expect(page.getByText(/正文已保存/)).toBeVisible();
 await page.getByLabel('项目经历正文').fill('人工文本：任务级断点续跑');await page.getByRole('button',{name:'分析当前文本',exact:true}).click();await expect(page.getByText(/离线模拟：请核对新增能力/)).toBeVisible();await expect(page.getByLabel('项目经历正文')).toHaveValue('人工文本：任务级断点续跑');await page.getByRole('button',{name:'拒绝建议',exact:true}).click();await expect(page.getByLabel('项目经历正文')).toHaveValue('人工文本：任务级断点续跑');
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
 for(const name of ['讨论区','当前信息','项目经历编辑器'])await expect(page.getByRole('button',{name,exact:true})).toBeInViewport();
 await expect(page.getByText('历史生成与证据工具（兼容入口）',{exact:true})).toHaveCount(0);
 await expect(page.getByText('执行记录与中间材料',{exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'项目经历编辑器',exact:true}).click();
 await page.getByLabel('项目经历正文').fill('跨区域切换不能丢失的手动文本');
 await page.getByRole('button',{name:'项目全貌',exact:true}).click();
 await page.getByRole('button',{name:'当前信息',exact:true}).click();
 await page.getByRole('button',{name:'项目经历编辑器',exact:true}).click();
 await expect(page.getByLabel('项目经历正文')).toHaveValue('跨区域切换不能丢失的手动文本');
 await page.screenshot({path:test.info().outputPath('simple-editor.png'),fullPage:true});
 await page.goto('/?view=admin');await expect(page.getByRole('heading',{name:'项目过程后台',exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'执行记录与中间材料',exact:true})).toBeVisible();
 await page.goto('/');await page.getByRole('button',{name:'项目经历编辑器',exact:true}).click();await expect(page.getByLabel('项目经历正文')).toHaveValue('跨区域切换不能丢失的手动文本');
 await page.setViewportSize({width:390,height:844});await expect(page.getByRole('button',{name:'讨论区',exact:true})).toBeInViewport();expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);expect(errors).toEqual([]);
});

test('empty project still explains where discussion and editor are',async({page})=>{
 await page.route('**/api/workspaces',r=>r.fulfill({json:[]}));await page.goto('/');
 await page.getByRole('button',{name:'讨论区',exact:true}).click();await expect(page.getByText('先保存一个 GitHub 仓库链接，或在顶部选择已有项目。',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'项目经历编辑器',exact:true}).click();await expect(page.getByRole('heading',{name:'项目经历编辑器',exact:true})).toBeVisible();
});
