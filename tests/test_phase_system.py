"""Pruebas del Sistema de Fases Adaptativo (Fase 7e).

Valida la lógica de progresión de fases, restricciones de generación de quizzes,
y control de acceso por rol de profesor. Usa unittest.mock para simular DynamoDB.
"""
import json
import sys
import os
import unittest
from unittest import mock
from datetime import datetime, timezone, timedelta
from decimal import Decimal

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
        'FailedAttempts': failed_attempts or {'phase_1': 0, 'phase_2': 0, 'final_exam': 0},
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
    """Test 1: Verifica que create_student agregue campos de fase."""

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

        # Verificar que put_item fue llamado con los campos de fase
        call_args = mock_students.put_item.call_args
        item = call_args[1]['Item'] if 'Item' in call_args[1] else call_args[0][0]

        self.assertEqual(item['CurrentPhase'], 'initial')
        self.assertEqual(item['PhaseHistory'], [])
        self.assertEqual(item['FailedAttempts'], {
            'phase_1': 0,
            'phase_2': 0,
            'final_exam': 0
        })


class TestGenerateQuizPhaseRestriction(unittest.TestCase):
    """Test 2: Verifica que generate_quiz restrinja tipos según la fase."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.questions_table')
    def test_initial_phase_cannot_generate_phase_1(self, mock_questions, mock_quizzes, mock_students):
        import quiz_engine

        # Estudiante en fase 'initial'
        mock_students.get_item.return_value = {'Item': make_student_item(phase='initial')}

        event = make_api_event('POST /quizzes/generate', body={'quiz_type': 'phase_1'})
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

        # Estudiante en fase 'initial' - mock para generate_initial_quiz
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
    def test_phase_1_can_generate_free(self, mock_questions, mock_quizzes, mock_students):
        import quiz_engine

        # Estudiante en fase 'phase_1' puede generar 'free'
        mock_students.get_item.return_value = {'Item': make_student_item(phase='phase_1')}
        mock_questions.query.return_value = {'Items': [make_question_item('q1')]}
        mock_quizzes.put_item.return_value = {}

        event = make_api_event('POST /quizzes/generate', body={
            'quiz_type': 'free',
            'topic': 'Cloud Concepts & Well-Architected',
            'count': 1
        })
        claims = {'sub': 'student-123'}
        event['requestContext']['authorizer']['jwt']['claims'] = claims

        response = quiz_engine.lambda_handler(event, None)

        self.assertEqual(response['statusCode'], 201)


class TestCompleteQuizPhaseAdvancement(unittest.TestCase):
    """Test 3: Verifica avance de fase al completar con >= 70%."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    def test_advances_initial_to_phase_1_on_70_percent(self, mock_results, mock_quizzes, mock_students):
        import quiz_engine

        # Quiz de tipo 'initial' completado
        quiz = make_quiz_item(quiz_type='initial', questions=['q1', 'q2', 'q3', 'q4', 'q5'])
        mock_quizzes.get_item.return_value = {'Item': quiz}

        # 4 de 5 correctas = 80%
        mock_results.query.return_value = {'Items': [
            make_result_item(is_correct=True),
            make_result_item(result_id='r2', question_id='q2', is_correct=True),
            make_result_item(result_id='r3', question_id='q3', is_correct=True),
            make_result_item(result_id='r4', question_id='q4', is_correct=True),
            make_result_item(result_id='r5', question_id='q5', is_correct=False),
        ]}

        # Estudiante en fase 'initial'
        student = make_student_item(phase='initial')
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.update_item.return_value = {}
        mock_students.update_item.return_value = {}

        response = quiz_engine.complete_quiz('quiz-123', 'student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertTrue(body.get('phase_advanced'))
        self.assertEqual(body['previous_phase'], 'initial')
        self.assertEqual(body['new_phase'], 'phase_1')

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    def test_does_not_advance_below_70_percent(self, mock_results, mock_quizzes, mock_students):
        import quiz_engine

        # Quiz de tipo 'initial'
        quiz = make_quiz_item(quiz_type='initial', questions=['q1', 'q2', 'q3', 'q4', 'q5'])
        mock_quizzes.get_item.return_value = {'Item': quiz}

        # 3 de 5 correctas = 60%
        mock_results.query.return_value = {'Items': [
            make_result_item(is_correct=True),
            make_result_item(result_id='r2', question_id='q2', is_correct=True),
            make_result_item(result_id='r3', question_id='q3', is_correct=True),
            make_result_item(result_id='r4', question_id='q4', is_correct=False),
            make_result_item(result_id='r5', question_id='q5', is_correct=False),
        ]}

        student = make_student_item(phase='initial')
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.update_item.return_value = {}

        response = quiz_engine.complete_quiz('quiz-123', 'student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertFalse(body.get('phase_advanced'))


class TestFailedAttemptsIncrement(unittest.TestCase):
    """Test 4: Verifica que puntajes < 70% incrementen FailedAttempts."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    def test_increments_failed_attempts_on_low_score(self, mock_results, mock_quizzes, mock_students):
        import quiz_engine

        # Quiz de tipo 'phase_1'
        quiz = make_quiz_item(quiz_type='phase_1', questions=['q1', 'q2', 'q3', 'q4', 'q5'])
        mock_quizzes.get_item.return_value = {'Item': quiz}

        # 2 de 5 correctas = 40%
        mock_results.query.return_value = {'Items': [
            make_result_item(is_correct=True),
            make_result_item(result_id='r2', question_id='q2', is_correct=True),
            make_result_item(result_id='r3', question_id='q3', is_correct=False),
            make_result_item(result_id='r4', question_id='q4', is_correct=False),
            make_result_item(result_id='r5', question_id='q5', is_correct=False),
        ]}

        student = make_student_item(phase='phase_1', failed_attempts={
            'phase_1': 0, 'phase_2': 0, 'final_exam': 0
        })
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.update_item.return_value = {}
        mock_students.update_item.return_value = {}

        response = quiz_engine.complete_quiz('quiz-123', 'student-123')

        self.assertEqual(response['statusCode'], 200)

        # Verificar que update_item fue llamado para incrementar FailedAttempts
        mock_students.update_item.assert_called()
        call_args = mock_students.update_item.call_args
        update_expr = call_args[1].get('UpdateExpression', call_args[0][0] if call_args[0] else '')
        self.assertIn('FailedAttempts', update_expr)


class TestMaxAttemptsExceeded(unittest.TestCase):
    """Test 5: Verifica que al 3er fallo se genere MaxAttemptsAlert."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    def test_max_attempts_exceeded_on_third_failure(self, mock_results, mock_quizzes, mock_students):
        import quiz_engine

        # Quiz de tipo 'phase_2'
        quiz = make_quiz_item(quiz_type='phase_2', questions=['q1', 'q2', 'q3', 'q4', 'q5'])
        mock_quizzes.get_item.return_value = {'Item': quiz}

        # 1 de 5 correctas = 20%
        mock_results.query.return_value = {'Items': [
            make_result_item(is_correct=True),
            make_result_item(result_id='r2', question_id='q2', is_correct=False),
            make_result_item(result_id='r3', question_id='q3', is_correct=False),
            make_result_item(result_id='r4', question_id='q4', is_correct=False),
            make_result_item(result_id='r5', question_id='q5', is_correct=False),
        ]}

        # Estudiante ya tiene 2 fallos (este es el 3ero)
        student = make_student_item(phase='phase_2', failed_attempts={
            'phase_1': 0, 'phase_2': 2, 'final_exam': 0
        })
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.update_item.return_value = {}
        mock_students.update_item.return_value = {}

        response = quiz_engine.complete_quiz('quiz-123', 'student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertIn('alert', body)
        self.assertEqual(body['alert'], 'MAX_ATTEMPTS_EXCEEDED: Contact your instructor')

        # Verificar que se actualizó MaxAttemptsAlert en DynamoDB
        mock_students.update_item.assert_called()
        call_args = mock_students.update_item.call_args
        expr_values = call_args[1].get('ExpressionAttributeValues', {})
        self.assertIn(':alert', expr_values)
        alert_data = expr_values[':alert']
        self.assertEqual(alert_data['AlertType'], 'MAX_ATTEMPTS_EXCEEDED')
        self.assertEqual(alert_data['Phase'], 'phase_2')


class TestTeacherUpdatePhase(unittest.TestCase):
    """Test 6: Verifica que update_student_phase valide el grupo Teachers."""

    @mock.patch('student_api.students_table')
    def test_teacher_can_update_phase(self, mock_students):
        import student_api

        # Mock para obtener estudiante actual
        mock_students.get_item.return_value = {'Item': make_student_item(phase='initial')}
        mock_students.update_item.return_value = {'Attributes': make_student_item(phase='phase_1')}

        # Claims con grupo Teachers
        claims = {'sub': 'teacher-123', 'cognito:groups': 'Teachers'}
        event = make_api_event('PUT /students/{studentId}/phase',
                               body={'phase': 'phase_1'},
                               student_id='student-123',
                               claims=claims)

        response = student_api.update_student_phase(event, claims, 'student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['previous_phase'], 'initial')
        self.assertEqual(body['new_phase'], 'phase_1')

    @mock.patch('student_api.students_table')
    def test_non_teacher_cannot_update_phase(self, mock_students):
        import student_api

        # Claims SIN grupo Teachers
        claims = {'sub': 'student-456', 'cognito:groups': ''}
        event = make_api_event('PUT /students/{studentId}/phase',
                               body={'phase': 'phase_1'},
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

    @mock.patch('student_api.students_table')
    def test_teacher_group_as_list(self, mock_students):
        """Verifica que cognito:groups funcione como lista."""
        import student_api

        mock_students.get_item.return_value = {'Item': make_student_item(phase='phase_1')}
        mock_students.update_item.return_value = {'Attributes': make_student_item(phase='phase_2')}

        # Groups como lista
        claims = {'sub': 'teacher-123', 'cognito:groups': ['Teachers', 'Admin']}
        event = make_api_event('PUT /students/{studentId}/phase',
                               body={'phase': 'phase_2'},
                               student_id='student-123',
                               claims=claims)

        response = student_api.update_student_phase(event, claims, 'student-123')

        self.assertEqual(response['statusCode'], 200)


if __name__ == '__main__':
    unittest.main()
