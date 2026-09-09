import json
import uuid
import os
import re
import boto3
from datetime import datetime, timezone
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr

# Configuración de Entorno
dynamodb = boto3.resource('dynamodb')
questions_table = dynamodb.Table(os.environ['QUESTIONS_TABLE'])
quizzes_table = dynamodb.Table(os.environ['QUIZZES_TABLE'])
quiz_results_table = dynamodb.Table(os.environ['QUIZ_RESULTS_TABLE'])
students_table = dynamodb.Table(os.environ['STUDENTS_TABLE'])

# Distribución fija para el quiz diagnóstico inicial (20 preguntas)
INITIAL_TEST_DISTRIBUTION = {
    "Cloud Concepts & Well-Architected": 6,
    "Security, Identity & Compliance": 2,
    "Compute & Containers": 2,
    "Storage & Database": 2,
    "Networking & Content Delivery": 2,
    "Management, Governance & DevOps": 2,
    "Data, Analytics & Machine Learning": 1,
    "Billing, Cost Management & Support": 1,
    "Application Integration & Serverless Architecture": 1,
    "General / Otros Servicios": 1,
}

# Distribución para Examen Final (65 preguntas, matriz AWS Cloud Practitioner)
FINAL_EXAM_DISTRIBUTION = {
    "Cloud Concepts & Well-Architected": 16,
    "Security, Identity & Compliance": 20,
    "Compute & Containers": 7,
    "Storage & Database": 6,
    "Networking & Content Delivery": 5,
    "Data, Analytics & Machine Learning": 2,
    "Application Integration & Serverless Architecture": 2,
    "Billing, Cost Management & Support": 7,
    "Management, Governance & DevOps": 0,
    "General / Otros Servicios": 0,
}
# SUMA: 16 + 20 + 7 + 6 + 5 + 2 + 2 + 7 + 0 + 0 = 65

# Mapeo de tema interno -> dominio oficial CLF-C02 (para domain_breakdown)
TOPIC_TO_DOMAIN = {
    "Cloud Concepts & Well-Architected": "Cloud Concepts & Well-Architected Framework",
    "Security, Identity & Compliance": "Security, Identity & Compliance",
    "Compute & Containers": "Cloud Technology & Services",
    "Storage & Database": "Cloud Technology & Services",
    "Networking & Content Delivery": "Cloud Technology & Services",
    "Data, Analytics & Machine Learning": "Cloud Technology & Services",
    "Application Integration & Serverless Architecture": "Cloud Technology & Services",
    "Billing, Cost Management & Support": "Billing, Pricing & Support",
    "Management, Governance & DevOps": "Cloud Technology & Services",
    "General / Otros Servicios": "Cloud Technology & Services",
}

# Encabezados CORS estándar para las respuestas HTTP
HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
}


def lambda_handler(event, context):
    """Enrutador principal para el motor de simulados (formato API Gateway v2.0)"""
    route_key = event.get('routeKey')
    path_params = event.get('pathParameters', {})
    
    # Extraer claims validados del JWT de Cognito por API Gateway
    claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
    student_id = claims.get('sub')

    # Decodificar el cuerpo de la petición una sola vez
    body = {}
    if event.get('body'):
        try:
            body = json.loads(event['body'])
        except json.JSONDecodeError:
            return build_response(400, {'error': 'Invalid JSON in request body'})

    # Enrutamiento basado en route_key
    if route_key == 'POST /quizzes/generate':
        return generate_quiz(student_id, body)
    elif route_key == 'POST /quizzes/submit':
        return submit_answer(student_id, body)
    elif route_key == 'GET /quizzes/{quizId}/results':
        quiz_id = path_params.get('quizId')
        return get_results(quiz_id, student_id, claims)
    elif route_key == 'GET /quizzes/{quizId}':
        quiz_id = path_params.get('quizId')
        return get_quiz(quiz_id, student_id)
    elif route_key == 'POST /quizzes/{quizId}/complete':
        quiz_id = path_params.get('quizId')
        return complete_quiz(quiz_id, student_id)
    else:
        return build_response(404, {'error': f'Route not found: {route_key}'})


