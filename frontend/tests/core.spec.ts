import {test,expect} from '@playwright/test';

test('repository alone can start analysis and resume entry points are gone',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 const w=await (await page.request.post('/api/workspaces',{data:{interest:'项目分析流程',role:'待填写'}})).json();
 await page.addInitScript(id=>localStorage.setItem('repocareer.workspace',id),w.id);await page.goto('/?view=admin');
 await page.getByLabel('GitHub仓库链接').fill('https://github.com/example/document-agent');await page.getByRole('button',{name:'保存仓库链接',exact:true}).click();
 await expect(page.getByRole('status')).toContainText('GitHub链接已保存');await expect(page.getByLabel('岗位名称',{exact:true})).toHaveValue('');
 await page.getByText('分析服务与演示说明').click();await page.getByRole('checkbox').check();await page.getByRole('button',{name:'分析项目全貌与优化方向 →'}).click();
 await expect(page.getByText('演示文档助手项目，不是上传仓库的分析。',{exact:true})).toBeVisible({timeout:15000});
 await expect(page.getByRole('button',{name:/生成.*简历|项目经历编辑器/})).toHaveCount(0);
 await page.goto('/');await page.getByRole('button',{name:'查看项目全貌'}).click();
 await expect(page.getByRole('navigation',{name:'Wiki章节'})).toBeVisible();await expect(page.getByRole('complementary',{name:'项目聊天窗口'})).toBeVisible();
 await expect(page.getByRole('button',{name:'发送问题',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'向项目提问',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'优化大方向',exact:true}).click();await expect(page.getByRole('button',{name:'发送讨论',exact:true})).toBeDisabled();
 await expect(page.getByRole('button',{name:'生成简历',exact:true})).toHaveCount(0);expect(errors).toEqual([]);
});

async function fixture(page:any){
 const w={id:'wiki-fixture',interest:'问答测试',role:'工程师',snapshots:[],jd_versions:[],messages:[],events:[],improvements:[{id:'direction-one',status:'proposed',details:{title:'版本校验方案',proposal:'比较失败处理；尚未实施'}}],contributions:[],evidence:[],artifacts:[],runs:[{id:'wiki-run',status:'completed',request:{architecture:true},steps:[],result:{mode:'real',wiki:{generated_pages:{one:{title:'任务编排',content:'# 调度机制\n\n**并行执行**'},two:{title:'状态管理',content:'版本检查'}}}}}]};
 await page.route('**/api/workspaces', (r:any)=>r.fulfill({json:[w]}));
 await page.route('**/api/workspaces/wiki-fixture?summary=true',(r:any)=>r.fulfill({json:w}));
 await page.route('**/api/workspaces/wiki-fixture/interaction',(r:any)=>r.fulfill({json:{version:'fixture'}}));
 const requests:any[]=[],cancels:any[]=[];let messages:any[]=[],revision=0;
 await page.route('**/api/workspaces/wiki-fixture/conversations**',(r:any)=>{
  const url=r.request().url();
  if(url.endsWith('/turns')){const body=r.request().postDataJSON();requests.push(body);revision+=2;messages.push({id:'u'+requests.length,role:'user',content:body.content,proposal:{discussion:{status:'completed'}}});messages.push({id:'a'+requests.length,role:'assistant',content:'本轮回答'+requests.length,proposal:{discussion:{status:'completed'}}});return r.fulfill({contentType:'application/x-ndjson',body:'{"delta":"本轮回答'+requests.length+'"}\n{"done":true}\n'});}
  if(url.endsWith('/cancel')){cancels.push(r.request().postDataJSON());return r.fulfill({json:{cancelled:true}});}
  return r.fulfill({json:{id:'conv',revision,data:{topics:[]},messages,message_count:messages.length,memories:[],pending_requests:[]}});
 });
 await page.addInitScript(()=>localStorage.setItem('repocareer.workspace','wiki-fixture'));await page.goto('/');return {requests,cancels};
}

test('limited chapter clearly shows unconfirmed scope without hiding content',async({page})=>{
 await fixture(page);
 await page.route('**/api/workspaces/wiki-fixture?summary=true',r=>r.fulfill({json:{id:'wiki-fixture',role:'工程师',snapshots:[],jd_versions:[],messages:[],events:[],improvements:[],contributions:[],evidence:[],artifacts:[],runs:[{id:'wiki-run',status:'completed',request:{architecture:true},steps:[],result:{wiki:{generated_pages:{one:{title:'材料范围',content:'已读取的具体材料',retrieval:{status:'limited',stop_reason:'no_progress',cached:false}}}}}}]}}));
 await page.reload();await page.getByRole('button',{name:'查看项目全貌'}).click();
 await expect(page.getByLabel('章节证据范围')).toContainText('本章存在未确认范围');
 await expect(page.getByLabel('章节证据范围')).toContainText('no_progress');
 await expect(page.locator('.wiki-reading>article')).toContainText('已读取的具体材料');
});

