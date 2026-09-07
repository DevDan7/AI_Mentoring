#!/usr/bin/env python3
"""Limpieza y migración de datos para el MVP (Fase 7).

Elimina todos los registros de las tablas Students, Quizzes, QuizResults y
Cohorts, genera un backup previo y crea la turma beta inicial. La tabla
MentoringQuestions queda explícitamente excluida y congelada.

USO (requiere credenciales AWS válidas en el entorno local, nunca CI/CD):
    .venv/bin/python scripts/migrate_clean.py                # flujo completo (pide confirmación SI)
    .venv/bin/python scripts/migrate_clean.py --dry-run      # solo lectura, no muta nada
    .venv/bin/python scripts/migrate_clean.py --export-only  # genera backups y se detiene
"""
import argparse
import json
import os
import sys
from datetime import datetime
from decimal import Decimal

import boto3

BACKUP_DIR = os.path.join('scripts', 'backup')
MENTORING_QUESTIONS_TABLE = 'MentoringQuestions'
BETA_COHORT = {
    'CohortID': 'turma-beta-01',
    'Name': 'Beta Turma 01',
    'MaxStudents': Decimal('7'),
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default='AI_Mentoring',
                        help='Proyecto usado en el prefijo de nombres de tabla.')
    parser.add_argument('--environment', default='dev')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--backup-dir', default=BACKUP_DIR)
    parser.add_argument('--timestamp', default=None,
                        help='Timestamp para los backups (YYYYMMDD_HHMMSS). Default: ahora.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Solo lectura: imprime el reporte sin escribir ni eliminar.')
    parser.add_argument('--export-only', action='store_true',
                        help='Genera los backups y se detiene antes de la eliminación.')
    return parser.parse_args(argv)


def table_defs(project, environment):
    """Nombres de tabla DynamoDB y key de partición por servicio."""
    return {
        'students': {'name': f'{project}-Students-{environment}', 'key': 'StudentID'},
        'quizzes': {'name': f'{project}-Quizzes-{environment}', 'key': 'QuizID'},
        'quiz_results': {'name': f'{project}-QuizResults-{environment}', 'key': 'ResultID'},
        'cohorts': {'name': f'{project}-Cohorts-{environment}', 'key': 'CohortID'},
    }


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def scan_table(table):
    items = []
    kwargs = {}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get('Items', []))
        if 'LastEvaluatedKey' not in resp:
            return items
        kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']


def count_items(table):
    total = 0
    kwargs = {'Select': 'COUNT'}
    while True:
        resp = table.scan(**kwargs)
        total += resp.get('Count', 0)
        if 'LastEvaluatedKey' not in resp:
            return total
        kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']


def delete_all_items(table, key_name):
    """Paso 3: batch delete de todos los ítems de una tabla (por key de partición)."""
    items = scan_table(table)
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={key_name: item[key_name]})
    return len(items)


def seed_beta_cohort(table):
    """Paso 4: inserta la turma beta inicial con cupo 7."""
    table.put_item(Item=dict(BETA_COHORT))


def verify_empty(resource, defs, mentoring_table_name=MENTORING_QUESTIONS_TABLE,
                 beta_cohort_id='turma-beta-01'):
    """Paso 5: verifica las 4 tablas limpias (cohorts solo con la turma beta),
    la existencia de la turma beta y que MentoringQuestions no cambió."""
    counts = {}
    status = {}
    for label, defn in defs.items():
        counts[label] = count_items(resource.Table(defn['name']))
        status[label] = counts[label] == 0 if label != 'cohorts' else counts[label] == 1
    cohort_response = resource.Table(defs['cohorts']['name']).get_item(
        Key={'CohortID': beta_cohort_id}
    )
    beta_cohort_exists = 'Item' in cohort_response
    mq_count = count_items(resource.Table(mentoring_table_name))
    return {
        'ok': all(status.values()) and beta_cohort_exists,
        'counts': counts,
        'beta_cohort_exists': beta_cohort_exists,
        'mentoring_questions_count': mq_count,
    }


def run_clean(resource, defs, *, timestamp=None, dry_run=False, export_only=False,
              backup_dir=BACKUP_DIR, mentoring_table_name=MENTORING_QUESTIONS_TABLE, ask=None):
    """Orquesta los pasos del plan de migración (design.md). Retorna un dict de reporte."""
    ts = timestamp or datetime.now().strftime('%Y%m%d_%H%M%S')
    ask = ask or input
    os.makedirs(backup_dir, exist_ok=True)

    result = {
        'mode': 'export_only' if export_only else ('dry_run' if dry_run else 'full'),
        'timestamp': ts,
        'counts': {},
        'backup_files': {},
        'deleted': {},
    }

    # Paso 1: export de las 4 tablas a JSON (no se escribe en dry-run)
    for label, defn in defs.items():
        items = scan_table(resource.Table(defn['name']))
        result['counts'][label] = len(items)
        filename = os.path.join(backup_dir, f'backup_{ts}_{label}.json')
        result['backup_files'][label] = filename
        if dry_run:
            print(f'[DRY-RUN][{label}] {len(items)} ítems → se escribiría un backup en {filename}')
            continue
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2, cls=DecimalEncoder)
        print(f'[{label}] {len(items)} ítems → {filename}')

    if export_only:
        print('\n--export-only: backups generados. No se eliminará nada.')
        return result

    if dry_run:
        print('\n[DRY-RUN] Reporte (no se escribe ni elimina nada):')
        for label, count in result['counts'].items():
            print(f'  se eliminarían {count} ítems de {label}')
        print(f"  se insertaría la turma beta {BETA_COHORT['CohortID']}")
        print('  MentoringQuestions no se toca.')
        return result

    # Paso 2: confirmación manual explícita del operador
    answer = ask("Confirmar eliminación? [escribir 'SI']: ").strip().upper()
    if answer != 'SI':
        print('Eliminación cancelada. Nada fue modificado.')
        result['mode'] = 'cancelled'
        return result

    # Paso 3: batch delete de las 4 tablas
    for label, defn in defs.items():
        deleted = delete_all_items(resource.Table(defn['name']), defn['key'])
        result['deleted'][label] = deleted
        print(f'[{label}] {deleted} ítems eliminados')

    # Paso 4: seed de la turma beta inicial
    seed_beta_cohort(resource.Table(defs['cohorts']['name']))
    print(f"[cohorts] turma beta creada: {BETA_COHORT['CohortID']}")

    # Paso 5-6: verificación y reporte final
    verification = verify_empty(resource, defs, mentoring_table_name=mentoring_table_name)
    result['verification'] = verification
    print('\nVerificación:')
    for label, count in verification['counts'].items():
        expected = 1 if label == 'cohorts' else 0
        print(f'  {label}: {count} ítems (debe ser {expected})')
    beta_status = 'presente' if verification['beta_cohort_exists'] else 'AUSENTE'
    print(f'  turma beta {BETA_COHORT["CohortID"]}: {beta_status}')
    print(f"  {mentoring_table_name}: {verification['mentoring_questions_count']} "
          f"ítems (no debe cambiar)")
    print(f"  resultado: {'OK' if verification['ok'] else 'ERROR: verificar tablas'}")
    return result


def main(argv=None):
    args = parse_args(argv)
    defs = table_defs(args.project, args.environment)
    resource = boto3.resource('dynamodb', region_name=args.region)
    run_clean(resource, defs,
              timestamp=args.timestamp,
              dry_run=args.dry_run,
              export_only=args.export_only,
              backup_dir=args.backup_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())