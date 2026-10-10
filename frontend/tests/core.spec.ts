import {test,expect} from '@playwright/test';
test('GitHub link JD report discussion correction and resume',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const response=await page.request.post('/api/workspaces',{data:{interest:'文档处理 E2E '+Date.now(),role:'Agent开发工程师'}});expect(response.ok()).toBeTruthy();
 const workspace=await response.json();await page.addInitScript(id=>localStorage.setItem('repocareer.workspace',id),workspace.id);
 await page.goto('/');await page.getByLabel('GitHub仓库链接').fill('https://github.com/example/document-agent');await page.getByRole('button',{name:'保存仓库链接',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('GitHub链接已保存');
 await page.getByLabel('岗位名称',{exact:true}).fill('Agent开发工程师');await page.getByLabel('岗位JD',{exact:true}).fill('要求Skill、MCP与multi-agent，先评估必要性。');
 await page.getByText('分析服务与演示说明').click();await page.getByRole('checkbox').check();
 await page.getByRole('button',{name:'分析项目全貌与优化方向 →'}).click();
 await expect(page.getByText('演示文档助手项目，不是上传仓库的分析。',{exact:true})).toBeVisible({timeout:15000});
 await page.getByLabel('项目讨论',{exact:true}).fill('只是讨论Skill，没有实现');await page.getByRole('button',{name:'发送讨论',exact:true}).click();await expect(page.getByText('只是讨论Skill，没有实现',{exact:true})).toBeVisible();
 await page.getByText('确认个人贡献与完成状态',{exact:true}).click();await page.getByLabel('本人职责',{exact:true}).fill('本人负责工作流模块');await page.getByLabel('具体问题',{exact:true}).fill('重复文档流程难维护');await page.getByLabel('技术行动',{exact:true}).fill('抽取领域工作流配置');await page.getByLabel('方案取舍',{exact:true}).fill('保留单Agent，减少调度复杂度');await page.getByLabel('贡献状态',{exact:true}).selectOption('implemented');await page.getByRole('button',{name:'确认保存贡献',exact:true}).click();
 await page.getByLabel('简历写作方式',{exact:true}).selectOption('reference');await page.getByRole('button',{name:'生成项目简历参考稿',exact:true}).click();await expect(page.getByText('简历 v1 · 当前事实生成',{exact:true})).toBeVisible();await page.getByText('简历 v1 · 当前事实生成',{exact:true}).click();await expect(page.getByTestId('resume-preview').filter({hasText:'已实现优化'})).toBeVisible();await expect(page.getByRole('heading',{name:'技术亮点',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'更正贡献',exact:true}).click();await page.getByLabel('贡献状态',{exact:true}).selectOption('proposed');await page.getByRole('button',{name:'确认保存贡献',exact:true}).click();await expect(page.getByText('简历 v1 · 待复核',{exact:true})).toBeVisible();
 await page.reload();await expect(page.getByText('简历 v1 · 待复核',{exact:true})).toBeVisible();expect(errors).toEqual([]);
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});



test('restores model resume when default arrays are omitted',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const workspace={id:'regression',interest:'测试项目',role:'Agent工程师',skills:'',time_budget:'',environment:'',snapshots:[],runs:[],jd_versions:[],messages:[],contributions:[],evidence:[],experiments:[],attempts:[],memory_events:[],artifacts:[{id:'a',type:'resume',version:1,review_status:'current',content:'项目简介\n技术亮点\n- **主题**：机制\n项目成果',claims:[{kind:'writing_review',iterations:1,status:'passed',selection:{selected:[{title:'主题',source_refs:['overview'],state:'project_existing'}]},reviews:[]}]}]};
 await page.route('**/api/workspaces',r=>r.fulfill({json:[workspace]}));
 await page.route('**/api/workspaces/regression?summary=true',r=>r.fulfill({json:workspace}));
 await page.addInitScript(()=>localStorage.setItem('repocareer.workspace','regression'));
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'04 · 项目讨论与简历参考稿'})).toBeVisible();
 await page.getByText('简历 v1 · 当前事实生成',{exact:true}).click();
 await page.getByText('查看岗位亮点评选依据（HR / 技术面试官视角）',{exact:true}).click();
 await expect(page.getByRole('heading',{name:'1. 主题',exact:true})).toBeVisible();
 expect(errors).toEqual([]);
});
