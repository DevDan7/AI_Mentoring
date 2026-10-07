"""Pruebas del ciclo de vida de turmas (doc/ciclo-de-vida-turmas.md).

Cubre la regla de acceso manual (bloqueo/extensión por alumno, cierre de turma),
la turma de convidados y el reintento por ciclos ("Recomeçar do zero").
Usa unittest.mock para simular DynamoDB, igual que test_phase_system.py.
"""
import json
import os
import sys
import unittest
from unittest import mock
from datetime import datetime, timezone, timedelta

os.environ['STUDENTS_TABLE'] = 'test-students'
os.environ['COHORTS_TABLE'] = 'test-cohorts'
os.environ['QUIZZES_TABLE'] = 'test-quizzes'
os.environ['QUESTIONS_TABLE'] = 'test-questions'
os.environ['QUIZ_RESULTS_TABLE'] = 'test-quiz-results'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import quiz_engine  # noqa: E402
import student_api  # noqa: E402

TEACHER = {'sub': 'teacher-1', 'cognito:groups': '[Teachers]'}
STUDENT = {'sub': 'student-123', 'email': 'a@test.com'}
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def iso(delta_days):
    return (NOW + timedelta(days=delta_days)).isoformat()


def event(route_key, body=None, path=None, claims=None):
    ev = {
        'routeKey': route_key,
        'pathParameters': path or {},
        'requestContext': {'authorizer': {'jwt': {'claims': claims or STUDENT}}},
    }
    if body is not None:
        ev['body'] = json.dumps(body)
    return ev


class TestEvaluateAccess(unittest.TestCase):
    """Precedencia: bloqueo > extensión > turma cerrada > acceso."""

    def check(self, student, cohort, expected):
        for module in (student_api, quiz_engine):
            self.assertEqual(module.evaluate_access(student, cohort, NOW), expected, module.__name__)

    def test_open_cohort_without_flags_has_access(self):
        self.check({}, {'Status': 'active'}, (True, 'active'))

    def test_student_without_cohort_has_access(self):
        self.check({}, None, (True, 'active'))

    def test_closed_cohort_blocks(self):
        self.check({}, {'Status': 'closed'}, (False, 'cohort_closed'))

    def test_blocked_wins_over_open_cohort(self):
        self.check({'AccessStatus': 'blocked'}, {'Status': 'active'}, (False, 'blocked'))

    def test_open_without_until_survives_closed_cohort(self):
        self.check({'AccessStatus': 'open'}, {'Status': 'closed'}, (True, 'open'))

    def test_open_with_future_until_survives_closed_cohort(self):
        self.check({'AccessStatus': 'open', 'AccessUntil': iso(3)}, {'Status': 'closed'}, (True, 'open'))

    def test_expired_extension_falls_back_to_cohort(self):
        self.check({'AccessStatus': 'open', 'AccessUntil': iso(-1)}, {'Status': 'closed'}, (False, 'cohort_closed'))
        self.check({'AccessStatus': 'open', 'AccessUntil': iso(-1)}, {'Status': 'active'}, (True, 'active'))

    def test_legacy_access_expires_at_is_ignored(self):
        # La regla de 30 días se eliminó: un AccessExpiresAt viejo ya no corta el acceso
        self.check({'AccessExpiresAt': iso(-10)}, {'Status': 'active'}, (True, 'active'))


