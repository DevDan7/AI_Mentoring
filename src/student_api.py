import json
import os
import boto3
from datetime import datetime, timezone, timedelta
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

# Inicialización del cliente de DynamoDB
dynamodb = boto3.resource('dynamodb')
students_table = dynamodb.Table(os.environ['STUDENTS_TABLE'])
cohorts_table = dynamodb.Table(os.environ['COHORTS_TABLE'])
quizzes_table = dynamodb.Table(os.environ['QUIZZES_TABLE'])

# Encabezados CORS estándar para permitir integración con el Frontend
HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
}


def build_response(status_code, body):
    """Auxiliar para generar respuestas formateadas para API Gateway v2.0"""
    return {
        'statusCode': status_code,
        'headers': HEADERS,
        'body': json.dumps(body)
    }


def lambda_handler(event, context):
    route_key = event.get('routeKey')
    path_params = event.get('pathParameters', {})
    
    # Extraer los claims validados directamente desde el JWT de Cognito
    claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})

    # Enrutamiento basado en el routeKey expuesto por API Gateway
    if route_key == 'POST /students':
        return create_student(event, claims)
    elif route_key == 'GET /students/me':
        return get_student_by_claims(claims)
    elif route_key == 'PUT /students/me':
        return update_student_by_claims(event, claims)
    elif route_key == 'GET /students/{studentId}':
        student_id = path_params.get('studentId')
        return get_student(student_id)
    elif route_key == 'GET /students/me/quizzes':
        return get_quiz_history(claims)
    elif route_key == 'GET /cohorts/{cohortId}/capacity':
        cohort_id = path_params.get('cohortId')
        return get_cohort_capacity(cohort_id)
    elif route_key == 'GET /public/cohorts/{cohortId}/capacity':
        cohort_id = path_params.get('cohortId')
        return get_cohort_capacity(cohort_id)
    else:
        return build_response(404, {'message': f'Route not found: {route_key}'})


def get_cohort_capacity(cohort_id):
    """Retorna el cupo disponible de una turma para validación previa al registro."""
    if not cohort_id:
        return build_response(400, {'message': 'cohort_id is required'})

    cohort_item = cohorts_table.get_item(Key={'CohortID': cohort_id})
    if 'Item' not in cohort_item:
        return build_response(404, {'message': f'Cohort not found: {cohort_id}'})

    cohort = cohort_item['Item']
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
        
        # Validar cupo máximo de la turma
        cohort = cohort_item['Item']
        max_students = cohort.get('MaxStudents')
        if max_students is not None:
            # Contar alumnos actuales en la turma
            count_response = students_table.query(
                IndexName='CohortIndex',
                KeyConditionExpression=Key('CohortID').eq(cohort_id),
                Select='COUNT'
            )
            current_count = count_response.get('Count', 0)
            if current_count >= max_students:
                return build_response(403, {'message': f'Cohort is full: {current_count}/{max_students} students'})

    try:
        # AccessExpiresAt = CreatedAt + 30 días por defecto
        access_expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        
        item = {
            'StudentID': student_id,
            'Email': email,
            'Name': name,
            'Cohort': data.get('cohort', ''),
            'CreatedAt': created_at,
            'UpdatedAt': created_at,
            'AccessExpiresAt': access_expires_at
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
    return get_student(student_id)


def get_student(student_id):
    if not student_id:
        return build_response(400, {'message': 'student_id is required'})

    response = students_table.get_item(Key={'StudentID': student_id})
    student = response.get('Item')

    if not student:
        return build_response(404, {'message': f'Student not found: {student_id}'})

    # Verificar si el acceso expiró
    access_expires_at = student.get('AccessExpiresAt')
    if access_expires_at:
        expires_dt = datetime.fromisoformat(access_expires_at.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_dt:
            return build_response(403, {'message': 'Access expired. Contact your instructor to renew access.'})

    return build_response(200, student)


def update_student_by_claims(event, claims):
    student_id = claims.get('sub')
    if not student_id:
        return build_response(401, {'message': 'Unauthorized: Invalid JWT claims'})

    data = json.loads(event.get('body', '{}'))

    update_expr = "SET UpdatedAt = :updated_at"
    expr_values = {':updated_at': datetime.now(timezone.utc).isoformat()}
    expr_names = {}

    if 'name' in data:
        update_expr += ", #n = :name"
        expr_values[':name'] = data['name']
        expr_names['#n'] = 'Name'

    if 'cohort' in data:
        update_expr += ", Cohort = :cohort"
        expr_values[':cohort'] = data['cohort']

    if 'cohort_id' in data:
        cohort_id = data['cohort_id']
        if cohort_id:
            cohort_item = cohorts_table.get_item(Key={'CohortID': cohort_id})
            if 'Item' not in cohort_item:
                return build_response(400, {'message': f'Cohort not found: {cohort_id}'})
            update_expr += ", CohortID = :cohort_id"
            expr_values[':cohort_id'] = cohort_id
        else:
            update_expr += " REMOVE CohortID"

    kwargs = {
        'Key': {'StudentID': student_id},
        'UpdateExpression': update_expr,
        'ExpressionAttributeValues': expr_values,
        'ReturnValues': 'ALL_NEW'
    }

    if expr_names:
        kwargs['ExpressionAttributeNames'] = expr_names

    result = students_table.update_item(**kwargs)
    return build_response(200, result['Attributes'])


def get_quiz_history(claims):
    """Retorna historial de quizzes del estudiante autenticado."""
    student_id = claims.get('sub')
    if not student_id:
        return build_response(401, {'message': 'Unauthorized'})

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
            'score_percentage': float(q['ScorePercentage']) if q.get('ScorePercentage') is not None else None
        })

    return build_response(200, {'quizzes': history})
