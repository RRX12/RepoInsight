import {test,expect} from '@playwright/test';
test('GitHub link JD report discussion correction and resume',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const response=await page.request.post('/api/workspaces',{data:{interest:'文档处理 E2E '+Date.now(),role:'Agent开发工程师'}});expect(response.ok()).toBeTruthy();
 const workspace=await response.json();await page.addInitScript(id=>localStorage.setItem('repocareer.workspace',id),workspace.id);
 await page.goto('/?view=admin');await page.getByLabel('GitHub仓库链接').fill('https://github.com/example/document-agent');await page.getByRole('button',{name:'保存仓库链接',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('GitHub链接已保存');
 await page.getByLabel('岗位名称',{exact:true}).fill('Agent开发工程师');await page.getByLabel('岗位JD',{exact:true}).fill('要求Skill、MCP与multi-agent，先评估必要性。');
 await page.getByText('分析服务与演示说明').click();await page.getByRole('checkbox').check();
 await page.getByRole('button',{name:'分析项目全貌与优化方向 →'}).click();
 await expect(page.getByText('演示文档助手项目，不是上传仓库的分析。',{exact:true})).toBeVisible({timeout:15000});
 await page.goto('/');await page.getByRole('button',{name:'讨论区',exact:true}).click();await page.getByLabel('项目讨论',{exact:true}).fill('只是讨论Skill，没有实现');await page.getByRole('button',{name:'发送讨论',exact:true}).click();await expect(page.getByText('只是讨论Skill，没有实现',{exact:true})).toBeVisible();
 await page.goto('/?view=admin');await page.getByText('历史生成与证据工具（兼容入口）',{exact:true}).click();await page.getByText('确认个人贡献与完成状态',{exact:true}).click();await page.getByLabel('本人职责',{exact:true}).fill('本人负责工作流模块');await page.getByLabel('具体问题',{exact:true}).fill('重复文档流程难维护');await page.getByLabel('技术行动',{exact:true}).fill('抽取领域工作流配置');await page.getByLabel('方案取舍',{exact:true}).fill('保留单Agent，减少调度复杂度');await page.getByLabel('贡献状态',{exact:true}).selectOption('implemented');await page.getByRole('button',{name:'确认保存贡献',exact:true}).click();
 await page.getByLabel('简历写作方式',{exact:true}).selectOption('reference');if(!await page.getByRole('button',{name:'生成项目简历参考稿',exact:true}).isVisible())await page.getByText('历史生成与证据工具（兼容入口）',{exact:true}).click();await page.getByRole('button',{name:'生成项目简历参考稿',exact:true}).click();await expect(page.getByText('简历 v1 · 当前事实生成',{exact:true})).toBeVisible();await page.getByText('简历 v1 · 当前事实生成',{exact:true}).click();await expect(page.getByTestId('resume-preview').filter({hasText:'已实现优化'})).toBeVisible();await expect(page.getByRole('heading',{name:'技术亮点',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'更正贡献',exact:true}).click();await page.getByLabel('贡献状态',{exact:true}).selectOption('proposed');await page.getByRole('button',{name:'确认保存贡献',exact:true}).click();await expect(page.getByText('简历 v1 · 待复核',{exact:true})).toBeVisible();
 await page.reload();await page.getByText('历史生成与证据工具（兼容入口）',{exact:true}).click();await expect(page.getByText('简历 v1 · 待复核',{exact:true})).toBeVisible();expect(errors).toEqual([]);
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});



test('restores model resume when default arrays are omitted',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const workspace={id:'regression',interest:'测试项目',role:'Agent工程师',skills:'',time_budget:'',environment:'',snapshots:[],runs:[],jd_versions:[],messages:[],contributions:[],evidence:[],experiments:[],attempts:[],memory_events:[],artifacts:[{id:'a',type:'resume',version:1,review_status:'current',content:'项目简介\n技术亮点\n- **主题**：机制\n项目成果',claims:[{kind:'writing_review',iterations:1,status:'passed',selection:{selected:[{title:'主题',source_refs:['overview'],state:'project_existing'}]},reviews:[]}]}]};
 await page.route('**/api/workspaces',r=>r.fulfill({json:[workspace]}));
 await page.route('**/api/workspaces/regression?summary=true',r=>r.fulfill({json:workspace}));
 await page.addInitScript(()=>localStorage.setItem('repocareer.workspace','regression'));
 await page.goto('/?view=admin');
 await expect(page.getByRole('heading',{name:'04 · 项目讨论与简历参考稿'})).toBeVisible();
 await page.getByText('历史生成与证据工具（兼容入口）',{exact:true}).click();await page.getByText('简历 v1 · 当前事实生成',{exact:true}).click();
 await page.getByText('查看岗位亮点评选依据（HR / 技术面试官视角）',{exact:true}).click();
 await expect(page.getByRole('heading',{name:'1. 主题',exact:true})).toBeVisible();
 expect(errors).toEqual([]);
});

test('generation submits edited role and JD including explicit empty values',async({page})=>{
 const workspace={id:'target-regression',interest:'目标传递测试',role:'旧岗位',snapshots:[],runs:[],jd_versions:[{id:'old-jd',raw_text:'旧JD'}],messages:[],contributions:[],evidence:[],artifacts:[]};
 const requests:any[]=[];
 await page.route('**/api/workspaces/target-regression/interaction',r=>r.fulfill({json:{version:'fixture',role:workspace.role,jd:'旧JD',metrics:[],improvements:[],contributions:[],proposals:[],resume_versions:[],stale_reasons:[],actions:[],current_resume:null}}));
 await page.route('**/api/workspaces',r=>r.fulfill({json:[workspace]}));
 await page.route('**/api/workspaces/target-regression?summary=true',r=>r.fulfill({json:workspace}));
 await page.route('**/api/workspaces/target-regression/artifacts',r=>{
  requests.push(r.request().postDataJSON());return r.fulfill({status:502,json:{error:{message:'离线拦截，不调用模型'}}});
 });
 await page.addInitScript(()=>localStorage.setItem('repocareer.workspace','target-regression'));
 await page.goto('/?view=admin');
 await expect(page.getByLabel('岗位名称',{exact:true})).toHaveValue('旧岗位');
 await expect(page.getByLabel('岗位JD',{exact:true})).toHaveValue('旧JD');
 await page.getByLabel('岗位名称',{exact:true}).fill('AI应用工程师');
 await page.getByLabel('岗位JD',{exact:true}).fill('新JD：多智能体任务编排');
 await page.getByText('历史生成与证据工具（兼容入口）',{exact:true}).click();const generate=page.getByRole('button',{name:'生成项目简历参考稿',exact:true});
 await generate.click();await expect(page.getByRole('alert')).toContainText('离线拦截');
 expect(requests[0].target_role).toBe('AI应用工程师');expect(requests[0].target_jd).toBe('新JD：多智能体任务编排');
 await page.getByLabel('岗位JD',{exact:true}).fill('');await generate.click();
 await expect.poll(()=>requests.length).toBe(2);await expect(generate).toBeEnabled();
 expect(requests[1].target_jd).toBe('');
 await page.getByLabel('岗位名称',{exact:true}).fill('');await generate.click();
 await expect.poll(()=>requests.length).toBe(3);
 expect(requests[2].target_role).toBe('');
});

test('current audit displays unknown evidence and independent review feedback',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const audit={kind:'writing_review',iterations:1,status:'needs_review',requirements:{requirements:[{requirement_id:'r1',description:'任务编排'}]},
  job_evidence:[{requirement_id:'r1',question:'如何编排任务？',status:'unknown'},{requirement_id:'r2',status:'candidates_need_verification',candidate_evidence:[{}]}],
  reviews:[{perspectives:[{perspective:'hr',approved:false,feedback:[{category:'expression',issue:'需要交代项目整体主线',blocking:false,part_ids:['intro']}]},{perspective:'technical',approved:false,feedback:[{category:'needs_evidence',issue:'缺少任务恢复证据',blocking:true,candidate_ids:['n1'],paths:['lib/runtime.ts']}]}]}]};
 const workspace={id:'audit-regression',interest:'审查测试',role:'AI工程师',snapshots:[],runs:[],jd_versions:[],messages:[],contributions:[],evidence:[],artifacts:[{id:'a',type:'resume',version:1,review_status:'needs_review',content:'项目简介\n技术亮点\n- **主题**：机制',claims:[audit]}]};
 await page.route('**/api/workspaces',r=>r.fulfill({json:[workspace]}));
 await page.route('**/api/workspaces/audit-regression?summary=true',r=>r.fulfill({json:workspace}));
 await page.addInitScript(()=>localStorage.setItem('repocareer.workspace','audit-regression'));
 await page.goto('/?view=admin');await page.getByText('历史生成与证据工具（兼容入口）',{exact:true}).click();await page.getByText('简历 v1 · 待复核',{exact:true}).click();
 await page.getByText('JD问题与候选证据',{exact:true}).click();
 await expect(page.getByText('任务编排',{exact:true})).toBeVisible();
 await expect(page.getByText('尚未找到候选证据 · 0 段',{exact:true})).toBeVisible();
 await expect(page.getByText('找到候选，尚待核验 · 1 段',{exact:true})).toBeVisible();
 await page.getByText('独立双评审结果',{exact:true}).click();
 await expect(page.getByText('表达修改 · 审查建议：需要交代项目整体主线',{exact:true})).toBeVisible();
 await expect(page.getByText('需补材料 · 阻断问题：缺少任务恢复证据',{exact:true})).toBeVisible();
 await expect(page.getByText('待核对来源：lib/runtime.ts',{exact:true})).toBeVisible();
 expect(errors).toEqual([]);
});


