import json
import os
import re
import boto3
from decimal import Decimal
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr

# Inicialización del cliente de DynamoDB
dynamodb = boto3.resource('dynamodb')
students_table = dynamodb.Table(os.environ['STUDENTS_TABLE'])
cohorts_table = dynamodb.Table(os.environ['COHORTS_TABLE'])
quizzes_table = dynamodb.Table(os.environ['QUIZZES_TABLE'])

# Constante de cabeceras CORS
HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'OPTIONS,GET,POST,PUT,DELETE',
    'Content-Type': 'application/json',
}


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)


def build_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': HEADERS,
        'body': json.dumps(body, cls=DecimalEncoder),
    }


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


COHORT_TYPE_GUESTS = 'convidados'


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


def get_cohort_item(cohort_id):
    if not cohort_id:
        return None
    return cohorts_table.get_item(Key={'CohortID': cohort_id}).get('Item')


def lambda_handler(event, context):
    route_key = event.get('routeKey')
    path_params = event.get('pathParameters', {})
    
    # Extraer los claims validados directamente desde el JWT de Cognito
    claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})

    # Enrutamiento basado en el routeKey expuesto por API Gateway
    if route_key == 'GET /config':
        return get_config()
    elif route_key == 'POST /students':
        return create_student(event, claims)
    elif route_key == 'GET /students':
        return list_all_students(claims)
    elif route_key == 'GET /students/me':
        return get_student_by_claims(claims)
    elif route_key == 'PUT /students/me':
        return update_student_by_claims(event, claims)
    elif route_key == 'GET /students/{studentId}':
        student_id = path_params.get('studentId')
        return get_student(student_id, claims)
    elif route_key == 'GET /students/me/quizzes':
        return get_quiz_history(claims)
    elif route_key == 'GET /students/{studentId}/quizzes':
        student_id = path_params.get('studentId')
        return get_student_quizzes(student_id, claims)
    elif route_key == 'GET /cohorts/{cohortId}/capacity':
        cohort_id = path_params.get('cohortId')
        return get_cohort_capacity(cohort_id)
    elif route_key == 'GET /cohorts':
        return list_cohorts(claims)
    elif route_key == 'GET /public/cohorts/{cohortId}/capacity':
        cohort_id = path_params.get('cohortId')
        return get_cohort_capacity(cohort_id)
    elif route_key == 'PUT /students/{studentId}/phase':
        student_id = path_params.get('studentId')
        return update_student_phase(event, claims, student_id)
    elif route_key == 'PUT /students/{studentId}/final-exam-release':
        student_id = path_params.get('studentId')
        return set_final_exam_release(event, claims, student_id)
    elif route_key == 'DELETE /students/{studentId}/final-exam-attempt':
        student_id = path_params.get('studentId')
        return reset_final_exam_attempt(claims, student_id)
    elif route_key == 'PUT /students/{studentId}/access':
        student_id = path_params.get('studentId')
        return set_student_access(event, claims, student_id)
    elif route_key == 'POST /students/{studentId}/restart':
        student_id = path_params.get('studentId')
        return restart_student_cycle(claims, student_id)
    elif route_key == 'PUT /cohorts/{cohortId}/status':
        cohort_id = path_params.get('cohortId')
        return set_cohort_status(event, claims, cohort_id)
    else:
        return build_response(404, {'message': f'Route not found: {route_key}'})


def get_config():
    """Retorna la configuración pública del frontend (sin autenticación)."""
    return build_response(200, {
        'apiUrl': os.environ.get('API_URL', ''),
        'userPoolId': os.environ.get('COGNITO_USER_POOL_ID', ''),
        'clientId': os.environ.get('COGNITO_CLIENT_ID', ''),
    })


def get_cohort_capacity(cohort_id):
    """Retorna el cupo disponible de una turma para validación previa al registro."""
    if not cohort_id:
        return build_response(400, {'message': 'cohort_id is required'})

    cohort_item = cohorts_table.get_item(Key={'CohortID': cohort_id})
    if 'Item' not in cohort_item:
        return build_response(404, {'message': f'Cohort not found: {cohort_id}'})

    cohort = cohort_item['Item']
    if cohort.get('Type') == COHORT_TYPE_GUESTS:
        return build_response(200, {
            'cohort_id': cohort_id, 'current_count': 0, 'max_students': 0, 'is_full': False
        })
    max_students = int(cohort.get('MaxStudents', 0))

    count_response = students_table.query(
        IndexName='CohortIndex',
        KeyConditionExpression=Key('CohortID').eq(cohort_id),
        Select='COUNT'
    )
    current_count = count_response.get('Count', 0)

    return build_response(200, {
        'cohort_id': cohort_id,
        'current_count': current_count,
        'max_students': max_students,
        'is_full': current_count >= max_students
    })