def build_response(status_code, body):
    """Auxiliar para formatear respuestas compatibles con API Gateway HTTP API v2.0"""
    return {
        'statusCode': status_code,
        'headers': HEADERS,
        'body': json.dumps(body)
    }


def is_teacher(claims):
    """True si el usuario pertenece al grupo Cognito 'Teachers'.

    Tolera todos los formatos en que puede llegar el claim 'cognito:groups',
    sin lanzar excepción:
      - API Gateway HTTP API v2: string con corchetes, separado por espacios y
        SIN comillas  ->  "[Teachers]"  |  "[Teachers Admin]"
      - JSON array string (por si AWS cambia el formato): '["Teachers"]'
      - lista/tupla/set nativa: ["Teachers", "Admin"]
      - string separado por comas (legacy): "Teachers,Admin"
      - None / no-dict / tipo no soportado  ->  False

    NOTA: función DUPLICADA IDÉNTICA en student_api.py y quiz_engine.py — cada
    Lambda se empaqueta como un único .py (archive_file source_file), no hay
    módulo compartido. Si se cambia una copia, cambiar la otra.
    """
    if not isinstance(claims, dict):
        return False

    raw = claims.get('cognito:groups')

    if isinstance(raw, (list, tuple, set)):
        groups = {str(g).strip() for g in raw}
    elif isinstance(raw, str):
        text = raw.strip()
        try:
            parsed = json.loads(text)
            groups = (
                {str(g).strip() for g in parsed}
                if isinstance(parsed, list)
                else {str(parsed).strip()}
            )
        except (json.JSONDecodeError, TypeError):
            # "[Teachers Admin]" / "Teachers,Admin" -> quitar corchetes y separar
            groups = {t for t in re.split(r'[\s,]+', text.strip('[]')) if t}
    else:
        groups = set()

    return 'Teachers' in groups


