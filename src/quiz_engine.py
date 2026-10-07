import json
import uuid
import os
import re
import random
import difflib
import unicodedata
import boto3
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

# Configuración de Entorno
dynamodb = boto3.resource('dynamodb')
questions_table = dynamodb.Table(os.environ['QUESTIONS_TABLE'])
quizzes_table = dynamodb.Table(os.environ['QUIZZES_TABLE'])
quiz_results_table = dynamodb.Table(os.environ['QUIZ_RESULTS_TABLE'])
students_table = dynamodb.Table(os.environ['STUDENTS_TABLE'])
cohorts_table = dynamodb.Table(os.environ['COHORTS_TABLE'])

# Un lock de generación más viejo que esto se considera abandonado (Lambda cortada por
# timeout: el `finally` no corre). Debe ser MAYOR que el timeout de la Lambda (25 s en
# lambda_quiz_engine.tf) para que una ejecución lenta pero viva no pierda su lock.
GENERATION_LOCK_STALE_SECONDS = 30

# Tope de preguntas en un quiz de práctica libre (el frontend ofrece 1-10)
MAX_FREE_QUIZ_QUESTIONS = 20

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
    query_params = event.get('queryStringParameters') or {}

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

    # Idioma solicitado para el contenido de la BD (enunciados/opciones/explicaciones).
    # 'en' por defecto; solo se traduce a 'pt' si la pregunta ya tiene traducción, ver
    # clean_question(). Body para POST, query string para GET.
    lang = body.get('lang') or query_params.get('lang') or 'en'

    # Enrutamiento basado en route_key
    if route_key == 'POST /quizzes/generate':
        return generate_quiz(student_id, body, lang)
    elif route_key == 'POST /quizzes/submit':
        return submit_answer(student_id, body, lang)
    elif route_key == 'GET /quizzes/{quizId}/results':
        quiz_id = path_params.get('quizId')
        return get_results(quiz_id, student_id, claims, lang)
    elif route_key == 'GET /quizzes/{quizId}':
        quiz_id = path_params.get('quizId')
        return get_quiz(quiz_id, student_id, lang)
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


def parse_iso_datetime_utc(value):
    """Parsea un string ISO-8601 a datetime tz-aware. Un valor naive se asume UTC.
    Lanza ValueError si no parsea — el caller decide devolver 400.

    NOTA: función DUPLICADA IDÉNTICA en student_api.py y quiz_engine.py — cada
    Lambda se empaqueta como un único .py (archive_file source_file), no hay
    módulo compartido. Si se cambia una copia, cambiar la otra.
    """
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def evaluate_access(student, cohort, now=None):
    """Decide si el alumno tiene acceso. Retorna (bool, motivo).

    Precedencia (ver doc/ciclo-de-vida-turmas.md):
      1. AccessStatus == 'blocked'                       -> sin acceso
      2. AccessStatus == 'open' y AccessUntil vigente/ausente -> con acceso
      3. Turma con Status == 'closed'                    -> sin acceso
      4. Caso contrario                                  -> con acceso
    No hay vencimiento automático: el ciclo lo cierra el profesor.

    NOTA: función DUPLICADA IDÉNTICA en student_api.py y quiz_engine.py — cada
    Lambda se empaqueta como un único .py (archive_file source_file), no hay
    módulo compartido. Si se cambia una copia, cambiar la otra.
    """
    now = now or datetime.now(timezone.utc)
    status = (student or {}).get('AccessStatus')
    if status == 'blocked':
        return False, 'blocked'
    if status == 'open':
        until = student.get('AccessUntil')
        if not until:
            return True, 'open'
        try:
            if parse_iso_datetime_utc(until) > now:
                return True, 'open'
        except ValueError:
            pass
    if (cohort or {}).get('Status') == 'closed':
        return False, 'cohort_closed'
    return True, 'active'


def student_cycle(student):
    """Ciclo actual del alumno (1 si nunca se reinició)."""
    return int((student or {}).get('Cycle', 1))


def quiz_cycle(quiz):
    """Ciclo al que pertenece un quiz (los anteriores a los ciclos no tienen el campo)."""
    return int((quiz or {}).get('Cycle', 1))


