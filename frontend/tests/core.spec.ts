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
