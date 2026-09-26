"""Pruebas del motor de quizzes (quiz_engine.py) para el nuevo modelo.

Cubre: reanudación de examen final en progreso, bloqueo por examen completado,
enriquecimiento de get_results() (statement/correct_answers/explanation,
domain_breakdown solo para final_exam) y persistencia/idempotencia de submit_answer().
"""
import json
import random
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


def make_question_item(question_id='q1', topic='Cloud Concepts & Well-Architected', text=None):
    return {
        'QuestionID': question_id,
        'Topic': topic,
        'QuestionText': text if text is not None else f'Statement {question_id}?',
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


class TestCleanQuestionLang(unittest.TestCase):
    """Traducción PT-BR del contenido de la BD: clean_question(q, lang) devuelve el
    texto traducido si existe, y cae a inglés si falta (pregunta vieja sin traducir)."""

    def test_lang_en_default_returns_english(self):
        import quiz_engine
        q = make_question_item()
        cleaned = quiz_engine.clean_question(q)
        self.assertEqual(cleaned['statement'], 'Statement q1?')
        self.assertEqual(cleaned['options']['A']['text'], 'Option A')

    def test_lang_pt_returns_translation_when_present(self):
        import quiz_engine
        q = make_question_item()
        q['QuestionText_pt'] = 'Enunciado q1?'
        q['Options']['A']['text_pt'] = 'Opção A'
        cleaned = quiz_engine.clean_question(q, lang='pt')
        self.assertEqual(cleaned['statement'], 'Enunciado q1?')
        self.assertEqual(cleaned['options']['A']['text'], 'Opção A')

    def test_lang_pt_falls_back_to_english_when_missing(self):
        import quiz_engine
        q = make_question_item()  # sin campos _pt
        cleaned = quiz_engine.clean_question(q, lang='pt')
        self.assertEqual(cleaned['statement'], 'Statement q1?')
        self.assertEqual(cleaned['options']['A']['text'], 'Option A')


class TestBuildOptionBreakdown(unittest.TestCase):
    """Bug reportado (26-Sep): al responder correcto no se mostraba ninguna
    explicación, y al responder incorrecto solo se mostraba la de la opción
    correcta (no la elegida). Fix: devolver el desglose de TODAS las opciones."""

    def test_returns_all_options_with_explanation_and_is_correct(self):
        import quiz_engine
        q = make_question_item()
        breakdown = quiz_engine.build_option_breakdown(q['Options'])
        self.assertEqual(len(breakdown), 2)
        by_key = {o['key']: o for o in breakdown}
        self.assertTrue(by_key['A']['is_correct'])
        self.assertEqual(by_key['A']['explanation'], 'Because A')
        self.assertFalse(by_key['B']['is_correct'])
        self.assertEqual(by_key['B']['explanation'], 'No B')

    def test_lang_pt_falls_back_to_english_explanation_when_missing(self):
        import quiz_engine
        q = make_question_item()
        q['Options']['A']['text_pt'] = 'Opção A'
        # Sin explanation_pt: debe caer a la explicación en inglés.
        breakdown = quiz_engine.build_option_breakdown(q['Options'], lang='pt')
        by_key = {o['key']: o for o in breakdown}
        self.assertEqual(by_key['A']['text'], 'Opção A')
        self.assertEqual(by_key['A']['explanation'], 'Because A')

    def test_non_dict_options_returns_empty_list(self):
        import quiz_engine
        self.assertEqual(quiz_engine.build_option_breakdown(['legacy', 'list']), [])
        self.assertEqual(quiz_engine.build_option_breakdown(None), [])


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


class TestGenerateFinalExamRandomization(unittest.TestCase):
    """Bug reportado en testing E2E (22-Sep): dos exámenes finales generados para el
    mismo alumno (p.ej. tras un reset del profesor) traían las mismas preguntas en el
    mismo orden, porque TopicIndex es HASH-only (sin sort key) y DynamoDB devuelve
    siempre el mismo orden. Fix: random.shuffle() sobre los candidatos antes de elegir."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_two_generations_produce_different_question_order(
        self, mock_questions, mock_results, mock_quizzes, mock_students
    ):
        import quiz_engine

        student = make_student_item()
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.query.return_value = {'Items': []}
        mock_results.query.return_value = {'Items': []}

        # Pool en orden fijo (simula lo que devuelve TopicIndex sin sort key).
        pool = [make_question_item(f'q{i}', topic='Cloud Concepts & Well-Architected')
                for i in range(60)]
        mock_questions.query.return_value = {'Items': pool}

        with mock.patch.object(
            quiz_engine, 'FINAL_EXAM_DISTRIBUTION',
            {'Cloud Concepts & Well-Architected': 16}
        ):
            random.seed(1)
            body_a = json.loads(quiz_engine.generate_final_exam('student-123')['body'])
            random.seed(2)
            body_b = json.loads(quiz_engine.generate_final_exam('student-123')['body'])

        ids_a = [q['question_id'] for q in body_a['questions']]
        ids_b = [q['question_id'] for q in body_b['questions']]

        self.assertEqual(len(ids_a), 16)
        self.assertEqual(len(set(ids_a)), 16)  # sin duplicados dentro del examen
        self.assertNotEqual(ids_a, ids_b)


class TestInterleaveByTopic(unittest.TestCase):
    """Bug reportado (24-Sep): las primeras ~16 preguntas del examen/diagnóstico salían
    todas del mismo tema porque los buckets por tema se concatenaban sin intercalar."""

    def test_interleaves_round_robin(self):
        import quiz_engine

        buckets = [['a1', 'a2', 'a3'], ['b1'], ['c1', 'c2']]
        result = quiz_engine.interleave_by_topic(buckets)
        self.assertEqual(result, ['a1', 'b1', 'c1', 'a2', 'c2', 'a3'])

    def test_empty_buckets_are_skipped(self):
        import quiz_engine

        buckets = [[], ['b1', 'b2'], []]
        result = quiz_engine.interleave_by_topic(buckets)
        self.assertEqual(result, ['b1', 'b2'])


class TestIsNearDuplicate(unittest.TestCase):
    """Bug reportado (25-Sep): el examen final traía varias preguntas casi-idénticas
    reformuladas (3 variantes de Inspector, 2 de GuardDuty, 2 de WAF/SQLi) porque
    MentoringQuestions las tiene como QuestionID distintos. Mismo método/umbral que
    scripts/detectar_casi_duplicados_contenido.py (difflib.SequenceMatcher, 0.85)."""

    def test_reworded_question_is_flagged_as_duplicate(self):
        import quiz_engine

        a = 'What is the primary purpose of Amazon Inspector?'
        b = 'What is the main purpose of Amazon Inspector?'
        self.assertTrue(quiz_engine.is_near_duplicate(a, b))

    def test_unrelated_questions_are_not_duplicates(self):
        import quiz_engine

        a = 'What is the primary purpose of Amazon Inspector?'
        b = 'Which AWS service provides a content delivery network?'
        self.assertFalse(quiz_engine.is_near_duplicate(a, b))

    def test_empty_text_is_never_a_duplicate(self):
        import quiz_engine

        self.assertFalse(quiz_engine.is_near_duplicate('', 'Some question?'))
        self.assertFalse(quiz_engine.is_near_duplicate(None, None))


class TestGenerateFinalExamAntiSimilarity(unittest.TestCase):
    """El examen no debe elegir dos preguntas casi-idénticas del mismo tema cuando
    hay alternativas distintas disponibles, pero tampoco debe salir corto si el
    banco no tiene suficientes preguntas únicas para completar la cuota."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_prefers_distinct_questions_over_near_duplicates(
        self, mock_questions, mock_results, mock_quizzes, mock_students
    ):
        import quiz_engine

        student = make_student_item()
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.query.return_value = {'Items': []}
        mock_results.query.return_value = {'Items': []}

        # 3 reformulaciones de la misma pregunta (Inspector) + 3 preguntas distintas.
        pool = [
            make_question_item('insp-1', text='What is the primary purpose of Amazon Inspector?'),
            make_question_item('insp-2', text='What is the main purpose of Amazon Inspector?'),
            make_question_item('insp-3', text='What is the core purpose of Amazon Inspector?'),
            make_question_item('waf', text='How does AWS WAF protect web applications?'),
            make_question_item('guardduty', text='What does Amazon GuardDuty monitor?'),
            make_question_item('s3', text='Which service provides durable object storage?'),
        ]
        mock_questions.query.return_value = {'Items': pool}

        with mock.patch.object(
            quiz_engine, 'FINAL_EXAM_DISTRIBUTION',
            {'Cloud Concepts & Well-Architected': 3}
        ):
            body = json.loads(quiz_engine.generate_final_exam('student-123')['body'])

        ids = [q['question_id'] for q in body['questions']]
        self.assertEqual(len(ids), 3)
        # Con 3 preguntas distintas disponibles (waf, guardduty, s3), no debería
        # necesitar más de una variante de Inspector para llegar a la cuota.
        inspector_count = sum(1 for qid in ids if qid.startswith('insp-'))
        self.assertLessEqual(inspector_count, 1)

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_fallback_fills_quota_even_if_only_near_duplicates_available(
        self, mock_questions, mock_results, mock_quizzes, mock_students
    ):
        import quiz_engine

        student = make_student_item()
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.query.return_value = {'Items': []}
        mock_results.query.return_value = {'Items': []}

        # Solo 3 preguntas en el banco, las 3 son la misma reformulada (como
        # Security en producción: pool corto y con casi-duplicados).
        pool = [
            make_question_item('insp-1', text='What is the primary purpose of Amazon Inspector?'),
            make_question_item('insp-2', text='What is the main purpose of Amazon Inspector?'),
            make_question_item('insp-3', text='What is the core purpose of Amazon Inspector?'),
        ]
        mock_questions.query.return_value = {'Items': pool}

        with mock.patch.object(
            quiz_engine, 'FINAL_EXAM_DISTRIBUTION',
            {'Cloud Concepts & Well-Architected': 3}
        ):
            body = json.loads(quiz_engine.generate_final_exam('student-123')['body'])

        # El examen nunca debe salir corto: si no hay 3 preguntas únicas, se
        # completa igual con las casi-duplicadas que queden.
        self.assertEqual(len(body['questions']), 3)