def check_student_access(student_id):
    """Verifica si el estudiante tiene acceso vigente. Retorna el error (para 403) o None."""
    student_response = students_table.get_item(Key={'StudentID': student_id})
    student = student_response.get('Item')

    if not student:
        return {'error': 'Student not found'}

    cohort = None
    if student.get('CohortID'):
        cohort = cohorts_table.get_item(Key={'CohortID': student['CohortID']}).get('Item')
    allowed, _ = evaluate_access(student, cohort)
    if not allowed:
        return {'error': 'Acesso encerrado. Entre em contato com seu instrutor.', 'code': 'access_closed'}

    return None


def clean_question(q, lang='en'):
    """Limpia una pregunta de DynamoDB ocultando is_correct y explanation.

    Si lang=='pt' y existe la traducción (QuestionText_pt / Options[*].text_pt), la
    devuelve en el mismo campo ('statement'/'text') que ya usa el frontend -- así no hace
    falta tocar quiz.html/results.html, solo qué idioma se pide. Si falta la traducción
    (pregunta vieja aún no traducida, o campo vacío), cae a inglés sin romper nada.
    """
    raw_options = q.get('Options', {})
    cleaned_options = {}
    for key, opt in raw_options.items():
        text = opt.get('text_pt') or opt.get('text', '') if lang == 'pt' else opt.get('text', '')
        cleaned_options[key] = {
            'text': text,
            'keywords': opt.get('keywords', '')
        }
    statement = q.get('QuestionText_pt') or q.get('QuestionText', '') if lang == 'pt' else q.get('QuestionText', '')
    return {
        'question_id': q['QuestionID'],
        'topic': q['Topic'],
        'type': q.get('QuestionType', 'single'),
        'statement': statement,
        'options': cleaned_options
    }


def build_option_breakdown(options, lang='en'):
    """Devuelve cada opción (letra, texto, si es correcta, explicación) en el idioma
    pedido, para mostrar por qué cada alternativa es o no la correcta."""
    if not isinstance(options, dict):
        return []
    text_key = 'text_pt' if lang == 'pt' else 'text'
    explanation_key = 'explanation_pt' if lang == 'pt' else 'explanation'
    breakdown = []
    for key in sorted(options.keys()):
        opt = options[key]
        if not isinstance(opt, dict):
            continue
        breakdown.append({
            'key': key,
            'text': opt.get(text_key) or opt.get('text', ''),
            'is_correct': bool(opt.get('is_correct', False)),
            'explanation': opt.get(explanation_key) or opt.get('explanation', ''),
        })
    return breakdown


def generate_quiz(student_id, body, lang='en'):
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

    cycle = student_cycle(student)
    if quiz_type == 'initial':
        return generate_initial_quiz(student_id, lang, cycle)
    elif quiz_type == 'final_exam':
        return generate_final_exam(student_id, lang)

    # Práctica Libre por Tema
    topic = body.get('topic')
    count = body.get('num_questions', 5)

    if not topic:
        return build_response(400, {'error': 'O campo topic é obrigatório'})
    # Entero acotado: un valor enorme hacía que la query trajera todo el tema y el filtro
    # de casi-duplicados (O(n²)) llegara al timeout; un string se multiplicaba ("5"*3).
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_FREE_QUIZ_QUESTIONS:
        return build_response(400, {
            'error': f'num_questions deve ser um inteiro entre 1 e {MAX_FREE_QUIZ_QUESTIONS}'
        })

    response_query = questions_table.query(
        IndexName='TopicIndex',
        KeyConditionExpression=Key('Topic').eq(topic),
        Limit=count * 3
    )
    # TopicIndex no tiene sort key: sin shuffle, DynamoDB devuelve siempre el mismo
    # orden de inserción y el alumno recibe las mismas preguntas en cada práctica.
    candidates = response_query.get('Items', [])
    random.shuffle(candidates)

    if not candidates:
        return build_response(404, {'error': f'No questions found for topic: {topic}'})

    answered_ids = get_student_answered_question_ids(student_id)

    question_ids = []
    cleaned_questions = []
    chosen = NearDuplicateIndex()

    selected = 0
    # Pase 1: sin preguntas ya respondidas ni casi-duplicadas de otra ya elegida
    # en esta misma tanda de práctica (misma pregunta reformulada dos veces).
    for q in candidates:
        if selected >= count:
            break
        text = q.get('QuestionText', '')
        if q['QuestionID'] not in answered_ids and not chosen.is_duplicate(text):
            question_ids.append(q['QuestionID'])
            cleaned_questions.append(clean_question(q, lang))
            chosen.add(text)
            selected += 1

    # Pase 2 (fallback): completar la cantidad pedida igual si el tema no tiene
    # suficientes preguntas únicas — nunca dejar la práctica con menos preguntas.
    if selected < count:
        for q in candidates:
            if selected >= count:
                break
            if q['QuestionID'] not in question_ids:
                question_ids.append(q['QuestionID'])
                cleaned_questions.append(clean_question(q, lang))
                selected += 1

    quiz_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    quizzes_table.put_item(Item={
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuizType': 'free',
        'Topic': topic,
        'Questions': question_ids,
        'Status': 'in_progress',
        'CreatedAt': created_at,
        'Cycle': cycle
    })

    return build_response(201, {
        'quiz_id': quiz_id,
        'student_id': student_id,
        'quiz_type': 'free',
        'topic': topic,
        'questions': cleaned_questions
    })


