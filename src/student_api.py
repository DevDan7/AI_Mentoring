import json
import uuid
import os
import boto3
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

COGNITO_USER_POOL_ID = os.environ['COGNITO_USER_POOL_ID']
COGNITO_CLIENT_ID = os.environ['COGNITO_CLIENT_ID']
STUDENTS_TABLE = os.environ['STUDENTS_TABLE']

dynamodb = boto3.resource('dynamodb')
cognito_client = boto3.client('cognito-idp')
students_table = dynamodb.Table(STUDENTS_TABLE)


def lambda_handler(event, context):
    action = event.get('action')

    if action != 'create_student':
        token = event.get('access_token')
        if not token:
            return {'statusCode': 401, 'body': 'Missing access_token'}
        user = validate_token(token)
        if not user:
            return {'statusCode': 401, 'body': 'Invalid or expired token'}

    if action == 'create_student':
        return create_student(event)
    elif action == 'get_student':
        return get_student(event)
    elif action == 'update_student':
        return update_student(event)
    elif action == 'get_student_by_email':
        return get_student_by_email(event)
    else:
        return {'statusCode': 400, 'body': f'Unknown action: {action}'}


def validate_token(access_token):
    try:
        response = cognito_client.get_user(AccessToken=access_token)
        attributes = {a['Name']: a['Value'] for a in response['UserAttributes']}
        return {
            'sub': response['Username'],
            'email': attributes.get('email'),
            'name': attributes.get('name')
        }
    except ClientError:
        return None


def create_student(event):
    data = event.get('data', {})
    email = data['email']
    name = data['name']
    student_id = data.get('student_id', str(uuid.uuid4()))
    created_at = datetime.now(timezone.utc).isoformat()

    students_table.put_item(Item={
        'StudentID': student_id,
        'Email': email,
        'Name': name,
        'Cohort': data.get('cohort', ''),
        'CreatedAt': created_at,
        'UpdatedAt': created_at
    })

    return {
        'statusCode': 200,
        'body': {
            'student_id': student_id,
            'email': email,
            'name': name
        }
    }


def get_student(event):
    student_id = event['student_id']

    response = students_table.get_item(Key={'StudentID': student_id})
    student = response.get('Item')

    if not student:
        return {'statusCode': 404, 'body': f'Student not found: {student_id}'}

    return {'statusCode': 200, 'body': student}


def update_student(event):
    student_id = event['student_id']
    data = event.get('data', {})

    update_expr = "SET UpdatedAt = :updated_at"
    expr_values = {':updated_at': datetime.now(timezone.utc).isoformat()}

    if 'name' in data:
        update_expr += ", #n = :name"
        expr_values[':name'] = data['name']

    if 'cohort' in data:
        update_expr += ", Cohort = :cohort"
        expr_values[':cohort'] = data['cohort']

    response = students_table.update_item(
        Key={'StudentID': student_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames={'#n': 'Name'} if 'name' in data else {},
        ExpressionAttributeValues=expr_values,
        ReturnValues="ALL_NEW"
    )

    return {'statusCode': 200, 'body': response['Attributes']}


def get_student_by_email(event):
    email = event['email']

    response = students_table.query(
        IndexName='EmailIndex',
        KeyConditionExpression=Key('Email').eq(email)
    )
    items = response.get('Items', [])

    if not items:
        return {'statusCode': 404, 'body': f'Student not found: {email}'}

    return {'statusCode': 200, 'body': items[0]}