class TestCreateStudentNoExpiry(unittest.TestCase):

    @mock.patch('student_api.students_table')
    def test_profile_has_cycle_and_no_expiry(self, mock_students):
        claims = {'sub': 'new', 'email': 'n@test.com', 'name': 'N'}
        response = student_api.create_student(event('POST /students', body={}), claims)
        self.assertEqual(response['statusCode'], 201)
        item = mock_students.put_item.call_args[1]['Item']
        self.assertNotIn('AccessExpiresAt', item)
        self.assertEqual(item['Cycle'], 1)

    @mock.patch('student_api.students_table')
    @mock.patch('student_api.cohorts_table')
    def test_guest_cohort_has_no_capacity_limit(self, mock_cohorts, mock_students):
        mock_cohorts.get_item.return_value = {'Item': {'CohortID': 'CONVIDADOS', 'MaxStudents': 1, 'Type': 'convidados'}}
        mock_students.query.return_value = {'Count': 5}
        claims = {'sub': 'new', 'email': 'n@test.com', 'name': 'N'}
        response = student_api.create_student(event('POST /students', body={'cohort_id': 'CONVIDADOS'}), claims)
        self.assertEqual(response['statusCode'], 201)


class TestGetStudentAccess(unittest.TestCase):

    @mock.patch('student_api.cohorts_table')
    @mock.patch('student_api.students_table')
    def test_student_gets_403_when_cohort_closed(self, mock_students, mock_cohorts):
        mock_students.get_item.return_value = {'Item': {'StudentID': 'student-123', 'CohortID': 'G3'}}
        mock_cohorts.get_item.return_value = {'Item': {'CohortID': 'G3', 'Status': 'closed'}}
        response = student_api.get_student('student-123', STUDENT)
        self.assertEqual(response['statusCode'], 403)
        self.assertEqual(json.loads(response['body'])['code'], 'access_closed')

    @mock.patch('student_api.cohorts_table')
    @mock.patch('student_api.students_table')
    def test_teacher_sees_profile_of_closed_cohort(self, mock_students, mock_cohorts):
        mock_students.get_item.return_value = {'Item': {'StudentID': 'student-123', 'CohortID': 'G3'}}
        mock_cohorts.get_item.return_value = {'Item': {'CohortID': 'G3', 'Status': 'closed'}}
        response = student_api.get_student('student-123', TEACHER)
        self.assertEqual(response['statusCode'], 200)


class TestQuizEngineAccess(unittest.TestCase):

    @mock.patch('quiz_engine.cohorts_table')
    @mock.patch('quiz_engine.students_table')
    def test_generate_rejected_when_cohort_closed(self, mock_students, mock_cohorts):
        mock_students.get_item.return_value = {'Item': {'StudentID': 'student-123', 'CohortID': 'G3',
                                                        'CurrentPhase': 'free_practice'}}
        mock_cohorts.get_item.return_value = {'Item': {'CohortID': 'G3', 'Status': 'closed'}}
        response = quiz_engine.lambda_handler(
            event('POST /quizzes/generate', body={'quiz_type': 'free', 'topic': 'X'}), None)
        self.assertEqual(response['statusCode'], 403)

    @mock.patch('quiz_engine.cohorts_table')
    @mock.patch('quiz_engine.students_table')
    def test_blocked_student_cannot_submit(self, mock_students, mock_cohorts):
        mock_students.get_item.return_value = {'Item': {'StudentID': 'student-123', 'AccessStatus': 'blocked'}}
        response = quiz_engine.lambda_handler(
            event('POST /quizzes/submit', body={'quiz_id': 'q', 'question_id': 'x', 'given_answers': ['A']}), None)
        self.assertEqual(response['statusCode'], 403)
        mock_cohorts.get_item.assert_not_called()


