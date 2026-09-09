"""Pruebas del Sistema de Fases (nuevo modelo).

Valida la progresión de fases (initial → free_practice sin umbral), el control
de acceso por rol de profesor y la gestión del examen final. Usa unittest.mock
para simular DynamoDB.
"""
import json
import sys
import os
import unittest
from unittest import mock
from datetime import datetime, timezone, timedelta

# Configurar entorno antes de importar los módulos
os.environ['STUDENTS_TABLE'] = 'test-students'
os.environ['COHORTS_TABLE'] = 'test-cohorts'
os.environ['QUIZZES_TABLE'] = 'test-quizzes'
os.environ['QUESTIONS_TABLE'] = 'test-questions'
os.environ['QUIZ_RESULTS_TABLE'] = 'test-quiz-results'

# Agregar src al path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def make_student_item(student_id='student-123', phase='initial', failed_attempts=None):
    """Crea un item de estudiante de prueba."""
    return {
        'StudentID': student_id,
        'Email': 'test@example.com',
        'Name': 'Test Student',
        'CurrentPhase': phase,
        'PhaseHistory': [],
        'FailedAttempts': failed_attempts or {'final_exam': 0},
        'AccessExpiresAt': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        'CreatedAt': datetime.now(timezone.utc).isoformat(),
    }


def make_quiz_item(quiz_id='quiz-123', student_id='student-123', quiz_type='initial',
                   status='in_progress', questions=None):
    """Crea un item de quiz de prueba."""
    return {
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuizType': quiz_type,
        'Topic': quiz_type,
        'Questions': questions or ['q1', 'q2', 'q3'],
        'Status': status,
        'CreatedAt': datetime.now(timezone.utc).isoformat(),
    }


def make_question_item(question_id='q1', topic='Cloud Concepts & Well-Architected'):
    """Crea un item de pregunta de prueba."""
    return {
        'QuestionID': question_id,
        'Topic': topic,
        'QuestionText': 'What is AWS?',
        'Options': {
            'A': {'text': 'Option A', 'is_correct': True, 'explanation': 'Because'},
            'B': {'text': 'Option B', 'is_correct': False, 'explanation': 'No'}
        }
    }


def make_result_item(result_id='r1', quiz_id='quiz-123', student_id='student-123',
                     question_id='q1', is_correct=True):
    """Crea un item de resultado de prueba."""
    return {
        'ResultID': result_id,
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuestionID': question_id,
        'IsCorrect': is_correct,
        'GivenAnswers': ['A'] if is_correct else ['B'],
        'Timestamp': datetime.now(timezone.utc).isoformat()
    }


def make_api_event(route_key, body=None, student_id=None, claims=None):
    """Crea un evento API Gateway de prueba."""
    event = {
        'routeKey': route_key,
        'pathParameters': {'studentId': student_id} if student_id else {},
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': claims or {'sub': 'student-123', 'email': 'test@example.com'}
                }
            }
        }
    }
    if body is not None:
        event['body'] = json.dumps(body)
    return event


class TestCreateStudentPhaseFields(unittest.TestCase):
    """Verifica que create_student agregue los campos del nuevo modelo."""

    @mock.patch('student_api.students_table')
    @mock.patch('student_api.cohorts_table')
    @mock.patch('student_api.quizzes_table')
    def test_create_student_has_phase_fields(self, mock_quizzes, mock_cohorts, mock_students):
        import student_api

        mock_students.put_item.return_value = {}

        event = make_api_event('POST /students', body={'name': 'Test'})
        claims = {'sub': 'new-student', 'email': 'new@test.com', 'name': 'Test'}

        response = student_api.create_student(event, claims)

        self.assertEqual(response['statusCode'], 201)

        call_args = mock_students.put_item.call_args
        item = call_args[1]['Item'] if 'Item' in call_args[1] else call_args[0][0]

        self.assertEqual(item['CurrentPhase'], 'initial')
        self.assertEqual(item['PhaseHistory'], [])
        self.assertEqual(item['FailedAttempts'], {'final_exam': 0})
        self.assertNotIn('Cohort', item)

    @mock.patch('student_api.students_table')
    @mock.patch('student_api.cohorts_table')
    def test_create_student_with_full_cohort_rejected(self, mock_cohorts, mock_students):
        import student_api

        # Turma con cupo máximo 1 y ya con 1 alumno
        mock_cohorts.get_item.return_value = {'Item': {'CohortID': 'turma-1', 'MaxStudents': 1}}
        mock_students.query.return_value = {'Count': 1}

        event = make_api_event('POST /students', body={'cohort_id': 'turma-1'})
        claims = {'sub': 'new-student', 'email': 'new@test.com', 'name': 'Test'}

        response = student_api.create_student(event, claims)

        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Turma está cheia', body['message'])


