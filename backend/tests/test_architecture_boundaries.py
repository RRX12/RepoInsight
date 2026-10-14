from scripts.check_architecture import check


def app(tmp_path,files):
    folder=tmp_path/'backend/app';folder.mkdir(parents=True)
    for name,text in files.items():(folder/(name+'.py')).write_text(text,encoding='utf-8')
    return tmp_path


def test_no_legacy_bridge_exception_remains(tmp_path):
    root=app(tmp_path,{'resume_writer':"def write_legacy():\n    from .resume_legacy import write_legacy as baseline\n    return baseline()\n\ndef write():\n    from .resume_legacy import write_legacy\n",'resume_legacy':''})
    errors=check(root)
    assert len(errors)==2 and all('A01' in e for e in errors)
    assert ':2:' in errors[0] and ':6:' in errors[1]


def test_all_import_forms_and_production_bridge_call_are_detected(tmp_path):
    root=app(tmp_path,{'service':"from backend.app import resume_legacy\nimport backend.app.resume_legacy as old\nfrom .resume_writer import write_legacy as old_write\nimport importlib\nimportlib.import_module('backend.app.resume_legacy')\nwriter.write_legacy()\n"})
    errors=check(root)
    assert len(errors)==5 and all('A01' in e for e in errors)


def test_contract_transitive_dependency_reports_chain_without_importing_code(tmp_path):
    root=app(tmp_path,{'resume_contract':'from .source_reader import SourceEvidence\n','source_reader':'from .artifact_service import create_artifact\nraise RuntimeError("must not execute")\n','artifact_service':''})
    errors=check(root)
    assert len(errors)==1 and 'A02' in errors[0]
    assert 'resume_contract -> source_reader -> artifact_service' in errors[0]


def test_allowed_current_directions_and_eval_are_preserved(tmp_path):
    root=app(tmp_path,{'schemas':'','architecture_schema':'from .schemas import Strict\n','resume_contract':'from .source_reader import SourceEvidence\n','source_reader':'from .db import DATA\n','db':'','resume_legacy':'from .resume_support import WritingModel\n','resume_support':'from .memory import scoped\n','memory':'from .schemas import Strict\n'})
    assert check(root)==[]


def test_new_subpackage_and_aliased_dynamic_import_do_not_escape_check(tmp_path):
    root=app(tmp_path,{'schemas':'from .feature import helper\n','artifact_service':''})
    folder=root/'backend/app/feature';folder.mkdir()
    (folder/'helper.py').write_text('from ..artifact_service import create_artifact\nfrom importlib import import_module as load\nload("backend.app.resume_legacy")\n',encoding='utf-8')
    errors=check(root)
    assert any('A01' in e for e in errors)
    assert any('schemas -> feature.helper -> artifact_service' in e for e in errors)