test('failed generation refreshes terminal status and preserves saved resume',async({page})=>{
 const workspace={id:'terminal-regression',interest:'测试',role:'AI工程师',snapshots:[],runs:[],jd_versions:[],messages:[],contributions:[],evidence:[],artifacts:[{id:'a',type:'resume',version:17,review_status:'needs_review',content:'旧稿',claims:[]}]};
 let failed=false;
 await page.route('**/api/workspaces',r=>r.fulfill({json:[workspace]}));
 await page.route('**/api/workspaces/terminal-regression?summary=true',r=>r.fulfill({json:{...workspace,runs:failed?[{id:'r',request:{resume_generation:true},status:'failed',steps:[{stage:'CONTRACT'}],error:'候选引用失败'}]:[]}}));
 await page.route('**/api/workspaces/terminal-regression/artifacts',async r=>{failed=true;await r.fulfill({status:502,json:{error:{message:'候选引用失败'}}});});
 await page.addInitScript(()=>localStorage.setItem('repocareer.workspace','terminal-regression'));
 await page.goto('/?view=admin');
 await expect(page.getByLabel('岗位名称',{exact:true})).toHaveValue('AI工程师');
 if(!await page.getByRole('button',{name:'生成项目简历参考稿',exact:true}).isVisible())await page.getByText('历史生成与证据工具（兼容入口）',{exact:true}).click();await page.getByRole('button',{name:'生成项目简历参考稿',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('failed · CONTRACT');
 await expect(page.getByText('简历 v17 · 待复核',{exact:true})).toBeVisible();
});