def _find_in_progress_initial(student_id, cycle=1):
    response = quizzes_table.query(
        IndexName='StudentIndex',
        KeyConditionExpression=Key('StudentID').eq(student_id),
        FilterExpression=Attr('QuizType').eq('initial')
    )
    return next((q for q in response.get('Items', [])
                 if q.get('Status') == 'in_progress' and quiz_cycle(q) == cycle), None)


def generate_initial_quiz(student_id, lang='en', cycle=1):
    """Genera el diagnóstico inicial, o reanuda el que ya esté en curso.

    Mismo patrón que generate_final_exam: sin el lock, dos requests casi simultáneas
    (doble tap en "Iniciar teste") creaban dos diagnósticos para el mismo alumno
    (bug 29-Sep: alumna con un inicial completado y otro "in_progress" 0/20,
    creados con 2 s de diferencia)."""
    in_progress = _find_in_progress_initial(student_id, cycle)
    if in_progress:
        return resume_quiz(in_progress, lang)

    if not _acquire_generation_lock(student_id, 'InitialTestGenerationLock'):
        return build_response(409, {
            'error': 'Já existe uma geração do teste inicial em andamento para este aluno. '
                     'Aguarde alguns segundos e tente novamente.'
        })

    try:
        # Double-check con datos frescos: otra request pudo crearlo mientras esperábamos el lock.
        in_progress = _find_in_progress_initial(student_id, cycle)
        if in_progress:
            return resume_quiz(in_progress, lang)
        return _create_initial_quiz(student_id, lang, cycle)
    finally:
        _release_generation_lock(student_id, 'InitialTestGenerationLock')


def _create_initial_quiz(student_id, lang='en', cycle=1):
    """Selecciona 20 preguntas distribuidas por temas y crea el quiz. Se asume que
    ya se tiene el lock de generación (ver generate_initial_quiz)."""
    topic_buckets = []
    chosen = NearDuplicateIndex()

    for topic, count in INITIAL_TEST_DISTRIBUTION.items():
        if count == 0:
            continue
        response_query = questions_table.query(
            IndexName='TopicIndex',
            KeyConditionExpression=Key('Topic').eq(topic),
            Limit=count * 3
        )
        # TopicIndex no tiene sort key: sin shuffle, DynamoDB devuelve siempre el
        # mismo orden de inserción y el diagnóstico sale idéntico entre alumnos.
        candidates = response_query.get('Items', [])
        random.shuffle(candidates)

        bucket = []
        # Pase 1: evitar casi-duplicadas de otras ya elegidas en este diagnóstico.
        for q in candidates:
            if len(bucket) >= count:
                break
            if not chosen.is_duplicate(q.get('QuestionText', '')):
                bucket.append((q['QuestionID'], clean_question(q, lang)))
                chosen.add(q.get('QuestionText', ''))

        # Pase 2 (fallback): completar la cuota igual si el tema no tiene
        # suficientes preguntas únicas — nunca dejar el quiz corto.
        if len(bucket) < count:
            chosen_ids_here = {qid for qid, _ in bucket}
            for q in candidates:
                if len(bucket) >= count:
                    break
                if q['QuestionID'] not in chosen_ids_here:
                    bucket.append((q['QuestionID'], clean_question(q, lang)))
                    chosen.add(q.get('QuestionText', ''))

        topic_buckets.append(bucket)

    # Se intercalan los temas (round-robin) para que el orden final no agrupe
    # todo un tema al principio del quiz (p.ej. las 6 de Cloud Concepts primero).
    interleaved = interleave_by_topic(topic_buckets)
    question_ids = [qid for qid, _ in interleaved]
    cleaned_questions = [cq for _, cq in interleaved]

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
        'CreatedAt': created_at,
        'Cycle': cycle
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