test('analysis time freezes after completion and opens readable steps',async({page})=>{
 await fixture(page);
 await page.route('**/api/workspaces/wiki-fixture?summary=true',r=>r.fulfill({json:{id:'wiki-fixture',role:'工程师',snapshots:[],jd_versions:[],messages:[],events:[],improvements:[],contributions:[],evidence:[],artifacts:[],runs:[{id:'clock-run',status:'completed',request:{architecture:true},steps:[{summary:'已核对项目材料'}],result:{elapsed_seconds:44}}]}}));
 await page.reload();await expect(page.getByLabel('分析用时与阶段')).toHaveText('用时 44秒›');
 await page.getByLabel('分析用时与阶段').click();await expect(page.getByRole('region',{name:'分析阶段记录'})).toContainText('已核对项目材料');
 await page.route('**/api/analysis-history',r=>{expect(r.request().method()).toBe('DELETE');return r.fulfill({json:{deleted_count:2,protected_count:0}});});
 await page.getByRole('button',{name:'清除所有项目分析历史',exact:true}).click();await expect(page.getByRole('status')).toContainText('2 条分析历史');
});

test('running analysis time advances each second',async({page})=>{
 const started=new Date();await page.clock.install({time:new Date(started.getTime()-1000)});await page.clock.pauseAt(started);await fixture(page);
 await page.route('**/api/workspaces/wiki-fixture?summary=true',r=>r.fulfill({json:{id:'wiki-fixture',role:'工程师',snapshots:[],jd_versions:[],messages:[],events:[],improvements:[],contributions:[],evidence:[],artifacts:[],runs:[{id:'live-clock',status:'running',created_at:started.toISOString(),request:{architecture:true},steps:[],result:{analysis_started_at:started.toISOString()}}]}}));
 await page.reload();await expect(page.getByLabel('分析用时与阶段')).toContainText('用时 0秒');
 await page.clock.fastForward(3000);await expect(page.getByLabel('分析用时与阶段')).toContainText('用时 3秒');
});

test('user progress shows automatic index preparation counts',async({page})=>{
 await fixture(page);
 await page.route('**/api/workspaces/wiki-fixture?summary=true',r=>r.fulfill({json:{id:'wiki-fixture',role:'工程师',snapshots:[],jd_versions:[],messages:[],events:[],improvements:[],contributions:[],evidence:[],artifacts:[],runs:[{id:'index-run',status:'running',created_at:new Date().toISOString(),request:{architecture:true},steps:[{tool:'deepwiki_index',summary:'索引准备 · 缓存复用 16 · 新向量 100/3388 · 剩余 3288'}],result:{}}]}}));
 await page.reload();await expect(page.locator('.progress-line')).toContainText('100/3388');await expect(page.locator('.progress-line')).toContainText('缓存复用 16');
});

test('sidebar changes content and each question carries current chapter',async({page})=>{
 const {requests}=await fixture(page);await page.getByRole('button',{name:'查看项目全貌'}).click();
 await expect(page.getByRole('heading',{name:'调度机制'})).toBeVisible();
 const nav=page.getByRole('navigation',{name:'Wiki章节'}),article=page.locator('.wiki-reading>article');
 const n=await nav.boundingBox(),a=await article.boundingBox();expect(n!.x+n!.width).toBeLessThanOrEqual(a!.x);
 await page.getByLabel('向项目提问',{exact:true}).fill('如何调度？');await page.getByRole('button',{name:'发送问题',exact:true}).click();await expect(page.getByText('本轮回答1',{exact:true})).toBeVisible();
 await nav.getByRole('button',{name:'状态管理',exact:true}).click();await expect(article).toContainText('版本检查');
 await page.getByLabel('向项目提问',{exact:true}).fill('如何更新？');await page.getByRole('button',{name:'发送问题',exact:true}).click();await expect(page.getByText('本轮回答2',{exact:true})).toBeVisible();
 expect(requests[0].page_id).toBe('one');expect(requests[1].page_id).toBe('two');expect(requests[1].history).toBeUndefined();
 await page.reload();await page.getByRole('button',{name:'查看项目全貌'}).click();await expect(page.getByText('本轮回答1',{exact:true})).toBeVisible();
});

