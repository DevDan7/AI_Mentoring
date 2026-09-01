import json
import uuid
import os
import boto3
from datetime import datetime, timezone
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
        return get_results(quiz_id, student_id)
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
    quiz_type = body.get('quiz_type', 'free')

    if quiz_type == 'initial':
        return generate_initial_quiz(student_id)

    topic = body.get('topic')
    count = body.get('count', 5)

    if not topic:
        return build_response(400, {'error': 'Topic is required'})

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
    """Marca un quiz como completado, calcula score y actualiza student si es initial."""
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
    score_percentage = round((correct_answers / total_questions) * 100, 1) if total_questions > 0 else 0

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

    # Si es el quiz inicial, marcar en el student
    if quiz.get('QuizType') == 'initial':
        students_table.update_item(
            Key={'StudentID': student_id},
            UpdateExpression='SET HasTakenInitialTest = :taken, InitialTestQuizID = :quiz_id',
            ExpressionAttributeValues={
                ':taken': True,
                ':quiz_id': quiz_id
            }
        )

    return build_response(200, {
        'message': 'Quiz completed',
        'quiz_id': quiz_id,
        'completed_at': completed_at,
        'score_percentage': score_percentage
    })


def submit_answer(student_id, body):
    """Verifica la respuesta soportando single y multiple choice.
    given_answers es una lista de letras (ej: ["A"] o ["A", "C"]).
    La calificación es correcta solo si el set de respuestas coincide exactamente con las opciones correctas."""
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
    normalized_given = set(a.strip().upper() for a in given_answers)

    # Construir el set de opciones correctas desde DynamoDB
    correct_options = set()
    for key, opt in options.items():
        if opt.get('is_correct', False):
            correct_options.add(key.strip().upper())

    # Calificación: correcto solo si ambos sets son idénticos
    is_correct = normalized_given == correct_options

    # Recoger la explicación de la primera opción correcta encontrada
    explanation = ''
    for key, opt in options.items():
        if opt.get('is_correct', False):
            explanation = opt.get('explanation', '')
            break

    result_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    quiz_results_table.put_item(Item={
        'ResultID': result_id,
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuestionID': question_id,
        'GivenAnswers': sorted(list(normalized_given)),
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


def get_results(quiz_id, student_id):
    quiz_response = quizzes_table.get_item(Key={'QuizID': quiz_id})
    quiz = quiz_response.get('Item')

    if not quiz:
        return build_response(404, {'error': f'Quiz not found: {quiz_id}'})

    if quiz.get('StudentID') != student_id:
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

    questions_details = []
    for result in results:
        questions_details.append({
            'question_id': result['QuestionID'],
            'given_answers': result.get('GivenAnswers', []),
            'is_correct': result.get('IsCorrect', False),
            'timestamp': result.get('Timestamp', '')
        })

    return build_response(200, {
        'quiz': {
            'quiz_id': quiz['QuizID'],
            'student_id': quiz['StudentID'],
            'topic': quiz.get('Topic', ''),
            'status': quiz.get('Status', ''),
            'created_at': quiz.get('CreatedAt', '')
        },
        'metrics': {
            'total_questions': total_questions,
            'answered_questions': answered_questions,
            'correct_answers': correct_answers,
            'incorrect_answers': incorrect_answers,
            'score_percentage': score_percentage
        },
        'answers': questions_details
    })