class TestGenerateQuizPhaseRestriction(unittest.TestCase):
    """Verifica que generate_quiz restrinja tipos según la fase."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.questions_table')
    def test_initial_phase_cannot_generate_final_exam(self, mock_questions, mock_quizzes, mock_students):
        import quiz_engine

        mock_students.get_item.return_value = {'Item': make_student_item(phase='initial')}

        event = make_api_event('POST /quizzes/generate', body={'quiz_type': 'final_exam'})
        claims = {'sub': 'student-123'}
        event['requestContext']['authorizer']['jwt']['claims'] = claims

        response = quiz_engine.lambda_handler(event, None)

        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('not allowed', body['error'])
        self.assertEqual(body['current_phase'], 'initial')

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.questions_table')
    def test_initial_phase_can_generate_initial(self, mock_questions, mock_quizzes, mock_students):
        import quiz_engine

        mock_students.get_item.return_value = {'Item': make_student_item(phase='initial')}
        mock_questions.query.return_value = {'Items': [make_question_item(f'q{i}') for i in range(20)]}
        mock_quizzes.put_item.return_value = {}
        mock_students.update_item.return_value = {}

        event = make_api_event('POST /quizzes/generate', body={'quiz_type': 'initial'})
        claims = {'sub': 'student-123'}
        event['requestContext']['authorizer']['jwt']['claims'] = claims

        response = quiz_engine.lambda_handler(event, None)

        self.assertEqual(response['statusCode'], 201)
        body = json.loads(response['body'])
        self.assertEqual(body['quiz_type'], 'initial')

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.questions_table')
    def test_free_quiz_uses_num_questions(self, mock_questions, mock_quizzes, mock_students):
        import quiz_engine

        mock_students.get_item.return_value = {'Item': make_student_item(phase='free_practice')}
        mock_questions.query.return_value = {'Items': [make_question_item(f'q{i}') for i in range(5)]}
        mock_quizzes.put_item.return_value = {}

        event = make_api_event('POST /quizzes/generate', body={
            'quiz_type': 'free',
            'topic': 'Cloud Concepts & Well-Architected',
            'num_questions': 5
        })
        claims = {'sub': 'student-123'}
        event['requestContext']['authorizer']['jwt']['claims'] = claims

        response = quiz_engine.lambda_handler(event, None)

        self.assertEqual(response['statusCode'], 201)
        # El topic es obligatorio y la query usa el parámetro num_questions
        mock_questions.query.assert_called_once()
        query_kwargs = mock_questions.query.call_args[1]
        self.assertEqual(query_kwargs['Limit'], 5)

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.questions_table')
    def test_free_quiz_requires_topic(self, mock_questions, mock_quizzes, mock_students):
        import quiz_engine

        mock_students.get_item.return_value = {'Item': make_student_item(phase='free_practice')}

        event = make_api_event('POST /quizzes/generate', body={'quiz_type': 'free'})
        claims = {'sub': 'student-123'}
        event['requestContext']['authorizer']['jwt']['claims'] = claims

        response = quiz_engine.lambda_handler(event, None)

        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('topic é obrigatório', body['error'])


class TestCompleteQuizPhaseAdvancement(unittest.TestCase):
    """Verifica que el diagnóstico inicial avance a free_practice sin umbral."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    def test_initial_advances_to_free_practice_with_any_score(self, mock_results, mock_quizzes, mock_students):
        import quiz_engine

        # Solo 1 de 3 correctas (33%) — debe avanzar igualmente
        quiz = make_quiz_item(quiz_type='initial', questions=['q1', 'q2', 'q3'])
        mock_quizzes.get_item.return_value = {'Item': quiz}

        mock_results.query.return_value = {'Items': [
            make_result_item(is_correct=True),
            make_result_item(result_id='r2', question_id='q2', is_correct=False),
            make_result_item(result_id='r3', question_id='q3', is_correct=False),
        ]}

        student = make_student_item(phase='initial')
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.update_item.return_value = {}
        mock_students.update_item.return_value = {}

        response = quiz_engine.complete_quiz('quiz-123', 'student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertTrue(body.get('phase_advanced'))
        self.assertEqual(body['previous_phase'], 'initial')
        self.assertEqual(body['new_phase'], 'free_practice')

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    def test_free_quiz_does_not_change_phase(self, mock_results, mock_quizzes, mock_students):
        import quiz_engine

        quiz = make_quiz_item(quiz_type='free', questions=['q1', 'q2', 'q3'])
        mock_quizzes.get_item.return_value = {'Item': quiz}

        mock_results.query.return_value = {'Items': [
            make_result_item(is_correct=True),
            make_result_item(result_id='r2', question_id='q2', is_correct=True),
            make_result_item(result_id='r3', question_id='q3', is_correct=True),
        ]}

        student = make_student_item(phase='free_practice')
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.update_item.return_value = {}

        response = quiz_engine.complete_quiz('quiz-123', 'student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertFalse(body.get('phase_advanced'))


class TestGenerateFinalExamReleaseDate(unittest.TestCase):
    """Verifica la liberación por fecha del examen final (Req. 7.1, 7.2)."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.questions_table')
    @mock.patch('quiz_engine.quiz_results_table')
    def test_generates_when_release_date_in_past(self, mock_results, mock_questions, mock_quizzes, mock_students):
        import quiz_engine

        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        student = make_student_item(phase='free_practice')
        student['FinalExamReleaseDate'] = past
        mock_students.get_item.return_value = {'Item': student}

        # Sin exámenes previos ni quizzes completados
        mock_quizzes.query.return_value = {'Items': []}
        mock_results.query.return_value = {'Items': []}
        mock_questions.query.return_value = {
            'Items': [make_question_item(f'q{i}') for i in range(70)]
        }
        mock_quizzes.put_item.return_value = {}

        response = quiz_engine.generate_final_exam('student-123')

        self.assertEqual(response['statusCode'], 201)
        body = json.loads(response['body'])
        self.assertEqual(body['quiz_type'], 'final_exam')

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    def test_returns_403_when_release_date_in_future(self, mock_quizzes, mock_students):
        import quiz_engine

        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        student = make_student_item(phase='free_practice')
        student['FinalExamReleaseDate'] = future
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.query.return_value = {'Items': []}

        response = quiz_engine.generate_final_exam('student-123')

        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Exame disponível', body['error'])

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    def test_returns_403_when_no_release_date(self, mock_quizzes, mock_students):
        import quiz_engine

        student = make_student_item(phase='free_practice')
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.query.return_value = {'Items': []}

        response = quiz_engine.generate_final_exam('student-123')

        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('não liberado', body['error'])


class TestIsTeacher(unittest.TestCase):
    """Verifica is_teacher() con claim como lista, string o ausente (Req. 12.2)."""

    def test_teacher_with_list_claim(self):
        import student_api
        self.assertTrue(student_api.is_teacher({'cognito:groups': ['Teachers', 'Admin']}))

    def test_non_teacher_with_list_claim(self):
        import student_api
        self.assertFalse(student_api.is_teacher({'cognito:groups': ['Students']}))

    def test_teacher_with_string_claim(self):
        import student_api
        self.assertTrue(student_api.is_teacher({'cognito:groups': 'Teachers'}))

    def test_non_teacher_with_string_claim(self):
        import student_api
        self.assertFalse(student_api.is_teacher({'cognito:groups': 'Students'}))

    def test_missing_groups_claim(self):
        import student_api
        self.assertFalse(student_api.is_teacher({'sub': 'student-123'}))

    def test_claims_none_returns_false(self):
        import student_api
        self.assertFalse(student_api.is_teacher(None))
        self.assertFalse(student_api.is_teacher({}))
        self.assertFalse(student_api.is_teacher('not-a-dict'))

    def test_empty_groups_string_returns_false(self):
        import student_api
        self.assertFalse(student_api.is_teacher({'sub': 'student-123', 'cognito:groups': ''}))

    def test_teacher_with_comma_separated_groups(self):
        import student_api
        self.assertTrue(student_api.is_teacher({'cognito:groups': 'Teachers, Admin'}))

    def test_non_teacher_with_comma_separated_groups(self):
        import student_api
        self.assertFalse(student_api.is_teacher({'cognito:groups': ' Students, Testers'}))

    def test_non_iterable_groups_returns_false(self):
        import student_api
        self.assertFalse(student_api.is_teacher({'cognito:groups': 123}))

    def test_teacher_with_bracket_space_single_group(self):
        """Formato REAL de API Gateway HTTP API v2: corchetes literales, sin comillas."""
        import student_api
        self.assertTrue(student_api.is_teacher({'cognito:groups': '[Teachers]'}))

    def test_teacher_with_bracket_space_multiple_groups(self):
        """Formato REAL con varios grupos: separados por espacios dentro de corchetes."""
        import student_api
        self.assertTrue(student_api.is_teacher({'cognito:groups': '[Teachers Admin]'}))

    def test_non_teacher_with_bracket_space_multiple_groups(self):
        import student_api
        self.assertFalse(student_api.is_teacher({'cognito:groups': '[Students Testers]'}))

    def test_empty_brackets_returns_false(self):
        import student_api
        self.assertFalse(student_api.is_teacher({'cognito:groups': '[]'}))

    def test_teacher_with_json_array_string_groups(self):
        """Formato alternativo (JSON array string) — no es el que llega hoy, pero se soporta."""
        import student_api
        self.assertTrue(student_api.is_teacher({'cognito:groups': '["Teachers"]'}))

    def test_non_teacher_with_json_array_string_groups(self):
        import student_api
        self.assertFalse(student_api.is_teacher({'cognito:groups': '["Students","Testers"]'}))

    def test_teacher_with_json_array_multiple_groups(self):
        import student_api
        self.assertTrue(student_api.is_teacher({'cognito:groups': '["Students"," Teachers "]'}))

    def test_json_string_not_a_list_falls_back_to_split(self):
        import student_api
        self.assertTrue(student_api.is_teacher({'cognito:groups': 'Teachers,Admin'}))
        self.assertFalse(student_api.is_teacher({'cognito:groups': 'not-an-array'}))


class TestTeacherUpdatePhase(unittest.TestCase):
    """Verifica que update_student_phase valide el grupo Teachers."""

    @mock.patch('student_api.students_table')
    def test_teacher_can_update_phase(self, mock_students):
        import student_api

        mock_students.get_item.return_value = {'Item': make_student_item(phase='initial')}
        mock_students.update_item.return_value = {'Attributes': make_student_item(phase='free_practice')}

        claims = {'sub': 'teacher-123', 'cognito:groups': 'Teachers'}
        event = make_api_event('PUT /students/{studentId}/phase',
                               body={'phase': 'free_practice'},
                               student_id='student-123',
                               claims=claims)

        response = student_api.update_student_phase(event, claims, 'student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['previous_phase'], 'initial')
        self.assertEqual(body['new_phase'], 'free_practice')

    @mock.patch('student_api.students_table')
    def test_non_teacher_cannot_update_phase(self, mock_students):
        import student_api

        claims = {'sub': 'student-456', 'cognito:groups': ''}
        event = make_api_event('PUT /students/{studentId}/phase',
                               body={'phase': 'free_practice'},
                               student_id='student-123',
                               claims=claims)

        response = student_api.update_student_phase(event, claims, 'student-123')

        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('Only teachers', body['message'])

    @mock.patch('student_api.students_table')
    def test_invalid_phase_rejected(self, mock_students):
        import student_api

        mock_students.get_item.return_value = {'Item': make_student_item(phase='initial')}

        claims = {'sub': 'teacher-123', 'cognito:groups': 'Teachers'}
        event = make_api_event('PUT /students/{studentId}/phase',
                               body={'phase': 'invalid_phase'},
                               student_id='student-123',
                               claims=claims)

        response = student_api.update_student_phase(event, claims, 'student-123')

        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('Invalid phase', body['message'])


class TestGetConfig(unittest.TestCase):
    """Verifica que GET /config retorne los tres campos requeridos (Req. 1.1)."""

    @mock.patch.dict(os.environ, {
        'API_URL': 'https://api.example.com',
        'COGNITO_USER_POOL_ID': 'us-east-1_XXXXX',
        'COGNITO_CLIENT_ID': 'client-123'
    })
    def test_get_config_returns_fields(self):
        import student_api
        response = student_api.get_config()
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['apiUrl'], 'https://api.example.com')
        self.assertEqual(body['userPoolId'], 'us-east-1_XXXXX')
        self.assertEqual(body['clientId'], 'client-123')


if __name__ == '__main__':
    unittest.main()