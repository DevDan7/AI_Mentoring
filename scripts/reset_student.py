#!/usr/bin/env python3
"""Reset completo de un alumno: borra todos sus simulados y lo deja como recién creado.

Elimina todos los Quizzes y QuizResults del alumno (encontrado por email vía
EmailIndex), genera un backup previo, y resetea sus campos de progreso
(CurrentPhase, PhaseHistory, FailedAttempts, HasTakenInitialTest,
InitialTestQuizID, FinalExamReleaseDate) a los valores de un alumno nuevo.
No toca Students.Email/Name/CohortID/AccessExpiresAt ni MentoringQuestions.

USO (requiere credenciales AWS válidas en el entorno local, nunca CI/CD):
    .venv/bin/python scripts/reset_student.py --email bomjob8@gmail.com --dry-run
    .venv/bin/python scripts/reset_student.py --email bomjob8@gmail.com
"""
import argparse
import json
import os
import sys
from datetime import datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

BACKUP_DIR = os.path.join('scripts', 'backup')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email', required=True, help='Email del alumno a resetear.')
    parser.add_argument('--project', default='AI_Mentoring')
    parser.add_argument('--environment', default='dev')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--backup-dir', default=BACKUP_DIR)
    parser.add_argument('--timestamp', default=None,
                        help='Timestamp para el backup (YYYYMMDD_HHMMSS). Default: ahora.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Solo lectura: imprime el reporte sin escribir ni eliminar nada.')
    return parser.parse_args(argv)


def table_defs(project, environment):
    return {
        'students': f'{project}-Students-{environment}',
        'quizzes': f'{project}-Quizzes-{environment}',
        'quiz_results': f'{project}-QuizResults-{environment}',
    }


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def find_student_by_email(students_table, email):
    response = students_table.query(
        IndexName='EmailIndex',
        KeyConditionExpression=Key('Email').eq(email)
    )
    items = response.get('Items', [])
    return items[0] if items else None


def find_quizzes(quizzes_table, student_id):
    response = quizzes_table.query(
        IndexName='StudentIndex',
        KeyConditionExpression=Key('StudentID').eq(student_id)
    )
    return response.get('Items', [])


def find_quiz_results(quiz_results_table, quiz_id):
    response = quiz_results_table.query(
        IndexName='QuizIndex',
        KeyConditionExpression=Key('QuizID').eq(quiz_id)
    )
    return response.get('Items', [])


def run_reset(resource, defs, email, *, timestamp=None, dry_run=False,
              backup_dir=BACKUP_DIR, ask=None):
    ts = timestamp or datetime.now().strftime('%Y%m%d_%H%M%S')
    ask = ask or input

    students_table = resource.Table(defs['students'])
    quizzes_table = resource.Table(defs['quizzes'])
    quiz_results_table = resource.Table(defs['quiz_results'])

    result = {
        'mode': 'dry_run' if dry_run else 'full',
        'timestamp': ts,
        'email': email,
    }

    student = find_student_by_email(students_table, email)
    if not student:
        print(f'No se encontró ningún alumno con email {email!r}.')
        result['mode'] = 'not_found'
        return result

    student_id = student['StudentID']
    quizzes = find_quizzes(quizzes_table, student_id)
    all_results = []
    for quiz in quizzes:
        all_results.extend(find_quiz_results(quiz_results_table, quiz['QuizID']))

    result['student_id'] = student_id
    result['quizzes_found'] = len(quizzes)
    result['results_found'] = len(all_results)

    print(f'Alumno: {student.get("Name", "")} <{email}> (StudentID={student_id})')
    print(f'  Fase actual: {student.get("CurrentPhase", "initial")}')
    print(f'  Quizzes encontrados: {len(quizzes)}')
    print(f'  Resultados encontrados: {len(all_results)}')

    if dry_run:
        print('\n[DRY-RUN] No se escribe backup ni se elimina nada. Se haría:')
        print(f'  - Borrar {len(quizzes)} ítems de Quizzes')
        print(f'  - Borrar {len(all_results)} ítems de QuizResults')
        print('  - Resetear Students: CurrentPhase=initial, PhaseHistory=[],')
        print('    FailedAttempts={"final_exam": 0}, HasTakenInitialTest=False,')
        print('    quitar InitialTestQuizID y FinalExamReleaseDate.')
        return result

    # Backup previo (alumno + sus quizzes + sus resultados)
    os.makedirs(backup_dir, exist_ok=True)
    backup_file = os.path.join(backup_dir, f'backup_reset_student_{student_id}_{ts}.json')
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump({
            'student': student,
            'quizzes': quizzes,
            'quiz_results': all_results,
        }, f, ensure_ascii=False, indent=2, cls=DecimalEncoder)
    print(f'\nBackup escrito en {backup_file}')
    result['backup_file'] = backup_file

    answer = ask(f"Confirmar reset completo de {email}? [escribir 'SI']: ").strip().upper()
    if answer != 'SI':
        print('Reset cancelado. Nada fue modificado.')
        result['mode'] = 'cancelled'
        return result

    with quiz_results_table.batch_writer() as batch:
        for r in all_results:
            batch.delete_item(Key={'ResultID': r['ResultID']})
    print(f'[quiz_results] {len(all_results)} ítems eliminados')

    with quizzes_table.batch_writer() as batch:
        for q in quizzes:
            batch.delete_item(Key={'QuizID': q['QuizID']})
    print(f'[quizzes] {len(quizzes)} ítems eliminados')

    students_table.update_item(
        Key={'StudentID': student_id},
        UpdateExpression=(
            'SET CurrentPhase = :phase, PhaseHistory = :empty_list, '
            'FailedAttempts = :failed_attempts, HasTakenInitialTest = :not_taken, '
            'UpdatedAt = :updated_at '
            'REMOVE InitialTestQuizID, FinalExamReleaseDate'
        ),
        ExpressionAttributeValues={
            ':phase': 'initial',
            ':empty_list': [],
            ':failed_attempts': {'final_exam': 0},
            ':not_taken': False,
            ':updated_at': datetime.now().astimezone().isoformat(),
        }
    )
    print('[students] fase y progreso reseteados a valores de alumno nuevo')

    result['deleted'] = {'quizzes': len(quizzes), 'quiz_results': len(all_results)}
    return result


def main(argv=None):
    args = parse_args(argv)
    defs = table_defs(args.project, args.environment)
    resource = boto3.resource('dynamodb', region_name=args.region)
    run_reset(resource, defs, args.email,
              timestamp=args.timestamp,
              dry_run=args.dry_run,
              backup_dir=args.backup_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