class TestSetStudentAccess(unittest.TestCase):

    def call(self, body, claims=TEACHER):
        return student_api.lambda_handler(
            event('PUT /students/{studentId}/access', body=body, path={'studentId': 's1'}, claims=claims), None)

    @mock.patch('student_api.students_table')
    def test_only_teacher(self, mock_students):
        self.assertEqual(self.call({'action': 'block'}, claims=STUDENT)['statusCode'], 403)
        mock_students.update_item.assert_not_called()

    @mock.patch('student_api.students_table')
    def test_block(self, mock_students):
        mock_students.update_item.return_value = {'Attributes': {'AccessStatus': 'blocked'}}
        response = self.call({'action': 'block'})
        self.assertEqual(response['statusCode'], 200)
        kwargs = mock_students.update_item.call_args[1]
        self.assertEqual(kwargs['ExpressionAttributeValues'][':status'], 'blocked')
        self.assertIn('REMOVE AccessUntil', kwargs['UpdateExpression'])

    @mock.patch('student_api.students_table')
    def test_unblock_removes_flags(self, mock_students):
        mock_students.update_item.return_value = {'Attributes': {}}
        self.call({'action': 'unblock'})
        self.assertIn('REMOVE AccessStatus, AccessUntil', mock_students.update_item.call_args[1]['UpdateExpression'])

    @mock.patch('student_api.students_table')
    def test_open_with_future_until(self, mock_students):
        until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        mock_students.update_item.return_value = {'Attributes': {'AccessStatus': 'open', 'AccessUntil': until}}
        response = self.call({'action': 'open', 'until': until})
        self.assertEqual(response['statusCode'], 200)
        self.assertIn(':until', mock_students.update_item.call_args[1]['ExpressionAttributeValues'])

    @mock.patch('student_api.students_table')
    def test_open_rejects_past_or_invalid_until(self, mock_students):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.assertEqual(self.call({'action': 'open', 'until': past})['statusCode'], 400)
        self.assertEqual(self.call({'action': 'open', 'until': 'mañana'})['statusCode'], 400)
        self.assertEqual(self.call({'action': 'delete'})['statusCode'], 400)
        mock_students.update_item.assert_not_called()


class TestRestartCycle(unittest.TestCase):

    def call(self, claims=TEACHER):
        return student_api.lambda_handler(
            event('POST /students/{studentId}/restart', path={'studentId': 's1'}, claims=claims), None)

    @mock.patch('student_api.students_table')
    def test_only_teacher(self, mock_students):
        self.assertEqual(self.call(claims=STUDENT)['statusCode'], 403)

    @mock.patch('student_api.students_table')
    def test_restart_opens_next_cycle(self, mock_students):
        mock_students.get_item.return_value = {'Item': {'StudentID': 's1', 'CurrentPhase': 'free_practice',
                                                        'FinalExamReleaseDate': iso(-5)}}
        response = self.call()
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual((body['previous_cycle'], body['cycle']), (1, 2))

        kwargs = mock_students.update_item.call_args[1]
        values = kwargs['ExpressionAttributeValues']
        self.assertEqual(values[':new_cycle'], 2)
        self.assertEqual(values[':phase'], 'initial')
        self.assertEqual(values[':open'], 'open')
        self.assertIn('REMOVE FinalExamReleaseDate', kwargs['UpdateExpression'])

    @mock.patch('student_api.students_table')
    def test_restart_concurrent_returns_409(self, mock_students):
        from botocore.exceptions import ClientError
        mock_students.get_item.return_value = {'Item': {'StudentID': 's1', 'Cycle': 2}}
        mock_students.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException'}}, 'UpdateItem')
        self.assertEqual(self.call()['statusCode'], 409)


class TestCohortStatus(unittest.TestCase):

    def call(self, body, claims=TEACHER, cohort='G3'):
        return student_api.lambda_handler(
            event('PUT /cohorts/{cohortId}/status', body=body, path={'cohortId': cohort}, claims=claims), None)

    @mock.patch('student_api.cohorts_table')
    def test_only_teacher(self, mock_cohorts):
        self.assertEqual(self.call({'status': 'closed'}, claims=STUDENT)['statusCode'], 403)
        mock_cohorts.update_item.assert_not_called()

    @mock.patch('student_api.cohorts_table')
    def test_close_cohort(self, mock_cohorts):
        mock_cohorts.get_item.return_value = {'Item': {'CohortID': 'G3'}}
        mock_cohorts.update_item.return_value = {'Attributes': {'Status': 'closed', 'ClosedAt': NOW.isoformat()}}
        response = self.call({'status': 'closed'})
        self.assertEqual(response['statusCode'], 200)
        self.assertIn('ClosedAt', mock_cohorts.update_item.call_args[1]['UpdateExpression'])

    @mock.patch('student_api.cohorts_table')
    def test_guest_cohort_cannot_be_closed(self, mock_cohorts):
        mock_cohorts.get_item.return_value = {'Item': {'CohortID': 'CONVIDADOS', 'Type': 'convidados'}}
        self.assertEqual(self.call({'status': 'closed'}, cohort='CONVIDADOS')['statusCode'], 400)
        mock_cohorts.update_item.assert_not_called()

    @mock.patch('student_api.cohorts_table')
    def test_invalid_status_and_missing_cohort(self, mock_cohorts):
        self.assertEqual(self.call({'status': 'archived'})['statusCode'], 400)
        mock_cohorts.get_item.return_value = {}
        self.assertEqual(self.call({'status': 'closed'})['statusCode'], 404)


