import json
import uuid
import os
import boto3
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')

questions_table = dynamodb.Table(os.environ['QUESTIONS_TABLE'])
quizzes_table = dynamodb.Table(os.environ['QUIZZES_TABLE'])
quiz_results_table = dynamodb.Table(os.environ['QUIZ_RESULTS_TABLE'])


def lambda_handler(event, context):
    action = event.get('action')

    if action == 'generate_quiz':
        return generate_quiz(event)
    elif action == 'submit_answer':
        return submit_answer(event)
    elif action == 'get_results':
        return get_results(event)
    else:
        return {
            'statusCode': 400,
            'body': f'Unknown action: {action}'
        }


def generate_quiz(event):
    student_id = event['student_id']
    topic = event['topic']
    count = event.get('count', 5)

    response = questions_table.query(
        IndexName='TopicIndex',
        KeyConditionExpression=Key('Topic').eq(topic),
        Limit=count
    )
    questions = response.get('Items', [])

    if not questions:
        return {
            'statusCode': 404,
            'body': f'No questions found for topic: {topic}'
        }

    question_ids = [q['QuestionID'] for q in questions]
    quiz_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    quizzes_table.put_item(Item={
        'QuizID': quiz_id,
        'StudentID': student_id,
        'Topic': topic,
        'Questions': question_ids,
        'Status': 'in_progress',
        'CreatedAt': created_at
    })

    return {
        'statusCode': 200,
        'body': {
            'quiz_id': quiz_id,
            'student_id': student_id,
            'topic': topic,
            'question_ids': question_ids
        }
    }


def submit_answer(event):
    quiz_id = event['quiz_id']
    student_id = event['student_id']
    question_id = event['question_id']
    given_answer = event['given_answer']
    is_correct = event['is_correct']

    result_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    quiz_results_table.put_item(Item={
        'ResultID': result_id,
        'QuizID': quiz_id,
        'StudentID': student_id,
        'QuestionID': question_id,
        'GivenAnswer': given_answer,
        'IsCorrect': is_correct,
        'Timestamp': timestamp
    })

    return {
        'statusCode': 200,
        'body': {
            'result_id': result_id,
            'quiz_id': quiz_id
        }
    }


def get_results(event):
    quiz_id = event['quiz_id']

    quiz_response = quizzes_table.get_item(Key={'QuizID': quiz_id})
    quiz = quiz_response.get('Item')

    if not quiz:
        return {
            'statusCode': 404,
            'body': f'Quiz not found: {quiz_id}'
        }

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
            'given_answer': result.get('GivenAnswer', ''),
            'is_correct': result.get('IsCorrect', False),
            'timestamp': result.get('Timestamp', '')
        })

    return {
        'statusCode': 200,
        'body': {
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
            'results': questions_details
        }
    }