def interleave_by_topic(topic_buckets):
    """Combina listas de preguntas por tema en una sola, alternando entre temas
    (round-robin) para que el orden de salida no agrupe un tema entero al principio."""
    result = []
    iterators = [iter(bucket) for bucket in topic_buckets]
    while iterators:
        next_round = []
        for it in iterators:
            item = next(it, None)
            if item is not None:
                result.append(item)
                next_round.append(it)
        iterators = next_round
    return result


SIMILARITY_THRESHOLD = 0.85


def _normalize_for_similarity(text):
    """Mismo criterio de normalización que scripts/detectar_casi_duplicados_contenido.py."""
    normalized = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode()
    normalized = re.sub(r'[^a-z0-9\s]', '', normalized.lower())
    return re.sub(r'\s+', ' ', normalized).strip()


def is_near_duplicate(text_a, text_b, threshold=SIMILARITY_THRESHOLD):
    """Detecta si dos enunciados son casi-duplicados (misma pregunta reformulada),
    con el mismo método fuzzy (difflib.SequenceMatcher) ya validado en
    scripts/detectar_casi_duplicados_contenido.py, para no elegir dos preguntas
    casi-idénticas dentro del mismo quiz.

    autojunk=False es crítico: por defecto SequenceMatcher trata como "ruido" a
    cualquier carácter que aparezca en más del 1% de una cadena de 200+ caracteres
    (típico en un enunciado de examen) -- eso incluye el espacio " ", degradando el
    ratio a ~0.25 incluso entre dos preguntas idénticas en un 90%. Bug encontrado
    26-Sep: 2 preguntas casi-idénticas ("empresa não sabe prever a demanda...")
    con distinta clave de respuesta correcta salieron ambas en el mismo examen sin
    ser detectadas como casi-duplicadas por este motivo."""
    a, b = _normalize_for_similarity(text_a), _normalize_for_similarity(text_b)
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= threshold


class NearDuplicateIndex:
    """Mismo resultado que `any(is_near_duplicate(text, c) for c in chosen)`, pero
    5-8x más rápido. Sin esto el examen final (65 preguntas, miles de comparaciones con
    autojunk=False) superaba el timeout de 15 s de la Lambda: el alumno veía
    "Internal Server Error" y, como el `finally` no llega a liberar el lock, los
    reintentos devolvían 409 (bug 30-Sep).

    - Un SequenceMatcher por texto elegido, con ese texto como seq2: difflib cachea el
      análisis de seq2, y el orden (candidato=a, elegido=b) es el mismo de
      is_near_duplicate (ratio() no es simétrico).
    - real_quick_ratio() y quick_ratio() son cotas superiores de ratio(): descartan rápido
      los pares claramente distintos sin cambiar el resultado.
    - El texto normalizado se calcula una sola vez por enunciado."""

    def __init__(self, threshold=SIMILARITY_THRESHOLD):
        self.threshold = threshold
        self._matchers = []

    def is_duplicate(self, text):
        a = _normalize_for_similarity(text)
        if not a:
            return False
        th = self.threshold
        for m in self._matchers:
            m.set_seq1(a)
            if m.real_quick_ratio() >= th and m.quick_ratio() >= th and m.ratio() >= th:
                return True
        return False

    def add(self, text):
        b = _normalize_for_similarity(text)
        if b:
            m = difflib.SequenceMatcher(None, autojunk=False)
            m.set_seq2(b)
            self._matchers.append(m)


def can_generate_final_exam(completed_count):
    """Property 3: solo se permite generar el examen final si no hay ninguno completado."""
    return completed_count == 0


def compute_active_questions(all_questions, answered):
    """Property 4: preguntas activas = todas - respondidas, sin duplicados ni pérdidas."""
    answered_set = set(answered)
    return [qid for qid in all_questions if qid not in answered_set]


def resume_quiz(quiz, lang='en'):
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
            cleaned_questions.append(clean_question(q, lang))

    return build_response(200, {
        'quiz_id': quiz['QuizID'],
        'student_id': quiz['StudentID'],
        'quiz_type': quiz.get('QuizType', 'final_exam'),
        'topic': quiz.get('Topic', 'final_exam'),
        'status': quiz.get('Status', 'in_progress'),
        'questions': cleaned_questions,
        'answered_question_ids': answered_ids
    })