class TestGenerateFinalExamTopicDistribution(unittest.TestCase):
    """El orden final del examen no debe agrupar un tema entero al principio."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_first_questions_are_not_all_same_topic(
        self, mock_questions, mock_results, mock_quizzes, mock_students
    ):
        import quiz_engine

        student = make_student_item()
        mock_students.get_item.return_value = {'Item': student}
        mock_quizzes.query.return_value = {'Items': []}
        mock_results.query.return_value = {'Items': []}

        def query_side_effect(**kwargs):
            topic = kwargs['KeyConditionExpression']._values[1]
            n = kwargs['Limit']
            pool = [make_question_item(f'{topic[:3]}-{i}', topic=topic) for i in range(n)]
            return {'Items': pool}

        mock_questions.query.side_effect = query_side_effect

        distribution = {
            'Cloud Concepts & Well-Architected': 16,
            'Security, Identity & Compliance': 20,
        }
        with mock.patch.object(quiz_engine, 'FINAL_EXAM_DISTRIBUTION', distribution):
            body = json.loads(quiz_engine.generate_final_exam('student-123')['body'])

        topics = [q['topic'] for q in body['questions']]
        self.assertEqual(len(topics), 36)
        # Ya no deben ser los primeros 16 preguntas del mismo tema.
        self.assertTrue(len(set(topics[:16])) > 1)


class TestGenerateQuizFreePracticeAntiRepetition(unittest.TestCase):
    """Bug reportado (24-Sep): la práctica libre repetía siempre las mismas preguntas
    porque TopicIndex (sin sort key) devuelve el mismo orden y no había anti-repetición
    ni shuffle. Fix: pool ampliado + shuffle + exclusión de answered_ids con fallback."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_excludes_already_answered_questions(
        self, mock_questions, mock_results, mock_quizzes, mock_students
    ):
        import quiz_engine

        student = make_student_item()
        mock_students.get_item.return_value = {'Item': student}

        # Textos bien distintos entre sí (no casi-duplicados) para no disparar el
        # filtro de similaridad de generate_quiz al elegir entre los no respondidos.
        distinct_texts = [
            'What is the AWS shared responsibility model?',
            'Which service provides object storage?',
            'What does an Auto Scaling group do?',
            'How does Amazon RDS handle automated backups?',
            'What is a VPC used for?',
            'Which service is used for serverless compute?',
            'What is the purpose of IAM roles?',
            'How does CloudFront reduce latency?',
            'What is Amazon SQS used for?',
            'Which billing tool tracks daily spend?',
            'What is Amazon Inspector used for?',
            'How does AWS WAF protect applications?',
            'What is the purpose of AWS Config?',
            'Which service orchestrates containers?',
            'What does Amazon GuardDuty detect?',
        ]
        pool = [make_question_item(f'q{i}', text=distinct_texts[i]) for i in range(15)]
        mock_questions.query.return_value = {'Items': pool}

        completed_quiz = {'QuizID': 'quiz-old', 'StudentID': 'student-123', 'Status': 'completed'}
        mock_quizzes.query.return_value = {'Items': [completed_quiz]}
        answered = [make_result_item(quiz_id='quiz-old', question_id=f'q{i}') for i in range(10)]
        mock_results.query.return_value = {'Items': answered}

        body = json.loads(quiz_engine.generate_quiz(
            'student-123', {'quiz_type': 'free', 'topic': 'Cloud Concepts & Well-Architected', 'num_questions': 5}
        )['body'])

        returned_ids = [q['question_id'] for q in body['questions']]
        self.assertEqual(len(returned_ids), 5)
        # Las 10 primeras (q0..q9) ya fueron respondidas; deben evitarse mientras
        # el pool alcance para completar la cantidad pedida sin repetir.
        self.assertTrue(all(qid not in [f'q{i}' for i in range(10)] for qid in returned_ids))


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
    def test_lang_pt_localizes_statement_and_explanation(
        self, mock_questions, mock_results, mock_quizzes, mock_students
    ):
        import quiz_engine

        quiz = {
            'QuizID': 'quiz-free', 'StudentID': 'student-123', 'QuizType': 'free',
            'Topic': 'Cloud Concepts & Well-Architected', 'Questions': ['q1'],
            'Status': 'completed', 'CreatedAt': datetime.now(timezone.utc).isoformat(),
        }
        question = make_question_item('q1')
        question['QuestionText_pt'] = 'Enunciado q1?'
        question['Options']['A']['explanation_pt'] = 'Porque A'

        mock_questions.name = 'test-questions'
        mock_quizzes.get_item.return_value = {'Item': quiz}
        mock_results.query.return_value = {'Items': [
            make_result_item(quiz_id='quiz-free', question_id='q1', given=['A'], correct=['A'])
        ]}
        mock_questions.meta.client.batch_get_item.return_value = {
            'Responses': {'test-questions': [question]}
        }

        response = quiz_engine.get_results('quiz-free', 'student-123', lang='pt')
        answer = json.loads(response['body'])['answers'][0]

        self.assertEqual(answer['statement'], 'Enunciado q1?')
        self.assertEqual(answer['explanation'], 'Porque A')
        # Desglose completo también en get_results (para la página de resultados).
        self.assertEqual(len(answer['options']), 2)
        by_key = {o['key']: o for o in answer['options']}
        self.assertTrue(by_key['A']['is_correct'])
        self.assertEqual(by_key['A']['explanation'], 'Porque A')
        self.assertFalse(by_key['B']['is_correct'])
        self.assertEqual(by_key['B']['explanation'], 'No B')

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

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.quizzes_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.questions_table')
    def test_teacher_json_array_string_groups_accesses_other_results(self, mock_questions, mock_results, mock_quizzes, mock_students):
        """API Gateway HTTP API v2 serializa cognito:groups como JSON string '["Teachers"]'."""
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

        claims = {'sub': 'teacher-1', 'cognito:groups': '["Teachers","Admin"]'}
        response = quiz_engine.get_results('quiz-other', 'other-student', claims)

        self.assertEqual(response['statusCode'], 200)


