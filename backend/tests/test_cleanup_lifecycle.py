import pytest
def test_target_and_jd_routes_share_terms_history_and_invalidation(client, wid):
    jd = client.post(f'/api/workspaces/{wid}/jd-versions',json={'content':'Multi-Agent 长期记忆'}).json()
    client.post(f'/api/workspaces/{wid}/target',json={'role':'AI开发','jd':'Multi-Agent 长期记忆'})
    assert len(client.get(f'/api/workspaces/{wid}').json()['jd_versions'])==1
    client.post(f'/api/workspaces/{wid}/target',json={'role':'AI开发','jd':'MCP 工具编排'})
    w = client.get(f'/api/workspaces/{wid}').json()
    latest = w['jd_versions'][-1]
    assert latest['requirements']==['MCP','工具编排']
    assert latest['supersedes_id']==jd['id'] and latest['version']==2
    client.post(f'/api/workspaces/{wid}/target',json={'role':'AI开发','jd':''})
    assert client.get(f'/api/workspaces/{wid}').json()['jd_versions'][-1]['requirements']==[]


def test_harness_checks_cancellation_before_any_provider_call():
    from fastapi import HTTPException
    from backend.app.analysis_harness import Harness
    import pytest
    def stopped():raise HTTPException(409,'cancelled')
    h = Harness(lambda p:(_ for _ in ()).throw(AssertionError('paid call')),check_active=stopped)
    with pytest.raises(HTTPException):h.call('WRITE\ntext')
    assert h.records==[]