def generate_final_exam(student_id, lang='en'):
    """Genera examen final de 65 preguntas con anti-repetición y manejo de quiz en progreso."""
    student_response = students_table.get_item(Key={'StudentID': student_id})
    student = student_response.get('Item', {})
    if not student:
        return build_response(404, {'error': 'Student not found'})

    # Revisar exámenes finales del alumno en su ciclo actual (un reintento
    # "Recomeçar do zero" abre un ciclo nuevo con derecho a otro examen final)
    cycle = student_cycle(student)
    quizzes_response = quizzes_table.query(
        IndexName='StudentIndex',
        KeyConditionExpression=Key('StudentID').eq(student_id),
        FilterExpression=Attr('QuizType').eq('final_exam')
    )
    exams = [q for q in quizzes_response.get('Items', []) if quiz_cycle(q) == cycle]
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
    try:
        release_dt = parse_iso_datetime_utc(release_date)
    except ValueError:
        return build_response(400, {
            'error': f'FinalExamReleaseDate mal formada ({release_date!r}). '
                     f'Contate seu instrutor para reconfigurar a data.'
        })
    if datetime.now(timezone.utc) < release_dt:
        formatted = release_dt.strftime('%d/%m/%Y %H:%M')
        return build_response(403, {
            'error': f'Exame disponível a partir de {formatted}'
        })

    # Reanudar examen final en progreso si existe (no crear uno nuevo)
    in_progress_quiz = next((q for q in exams if q.get('Status') == 'in_progress'), None)
    if in_progress_quiz:
        return resume_quiz(in_progress_quiz, lang)

    # Bloqueo atómico contra condición de carrera: si el alumno dispara varias
    # requests casi simultáneas (doble tap, reintento de red en mobile), sin esto
    # cada una lee "no hay examen en curso" antes de que la otra termine de
    # escribir, y las dos crean un examen final -> duplicados fantasma vacíos
    # (bug reportado 26-Sep: 2 exámenes "in_progress" con 0/65 respondidas).
    if not _acquire_generation_lock(student_id, 'FinalExamGenerationLock'):
        return build_response(409, {
            'error': 'Já existe uma geração de exame final em andamento para este aluno. '
                     'Aguarde alguns segundos e tente novamente.'
        })

    try:
        # Volver a chequear con datos frescos por si otra request creó el examen
        # mientras se esperaba el lock (double-check locking).
        recheck_response = quizzes_table.query(
            IndexName='StudentIndex',
            KeyConditionExpression=Key('StudentID').eq(student_id),
            FilterExpression=Attr('QuizType').eq('final_exam')
        )
        recheck_exams = [q for q in recheck_response.get('Items', []) if quiz_cycle(q) == cycle]
        existing_in_progress = next((q for q in recheck_exams if q.get('Status') == 'in_progress'), None)
        if existing_in_progress:
            return resume_quiz(existing_in_progress, lang)
        if any(q.get('Status') == 'completed' for q in recheck_exams):
            return build_response(403, {
                'error': 'Você já realizou o exame final. Contate seu instrutor para um novo intento.'
            })

        return _create_final_exam_quiz(student_id, lang, cycle)
    finally:
        _release_generation_lock(student_id, 'FinalExamGenerationLock')


def _acquire_generation_lock(student_id, lock_attr, stale_seconds=None):
    """Lock atómico (ConditionExpression) en el item del alumno para serializar la
    generación de un quiz. Retorna False si otra request ya tiene el lock.
    Un lock más viejo que stale_seconds se considera abandonado (Lambda caída a
    mitad de la generación) y se puede tomar igual."""
    if stale_seconds is None:
        stale_seconds = GENERATION_LOCK_STALE_SECONDS
    now = datetime.now(timezone.utc)
    try:
        students_table.update_item(
            Key={'StudentID': student_id},
            UpdateExpression=f'SET {lock_attr} = :token, {lock_attr}At = :now',
            ConditionExpression=f'attribute_not_exists({lock_attr}) OR {lock_attr}At < :stale',
            ExpressionAttributeValues={
                ':token': str(uuid.uuid4()),
                ':now': now.isoformat(),
                ':stale': (now - timedelta(seconds=stale_seconds)).isoformat(),
            }
        )
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return False
        raise


