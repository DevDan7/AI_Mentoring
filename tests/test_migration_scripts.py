"""Pruebas de los scripts de migración (Fase 7).

Usa un recurso DynamoDB simulado en memoria para validar el comportamiento de
migrate_clean.py y migrate_restore.py sin tocar AWS: modos --dry-run,
--export-only, confirmación SI/cancelación, seed de la turma beta, inmutabilidad
de MentoringQuestions y restauración de backups.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from decimal import Decimal  # noqa: E402

import migrate_clean  # noqa: E402
import migrate_restore  # noqa: E402

PROJECT = 'AI_Mentoring'
ENV = 'dev'


class FakeTable:
    def __init__(self, name, key, items=None):
        self.name = name
        self.key = key
        self._items = {}
        for item in (items or []):
            self._items[item[key]] = item
        self.delete_calls = 0
        self.put_items = []

    def scan(self, **kwargs):
        items = list(self._items.values())
        result = {'Items': items, 'Count': len(items)}
        if kwargs.get('Select') == 'COUNT':
            return result
        return result

    def put_item(self, **kwargs):
        item = kwargs['Item']
        self._items[item[self.key]] = item
        self.put_items.append(item)
        return {}

    def delete_item(self, **kwargs):
        key = kwargs['Key']
        self._items.pop(key[self.key], None)
        self.delete_calls += 1
        return {}

    def batch_writer(self):
        return _BatchWriter(self)

    def get_item(self, **kwargs):
        key = kwargs.get('Key', {})
        item = self._items.get(key.get(self.key))
        return {'Item': item} if item is not None else {}


class _BatchWriter:
    def __init__(self, table):
        self.table = table

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def delete_item(self, **kwargs):
        self.table.delete_item(**kwargs)

    def put_item(self, **kwargs):
        self.table.put_item(**kwargs)


class FakeResource:
    def __init__(self, tables):
        self.tables = tables  # {nombre de tabla: FakeTable}

    def Table(self, name):
        if name not in self.tables:
            raise KeyError(f'Tabla inexistente en el fake: {name}')
        return self.tables[name]


def build_defs():
    return migrate_clean.table_defs(PROJECT, ENV)


def student_item(student_id, cohort_id=None):
    item = {
        'StudentID': student_id,
        'Email': f'{student_id}@example.com',
        'Name': f'Student {student_id}',
        'CurrentPhase': 'initial',
        'PhaseHistory': [],
        'FailedAttempts': {'final_exam': 0},
        'AccessExpiresAt': '2026-10-01T00:00:00+00:00',
        'CreatedAt': '2026-01-01T00:00:00+00:00',
    }
    if cohort_id:
        item['CohortID'] = cohort_id
    return item


def quiz_item(quiz_id, student_id):
    return {
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuizType': 'free',
        'Topic': 'Compute & Containers',
        'Questions': ['q1'],
        'Status': 'completed',
        'CreatedAt': '2026-01-01T00:00:00+00:00',
        'ScorePercentage': Decimal('66.7'),
    }


def result_item(result_id, quiz_id):
    return {
        'ResultID': result_id,
        'QuizID': quiz_id,
        'StudentID': 'student-1',
        'QuestionID': 'q1',
        'GivenAnswers': ['A'],
        'CorrectAnswers': ['A'],
        'IsCorrect': True,
        'Timestamp': '2026-01-01T00:00:00+00:00',
    }


def cohort_item(cohort_id='turma-0', name='Turma 0'):
    return {
        'CohortID': cohort_id,
        'Name': name,
        'MaxStudents': Decimal('5'),
    }


def mq_item(question_id='q1'):
    return {
        'QuestionID': question_id,
        'Topic': 'Compute & Containers',
        'QuestionText': 'Statement',
        'Options': {'A': {'text': 'A', 'is_correct': True, 'explanation': 'e'}},
        'ContentHash': 'hash-1',
    }


def make_resource():
    defs = build_defs()
    tables = {
        defs['students']['name']: FakeTable(defs['students']['name'], 'StudentID', [
            student_item('s1'), student_item('s2', cohort_id='turma-0'),
        ]),
        defs['quizzes']['name']: FakeTable(defs['quizzes']['name'], 'QuizID', [
            quiz_item('quiz-1', 's1'),
        ]),
        defs['quiz_results']['name']: FakeTable(defs['quiz_results']['name'], 'ResultID', [
            result_item('r1', 'quiz-1'),
        ]),
        defs['cohorts']['name']: FakeTable(defs['cohorts']['name'], 'CohortID', [
            cohort_item(),
        ]),
        migrate_clean.MENTORING_QUESTIONS_TABLE: FakeTable(
            migrate_clean.MENTORING_QUESTIONS_TABLE, 'QuestionID', [mq_item()]),
    }
    return FakeResource(tables), tables


class TestMigrateClean(unittest.TestCase):
    def setUp(self):
        self.resource, self.tables = make_resource()
        self.defs = build_defs()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _tables_report(self):
        return {label: len(self.tables[defn['name']]._items)
                for label, defn in self.defs.items()}

    def test_dry_run_does_not_mutate(self):
        result = migrate_clean.run_clean(
            self.resource, self.defs, timestamp='20260907_000000',
            dry_run=True, backup_dir=self.tmp.name)
        self.assertEqual(result['mode'], 'dry_run')
        self.assertEqual(result['counts'], {'students': 2, 'quizzes': 1,
                                            'quiz_results': 1, 'cohorts': 1})
        self.assertEqual(self._tables_report(),
                         {'students': 2, 'quizzes': 1, 'quiz_results': 1, 'cohorts': 1})
        self.assertEqual(os.listdir(self.tmp.name), [], 'dry-run no debe escribir backups')

    def test_export_only_writes_backups_without_deleting(self):
        result = migrate_clean.run_clean(
            self.resource, self.defs, timestamp='20260907_123456',
            export_only=True, backup_dir=self.tmp.name)
        self.assertEqual(result['mode'], 'export_only')
        files = sorted(os.listdir(self.tmp.name))
        self.assertEqual(len(files), 4)
        for tabla in ('students', 'quizzes', 'quiz_results', 'cohorts'):
            self.assertIn(f'backup_20260907_123456_{tabla}.json', files)
            with open(os.path.join(self.tmp.name, f'backup_20260907_123456_{tabla}.json')) as f:
                items = json.load(f)
            self.assertEqual(len(items), result['counts'][tabla])
        # Nada fue eliminado ni sembrado
        self.assertEqual(self.tables[build_defs()['cohorts']['name']].delete_calls, 0)

    def test_full_flow_confirms_and_cleans(self):
        result = migrate_clean.run_clean(
            self.resource, self.defs, timestamp='20260907_000000',
            backup_dir=self.tmp.name, ask=lambda prompt: 'SI')
        self.assertEqual(result['mode'], 'full')
        # Tablas vacías tras el borrado
        self.assertEqual(self._tables_report(),
                         {'students': 0, 'quizzes': 0, 'quiz_results': 0, 'cohorts': 1})
        # Turma beta seeded
        cohorts = self.tables[self.defs['cohorts']['name']]
        self.assertIn('turma-beta-01', cohorts._items)
        self.assertEqual(cohorts._items['turma-beta-01']['MaxStudents'], Decimal('7'))
        # Backups escritos
        self.assertEqual(len(os.listdir(self.tmp.name)), 4)
        self.assertEqual(result['deleted'], {'students': 2, 'quizzes': 1,
                                             'quiz_results': 1, 'cohorts': 1})
        self.assertTrue(result['verification']['ok'])
        self.assertTrue(result['verification']['beta_cohort_exists'])
        # MentoringQuestions intacta
        mq = self.tables[migrate_clean.MENTORING_QUESTIONS_TABLE]
        self.assertEqual(len(mq._items), 1)
        self.assertEqual(result['verification']['mentoring_questions_count'], 1)

    def test_full_flow_cancelled_without_SI(self):
        result = migrate_clean.run_clean(
            self.resource, self.defs, timestamp='20260907_000000',
            backup_dir=self.tmp.name, ask=lambda prompt: 'no')
        self.assertEqual(result['mode'], 'cancelled')
        # Según el diseño la confirmación ocurre después del backup
        self.assertEqual(len(os.listdir(self.tmp.name)), 4)
        # Nada fue eliminado ni sembrado
        self.assertEqual(self._tables_report(),
                         {'students': 2, 'quizzes': 1, 'quiz_results': 1, 'cohorts': 1})
        cohorts = self.tables[self.defs['cohorts']['name']]
        self.assertNotIn('turma-beta-01', cohorts._items)
        self.assertEqual(result['deleted'], {})

    def test_backup_roundtrip_preserves_decimals(self):
        migrate_clean.run_clean(
            self.resource, self.defs, timestamp='20260907_000000',
            export_only=True, backup_dir=self.tmp.name)
        with open(os.path.join(self.tmp.name, 'backup_20260907_000000_quiz_results.json')) as f:
            items = json.load(f)
        self.assertEqual(items[0]['IsCorrect'], True)
        with open(os.path.join(self.tmp.name, 'backup_20260907_000000_students.json')) as f:
            students = json.load(f)
        self.assertIsInstance(students[0]['StudentID'], str)


class TestMigrateRestore(unittest.TestCase):
    def _exported_backups(self, tmpdir, ts='20260907_000000'):
        resource, tables = make_resource()
        migrate_clean.run_clean(resource, build_defs(), timestamp=ts,
                                export_only=True, backup_dir=tmpdir)
        return resource, tables

    def test_restores_latest_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_resource, old_tables = self._exported_backups(tmp, ts='20260906_000000')
            new_resource, new_tables = self._exported_backups(tmp, ts='20260907_111111')

            target = FakeResource({
                'AI_Mentoring-Students-dev': FakeTable('students', 'StudentID'),
                'AI_Mentoring-Quizzes-dev': FakeTable('quizzes', 'QuizID'),
                'AI_Mentoring-QuizResults-dev': FakeTable('quiz_results', 'ResultID'),
                'AI_Mentoring-Cohorts-dev': FakeTable('cohorts', 'CohortID'),
            })
            report = migrate_restore.run_restore(
                target, migrate_restore.table_names(PROJECT, ENV),
                backup_dir=tmp)

            self.assertEqual(report, {'students': 2, 'quizzes': 1,
                                      'quiz_results': 1, 'cohorts': 1})
            students = target.tables['AI_Mentoring-Students-dev']._items
            self.assertEqual(set(students), {'s1', 's2'})
            quiz_results = target.tables['AI_Mentoring-QuizResults-dev']._items
            self.assertEqual(quiz_results['r1']['CorrectAnswers'], ['A'])

    def test_restore_specific_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._exported_backups(tmp, ts='20260906_080000')
            self._exported_backups(tmp, ts='20260906_090000')

            target = FakeResource({
                'AI_Mentoring-Students-dev': FakeTable('students', 'StudentID'),
                'AI_Mentoring-Quizzes-dev': FakeTable('quizzes', 'QuizID'),
                'AI_Mentoring-QuizResults-dev': FakeTable('quiz_results', 'ResultID'),
                'AI_Mentoring-Cohorts-dev': FakeTable('cohorts', 'CohortID'),
            })
            report = migrate_restore.run_restore(
                target, migrate_restore.table_names(PROJECT, ENV),
                backup_dir=tmp, prefix='20260906_080000')
            self.assertEqual(report, {'students': 2, 'quizzes': 1,
                                      'quiz_results': 1, 'cohorts': 1})

    def test_missing_backups_aborts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                migrate_restore.run_restore(
                    FakeResource({}), migrate_restore.table_names(PROJECT, ENV),
                    backup_dir=tmp)

    def test_incomplete_backups_rejected_for_auto_detect(self):
        with tempfile.TemporaryDirectory() as tmp:
            resource, _ = self._exported_backups(tmp, ts='20260907_000000')
            # Eliminar un backup para que el juego quede incompleto
            os.remove(os.path.join(tmp, 'backup_20260907_000000_cohorts.json'))
            target = FakeResource({
                'AI_Mentoring-Students-dev': FakeTable('students', 'StudentID'),
                'AI_Mentoring-Quizzes-dev': FakeTable('quizzes', 'QuizID'),
                'AI_Mentoring-QuizResults-dev': FakeTable('quiz_results', 'ResultID'),
                'AI_Mentoring-Cohorts-dev': FakeTable('cohorts', 'CohortID'),
            })
            with self.assertRaises(SystemExit):
                migrate_restore.run_restore(
                    target, migrate_restore.table_names(PROJECT, ENV),
                    backup_dir=tmp)


if __name__ == '__main__':
    unittest.main()