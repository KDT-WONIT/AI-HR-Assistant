"""테스트 데이터와 임시 모델도 프로젝트 내부 .runtime에만 만듭니다."""
import os
from pathlib import Path
import shutil
import uuid

import pytest
from employee_tools import paths

SOURCE_PACKAGE = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='session')
def test_storage():
    directory = SOURCE_PACKAGE.parent / '.runtime' / 'tests' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    return directory


@pytest.fixture
def tmp_path(test_storage):
    directory = test_storage / uuid.uuid4().hex
    directory.mkdir()
    return directory


@pytest.fixture(autouse=True)
def project_root(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'PROJECT_ROOT', tmp_path)
    package = tmp_path / 'employee_tools'
    package.mkdir()
    shutil.copyfile(SOURCE_PACKAGE / 'sql_queries.json', package / 'sql_queries.json')
    keys = ['HF_HOME', 'HF_HUB_CACHE', 'HF_XET_CACHE', 'SENTENCE_TRANSFORMERS_HOME',
            'TORCH_HOME', 'XDG_CACHE_HOME', 'HF_TOKEN_PATH', 'HF_HUB_DISABLE_IMPLICIT_TOKEN',
            'HF_HUB_DISABLE_TELEMETRY']
    original = {key: os.environ.get(key) for key in keys}
    yield tmp_path
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
