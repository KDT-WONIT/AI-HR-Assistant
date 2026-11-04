"""폴더 이동, 외부 경로 거부, 모델 내부 준비 흐름을 검증합니다."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import ModuleType, SimpleNamespace

import pytest

from employee_tools import paths
from employee_tools.common import ToolError
from employee_tools.database import SqliteRepository
from employee_tools.rag_search_tool import RegulationSearch, _load_model
from employee_tools.prepare_model import prepare_model, select_model_files


def write_model_db(project_root):
    path = project_root / 'data/rag_data/chroma_db/chroma.sqlite3'
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE collections (id TEXT, name TEXT)')
        connection.execute('CREATE TABLE collection_metadata (collection_id TEXT, key TEXT, str_value TEXT, int_value INTEGER)')
        connection.execute('INSERT INTO collections VALUES (?,?)', ('id','kdn_regulations_bge_m3_v1'))
        connection.executemany('INSERT INTO collection_metadata VALUES (?,?,?,?)', [
            ('id','embedding_model','BAAI/bge-m3',None),
            ('id','embedding_revision','test-commit',None),
            ('id','embedding_dimension',None,1024)])


def test_default_paths_ignore_current_working_directory(project_root, monkeypatch):
    monkeypatch.chdir(project_root.parent)
    assert paths.employee_db_path() == project_root / 'data/employee/employee.sqlite3'
    assert RegulationSearch().database_path == project_root / 'data/rag_data/chroma_db'
    assert paths.embedding_model_path() == project_root / 'models/bge-m3'


def test_old_external_environment_variables_are_ignored(project_root, monkeypatch):
    for name in ['EMPLOYEE_DB_PATH', 'RAG_DATA_DIR', 'EMPLOYEE_SQL_PATH']:
        monkeypatch.setenv(name, str(project_root.parent / 'outside.sqlite3'))
    file = paths.employee_db_path()
    file.parent.mkdir(parents=True)
    with sqlite3.connect(file) as connection:
        connection.execute('CREATE TABLE employees (employee_id TEXT, name TEXT, department TEXT, job_title TEXT, travel_grade TEXT)')
        connection.execute('INSERT INTO employees VALUES (?,?,?,?,?)', ('000123','테스트','개발','사원','grade_3'))
    repository = SqliteRepository()
    assert repository.db_path == file
    assert repository.get_employee('000123')['employee_id'] == '000123'
    assert RegulationSearch().database_path == project_root / 'data/rag_data/chroma_db'


@pytest.mark.parametrize('kind', ['relative_parent', 'absolute', 'rag'])
def test_external_paths_are_rejected(project_root, kind):
    with pytest.raises(ToolError, match='프로젝트 폴더 내부'):
        if kind == 'relative_parent':
            paths.employee_db_path('../outside.sqlite3')
        elif kind == 'absolute':
            SqliteRepository(project_root.parent / 'outside.sqlite3')
        else:
            RegulationSearch(project_root.parent / 'outside_rag')


def test_missing_employee_database_is_not_created(project_root):
    with pytest.raises(ToolError):
        SqliteRepository()
    assert not paths.employee_db_path().exists()


def test_model_caches_are_inside_project(project_root):
    paths.configure_model_cache()
    for name in ['HF_HOME','HF_HUB_CACHE','HF_XET_CACHE','SENTENCE_TRANSFORMERS_HOME','TORCH_HOME','XDG_CACHE_HOME']:
        assert Path(os.environ[name]).resolve().is_relative_to(project_root)
    assert Path(os.environ['HF_TOKEN_PATH']).is_relative_to(project_root)


def test_dense_model_files_only():
    selected = select_model_files(['config.json','model.safetensors','pytorch_model.bin','1_Pooling/config.json',
                                   'onnx/model.onnx','colbert_linear.pt','custom.py'])
    assert selected == ['1_Pooling/config.json','config.json','model.safetensors']
    with pytest.raises(ToolError):
        select_model_files(['model.safetensors','1_Pooling/../../outside'])


def test_model_download_uses_internal_folder_and_can_be_reused(project_root, monkeypatch):
    write_model_db(project_root)
    calls = []
    fake = ModuleType('huggingface_hub')
    class Api:
        def __init__(self, token):
            assert token is False
        def model_info(self, name, revision, files_metadata):
            assert (name, revision, files_metadata) == ('BAAI/bge-m3','test-commit',True)
            return SimpleNamespace(siblings=[SimpleNamespace(rfilename=name) for name in
                                   ['config.json','modules.json','model.safetensors','1_Pooling/config.json']])
    def download(**kwargs):
        destination = Path(kwargs['local_dir'])
        assert destination == project_root / 'models/bge-m3'
        assert kwargs['token'] is False
        calls.append(kwargs)
        for name in kwargs['allow_patterns']:
            file = destination / name
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes(b'TEST DATA ONLY')
    fake.HfApi, fake.snapshot_download = Api, download
    monkeypatch.setitem(sys.modules, 'huggingface_hub', fake)
    result = prepare_model()
    assert result['revision'] == 'test-commit'
    assert (project_root / 'models/bge-m3/model_manifest.json').is_file()
    assert prepare_model() == result
    assert len(calls) == 1


def test_missing_internal_model_does_not_use_global_cache():
    with pytest.raises(ToolError) as captured:
        _load_model('BAAI/bge-m3','missing-test-commit','cpu')
    assert captured.value.code == 'MODEL_NOT_READY'


def test_mismatched_model_manifest_is_rejected(project_root):
    model = project_root / 'models/bge-m3'
    model.mkdir(parents=True)
    (model/'model_manifest.json').write_text(json.dumps({'model_name':'BAAI/bge-m3','revision':'wrong'}),encoding='utf-8')
    with pytest.raises(ToolError) as captured:
        _load_model('BAAI/bge-m3','expected-test-commit','cpu')
    assert captured.value.code == 'MODEL_REVISION_MISMATCH'