test('floating chat moves resizes collapses and fits a phone viewport',async({page})=>{
 await fixture(page);await page.getByRole('button',{name:'查看项目全貌'}).click();
 const chat=page.getByRole('complementary',{name:'项目聊天窗口'}),drag=page.getByRole('button',{name:'移动聊天框'});const before=await chat.boundingBox();const handle=await drag.boundingBox();
 await page.mouse.move(handle!.x+50,handle!.y+10);await page.mouse.down();await page.mouse.move(handle!.x-80,handle!.y+50,{steps:5});await page.mouse.up();const moved=await chat.boundingBox();expect(moved!.x).toBeLessThan(before!.x);expect(moved!.y).toBeGreaterThan(before!.y);
 await page.getByRole('button',{name:'放大聊天框'}).click();const big=await chat.boundingBox();expect(big!.width).toBeGreaterThan(moved!.width);
 await page.getByRole('button',{name:'缩小聊天框'}).click();const small=await chat.boundingBox();expect(small!.width).toBeLessThan(big!.width);
 const corner=await page.getByRole('button',{name:'调整聊天框大小'}).boundingBox();await page.mouse.move(corner!.x+5,corner!.y+5);await page.mouse.down();await page.mouse.move(corner!.x+45,corner!.y+35,{steps:4});await page.mouse.up();expect((await chat.boundingBox())!.width).toBeGreaterThan(small!.width);
 await page.getByRole('button',{name:'收起聊天框'}).click();await expect(page.getByLabel('向项目提问',{exact:true})).not.toBeVisible();await page.getByRole('button',{name:'展开聊天框'}).click();await expect(page.getByLabel('向项目提问',{exact:true})).toBeVisible();
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);const mobile=await chat.boundingBox();expect(mobile!.x).toBeGreaterThanOrEqual(0);expect(mobile!.x+mobile!.width).toBeLessThanOrEqual(390);await page.screenshot({path:test.info().outputPath('project-chat-mobile.png'),fullPage:true});
});

test('direction discussion sends selected proposal identity without business writes',async({page})=>{
 const {requests}=await fixture(page);await page.getByRole('button',{name:'优化大方向',exact:true}).click();await page.getByRole('button',{name:'讨论此方向'}).click();
 await expect(page.getByText('当前讨论：版本校验方案',{exact:true})).toBeVisible();await page.getByLabel('项目讨论',{exact:true}).fill('这个方案的取舍是什么？');await page.getByRole('button',{name:'发送讨论',exact:true}).click();await expect(page.getByText('本轮回答1',{exact:true})).toBeVisible();expect(requests[0].improvement_id).toBe('direction-one');
});

test('empty project explains the repository flow',async({page})=>{
 await page.route('**/api/workspaces',r=>r.fulfill({json:[]}));await page.goto('/');
 for(const name of ['项目设置','项目全貌','优化大方向'])await expect(page.getByRole('button',{name,exact:true})).toBeInViewport();
 await page.getByRole('button',{name:'项目全貌',exact:true}).click();await expect(page.getByText('先保存一个 GitHub 仓库链接，或在顶部选择已有项目。',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'项目经历编辑器',exact:true})).toHaveCount(0);
});

test('failed stream keeps completed history and does not save partial answer',async({page})=>{
 await fixture(page);await page.getByRole('button',{name:'查看项目全貌'}).click();
 await page.getByLabel('向项目提问',{exact:true}).fill('第一轮');await page.getByRole('button',{name:'发送问题',exact:true}).click();await expect(page.getByText('本轮回答1',{exact:true})).toBeVisible();
 await page.route('**/conversations/conv/turns',r=>r.fulfill({contentType:'application/x-ndjson',body:'{"delta":"失败部分"}\n{"error":"连接超时"}\n'}));
 await page.getByLabel('向项目提问',{exact:true}).fill('第二轮');await page.getByRole('button',{name:'发送问题',exact:true}).click();await expect(page.getByRole('alert')).toHaveText('连接超时');await expect(page.getByText('失败部分',{exact:true})).toHaveCount(0);await expect(page.getByText('本轮回答1',{exact:true})).toBeVisible();
});