def check_student_access(student_id):
    """Verifica si el estudiante tiene acceso vigente. Retorna error 403 si expiró."""
    student_response = students_table.get_item(Key={'StudentID': student_id})
    student = student_response.get('Item')
    
    if not student:
        return {'error': 'Student not found'}
    
    access_expires_at = student.get('AccessExpiresAt')
    if access_expires_at:
        expires_dt = datetime.fromisoformat(access_expires_at.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_dt:
            return {'error': 'Access expired. Contact your instructor to renew access.'}
    
    return None


def clean_question(q):
    """Limpia una pregunta de DynamoDB ocultando is_correct y explanation."""
    raw_options = q.get('Options', {})
    cleaned_options = {}
    for key, opt in raw_options.items():
        cleaned_options[key] = {
            'text': opt.get('text', ''),
            'keywords': opt.get('keywords', '')
        }
    return {
        'question_id': q['QuestionID'],
        'topic': q['Topic'],
        'type': q.get('QuestionType', 'single'),
        'statement': q.get('QuestionText', ''),
        'options': cleaned_options
    }


def generate_quiz(student_id, body):
    # Verificar acceso del estudiante
    access_error = check_student_access(student_id)
    if access_error:
        return build_response(403, access_error)
    
    quiz_type = body.get('quiz_type', 'free')

    # Obtener datos y fase actual del alumno
    student_response = students_table.get_item(Key={'StudentID': student_id})
    student = student_response.get('Item', {})
    current_phase = student.get('CurrentPhase', 'initial')

    # Validar si el tipo de quiz está permitido para su fase actual
    ALLOWED_TYPES = {
        'initial': ['initial', 'free'],
        'free_practice': ['free', 'initial', 'final_exam'],
        'final_exam': ['final_exam', 'free'],
    }

    allowed = ALLOWED_TYPES.get(current_phase, ['free'])
    if quiz_type not in allowed:
        return build_response(403, {
            'error': f'Quiz type "{quiz_type}" not allowed in current phase "{current_phase}"',
            'current_phase': current_phase,
            'allowed_types': allowed
        })

    if quiz_type == 'initial':
        return generate_initial_quiz(student_id)
    elif quiz_type == 'final_exam':
        return generate_final_exam(student_id)

    # Práctica Libre por Tema
    topic = body.get('topic')
    count = body.get('num_questions', 5)

    if not topic:
        return build_response(400, {'error': 'O campo topic é obrigatório'})

    response_query = questions_table.query(
        IndexName='TopicIndex',
        KeyConditionExpression=Key('Topic').eq(topic),
        Limit=count
    )
    questions = response_query.get('Items', [])

    if not questions:
        return build_response(404, {'error': f'No questions found for topic: {topic}'})

    question_ids = []
    cleaned_questions = []

    for q in questions:
        question_ids.append(q['QuestionID'])
        cleaned_questions.append(clean_question(q))

    quiz_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    quizzes_table.put_item(Item={
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuizType': 'free',
        'Topic': topic,
        'Questions': question_ids,
        'Status': 'in_progress',
        'CreatedAt': created_at
    })

    return build_response(201, {
        'quiz_id': quiz_id,
        'student_id': student_id,
        'quiz_type': 'free',
        'topic': topic,
        'questions': cleaned_questions
    })


def generate_initial_quiz(student_id):
    """Genera un quiz diagnóstico con 20 preguntas distribuidas por temas."""
    question_ids = []
    cleaned_questions = []

    for topic, count in INITIAL_TEST_DISTRIBUTION.items():
        response_query = questions_table.query(
            IndexName='TopicIndex',
            KeyConditionExpression=Key('Topic').eq(topic),
            Limit=count
        )
        questions = response_query.get('Items', [])
        for q in questions:
            question_ids.append(q['QuestionID'])
            cleaned_questions.append(clean_question(q))

    if not question_ids:
        return build_response(404, {'error': 'No questions found for initial test'})

    quiz_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    quizzes_table.put_item(Item={
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuizType': 'initial',
        'Topic': 'initial',
        'Questions': question_ids,
        'Status': 'in_progress',
        'CreatedAt': created_at
    })

    # Guardar referencia del quiz en el student para poder retomarlo
    students_table.update_item(
        Key={'StudentID': student_id},
        UpdateExpression='SET InitialTestQuizID = :quiz_id',
        ExpressionAttributeValues={':quiz_id': quiz_id}
    )

    return build_response(201, {
        'quiz_id': quiz_id,
        'student_id': student_id,
        'quiz_type': 'initial',
        'topic': 'initial',
        'questions': cleaned_questions
    })


def get_student_answered_question_ids(student_id):
    """Retorna IDs de preguntas que el alumno ya respondió (anti-repetición)."""
    quizzes_response = quizzes_table.query(
        IndexName='StudentIndex',
        KeyConditionExpression=Key('StudentID').eq(student_id),
        FilterExpression=Attr('Status').eq('completed')
    )

    answered_ids = set()
    for quiz in quizzes_response.get('Items', []):
        results = quiz_results_table.query(
            IndexName='QuizIndex',
            KeyConditionExpression=Key('QuizID').eq(quiz['QuizID'])
        )
        for r in results.get('Items', []):
            answered_ids.add(r['QuestionID'])

    return answered_ids


def can_generate_final_exam(completed_count):
    """Property 3: solo se permite generar el examen final si no hay ninguno completado."""
    return completed_count == 0


def compute_active_questions(all_questions, answered):
    """Property 4: preguntas activas = todas - respondidas, sin duplicados ni pérdidas."""
    answered_set = set(answered)
    return [qid for qid in all_questions if qid not in answered_set]


def resume_quiz(quiz):
    """Retorna un quiz en progreso con las preguntas ya respondidas excluidas."""
    quiz_id = quiz['QuizID']
    results_response = quiz_results_table.query(
        IndexName='QuizIndex',
        KeyConditionExpression=Key('QuizID').eq(quiz_id)
    )
    answered_ids = [r['QuestionID'] for r in results_response.get('Items', [])]

    cleaned_questions = []
    for qid in compute_active_questions(quiz.get('Questions', []), answered_ids):
        q_response = questions_table.get_item(Key={'QuestionID': qid})
        q = q_response.get('Item')
        if q:
            cleaned_questions.append(clean_question(q))

    return build_response(200, {
        'quiz_id': quiz['QuizID'],
        'student_id': quiz['StudentID'],
        'quiz_type': quiz.get('QuizType', 'final_exam'),
        'topic': quiz.get('Topic', 'final_exam'),
        'questions': cleaned_questions,
        'answered_question_ids': answered_ids
    })


def generate_final_exam(student_id):
    """Genera examen final de 65 preguntas con anti-repetición y manejo de quiz en progreso."""
    student_response = students_table.get_item(Key={'StudentID': student_id})
    student = student_response.get('Item', {})
    if not student:
        return build_response(404, {'error': 'Student not found'})

    # Revisar exámenes finales existentes del alumno
    quizzes_response = quizzes_table.query(
        IndexName='StudentIndex',
        KeyConditionExpression=Key('StudentID').eq(student_id),
        FilterExpression=Attr('QuizType').eq('final_exam')
    )
    exams = quizzes_response.get('Items', [])
    completed_count = sum(1 for q in exams if q.get('Status') == 'completed')
    if not can_generate_final_exam(completed_count):
        return build_response(403, {
            'error': 'Você já realizou o exame final. Contate seu instrutor para um novo intento.'
        })

    # Verificar fecha de liberación del examen final
    release_date = student.get('FinalExamReleaseDate')
    if not release_date:
        return build_response(403, {
            'error': 'Exame não liberado. Contate seu instrutor.'
        })
    release_dt = datetime.fromisoformat(release_date.replace('Z', '+00:00'))
    if datetime.now(timezone.utc) < release_dt:
        formatted = release_dt.strftime('%d/%m/%Y %H:%M')
        return build_response(403, {
            'error': f'Exame disponível a partir de {formatted}'
        })

    # Reanudar examen final en progreso si existe (no crear uno nuevo)
    in_progress_quiz = next((q for q in exams if q.get('Status') == 'in_progress'), None)
    if in_progress_quiz:
        return resume_quiz(in_progress_quiz)

    answered_ids = get_student_answered_question_ids(student_id)

    question_ids = []
    cleaned_questions = []

    for topic, count in FINAL_EXAM_DISTRIBUTION.items():
        if count == 0:
            continue

        response = questions_table.query(
            IndexName='TopicIndex',
            KeyConditionExpression=Key('Topic').eq(topic),
            Limit=count * 2
        )

        selected = 0
        for q in response.get('Items', []):
            if selected >= count:
                break
            if q['QuestionID'] not in answered_ids and q['QuestionID'] not in question_ids:
                question_ids.append(q['QuestionID'])
                cleaned_questions.append(clean_question(q))
                selected += 1

        if selected < count:
            for q in response.get('Items', []):
                if selected >= count:
                    break
                if q['QuestionID'] not in question_ids:
                    question_ids.append(q['QuestionID'])
                    cleaned_questions.append(clean_question(q))
                    selected += 1

    if not question_ids:
        return build_response(404, {'error': 'No questions found for final exam'})

    quiz_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    quizzes_table.put_item(Item={
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuizType': 'final_exam',
        'Topic': 'final_exam',
        'Questions': question_ids,
        'Status': 'in_progress',
        'CreatedAt': created_at
    })

    return build_response(201, {
        'quiz_id': quiz_id,
        'student_id': student_id,
        'quiz_type': 'final_exam',
        'topic': 'final_exam',
        'questions': cleaned_questions
    })


def get_quiz(quiz_id, student_id):
    """Obtiene un quiz con todas sus preguntas y las que ya fueron respondidas."""
    quiz_response = quizzes_table.get_item(Key={'QuizID': quiz_id})
    quiz = quiz_response.get('Item')

    if not quiz:
        return build_response(404, {'error': f'Quiz not found: {quiz_id}'})

    if quiz.get('StudentID') != student_id:
        return build_response(403, {'error': 'Forbidden: You cannot access a quiz that is not yours'})

    # Obtener las respuestas ya dadas para este quiz
    results_response = quiz_results_table.query(
        IndexName='QuizIndex',
        KeyConditionExpression=Key('QuizID').eq(quiz_id)
    )
    results = results_response.get('Items', [])
    answered_question_ids = [r['QuestionID'] for r in results]

    # Reconstruir la lista completa de preguntas (en orden, limpias)
    cleaned_questions = []
    for qid in quiz.get('Questions', []):
        q_response = questions_table.get_item(Key={'QuestionID': qid})
        q = q_response.get('Item')
        if q:
            cleaned_questions.append(clean_question(q))

    return build_response(200, {
        'quiz_id': quiz['QuizID'],
        'student_id': quiz['StudentID'],
        'quiz_type': quiz.get('QuizType', 'free'),
        'topic': quiz.get('Topic', ''),
        'questions': cleaned_questions,
        'answered_question_ids': answered_question_ids
    })


def complete_quiz(quiz_id, student_id):
    """Marca un quiz como completado, calcula score y aplica lógica de progresión de fases."""
    quiz_response = quizzes_table.get_item(Key={'QuizID': quiz_id})
    quiz = quiz_response.get('Item')

    if not quiz:
        return build_response(404, {'error': f'Quiz not found: {quiz_id}'})

    if quiz.get('StudentID') != student_id:
        return build_response(403, {'error': 'Forbidden: You cannot complete a quiz that is not yours'})

    completed_at = datetime.now(timezone.utc).isoformat()

    # Calcular score desde quiz_results
    results_response = quiz_results_table.query(
        IndexName='QuizIndex',
        KeyConditionExpression=Key('QuizID').eq(quiz_id)
    )
    results = results_response.get('Items', [])
    total_questions = len(quiz.get('Questions', []))
    answered_questions = len(results)
    correct_answers = sum(1 for r in results if r.get('IsCorrect', False))
    score_percentage = Decimal(str(round((correct_answers / total_questions) * 100, 1))) if total_questions > 0 else Decimal('0')

    # Guardar status, fecha y score en el quiz
    quizzes_table.update_item(
        Key={'QuizID': quiz_id},
        UpdateExpression='SET #s = :status, CompletedAt = :completed_at, ScorePercentage = :score',
        ExpressionAttributeNames={'#s': 'Status'},
        ExpressionAttributeValues={
            ':status': 'completed',
            ':completed_at': completed_at,
            ':score': score_percentage
        }
    )

    # Lógica de progresión de fases
    quiz_type = quiz.get('QuizType')
    student_response = students_table.get_item(Key={'StudentID': student_id})
    student = student_response.get('Item', {})
    current_phase = student.get('CurrentPhase', 'initial')
    new_phase = current_phase

    # El diagnóstico inicial avanza a práctica libre sin umbral de aprobación
    if quiz_type == 'initial' and current_phase == 'initial':
        new_phase = 'free_practice'

    # Actualizar fase si cambió
    if new_phase != current_phase:
        now = datetime.now(timezone.utc).isoformat()
        students_table.update_item(
            Key={'StudentID': student_id},
            UpdateExpression='SET CurrentPhase = :phase, PhaseHistory = list_append(if_not_exists(PhaseHistory, :empty_list), :entry)',
            ExpressionAttributeValues={
                ':phase': new_phase,
                ':entry': [{'Phase': new_phase, 'UnlockedAt': now, 'UnlockedBy': 'system'}],
                ':empty_list': []
            }
        )

    # Si es el quiz inicial, marcar en el student (mantener comportamiento existente)
    if quiz_type == 'initial':
        students_table.update_item(
            Key={'StudentID': student_id},
            UpdateExpression='SET HasTakenInitialTest = :taken, InitialTestQuizID = :quiz_id',
            ExpressionAttributeValues={
                ':taken': True,
                ':quiz_id': quiz_id
            }
        )

    response = {
        'message': 'Quiz completed',
        'quiz_id': quiz_id,
        'completed_at': completed_at,
        'score_percentage': float(score_percentage)
    }

    if new_phase != current_phase:
        response['phase_advanced'] = True
        response['previous_phase'] = current_phase
        response['new_phase'] = new_phase

    return build_response(200, response)


def grade_answer(given, correct):
    """Property 2: correcto si y solo si el conjunto de respuestas coincide exactamente."""
    return set(given) == set(correct)


def submit_answer(student_id, body):
    """Verifica la respuesta soportando single y multiple choice.
    given_answers es una lista de letras (ej: ["A"] o ["A", "C"]).
    La calificación es correcta solo si el set de respuestas coincide exactamente con las opciones correctas."""
    # Verificar acceso del estudiante
    access_error = check_student_access(student_id)
    if access_error:
        return build_response(403, access_error)
    
    quiz_id = body.get('quiz_id')
    question_id = body.get('question_id')
    given_answers = body.get('given_answers', [])

    if not all([quiz_id, question_id]) or not given_answers:
        return build_response(400, {'error': 'quiz_id, question_id, and given_answers (array) are required'})

    question_response = questions_table.get_item(Key={'QuestionID': question_id})
    question = question_response.get('Item')

    if not question:
        return build_response(404, {'error': f'Question not found: {question_id}'})

    options = question.get('Options', {})

    # Normalizar respuestas del alumno a mayúsculas
    normalized_given = [a.strip().upper() for a in given_answers]
    correct_options = sorted([k.strip().upper() for k, opt in options.items() if opt.get('is_correct', False)])

    is_correct = grade_answer(normalized_given, correct_options)

    # Recoger la explicación de la primera opción correcta encontrada
    explanation = next(
        (opt.get('explanation', '') for k, opt in options.items() if opt.get('is_correct', False)),
        ''
    )

    # No sobrescribir una respuesta ya enviada para el mismo quiz + pregunta
    existing_response = quiz_results_table.query(
        IndexName='QuizIndex',
        KeyConditionExpression=Key('QuizID').eq(quiz_id),
        FilterExpression=Attr('QuestionID').eq(question_id)
    )
    existing = existing_response.get('Items', [])
    if existing:
        result = existing[0]
        return build_response(201, {
            'result_id': result['ResultID'],
            'quiz_id': quiz_id,
            'is_correct': result.get('IsCorrect', False),
            'explanation': explanation
        })

    result_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    quiz_results_table.put_item(Item={
        'ResultID': result_id,
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuestionID': question_id,
        'GivenAnswers': normalized_given,
        'CorrectAnswers': correct_options,
        'IsCorrect': is_correct,
        'Timestamp': timestamp
    })

    # Verificar si es la última pregunta → auto-completar
    quiz_response = quizzes_table.get_item(Key={'QuizID': quiz_id})
    quiz = quiz_response.get('Item')
    if quiz:
        total_questions = len(quiz.get('Questions', []))
        results_response = quiz_results_table.query(
            IndexName='QuizIndex',
            KeyConditionExpression=Key('QuizID').eq(quiz_id)
        )
        answered_count = len(results_response.get('Items', []))
        if answered_count >= total_questions:
            complete_quiz(quiz_id, student_id)

    return build_response(201, {
        'result_id': result_id,
        'quiz_id': quiz_id,
        'is_correct': is_correct,
        'explanation': explanation
    })


def get_results(quiz_id, student_id, claims=None):
    quiz_response = quizzes_table.get_item(Key={'QuizID': quiz_id})
    quiz = quiz_response.get('Item')

    if not quiz:
        return build_response(404, {'error': f'Quiz not found: {quiz_id}'})

    # Un Teacher puede consultar resultados de cualquier alumno
    is_teacher_request = is_teacher(claims)

    if quiz.get('StudentID') != student_id and not is_teacher_request:
        return build_response(403, {'error': 'Forbidden: You cannot access results for a quiz that is not yours'})

    results_response = quiz_results_table.query(
        IndexName='QuizIndex',
        KeyConditionExpression=Key('QuizID').eq(quiz_id)
    )
    results = results_response.get('Items', [])

    total_questions = len(quiz.get('Questions', []))
    answered_questions = len(results)
    correct_answers = sum(1 for r in results if r.get('IsCorrect', False))
    incorrect_answers = answered_questions - correct_answers
    score_percentage = round((correct_answers / answered_questions) * 100, 1) if answered_questions > 0 else 0

    # Cargar enunciados, respuestas correctas y explicaciones desde MentoringQuestions
    question_ids = [r['QuestionID'] for r in results if r.get('QuestionID')]
    questions_map = {}
    if question_ids:
        batch = questions_table.meta.client.batch_get_item(
            RequestItems={
                questions_table.name: {'Keys': [{'QuestionID': qid} for qid in question_ids]}
            }
        )
        for item in batch.get('Responses', {}).get(questions_table.name, []):
            questions_map[item.get('QuestionID')] = item

    answers = []
    domain_totals = {}
    domain_correct = {}

    for result in results:
        # Enriquecimiento defensivo: un ítem mal formado no debe tumbar la respuesta
        try:
            question_id = result.get('QuestionID', '')
            q = questions_map.get(question_id, {})
            topic = q.get('Topic', 'General / Otros Servicios')
            domain = TOPIC_TO_DOMAIN.get(topic, 'Cloud Technology & Services')

            domain_totals[domain] = domain_totals.get(domain, 0) + 1
            if result.get('IsCorrect', False):
                domain_correct[domain] = domain_correct.get(domain, 0) + 1

            options = q.get('Options') or {}
            if not isinstance(options, dict):
                options = {}

            correct_answers_for_question = result.get('CorrectAnswers') or [
                k.strip().upper() for k, opt in options.items()
                if isinstance(opt, dict) and opt.get('is_correct', False)
            ]
            explanation = next(
                (opt.get('explanation', '') for k, opt in options.items()
                 if isinstance(opt, dict) and opt.get('is_correct', False)),
                ''
            )

            answers.append({
                'question_id': question_id,
                'statement': q.get('QuestionText', ''),
                'given_answers': result.get('GivenAnswers', []),
                'correct_answers': correct_answers_for_question,
                'is_correct': result.get('IsCorrect', False),
                'explanation': explanation
            })
        except Exception as exc:
            print(f'get_results: skipping malformed result {result.get("QuestionID", "<unknown>")}: {exc}')
            answers.append({
                'question_id': result.get('QuestionID', ''),
                'statement': '',
                'given_answers': result.get('GivenAnswers', []),
                'correct_answers': [],
                'is_correct': result.get('IsCorrect', False),
                'explanation': ''
            })

    response = {
        'quiz': {
            'quiz_id': quiz.get('QuizID', quiz_id),
            'student_id': quiz.get('StudentID', student_id),
            'topic': quiz.get('Topic', ''),
            'status': quiz.get('Status', ''),
            'created_at': quiz.get('CreatedAt', '')
        },
        'metrics': {
            'score_percentage': score_percentage,
            'total_questions': total_questions,
            'correct_answers': correct_answers,
            'incorrect_answers': incorrect_answers
        },
        'answers': answers
    }

    if quiz.get('QuizType') == 'final_exam':
        domain_breakdown = {}
        for domain in sorted(domain_totals.keys()):
            correct = domain_correct.get(domain, 0)
            total = domain_totals[domain]
            domain_breakdown[domain] = {
                'correct': correct,
                'total': total,
                'percentage': round((correct / total) * 100, 1) if total > 0 else 0.0
            }
        response['domain_breakdown'] = domain_breakdown

    return build_response(200, response)