def _release_generation_lock(student_id, lock_attr):
    students_table.update_item(
        Key={'StudentID': student_id},
        UpdateExpression=f'REMOVE {lock_attr}, {lock_attr}At'
    )


def _create_final_exam_quiz(student_id, lang='en', cycle=1):
    """Selecciona las 65 preguntas y crea el quiz. Se asume que ya se tiene el
    lock de generación (ver generate_final_exam) y que no hay otro examen final
    en curso o completado para este alumno."""
    answered_ids = get_student_answered_question_ids(student_id)

    topic_buckets = []
    chosen_ids = set()
    chosen = NearDuplicateIndex()

    for topic, count in FINAL_EXAM_DISTRIBUTION.items():
        if count == 0:
            continue

        response = questions_table.query(
            IndexName='TopicIndex',
            KeyConditionExpression=Key('Topic').eq(topic),
            Limit=count * 3
        )
        # TopicIndex es HASH-only (sin sort key): DynamoDB devuelve los ítems siempre
        # en el mismo orden (de inserción). Sin shuffle, dos generaciones para el mismo
        # tema traen literalmente las mismas primeras `count` preguntas -> exámenes
        # idénticos entre intentos (p.ej. tras un reset del profesor, ver changelog).
        candidates = response.get('Items', [])
        random.shuffle(candidates)

        bucket = []
        selected = 0
        # Pase 1: sin repetir preguntas ya vistas por el alumno ni casi-duplicadas
        # de otra ya elegida en este examen (p.ej. 3 variantes de "¿qué es Inspector?").
        for q in candidates:
            if selected >= count:
                break
            if (q['QuestionID'] not in answered_ids and q['QuestionID'] not in chosen_ids
                    and not chosen.is_duplicate(q.get('QuestionText', ''))):
                bucket.append((q['QuestionID'], clean_question(q, lang)))
                chosen_ids.add(q['QuestionID'])
                chosen.add(q.get('QuestionText', ''))
                selected += 1

        # Pase 2 (fallback): si el tema no tiene suficientes preguntas únicas, se
        # completa la cuota igual ignorando anti-repetición y anti-similaridad —
        # nunca debe quedar el examen corto por falta de contenido en el banco.
        if selected < count:
            for q in candidates:
                if selected >= count:
                    break
                if q['QuestionID'] not in chosen_ids:
                    bucket.append((q['QuestionID'], clean_question(q, lang)))
                    chosen_ids.add(q['QuestionID'])
                    chosen.add(q.get('QuestionText', ''))
                    selected += 1

        topic_buckets.append(bucket)

    # Se intercalan los temas (round-robin) para que el orden final no agrupe
    # todo un tema al principio del examen (p.ej. las 16 de Cloud Concepts primero).
    interleaved = interleave_by_topic(topic_buckets)
    question_ids = [qid for qid, _ in interleaved]
    cleaned_questions = [cq for _, cq in interleaved]

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
        'CreatedAt': created_at,
        'Cycle': cycle
    })

    return build_response(201, {
        'quiz_id': quiz_id,
        'student_id': student_id,
        'quiz_type': 'final_exam',
        'topic': 'final_exam',
        'questions': cleaned_questions
    })


def get_quiz(quiz_id, student_id, lang='en'):
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
            cleaned_questions.append(clean_question(q, lang))

    return build_response(200, {
        'quiz_id': quiz['QuizID'],
        'student_id': quiz['StudentID'],
        'quiz_type': quiz.get('QuizType', 'free'),
        'topic': quiz.get('Topic', ''),
        'status': quiz.get('Status', 'in_progress'),
        'questions': cleaned_questions,
        'answered_question_ids': answered_question_ids
    })