test('stop and leaving the page cancel pending requests without showing late answers',async({page})=>{
 const {cancels}=await fixture(page);let started=0;const releases:(()=>Promise<void>)[]=[];
 await page.route('**/conversations/conv/turns',async r=>{started++;await new Promise<void>(resolve=>releases.push(async()=>{await r.fulfill({contentType:'application/x-ndjson',body:'{"delta":"晚到回答"}\n{"done":true}\n'}).catch(()=>{});resolve();}));});
 await page.getByRole('button',{name:'查看项目全貌'}).click();await page.getByLabel('向项目提问',{exact:true}).fill('等待回答');await page.getByRole('button',{name:'发送问题',exact:true}).click();await expect.poll(()=>started).toBe(1);
 await page.getByRole('button',{name:'停止回答',exact:true}).click();await expect.poll(()=>cancels.length).toBe(1);await releases[0]();await expect(page.getByRole('button',{name:'发送问题',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'发送问题',exact:true}).click();await expect.poll(()=>started).toBe(2);await page.getByRole('button',{name:'项目设置',exact:true}).click();await expect.poll(()=>cancels.length).toBe(2);await releases[1]();
 await page.getByRole('button',{name:'项目全貌',exact:true}).click();await expect(page.getByText('晚到回答',{exact:true})).toHaveCount(0);
});


test('advisor v2 shows decisions, technical comparison, references and keeps discussion',async({page})=>{
 await fixture(page);
 const source={source_id:'s1',kind:'repository_code',path:'memory.ts',locator:'https://github.com/example/demo/blob/'+ 'a'.repeat(40)+'/memory.ts#L1',excerpt:'fixed source',source_version:'a'.repeat(40),retrieved_at:'2026-10-16',read_status:'read'};
 const report={schema_version:'optimization-v2',overview:{summary:'项目规划'},coverage:{web_status:'未完成外部调研'},candidate_assessments:[{candidate_id:'c',title:'局部评测',decision:'validate_first',kind:'capability_deepening',effort:'低',rationale:'先建立基线',project_value:'回归',jd_relation:'深化',fit:'局部',verifiability:'离线',evidence_sufficiency:'partial',source_refs:['s1'],assumptions:[]},{candidate_id:'no',title:'分布式集群',decision:'not_recommended',kind:'engineering_fix',effort:'高',rationale:'已有机制满足需求且不符合时间预算',project_value:'有限',jd_relation:'无',fit:'不适配',verifiability:'未知',evidence_sufficiency:'partial',source_refs:['s1'],assumptions:[]}],directions:[{candidate_id:'c',title:'局部评测',goal:'回归',current_design:{statement:'当前源码机制',source_refs:['s1']},scenario:'测试',why_now:'验证',technical_options:[{name:'局部方案',mechanism:'添加用例',prerequisites:'运行测试',benefits_expected:'发现回归',costs:'维护',tradeoffs:'不证明线上收益',source_refs:['s1']}],reference_practices:[],recommended_design:{chosen_option:'局部方案',rationale:'保持简单',components:['测试'],execution_steps:['跑基线'],failure_handling:'保留日志'},code_changes:[{change_type:'add',path:'new.test.ts',responsibility:'回归',change_description:'新增用例',source_refs:[]}],implementation_steps:[{step_id:'one',action:'基线',dependencies:[],deliverable:'记录'}],validation_plan:[{scenario:'边界',baseline:'当前结果',method:'运行用例',metric_or_acceptance:'一致',measurement_status:'not_measured'}],assumptions:[]}],validation_actions:[],roadmap:[],unresolved_questions:[],no_change_reason:'',sources:[source]};
 const w={id:'wiki-fixture',interest:'x',role:'x',snapshots:[],jd_versions:[],messages:[],events:[],improvements:[{id:'direction-one',status:'proposed',details:{title:'局部评测',proposal:'保持简单'}}],runs:[{id:'r',status:'completed',request:{architecture:true},steps:[],result:{report,improvement_ids:['direction-one']}}]};
 await page.route('**/api/workspaces/wiki-fixture?summary=true',r=>r.fulfill({json:w}));await page.reload();await page.getByRole('button',{name:'优化大方向',exact:true}).click();
 await expect(page.getByText('分布式集群 · 暂不建议')).toBeVisible();
 await page.getByText('局部评测 · 回归 · 技术对比（1种）',{exact:true}).click();await expect(page.getByRole('heading',{name:'技术方案比较'})).toBeVisible();await expect(page.getByText('拟新增：',{exact:false})).toBeVisible();await expect(page.getByRole('link',{name:'memory.ts'}).first()).toHaveAttribute('href',new RegExp('/blob/a{40}/'));
 await page.getByRole('button',{name:'讨论此方向'}).click();await expect(page.getByRole('button',{name:'发送讨论',exact:true})).toBeVisible();
});


test('failed newest run hides historical system suggestions until explicitly requested',async({page})=>{
 await fixture(page);
 const w={id:'wiki-fixture',interest:'x',role:'x',snapshots:[],jd_versions:[],messages:[],events:[],improvements:[{id:'old',status:'proposed',details:{title:'Old English system proposal',proposal:'Old summary',run_id:'old-run'}}],runs:[{id:'latest-run',created_at:'2026-10-16T00:00:00Z',status:'failed',error:'needs validation',request:{architecture:true},steps:[],result:{}}]};
 await page.route('**/api/workspaces/wiki-fixture?summary=true',r=>r.fulfill({json:w}));await page.reload();await page.getByRole('button',{name:'优化大方向',exact:true}).click();
 await expect(page.getByLabel('当前优化版本')).toContainText('本轮失败');
 await expect(page.getByText('Old English system proposal',{exact:true})).toHaveCount(0);
 await page.getByLabel('查看历史系统建议（1）').check();await expect(page.getByText('Old English system proposal',{exact:true})).toBeVisible();await expect(page.getByText('历史系统建议，非本轮结果',{exact:true})).toBeVisible();
});
