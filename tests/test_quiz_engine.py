"""Pruebas del motor de quizzes (quiz_engine.py) para el nuevo modelo.

Cubre: reanudación de examen final en progreso, bloqueo por examen completado,
enriquecimiento de get_results() (statement/correct_answers/explanation,
domain_breakdown solo para final_exam) y persistencia/idempotencia de submit_answer().
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def make_student_item(student_id='student-123', phase='free_practice', release_delta_days=-1):
    """Estudiante con examen final ya liberado (en el pasado)."""
    student = {
        'StudentID': student_id,
        'Email': 'test@example.com',
        'Name': 'Test Student',
        'CurrentPhase': phase,
        'PhaseHistory': [],
        'FailedAttempts': {'final_exam': 0},
        'AccessExpiresAt': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        'CreatedAt': datetime.now(timezone.utc).isoformat(),
    }
    if release_delta_days is not None:
        student['FinalExamReleaseDate'] = (
            datetime.now(timezone.utc) + timedelta(days=release_delta_days)
        ).isoformat()
    return student


def make_final_exam_item(quiz_id='fin-123', student_id='student-123', status='in_progress'):
    return {
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuizType': 'final_exam',
        'Topic': 'final_exam',
        'Questions': ['q1', 'q2', 'q3'],
        'Status': status,
        'CreatedAt': datetime.now(timezone.utc).isoformat(),
    }


def make_question_item(question_id='q1', topic='Cloud Concepts & Well-Architected'):
    return {
        'QuestionID': question_id,
        'Topic': topic,
        'QuestionText': f'Statement {question_id}?',
        'Options': {
            'A': {'text': 'Option A', 'is_correct': True, 'explanation': 'Because A'},
            'B': {'text': 'Option B', 'is_correct': False, 'explanation': 'No B'}
        }
    }


def make_result_item(result_id='r1', quiz_id='quiz-123', question_id='q1',
                     given=None, correct=None, is_correct=None):
    given = given or ['A']
    correct = correct or ['A']
    is_correct = is_correct if is_correct is not None else (given == correct)
    return {
        'ResultID': result_id,
        'QuizID': quiz_id,
        'StudentID': 'student-123',
        'QuestionID': question_id,
        'GivenAnswers': given,
        'CorrectAnswers': correct,
        'IsCorrect': is_correct,
        'Timestamp': datetime.now(timezone.utc).isoformat(),
    }


class TestGenerateFinalExamResume(unittest.TestCase):
    """Tarea 9.2: reanudación del examen final en progreso."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_returns_existing_in_progress_quiz(self, mock_questions, mock_results, mock_quizzes, mock_students):
        import quiz_engine

        student = make_student_item()
        mock_students.get_item.return_value = {'Item': student}

        existing_quiz = make_final_exam_item(status='in_progress')
        mock_quizzes.query.return_value = {'Items': [existing_quiz]}

        # Pregunta q1 ya respondida → queda excluida
        mock_results.query.return_value = {
            'Items': [make_result_item(quiz_id='fin-123', question_id='q1')]
        }
        mock_questions.get_item.side_effect = lambda **kw: {'Item': make_question_item(kw['Key']['QuestionID'])} or {}

        response = quiz_engine.generate_final_exam('student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertEqual(body['quiz_id'], 'fin-123')
        self.assertEqual(body['quiz_type'], 'final_exam')
        self.assertIn('answered_question_ids', body)
        self.assertEqual(body['answered_question_ids'], ['q1'])
        # No debe crear un nuevo quiz
        mock_quizzes.put_item.assert_not_called()

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    def test_returns_403_when_completed_exists(self, mock_quizzes, mock_students):
        import quiz_engine

        student = make_student_item()
        mock_students.get_item.return_value = {'Item': student}

        completed_quiz = make_final_exam_item(status='completed')
        mock_quizzes.query.return_value = {'Items': [completed_quiz]}

        response = quiz_engine.generate_final_exam('student-123')

        self.assertEqual(response['statusCode'], 403)
        body = json.loads(response['body'])
        self.assertIn('já realizou o exame final', body['error'])

        # No debe llamar a resume_quiz ni crear quiz
        mock_quizzes.put_item.assert_not_called()


class TestGetResultsEnrichment(unittest.TestCase):
    """Tarea 9.2: get_results() enriquecido (statement, correct_answers, explanation)."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_free_quiz_has_no_domain_breakdown(self, mock_questions, mock_results, mock_quizzes, mock_students):
        import quiz_engine

        quiz = {
            'QuizID': 'quiz-free',
            'StudentID': 'student-123',
            'QuizType': 'free',
            'Topic': 'Cloud Concepts & Well-Architected',
            'Questions': ['q1'],
            'Status': 'completed',
            'CreatedAt': datetime.now(timezone.utc).isoformat(),
        }
        mock_questions.name = 'test-questions'
        mock_quizzes.get_item.return_value = {'Item': quiz}
        mock_results.query.return_value = {'Items': [
            make_result_item(quiz_id='quiz-free', question_id='q1',
                             given=['B'], correct=['A'], is_correct=False)
        ]}
        mock_questions.meta.client.batch_get_item.return_value = {
            'Responses': {'test-questions': [make_question_item('q1')]}
        }

        response = quiz_engine.get_results('quiz-free', 'student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])

        answer = body['answers'][0]
        self.assertEqual(answer['statement'], 'Statement q1?')
        self.assertEqual(answer['correct_answers'], ['A'])
        self.assertEqual(answer['explanation'], 'Because A')
        self.assertFalse(answer['is_correct'])
        self.assertNotIn('domain_breakdown', body)

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_final_exam_includes_domain_breakdown(self, mock_questions, mock_results, mock_quizzes, mock_students):
        import quiz_engine

        quiz = {
            'QuizID': 'quiz-final',
            'StudentID': 'student-123',
            'QuizType': 'final_exam',
            'Topic': 'final_exam',
            'Questions': ['q-c', 'q-s', 'q-comp', 'q-bill'],
            'Status': 'completed',
            'CreatedAt': datetime.now(timezone.utc).isoformat(),
        }
        mock_questions.name = 'test-questions'
        mock_quizzes.get_item.return_value = {'Item': quiz}
        mock_results.query.return_value = {'Items': [
            make_result_item(result_id='r1', quiz_id='quiz-final', question_id='q-c'),
            make_result_item(result_id='r2', quiz_id='quiz-final', question_id='q-s'),
            make_result_item(result_id='r3', quiz_id='quiz-final', question_id='q-comp'),
            make_result_item(result_id='r4', quiz_id='quiz-final', question_id='q-bill'),
        ]}
        mock_questions.meta.client.batch_get_item.return_value = {
            'Responses': {'test-questions': [
                make_question_item('q-c', 'Cloud Concepts & Well-Architected'),
                make_question_item('q-s', 'Security, Identity & Compliance'),
                make_question_item('q-comp', 'Compute & Containers'),
                make_question_item('q-bill', 'Billing, Cost Management & Support'),
            ]}
        }

        response = quiz_engine.get_results('quiz-final', 'student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])

        self.assertIn('domain_breakdown', body)
        domains = body['domain_breakdown']
        self.assertIn('Cloud Concepts & Well-Architected Framework', domains)
        self.assertIn('Security, Identity & Compliance', domains)
        self.assertIn('Cloud Technology & Services', domains)
        self.assertIn('Billing, Pricing & Support', domains)

        for d in body['answers']:
            self.assertIn('statement', d)
            self.assertIn('correct_answers', d)
            self.assertIn('explanation', d)

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_teacher_can_access_other_student_results(self, mock_questions, mock_results, mock_quizzes, mock_students):
        import quiz_engine

        quiz = {
            'QuizID': 'quiz-other',
            'StudentID': 'student-999',
            'QuizType': 'free',
            'Topic': 'Compute & Containers',
            'Questions': ['q1'],
            'Status': 'completed',
            'CreatedAt': datetime.now(timezone.utc).isoformat(),
        }
        mock_quizzes.get_item.return_value = {'Item': quiz}
        mock_results.query.return_value = {
            'Items': [make_result_item(quiz_id='quiz-other', question_id='q1')]
        }
        mock_questions.meta.client.batch_get_item.return_value = {
            'Responses': {'test-questions': [make_question_item('q1', 'Compute & Containers')]}
        }

        claims = {'sub': 'teacher-1', 'cognito:groups': 'Teachers'}
        response = quiz_engine.get_results('quiz-other', 'other-student', claims)

        self.assertEqual(response['statusCode'], 200)

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_missing_question_in_bank_returns_fallbacks(self, mock_questions, mock_results, mock_quizzes, mock_students):
        """La pregunta no existe en el banco: 200 con fallbacks, nunca 500."""
        import quiz_engine

        quiz = {
            'QuizID': 'quiz-free',
            'StudentID': 'student-123',
            'QuizType': 'free',
            'Topic': 'Cloud Concepts & Well-Architected',
            'Questions': ['q-missing'],
            'Status': 'completed',
            'CreatedAt': datetime.now(timezone.utc).isoformat(),
        }
        mock_questions.name = 'test-questions'
        mock_quizzes.get_item.return_value = {'Item': quiz}
        mock_results.query.return_value = {'Items': [
            make_result_item(quiz_id='quiz-free', question_id='q-missing')
        ]}
        # Banco no devuelve la pregunta
        mock_questions.meta.client.batch_get_item.return_value = {'Responses': {'test-questions': []}}

        response = quiz_engine.get_results('quiz-free', 'student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        answer = body['answers'][0]
        self.assertEqual(answer['statement'], '')
        self.assertEqual(answer['correct_answers'], ['A'])
        self.assertEqual(answer['explanation'], '')

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_malformed_legacy_options_list_does_not_500(self, mock_questions, mock_results, mock_quizzes, mock_students):
        """Ítem legacy con Options como lista y sin CorrectAnswers: 200 sin excepción."""
        import quiz_engine

        quiz = {
            'QuizID': 'quiz-legacy',
            'StudentID': 'student-123',
            'QuizType': 'free',
            'Topic': 'Compute & Containers',
            'Questions': ['q-legacy'],
            'Status': 'completed',
            'CreatedAt': datetime.now(timezone.utc).isoformat(),
        }
        mock_questions.name = 'test-questions'
        mock_quizzes.get_item.return_value = {'Item': quiz}
        mock_results.query.return_value = {'Items': [
            {
                'ResultID': 'r-legacy',
                'QuizID': 'quiz-legacy',
                'StudentID': 'student-123',
                'QuestionID': 'q-legacy',
                'GivenAnswers': ['A'],
                'IsCorrect': True,
                'Timestamp': datetime.now(timezone.utc).isoformat(),
            }
        ]}
        legacy_question = make_question_item('q-legacy', 'Compute & Containers')
        legacy_question['Options'] = [
            {'text': 'A', 'is_correct': True, 'explanation': 'E'},
            {'text': 'B', 'is_correct': False, 'explanation': ''}
        ]
        mock_questions.meta.client.batch_get_item.return_value = {
            'Responses': {'test-questions': [legacy_question]}
        }

        response = quiz_engine.get_results('quiz-legacy', 'student-123')

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        answer = body['answers'][0]
        self.assertEqual(answer['correct_answers'], [])
        self.assertEqual(answer['explanation'], '')

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_teacher_claim_comma_separated_accesses_other_results(self, mock_questions, mock_results, mock_quizzes, mock_students):
        import quiz_engine

        quiz = {
            'QuizID': 'quiz-other',
            'StudentID': 'student-999',
            'QuizType': 'free',
            'Topic': 'Compute & Containers',
            'Questions': ['q1'],
            'Status': 'completed',
            'CreatedAt': datetime.now(timezone.utc).isoformat(),
        }
        mock_questions.name = 'test-questions'
        mock_quizzes.get_item.return_value = {'Item': quiz}
        mock_results.query.return_value = {
            'Items': [make_result_item(quiz_id='quiz-other', question_id='q1')]
        }
        mock_questions.meta.client.batch_get_item.return_value = {
            'Responses': {'test-questions': [make_question_item('q1', 'Compute & Containers')]}
        }

        claims = {'sub': 'teacher-1', 'cognito:groups': 'Teachers,Admin'}
        response = quiz_engine.get_results('quiz-other', 'other-student', claims)

        self.assertEqual(response['statusCode'], 200)

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_claims_none_cannot_access_other_results(self, mock_questions, mock_results, mock_quizzes, mock_students):
        """claims=None: sin privilegio de teacher → 403, nunca 500."""
        import quiz_engine

        quiz = {
            'QuizID': 'quiz-other',
            'StudentID': 'student-999',
            'QuizType': 'free',
            'Topic': 'Compute & Containers',
            'Questions': ['q1'],
            'Status': 'completed',
            'CreatedAt': datetime.now(timezone.utc).isoformat(),
        }
        mock_quizzes.get_item.return_value = {'Item': quiz}
        mock_results.query.return_value = {
            'Items': [make_result_item(quiz_id='quiz-other', question_id='q1')]
        }

        response = quiz_engine.get_results('quiz-other', 'other-student', None)

        self.assertEqual(response['statusCode'], 403)


class TestSubmitAnswer(unittest.TestCase):
    """Tarea 9.2: persistencia de CorrectAnswers e idempotencia."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.questions_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.quizzes_table')
    def test_persists_correct_answers(self, mock_quizzes, mock_results, mock_questions, mock_students):
        import quiz_engine

        # Student activo
        mock_students.get_item.return_value = {
            'Item': make_student_item(phase='free_practice', release_delta_days=None)
        }
        # Pregunta con A correcta
        mock_questions.get_item.return_value = {'Item': make_question_item('q1')}
        # Sin resultado previo
        mock_results.query.return_value = {'Items': []}
        mock_quizzes.get_item.return_value = {
            'Item': {
                'QuizID': 'quiz-1',
                'StudentID': 'student-123',
                'QuizType': 'free',
                'Questions': ['q1'],
                'Status': 'in_progress',
            }
        }

        response = quiz_engine.submit_answer('student-123', {
            'quiz_id': 'quiz-1',
            'question_id': 'q1',
            'given_answers': ['A']
        })

        self.assertEqual(response['statusCode'], 201)
        body = json.loads(response['body'])
        self.assertTrue(body['is_correct'])

        put_kwargs = mock_results.put_item.call_args[1]
        item = put_kwargs['Item']
        self.assertIn('CorrectAnswers', item)
        self.assertEqual(item['CorrectAnswers'], ['A'])
        self.assertIn('GivenAnswers', item)
        self.assertIn('IsCorrect', item)

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.questions_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.quizzes_table')
    def test_duplicate_answer_does_not_overwrite(self, mock_quizzes, mock_results, mock_questions, mock_students):
        import quiz_engine

        mock_students.get_item.return_value = {
            'Item': make_student_item(phase='free_practice', release_delta_days=None)
        }
        mock_questions.get_item.return_value = {'Item': make_question_item('q1')}

        # Ya existe un resultado para quiz-1 + q1 con respuesta B (incorrecta)
        existing = make_result_item(result_id='r-original', quiz_id='quiz-1',
                                    question_id='q1', given=['B'], correct=['A'], is_correct=False)
        mock_results.query.return_value = {'Items': [existing]}

        response = quiz_engine.submit_answer('student-123', {
            'quiz_id': 'quiz-1',
            'question_id': 'q1',
            'given_answers': ['A']
        })

        self.assertEqual(response['statusCode'], 201)
        body = json.loads(response['body'])
        self.assertEqual(body['result_id'], 'r-original')
        # La respuesta original (incorrecta) se conserva, no se sobreescribe
        self.assertFalse(body['is_correct'])

        mock_results.put_item.assert_not_called()

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.questions_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.quizzes_table')
    def test_missing_fields_returns_400(self, mock_quizzes, mock_results, mock_questions, mock_students):
        import quiz_engine

        mock_students.get_item.return_value = {
            'Item': make_student_item(phase='free_practice', release_delta_days=None)
        }

        response = quiz_engine.submit_answer('student-123', {})
        self.assertEqual(response['statusCode'], 400)

        response = quiz_engine.submit_answer('student-123', {
            'quiz_id': 'quiz-1',
            'question_id': 'q1',
            'given_answers': []
        })
        self.assertEqual(response['statusCode'], 400)


if __name__ == '__main__':
    unittest.main()