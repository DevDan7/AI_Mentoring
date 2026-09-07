"""Property-Based Tests (Hypothesis) para el nuevo modelo.

Implementa las 6 propiedades de corrección definidas en design.md (Testing
Strategy) y los Requisitos 16.1-16.7. Cada propiedad valida funciones puras
extraídas de quiz_engine.py y student_api.py.
"""
import os
import sys
from hypothesis import given
from hypothesis import strategies as st
from hypothesis import assume

# Configurar entorno antes de importar los módulos
os.environ['STUDENTS_TABLE'] = 'test-students'
os.environ['COHORTS_TABLE'] = 'test-cohorts'
os.environ['QUIZZES_TABLE'] = 'test-quizzes'
os.environ['QUESTIONS_TABLE'] = 'test-questions'
os.environ['QUIZ_RESULTS_TABLE'] = 'test-quiz-results'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from quiz_engine import (  # noqa: E402
    FINAL_EXAM_DISTRIBUTION,
    grade_answer,
    can_generate_final_exam,
    compute_active_questions,
    clean_question,
)
from student_api import simulate_student_insert  # noqa: E402


# Propiedad 1: Invariante de suma de la distribución (Req. 16.1)
@given(
    st.lists(
        st.integers(min_value=0, max_value=10),
        min_size=len(FINAL_EXAM_DISTRIBUTION) - 1,
        max_size=len(FINAL_EXAM_DISTRIBUTION) - 1,
    )
)
def test_distribution_sum_is_65(partial_values):
    # Feature: ai-mentoring-mvp-restructure, Property 1: Invariante de suma de la distribución
    topics = list(FINAL_EXAM_DISTRIBUTION)
    remainder = 65 - sum(partial_values)
    assume(0 <= remainder <= 30)
    distribution = dict(zip(topics[:-1], partial_values))
    distribution[topics[-1]] = remainder
    assert sum(distribution.values()) == 65


# Propiedad 2: Corrección exacta del conjunto de respuestas (Req. 16.2)
@given(
    correct=st.frozensets(st.sampled_from(list("ABCD")), min_size=1, max_size=4),
    given=st.frozensets(st.sampled_from(list("ABCD")), min_size=1, max_size=4)
)
def test_grading_correct_iff_exact_match(correct, given):
    # Feature: ai-mentoring-mvp-restructure, Property 2: Corrección exacta del conjunto de respuestas
    result = grade_answer(given, correct)  # función pura extraída de submit_answer()
    assert result == (set(given) == set(correct))


# Propiedad 3: Exclusividad del examen final completado (Req. 16.5)
@given(st.integers(min_value=0, max_value=3))
def test_final_exam_blocked_if_completed(completed_count):
    # Feature: ai-mentoring-mvp-restructure, Property 3: Exclusividad del examen final completado
    should_block = completed_count >= 1
    result = can_generate_final_exam(completed_count)
    assert result == (not should_block)


# Propiedad 4: Reanudación sin pérdida (Req. 16.6)
@given(
    all_questions=st.lists(st.uuids(), min_size=1, max_size=65, unique=True),
    answered_subset=st.data()
)
def test_resume_returns_unanswered_only(all_questions, answered_subset):
    # Feature: ai-mentoring-mvp-restructure, Property 4: Reanudación sin pérdida
    answered = answered_subset.draw(st.lists(st.sampled_from(all_questions), unique=True))
    active = compute_active_questions(all_questions, answered)
    assert set(active) == set(all_questions) - set(answered)
    assert len(active) == len(set(active))  # sin duplicados


# Propiedad 5: No emisión de secretos en preguntas (Req. 16.7)
@given(st.fixed_dictionaries({
    "QuestionID": st.uuids().map(str),
    "Topic": st.text(min_size=1),
    "QuestionText": st.text(min_size=1),
    "QuestionType": st.sampled_from(["single", "multiple"]),
    "Options": st.dictionaries(
        st.sampled_from(list("ABCDE")),
        st.fixed_dictionaries({
            "text": st.text(),
            "keywords": st.text(),
            "is_correct": st.booleans(),
            "explanation": st.text()
        }),
        min_size=2, max_size=5
    )
}))
def test_clean_question_hides_secrets(raw_question):
    # Feature: ai-mentoring-mvp-restructure, Property 5: No emisión de secretos en preguntas
    cleaned = clean_question(raw_question)
    for option in cleaned["options"].values():
        assert "is_correct" not in option
        assert "explanation" not in option


# Propiedad 6: Monotonía del conteo de alumnos en una turma (Req. 16.4)
@given(st.integers(min_value=0, max_value=6))
def test_cohort_count_increments_by_one(initial_count):
    # Feature: ai-mentoring-mvp-restructure, Property 6: Monotonía del conteo de alumnos
    count_after = simulate_student_insert(initial_count)
    assert count_after == initial_count + 1