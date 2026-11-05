import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import PROJECT_ROOT, Settings


class ConfigTests(unittest.TestCase):
    def test_data_root_updates_all_unset_children(self):
        config = Settings.from_env({'DATA_DIR': './custom-data'})
        root = (PROJECT_ROOT / 'custom-data').resolve()
        self.assertEqual(config.policy_path('work_labor'), root / 'raw' / 'policies' / 'work_labor')
        self.assertEqual(config.csv_dir, root / 'raw' / 'csv')
        self.assertEqual(config.chunks_dir, root / 'processed' / 'chunks')
        self.assertEqual(config.chroma_dir, PROJECT_ROOT.parent / 'kdn_regulations_rag' / 'rag_data' / 'chroma_db')
        self.assertEqual(config.sqlite_path, root / 'app.sqlite3')
        self.assertEqual(config.embedding_cache_dir, root / 'models')
        self.assertEqual(config.user_data_path, root / 'raw' / 'users.json')

    def test_specific_paths_override_derived_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Settings.from_env({
                'DATA_DIR': directory, 'VECTOR_DIR': './indexes', 'CHROMA_DIR': str(Path(directory) / 'chroma'),
                'PROCESSED_DIR': './work', 'CHUNKS_DIR': '',
            })
            self.assertEqual(config.vector_dir, PROJECT_ROOT / 'indexes')
            self.assertEqual(config.chunks_dir, PROJECT_ROOT / 'work' / 'chunks')
            self.assertEqual(config.chroma_dir, Path(directory).resolve() / 'chroma')

    def test_working_directory_does_not_change_relative_paths(self):
        # 파일이나 DB를 생성하지 않고 현재 실행 위치만 바꿉니다.
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                config = Settings.from_env({'DATA_DIR': './data'})
            finally:
                os.chdir(original)
        self.assertEqual(config.data_dir, PROJECT_ROOT / 'data')

    def test_settings_report_excludes_secrets(self):
        config = Settings.from_env({'MYSQL_PASSWORD': 'private-value', 'N8N_WEBHOOK_URL': 'https://private-webhook.example/hook'})
        self.assertNotIn('private-value', repr(config))
        self.assertNotIn('https://private-webhook.example/hook', repr(config))
        self.assertNotIn('mysql_password', config.paths())
        self.assertNotIn('n8n_webhook_url', config.paths())

    def test_invalid_options_and_domain_paths_are_rejected(self):
        for env in ({'MYSQL_PORT': '0'}, {'MYSQL_PORT': 'wrong'}, {'VECTOR_BACKEND': 'unknown'}, {'HISTORY_MESSAGE_LIMIT': '50'}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                Settings.from_env(env)
        with self.assertRaises(ValueError):
            Settings.from_env({}).policy_path('../outside')

    def test_n8n_event_names_are_loaded_and_validated(self):
        self.assertEqual(Settings.from_env({'N8N_EVENT_SESSION_END':'finish','N8N_EVENT_FEEDBACK':'rating'}).n8n_event_feedback,'rating')
        self.assertEqual(Settings.from_env({}).n8n_event_session_end,'end')
        for fields in [{'N8N_EVENT_ANSWER':''},{'N8N_EVENT_ANSWER':'question'},{'N8N_EVENT_ANSWER':'bad name'}]:
            with self.subTest(fields=fields),self.assertRaises(ValueError):
                Settings.from_env(fields)

    def test_prompt_and_chroma_consumers_use_settings(self):
        from app.integrations.ollama import OllamaClient
        from app.rag.vector_store import ChromaVectorStore
        from app.schemas import AnswerContext
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'answer_system.txt').write_text('custom prompt', encoding='utf-8')
            config = Settings.from_env({'PROMPTS_DIR': directory, 'CHROMA_DIR': directory, 'CHROMA_COLLECTION': 'test_policies'})
            with patch('app.integrations.ollama.settings', config):
                messages = OllamaClient.build_messages(AnswerContext(question='hello', employee_id='TEST'))
            self.assertEqual(messages[0]['content'], 'custom prompt')
            with patch('app.rag.vector_store.settings', config):
                store = ChromaVectorStore()
                self.assertEqual(store.directory, Path(directory))
                self.assertEqual(store.collection_name, 'test_policies')


if __name__ == '__main__':
    unittest.main()
