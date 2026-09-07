#!/usr/bin/env python3
"""Restauración de datos desde backups JSON generados por migrate_clean.py.

Lee backups/backup_<YYYYMMDD_HHMMSS>_{tabla}.json y reinserta los ítems en sus
tablas con batch_writer(). Detecta automáticamente el juego de backups más
reciente (las 4 tablas) o usa un prefijo de timestamp explícito.

USO (requiere credenciales AWS válidas en el entorno local, nunca CI/CD):
    .venv/bin/python scripts/migrate_restore.py                 # backups más recientes
    .venv/bin/python scripts/migrate_restore.py --prefix 20260907_150000
"""
import argparse
import json
import os
import re
import sys

import boto3

BACKUP_DIR = os.path.join('scripts', 'backup')
BACKUP_RE = re.compile(r'backup_(\d{8}_\d{6})_(students|quizzes|quiz_results|cohorts)\.json')
SUPPORTED_TABLES = ('students', 'quizzes', 'quiz_results', 'cohorts')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', default=None,
                        help='Prefijo de timestamp (YYYYMMDD_HHMMSS) de los backups a restaurar.')
    parser.add_argument('--project', default='AI_Mentoring')
    parser.add_argument('--environment', default='dev')
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--backup-dir', default=BACKUP_DIR)
    return parser.parse_args(argv)


def table_names(project, environment):
    """Nombres de tabla DynamoDB por servicio."""
    return {
        'students': f'{project}-Students-{environment}',
        'quizzes': f'{project}-Quizzes-{environment}',
        'quiz_results': f'{project}-QuizResults-{environment}',
        'cohorts': f'{project}-Cohorts-{environment}',
    }


def find_backups(backup_dir):
    """Agrupa rutas de backup por timestamp: {ts: {tabla: path}}."""
    groups = {}
    if not os.path.isdir(backup_dir):
        return groups
    for name in os.listdir(backup_dir):
        m = BACKUP_RE.match(name)
        if not m:
            continue
        ts, tabla = m.group(1), m.group(2)
        groups.setdefault(ts, {})[tabla] = os.path.join(backup_dir, name)
    return groups


def restore_items(table, items):
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
    return len(items)


def run_restore(resource, names, *, backup_dir=BACKUP_DIR, prefix=None):
    """Restaura un juego de backups. Retorna dict {tabla: ítems restaurados}."""
    groups = find_backups(backup_dir)
    if not groups:
        raise SystemExit(f'No se encontraron backups en {backup_dir}')

    if prefix is None:
        complete = {ts: g for ts, g in groups.items()
                    if all(t in g for t in SUPPORTED_TABLES)}
        if not complete:
            raise SystemExit('No existe un juego completo de backups (las 4 tablas) '
                             'para restaurar automáticamente.')
        ts = max(complete.keys())
        print(f'Timestamp detectado: {ts}')
    else:
        if prefix not in groups:
            raise SystemExit(f'No hay backups con prefijo {prefix} en {backup_dir}')
        ts = prefix

    report = {}
    for tabla in SUPPORTED_TABLES:
        path = groups[ts].get(tabla)
        if not path:
            print(f'  {tabla}: sin backup en {ts}, se omite')
            continue
        with open(path, 'r', encoding='utf-8') as f:
            items = json.load(f)
        table = resource.Table(names[tabla])
        restored = restore_items(table, items)
        report[tabla] = restored
        print(f'[{tabla}] {restored} ítems restaurados desde {path}')

    print(f'\nTotal restaurado: {sum(report.values())} ítems')
    return report


def main(argv=None):
    args = parse_args(argv)
    resource = boto3.resource('dynamodb', region_name=args.region)
    run_restore(resource, table_names(args.project, args.environment),
                backup_dir=args.backup_dir,
                prefix=args.prefix)
    return 0


if __name__ == '__main__':
    sys.exit(main())