def create_student(event, claims):
    if is_teacher(claims):
        return build_response(403, {'message': 'Professores não podem criar perfil de aluno'})

    data = json.loads(event.get('body', '{}'))

    # Identidad verificada por el Authorizer (no se confía en el body para email o ID)
    student_id = claims.get('sub')
    email = claims.get('email', data.get('email'))
    name = claims.get('name', data.get('name'))
    created_at = datetime.now(timezone.utc).isoformat()

    if not student_id or not email or not name:
        return build_response(400, {'message': 'Missing required student claims (sub, email, name)'})

    cohort_id = data.get('cohort_id', '')
    if cohort_id:
        cohort_item = cohorts_table.get_item(Key={'CohortID': cohort_id})
        if 'Item' not in cohort_item:
            return build_response(400, {'message': f'Cohort not found: {cohort_id}'})
        
        # Validar cupo máximo de la turma (la turma de convidados no tiene tope)
        cohort = cohort_item['Item']
        max_students = cohort.get('MaxStudents')
        if max_students is not None and cohort.get('Type') != COHORT_TYPE_GUESTS:
            # Contar alumnos actuales en la turma
            count_response = students_table.query(
                IndexName='CohortIndex',
                KeyConditionExpression=Key('CohortID').eq(cohort_id),
                Select='COUNT'
            )
            current_count = count_response.get('Count', 0)
            if current_count >= max_students:
                return build_response(403, {'message': 'Turma está cheia'})

    try:
        # Sin vencimiento automático: el acceso lo controla el profesor
        # (cierre del ciclo de la turma, bloqueo o extensión por alumno).
        item = {
            'StudentID': student_id,
            'Email': email,
            'Name': name,
            'CreatedAt': created_at,
            'UpdatedAt': created_at,
            'Cycle': 1,
            'CurrentPhase': 'initial',
            'PhaseHistory': [],
            'FailedAttempts': {
                'final_exam': 0
            }
        }
        if cohort_id:
            item['CohortID'] = cohort_id

        students_table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(StudentID)'
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return build_response(409, {'message': 'Student profile already exists'})
        raise

    return build_response(201, {
        'student_id': student_id,
        'email': email,
        'name': name
    })


def get_student_by_claims(claims):
    student_id = claims.get('sub')
    if not student_id:
        return build_response(401, {'message': 'Unauthorized: Invalid JWT claims'})
    return get_student(student_id, claims)


def get_student(student_id, claims):
    if not student_id:
        return build_response(400, {'message': 'student_id is required'})

    if not is_teacher(claims) and claims.get('sub') != student_id:
        return build_response(403, {'message': 'Forbidden: not the owner of this profile'})

    response = students_table.get_item(Key={'StudentID': student_id})
    student = response.get('Item')

    if not student:
        return build_response(404, {'message': f'Student not found: {student_id}'})

    # El profesor siempre puede ver el perfil; el alumno solo con acceso vigente
    if not is_teacher(claims):
        allowed, _ = evaluate_access(student, get_cohort_item(student.get('CohortID')))
        if not allowed:
            return build_response(403, {'message': 'Acesso encerrado. Entre em contato com seu instrutor.',
                                        'code': 'access_closed'})

    return build_response(200, student)