class TestSubmitAnswer(unittest.TestCase):
    """Tarea 9.2: persistencia de CorrectAnswers e idempotencia."""

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.questions_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.quizzes_table')
    def test_lang_pt_returns_translated_explanation(
        self, mock_quizzes, mock_results, mock_questions, mock_students
    ):
        """Bug reportado (23-Sep, capturas): el feedback inmediato de quiz.html
        mostraba la explicación siempre en inglés, aunque la UI estuviera en PT-BR."""
        import quiz_engine

        mock_students.get_item.return_value = {
            'Item': make_student_item(phase='free_practice', release_delta_days=None)
        }
        question = make_question_item('q1')
        question['Options']['A']['explanation_pt'] = 'Porque A'
        mock_questions.get_item.return_value = {'Item': question}
        mock_results.query.return_value = {'Items': []}
        mock_quizzes.get_item.return_value = {
            'Item': {
                'QuizID': 'quiz-1', 'StudentID': 'student-123', 'QuizType': 'free',
                'Questions': ['q1'], 'Status': 'in_progress',
            }
        }

        response = quiz_engine.submit_answer('student-123', {
            'quiz_id': 'quiz-1', 'question_id': 'q1', 'given_answers': ['A']
        }, lang='pt')

        body = json.loads(response['body'])
        self.assertEqual(body['explanation'], 'Porque A')
        # El desglose completo debe incluir ambas opciones (correcta e incorrecta),
        # no solo la elegida ni solo la correcta como string plano.
        self.assertEqual(len(body['options']), 2)
        by_key = {o['key']: o for o in body['options']}
        self.assertTrue(by_key['A']['is_correct'])
        self.assertEqual(by_key['A']['explanation'], 'Porque A')
        self.assertFalse(by_key['B']['is_correct'])
        self.assertEqual(by_key['B']['explanation'], 'No B')

    @mock.patch('quiz_engine.students_table')
    @mock.patch('quiz_engine.questions_table')
    @mock.patch('quiz_engine.quiz_results_table')
    @mock.patch('quiz_engine.quizzes_table')
    def test_lang_pt_falls_back_to_english_explanation_when_missing(
        self, mock_quizzes, mock_results, mock_questions, mock_students
    ):
        import quiz_engine

        mock_students.get_item.return_value = {
            'Item': make_student_item(phase='free_practice', release_delta_days=None)
        }
        mock_questions.get_item.return_value = {'Item': make_question_item('q1')}  # sin _pt
        mock_results.query.return_value = {'Items': []}
        mock_quizzes.get_item.return_value = {
            'Item': {
                'QuizID': 'quiz-1', 'StudentID': 'student-123', 'QuizType': 'free',
                'Questions': ['q1'], 'Status': 'in_progress',
            }
        }

        response = quiz_engine.submit_answer('student-123', {
            'quiz_id': 'quiz-1', 'question_id': 'q1', 'given_answers': ['A']
        }, lang='pt')

        body = json.loads(response['body'])
        self.assertEqual(body['explanation'], 'Because A')

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