def complete_quiz(quiz_id, student_id, pending_result=None):
    """Marca un quiz como completado, calcula score y aplica lógica de progresión de fases.

    pending_result: respuesta recién guardada por submit_answer. El GSI QuizIndex es
    eventualmente consistente y puede no devolverla todavía; se suma a mano para que
    el score no pierda la última respuesta."""
    # Lectura consistente: el frontend llama a /complete justo después del último submit
    # y una lectura eventual podía ver "in_progress" en un quiz ya completado.
    quiz_response = quizzes_table.get_item(Key={'QuizID': quiz_id}, ConsistentRead=True)
    quiz = quiz_response.get('Item')

    if not quiz:
        return build_response(404, {'error': f'Quiz not found: {quiz_id}'})

    if quiz.get('StudentID') != student_id:
        return build_response(403, {'error': 'Forbidden: You cannot complete a quiz that is not yours'})

    # Un quiz completado (o reseteado por el profesor) no se vuelve a completar:
    # antes se podía re-ejecutar y sobrescribir el score (auditoría 30-Sep).
    if quiz.get('Status') != 'in_progress':
        return build_response(409, {'error': 'Quiz is not in progress'})

    completed_at = datetime.now(timezone.utc).isoformat()

    # Calcular score desde quiz_results. Solo cuentan las preguntas del quiz: respuestas
    # "sueltas" podían sumar por encima del 100 %.
    results_response = quiz_results_table.query(
        IndexName='QuizIndex',
        KeyConditionExpression=Key('QuizID').eq(quiz_id)
    )
    quiz_questions = set(quiz.get('Questions', []))
    results = [r for r in results_response.get('Items', []) if r.get('QuestionID') in quiz_questions]
    if pending_result and pending_result.get('QuestionID') in quiz_questions \
            and pending_result.get('QuestionID') not in {r.get('QuestionID') for r in results}:
        results.append(pending_result)
    total_questions = len(quiz.get('Questions', []))
    answered_questions = len(results)
    correct_answers = sum(1 for r in results if r.get('IsCorrect', False))
    score_percentage = Decimal(str(round((correct_answers / total_questions) * 100, 1))) if total_questions > 0 else Decimal('0')

    # Guardar status, fecha y score en el quiz. Condicional: si dos llamadas compiten
    # (auto-completado del submit y /complete del frontend), solo una gana; la otra no
    # sobrescribe el score ni duplica el avance de fase.
    try:
        quizzes_table.update_item(
            Key={'QuizID': quiz_id},
            UpdateExpression='SET #s = :status, CompletedAt = :completed_at, ScorePercentage = :score',
            ConditionExpression='#s = :in_progress',
            ExpressionAttributeNames={'#s': 'Status'},
            ExpressionAttributeValues={
                ':status': 'completed',
                ':completed_at': completed_at,
                ':score': score_percentage,
                ':in_progress': 'in_progress'
            }
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return build_response(409, {'error': 'Quiz is not in progress'})
        raise

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


def submit_answer(student_id, body, lang='en'):
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
    if not isinstance(given_answers, list) or not all(isinstance(a, str) for a in given_answers):
        return build_response(400, {'error': 'given_answers must be an array of option letters'})

    # Validar el quiz ANTES de calificar: la respuesta incluye la clave y las explicaciones.
    # Sin esto, un alumno podía mandar cualquier quiz_id (inexistente o ajeno) con un
    # question_id real y obtener la respuesta correcta de cualquier pregunta del banco,
    # incluso durante el examen final (auditoría de seguridad 30-Sep).
    quiz = quizzes_table.get_item(Key={'QuizID': quiz_id}).get('Item')
    if not quiz or quiz.get('StudentID') != student_id:
        return build_response(403, {'error': 'Forbidden: quiz not found or not yours'})
    if question_id not in quiz.get('Questions', []):
        return build_response(403, {'error': 'Forbidden: question is not part of this quiz'})

    question_response = questions_table.get_item(Key={'QuestionID': question_id})
    question = question_response.get('Item')

    if not question:
        return build_response(404, {'error': f'Question not found: {question_id}'})

    options = question.get('Options', {})

    # Normalizar respuestas del alumno a mayúsculas
    normalized_given = [a.strip().upper() for a in given_answers]
    correct_options = sorted([k.strip().upper() for k, opt in options.items() if opt.get('is_correct', False)])

    is_correct = grade_answer(normalized_given, correct_options)

    # Desglose de todas las opciones (correcta e incorrectas) con su explicación,
    # para que el frontend siempre pueda mostrar por qué cada alternativa es o no
    # la mejor, responda bien o mal el alumno.
    options_breakdown = build_option_breakdown(options, lang)
    explanation = next((o['explanation'] for o in options_breakdown if o['is_correct']), '')

    # No sobrescribir una respuesta ya enviada para el mismo quiz + pregunta
    existing_response = quiz_results_table.query(
        IndexName='QuizIndex',
        KeyConditionExpression=Key('QuizID').eq(quiz_id),
        FilterExpression=Attr('QuestionID').eq(question_id)
    )
    existing = existing_response.get('Items', [])
    if existing:
        result = existing[0]
        # Reenvío de una respuesta ya guardada: si el quiz quedó "in_progress" con todo
        # respondido (auto-completado perdido), se cierra ahora.
        quiz_completed = quiz.get('Status') == 'in_progress' and complete_if_all_answered(quiz, student_id)
        # already_answered + given_answers: la calificación es la de la respuesta guardada,
        # no la que el alumno acaba de marcar. Sin esto, si el frontend volvía a mostrar una
        # pregunta ya respondida (copia vieja del quiz en localStorage tras recargar), la
        # alumna marcaba B (correcta), veía "Incorreto" (se había guardado C) y la explicación
        # mostraba B como correcta (bug 04-Oct).
        return build_response(201, {
            'result_id': result['ResultID'],
            'quiz_id': quiz_id,
            'is_correct': result.get('IsCorrect', False),
            'already_answered': True,
            'given_answers': result.get('GivenAnswers', []),
            'explanation': explanation,
            'options': options_breakdown,
            'quiz_completed': quiz_completed
        })

    # Respuestas nuevas solo mientras el quiz está en curso (antes se aceptaban después
    # de completar y el score se podía recalcular con complete_quiz).
    if quiz.get('Status') != 'in_progress':
        return build_response(409, {'error': 'Quiz is not in progress'})

    result_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    new_result = {
        'ResultID': result_id,
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuestionID': question_id,
        'GivenAnswers': normalized_given,
        'CorrectAnswers': correct_options,
        'IsCorrect': is_correct,
        'Timestamp': timestamp
    }
    quiz_results_table.put_item(Item=new_result)

    # Si es la última pregunta → auto-completar
    quiz_completed = complete_if_all_answered(quiz, student_id, pending_result=new_result)

    return build_response(201, {
        'result_id': result_id,
        'quiz_id': quiz_id,
        'is_correct': is_correct,
        'already_answered': False,
        'given_answers': normalized_given,
        'explanation': explanation,
        'options': options_breakdown,
        'quiz_completed': quiz_completed
    })


def complete_if_all_answered(quiz, student_id, pending_result=None):
    """Completa el quiz si todas sus preguntas tienen respuesta. Devuelve True si lo completó.

    Bug 02-Oct: se contaban los ítems del GSI QuizIndex, que es eventualmente consistente.
    Justo después del put_item de la última respuesta la query devolvía N-1 y el quiz
    quedaba "in_progress" para siempre con todo respondido (6 quizzes atascados, entre
    ellos un diagnóstico inicial que no avanzó de fase). Ahora se cuentan QuestionIDs
    únicos y se suma la respuesta recién guardada."""
    quiz_id = quiz['QuizID']
    quiz_questions = set(quiz.get('Questions', []))
    if not quiz_questions:
        return False

    results_response = quiz_results_table.query(
        IndexName='QuizIndex',
        KeyConditionExpression=Key('QuizID').eq(quiz_id)
    )
    answered = {r.get('QuestionID') for r in results_response.get('Items', [])}
    if pending_result:
        answered.add(pending_result.get('QuestionID'))

    if not quiz_questions <= answered:
        return False

    response = complete_quiz(quiz_id, student_id, pending_result=pending_result)
    return response['statusCode'] == 200


def get_results(quiz_id, student_id, claims=None, lang='en'):
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
            options_breakdown = build_option_breakdown(options, lang)
            explanation = next((o['explanation'] for o in options_breakdown if o['is_correct']), '')
            statement = (
                q.get('QuestionText_pt') or q.get('QuestionText', '')
                if lang == 'pt' else q.get('QuestionText', '')
            )

            answers.append({
                'question_id': question_id,
                'statement': statement,
                'given_answers': result.get('GivenAnswers', []),
                'correct_answers': correct_answers_for_question,
                'is_correct': result.get('IsCorrect', False),
                'explanation': explanation,
                'options': options_breakdown
            })
        except Exception as exc:
            print(f'get_results: skipping malformed result {result.get("QuestionID", "<unknown>")}: {exc}')
            answers.append({
                'question_id': result.get('QuestionID', ''),
                'statement': '',
                'given_answers': result.get('GivenAnswers', []),
                'correct_answers': [],
                'is_correct': result.get('IsCorrect', False),
                'explanation': '',
                'options': []
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