def update_student_by_claims(event, claims):
    student_id = claims.get('sub')
    if not student_id:
        return build_response(401, {'message': 'Unauthorized: Invalid JWT claims'})

    try:
        data = json.loads(event.get('body') or '{}')
    except ValueError:
        return build_response(400, {'message': 'Invalid JSON body'})

    # Solo el nombre es editable por el alumno. La turma la asigna el registro (con
    # chequeo de cupo) o el profesor: antes este endpoint permitía cambiarse a cualquier
    # turma sin cupo, y como update_item hace upsert, crear un perfil sin
    # AccessExpiresAt (acceso sin vencimiento) llamándolo antes del POST (auditoría 30-Sep).
    name = data.get('name') if isinstance(data, dict) else None
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        return build_response(400, {'message': 'name is required (1-80 characters)'})

    try:
        result = students_table.update_item(
            Key={'StudentID': student_id},
            UpdateExpression='SET #n = :name, UpdatedAt = :updated_at',
            ConditionExpression='attribute_exists(StudentID)',
            ExpressionAttributeNames={'#n': 'Name'},
            ExpressionAttributeValues={
                ':name': name.strip(),
                ':updated_at': datetime.now(timezone.utc).isoformat(),
            },
            ReturnValues='ALL_NEW'
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return build_response(404, {'message': 'Student profile not found'})
        raise
    return build_response(200, result['Attributes'])


def get_quiz_history(claims):
    """Retorna historial de quizzes del estudiante autenticado."""
    student_id = claims.get('sub')
    if not student_id:
        return build_response(401, {'message': 'Unauthorized'})

    # 1. Obtener los datos del estudiante para conocer su fase actual
    student_response = students_table.get_item(Key={'StudentID': student_id})
    student = student_response.get('Item', {})

    # 2. Consultar el historial de quizzes en el GSI StudentIndex
    response = quizzes_table.query(
        IndexName='StudentIndex',
        KeyConditionExpression=Key('StudentID').eq(student_id)
    )
    # El alumno solo ve su ciclo actual; los ciclos anteriores quedan para el profesor
    cycle = student_cycle(student)
    quizzes = [q for q in response.get('Items', []) if quiz_cycle(q) == cycle]
    quizzes.sort(key=lambda q: q.get('CreatedAt', ''), reverse=True)

    history = []
    for q in quizzes:
        history.append({
            'quiz_id': q['QuizID'],
            'quiz_type': q.get('QuizType', 'free'),
            'topic': q.get('Topic', ''),
            'status': q.get('Status', ''),
            'created_at': q.get('CreatedAt', ''),
            'completed_at': q.get('CompletedAt', ''),
            'score_percentage': float(q['ScorePercentage']) if q.get('ScorePercentage') is not None else None
        })

    # 3. Retornar el historial junto con la fase obtenida de forma segura
    return build_response(200, {
        'quizzes': history, 
        'current_phase': student.get('CurrentPhase', 'initial')
    })

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


def simulate_student_insert(initial_count):
    """Property 6: simula el incremento del contador de alumnos al insertar uno nuevo."""
    return initial_count + 1


def update_student_phase(event, claims, target_student_id):
    """Permite al profesor cambiar la fase de un alumno. Requiere grupo 'Teachers' en Cognito."""
    # Validar que el solicitante es teacher leyendo el claim del JWT
    if not is_teacher(claims):
        return build_response(403, {'message': 'Only teachers can modify student phases'})

    data = json.loads(event.get('body', '{}'))
    new_phase = data.get('phase')
    valid_phases = ['initial', 'free_practice', 'final_exam']

    if new_phase not in valid_phases:
        return build_response(400, {'message': f'Invalid phase. Must be one of: {valid_phases}'})

    # Obtener alumno actual
    student_response = students_table.get_item(Key={'StudentID': target_student_id})
    student = student_response.get('Item')
    if not student:
        return build_response(404, {'message': 'Student not found'})

    current_phase = student.get('CurrentPhase', 'initial')
    teacher_id = claims.get('sub')
    now = datetime.now(timezone.utc).isoformat()

    # Actualizar fase + agregar entrada al historial
    students_table.update_item(
        Key={'StudentID': target_student_id},
        UpdateExpression='SET CurrentPhase = :phase, PhaseHistory = list_append(if_not_exists(PhaseHistory, :empty_list), :entry)',
        ExpressionAttributeValues={
            ':phase': new_phase,
            ':entry': [{'Phase': new_phase, 'UnlockedAt': now, 'UnlockedBy': teacher_id}],
            ':empty_list': []
        },
        ReturnValues='ALL_NEW'
    )

    return build_response(200, {
        'student_id': target_student_id,
        'previous_phase': current_phase,
        'new_phase': new_phase
    })

def list_all_students(claims):
    """Retorna todos los alumnos. Solo accesible por teachers."""
    if not is_teacher(claims):
        return build_response(403, {'message': 'Only teachers can list students'})

    response = students_table.scan()
    students = []
    for s in response.get('Items', []):
        students.append({
            'student_id': s['StudentID'],
            'name': s.get('Name', ''),
            'email': s.get('Email', ''),
            'cohort_id': s.get('CohortID', ''),
            'current_phase': s.get('CurrentPhase', 'initial'),
            'failed_attempts': s.get('FailedAttempts', {}),
            'created_at': s.get('CreatedAt', ''),
            'access_status': s.get('AccessStatus', ''),
            'access_until': s.get('AccessUntil', ''),
            'cycle': student_cycle(s),
            'final_exam_release_date': s.get('FinalExamReleaseDate', ''),
            'has_taken_initial_test': s.get('HasTakenInitialTest', False)
        })

    return build_response(200, {'students': students, 'total': len(students)})


def get_student_quizzes(student_id, claims):
    """Retorna historial de quizzes de un alumno específico. Solo teachers."""
    if not is_teacher(claims):
        return build_response(403, {'message': 'Only teachers can view student quizzes'})

    response = quizzes_table.query(
        IndexName='StudentIndex',
        KeyConditionExpression=Key('StudentID').eq(student_id)
    )
    quizzes = response.get('Items', [])
    quizzes.sort(key=lambda q: q.get('CreatedAt', ''), reverse=True)

    history = []
    for q in quizzes:
        history.append({
            'quiz_id': q['QuizID'],
            'quiz_type': q.get('QuizType', 'free'),
            'topic': q.get('Topic', ''),
            'status': q.get('Status', ''),
            'created_at': q.get('CreatedAt', ''),
            'completed_at': q.get('CompletedAt', ''),
            'score_percentage': float(q['ScorePercentage']) if q.get('ScorePercentage') is not None else None,
            'cycle': quiz_cycle(q)
        })

    return build_response(200, {'quizzes': history})


def set_final_exam_release(event, claims, target_student_id):
    """Permite al profesor fijar o actualizar la fecha de habilitación del examen final."""
    if not is_teacher(claims):
        return build_response(403, {'message': 'Only teachers can set final exam release date'})

    data = json.loads(event.get('body', '{}'))
    release_date = data.get('release_date')
    if not release_date:
        return build_response(400, {'message': 'release_date is required'})

    # Validar y normalizar a ISO-8601 con offset (evita el 500 en quiz_engine al comparar)
    try:
        release_dt = parse_iso_datetime_utc(release_date)
    except ValueError:
        return build_response(400, {
            'message': f'release_date inválida: {release_date!r}. '
                       f'Usá ISO-8601, ej. "2026-09-09T13:00" o "2026-09-09T13:00:00-03:00".'
        })
    normalized = release_dt.isoformat()   # siempre con offset

    students_table.update_item(
        Key={'StudentID': target_student_id},
        UpdateExpression='SET FinalExamReleaseDate = :release_date, UpdatedAt = :updated_at',
        ExpressionAttributeValues={
            ':release_date': normalized,
            ':updated_at': datetime.now(timezone.utc).isoformat()
        }
    )

    return build_response(200, {
        'student_id': target_student_id,
        'final_exam_release_date': normalized
    })


def reset_final_exam_attempt(claims, target_student_id):
    """Permite al profesor resetear el intento del examen final de un alumno."""
    if not is_teacher(claims):
        return build_response(403, {'message': 'Only teachers can reset final exam attempts'})

    response = quizzes_table.query(
        IndexName='StudentIndex',
        KeyConditionExpression=Key('StudentID').eq(target_student_id),
        FilterExpression=Attr('QuizType').eq('final_exam')
    )
    student = students_table.get_item(Key={'StudentID': target_student_id}).get('Item', {})
    cycle = student_cycle(student)
    quizzes = [q for q in response.get('Items', []) if quiz_cycle(q) == cycle]
    quizzes.sort(key=lambda q: q.get('CreatedAt', ''), reverse=True)

    active_quiz = next((q for q in quizzes if q.get('Status') != 'reset'), None)
    if not active_quiz:
        return build_response(404, {'message': 'El alumno no tiene examen final registrado'})

    quizzes_table.update_item(
        Key={'QuizID': active_quiz['QuizID']},
        UpdateExpression='SET #s = :status, CompletedAt = :completed_at',
        ExpressionAttributeNames={'#s': 'Status'},
        ExpressionAttributeValues={
            ':status': 'reset',
            ':completed_at': datetime.now(timezone.utc).isoformat()
        }
    )

    return build_response(200, {
        'student_id': target_student_id,
        'message': 'Final exam attempt reset'
    })


def list_cohorts(claims):
    """Retorna todas las turmas con conteo de alumnos. Solo teachers."""
    if not is_teacher(claims):
        return build_response(403, {'message': 'Only teachers can list cohorts'})

    cohorts_response = cohorts_table.scan()
    cohorts = cohorts_response.get('Items', [])

    # Agrupar la cantidad de alumnos por CohortID con un único scan
    count_by_cohort = {}
    last_evaluated_key = None
    while True:
        scan_kwargs = {
            'ProjectionExpression': 'CohortID'
        }
        if last_evaluated_key:
            scan_kwargs['ExclusiveStartKey'] = last_evaluated_key
        page = students_table.scan(**scan_kwargs)
        for item in page.get('Items', []):
            cohort_id = item.get('CohortID')
            if cohort_id:
                count_by_cohort[cohort_id] = count_by_cohort.get(cohort_id, 0) + 1
        last_evaluated_key = page.get('LastEvaluatedKey')
        if not last_evaluated_key:
            break

    result = []
    for c in cohorts:
        cohort_id = c['CohortID']
        result.append({
            'cohort_id': cohort_id,
            'name': c.get('Name', ''),
            'max_students': int(c.get('MaxStudents', 0)),
            'current_count': count_by_cohort.get(cohort_id, 0),
            'type': c.get('Type', 'regular'),
            'status': c.get('Status', 'active'),
            'closed_at': c.get('ClosedAt', '')
        })

    return build_response(200, {'cohorts': result})


# ========== CICLO DE VIDA: ACCESO, REINTENTO Y CIERRE DE TURMA ==========
# Diseño: doc/ciclo-de-vida-turmas.md

def set_student_access(event, claims, target_student_id):
    """Profesor: bloquear, desbloquear o abrir (extender) el acceso de un alumno.

    body: {"action": "block"} | {"action": "unblock"} | {"action": "open", "until": <ISO opcional>}
      - block:   AccessStatus = blocked (gana sobre todo lo demás)
      - unblock: vuelve a heredar el estado de la turma
      - open:    acceso aunque la turma esté cerrada, hasta `until` o sin límite
    """
    if not is_teacher(claims):
        return build_response(403, {'message': 'Only teachers can change student access'})

    try:
        data = json.loads(event.get('body') or '{}')
    except ValueError:
        return build_response(400, {'message': 'Invalid JSON body'})
    action = data.get('action') if isinstance(data, dict) else None
    now = datetime.now(timezone.utc)

    values = {':updated_at': now.isoformat()}
    if action == 'block':
        update = 'SET AccessStatus = :status, UpdatedAt = :updated_at REMOVE AccessUntil'
        values[':status'] = 'blocked'
    elif action == 'unblock':
        update = 'SET UpdatedAt = :updated_at REMOVE AccessStatus, AccessUntil'
    elif action == 'open':
        until = data.get('until')
        if until:
            try:
                until_dt = parse_iso_datetime_utc(until)
            except ValueError:
                return build_response(400, {'message': f'until inválida: {until!r}'})
            if until_dt <= now:
                return build_response(400, {'message': 'until debe ser una fecha futura'})
            update = 'SET AccessStatus = :status, AccessUntil = :until, UpdatedAt = :updated_at'
            values[':until'] = until_dt.isoformat()
        else:
            update = 'SET AccessStatus = :status, UpdatedAt = :updated_at REMOVE AccessUntil'
        values[':status'] = 'open'
    else:
        return build_response(400, {'message': 'action must be one of: block, unblock, open'})

    try:
        result = students_table.update_item(
            Key={'StudentID': target_student_id},
            UpdateExpression=update,
            ConditionExpression='attribute_exists(StudentID)',
            ExpressionAttributeValues=values,
            ReturnValues='ALL_NEW'
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return build_response(404, {'message': 'Student not found'})
        raise

    student = result['Attributes']
    return build_response(200, {
        'student_id': target_student_id,
        'access_status': student.get('AccessStatus', ''),
        'access_until': student.get('AccessUntil', '')
    })


def restart_student_cycle(claims, target_student_id):
    """Profesor: "Recomeçar do zero". Abre un ciclo nuevo para el alumno.

    No borra nada: los quizzes del ciclo anterior quedan con su Cycle y siguen visibles
    para el profesor; el alumno ve el dashboard limpio. El acceso queda abierto
    (AccessStatus = open) aunque su turma esté cerrada, hasta que el profesor decida.
    """
    if not is_teacher(claims):
        return build_response(403, {'message': 'Only teachers can restart a student cycle'})

    student = students_table.get_item(Key={'StudentID': target_student_id}).get('Item')
    if not student:
        return build_response(404, {'message': 'Student not found'})

    previous_cycle = student_cycle(student)
    new_cycle = previous_cycle + 1
    now = datetime.now(timezone.utc).isoformat()

    try:
        students_table.update_item(
            Key={'StudentID': target_student_id},
            UpdateExpression=(
                'SET #c = :new_cycle, CurrentPhase = :phase, HasTakenInitialTest = :false, '
                'AccessStatus = :open, UpdatedAt = :now, '
                'PhaseHistory = list_append(if_not_exists(PhaseHistory, :empty_list), :entry) '
                'REMOVE FinalExamReleaseDate, InitialTestQuizID, AccessUntil'
            ),
            # Condición: evita doble reinicio si el profesor hace doble click
            ConditionExpression='attribute_not_exists(#c) OR #c = :prev_cycle',
            ExpressionAttributeNames={'#c': 'Cycle'},
            ExpressionAttributeValues={
                ':new_cycle': new_cycle,
                ':prev_cycle': previous_cycle,
                ':phase': 'initial',
                ':false': False,
                ':open': 'open',
                ':now': now,
                ':empty_list': [],
                ':entry': [{'Phase': 'initial', 'Cycle': new_cycle, 'UnlockedAt': now,
                            'UnlockedBy': claims.get('sub'), 'Reason': 'restart'}],
            }
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return build_response(409, {'message': 'O ciclo do aluno mudou; recarregue a página.'})
        raise

    return build_response(200, {
        'student_id': target_student_id,
        'previous_cycle': previous_cycle,
        'cycle': new_cycle
    })


def set_cohort_status(event, claims, cohort_id):
    """Profesor: encerrar (closed) o reabrir (active) el ciclo de una turma.

    Encerrar corta el acceso de todos sus alumnos, salvo los que tengan AccessStatus
    = open. ClosedAt delimita el ciclo para las métricas. La turma de convidados no
    se cierra: su acceso se maneja alumno por alumno.
    """
    if not is_teacher(claims):
        return build_response(403, {'message': 'Only teachers can change cohort status'})

    try:
        data = json.loads(event.get('body') or '{}')
    except ValueError:
        return build_response(400, {'message': 'Invalid JSON body'})
    status = data.get('status') if isinstance(data, dict) else None
    if status not in ('closed', 'active'):
        return build_response(400, {'message': 'status must be "closed" or "active"'})

    cohort = get_cohort_item(cohort_id)
    if not cohort:
        return build_response(404, {'message': f'Cohort not found: {cohort_id}'})
    if cohort.get('Type') == COHORT_TYPE_GUESTS:
        return build_response(400, {'message': 'A turma de convidados não tem ciclo; bloqueie alunos individualmente.'})

    now = datetime.now(timezone.utc).isoformat()
    if status == 'closed':
        update = 'SET #s = :status, ClosedAt = :now, ClosedBy = :by'
        values = {':status': 'closed', ':now': now, ':by': claims.get('sub')}
    else:
        update = 'SET #s = :status, ReopenedAt = :now REMOVE ClosedAt, ClosedBy'
        values = {':status': 'active', ':now': now}

    result = cohorts_table.update_item(
        Key={'CohortID': cohort_id},
        UpdateExpression=update,
        ExpressionAttributeNames={'#s': 'Status'},
        ExpressionAttributeValues=values,
        ReturnValues='ALL_NEW'
    )
    attrs = result['Attributes']
    return build_response(200, {
        'cohort_id': cohort_id,
        'status': attrs.get('Status'),
        'closed_at': attrs.get('ClosedAt', '')
    })