class TestCycleFiltering(unittest.TestCase):

    @mock.patch('student_api.quizzes_table')
    @mock.patch('student_api.students_table')
    def test_student_history_shows_only_current_cycle(self, mock_students, mock_quizzes):
        mock_students.get_item.return_value = {'Item': {'StudentID': 'student-123', 'Cycle': 2}}
        mock_quizzes.query.return_value = {'Items': [
            {'QuizID': 'old', 'CreatedAt': '2026-09-30'},               # ciclo 1 (sin campo)
            {'QuizID': 'new', 'CreatedAt': '2026-10-06', 'Cycle': 2},
        ]}
        body = json.loads(student_api.get_quiz_history(STUDENT)['body'])
        self.assertEqual([q['quiz_id'] for q in body['quizzes']], ['new'])

    @mock.patch('student_api.quizzes_table')
    def test_teacher_sees_all_cycles(self, mock_quizzes):
        mock_quizzes.query.return_value = {'Items': [
            {'QuizID': 'old', 'CreatedAt': '2026-09-30'},
            {'QuizID': 'new', 'CreatedAt': '2026-10-06', 'Cycle': 2},
        ]}
        body = json.loads(student_api.get_student_quizzes('s1', TEACHER)['body'])
        self.assertEqual({(q['quiz_id'], q['cycle']) for q in body['quizzes']}, {('old', 1), ('new', 2)})

    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.students_table')
    def test_final_exam_allowed_again_in_new_cycle(self, mock_students, mock_quizzes, mock_questions, mock_results):
        mock_students.get_item.return_value = {'Item': {
            'StudentID': 'student-123', 'Cycle': 2,
            'FinalExamReleaseDate': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}}
        # Examen final completado en el ciclo 1: no debe impedir el del ciclo 2
        mock_quizzes.query.return_value = {'Items': [
            {'QuizID': 'f1', 'QuizType': 'final_exam', 'Status': 'completed'}]}
        mock_results.query.return_value = {'Items': []}
        mock_questions.query.return_value = {'Items': [
            {'QuestionID': f'q{i}', 'Topic': 'T', 'QuestionText': f'Question number {i} about topic {i * 7}',
             'Options': {'A': {'text': 'a', 'is_correct': True}}} for i in range(70)]}

        response = quiz_engine.generate_final_exam('student-123')

        self.assertEqual(response['statusCode'], 201)
        self.assertEqual(mock_quizzes.put_item.call_args[1]['Item']['Cycle'], 2)

    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.students_table')
    def test_final_exam_still_blocked_in_same_cycle(self, mock_students, mock_quizzes):
        mock_students.get_item.return_value = {'Item': {'StudentID': 'student-123', 'Cycle': 2}}
        mock_quizzes.query.return_value = {'Items': [
            {'QuizID': 'f2', 'QuizType': 'final_exam', 'Status': 'completed', 'Cycle': 2}]}
        self.assertEqual(quiz_engine.generate_final_exam('student-123')['statusCode'], 403)


if __name__ == '__main__':
    unittest.main()
