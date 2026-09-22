"""Corrige la respuesta marcada (Options[*].is_correct) y CorrectCount de preguntas en
MentoringQuestions a partir de un reporte de auditoria revisado a mano.

MANUAL-ONLY. Nunca se conecta a CI/CD (ver CLAUDE.md / AGENTS.md). Uso:

    # 1. editar audit_corrections.json y poner "approved": true en las aceptadas
    python scripts/migrate_fix_answers.py --corrections /ruta/audit_corrections.json            # dry-run
    python scripts/migrate_fix_answers.py --corrections /ruta/audit_corrections.json --apply    # aplica

Antes de cualquier escritura hace un backup completo de la tabla en
scripts/backup_pre_fix_answers_<timestamp>.json (restaurable con scripts/migrate_restore.py).
Solo toca Options[*].is_correct y CorrectCount; no altera QuestionText, Topic, explanation,
keywords ni ContentHash.
"""
import argparse
import datetime
import json

import boto3

TABLE_NAME = 'MentoringQuestions'


def backup_tabla(dynamodb):
    table = dynamodb.Table(TABLE_NAME)
    items = []
    response = table.scan()
    items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'scripts/backup_pre_fix_answers_{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(items, f, indent=2, default=str)
    print(f"Respaldo guardado en: {filename}")
    return {it['QuestionID']: it for it in items}


def load_corrections(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    approved = [c for c in data if c.get('approved') is True]
    return data, approved


def build_new_options(current_options, set_is_correct):
    """Devuelve una copia de Options con is_correct recalculado.

    Solo se admite Options como dict {letra: {...}}. La forma legacy (lista) se rechaza
    para no corromper datos: esos items se revisan a mano.
    """
    if not isinstance(current_options, dict):
        raise ValueError("Options no es un dict (forma legacy) - corregir a mano")
    target = {l.strip().upper() for l in set_is_correct}
    new_opts = {}
    for letter, opt in current_options.items():
        opt = dict(opt or {})
        opt['is_correct'] = letter.strip().upper() in target
        new_opts[letter] = opt
    faltantes = target - {l.strip().upper() for l in current_options}
    if faltantes:
        raise ValueError(f"set_is_correct referencia letras inexistentes: {sorted(faltantes)}")
    return new_opts


def main():
    parser = argparse.ArgumentParser(
        description='Aplica correcciones de respuesta aprobadas a MentoringQuestions.'
    )
    parser.add_argument('--corrections', required=True,
                        help='Ruta al audit_corrections.json revisado (con "approved": true)')
    parser.add_argument('--apply', action='store_true',
                        help='Aplica los cambios reales en DynamoDB (sin este flag es dry-run)')
    args = parser.parse_args()

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(TABLE_NAME)

    total, approved = load_corrections(args.corrections)
    print(f"Correcciones en el archivo: {len(total)}  |  aprobadas: {len(approved)}")
    if not approved:
        print("Nada aprobado. Edita el JSON y pon \"approved\": true en las aceptadas.")
        return

    # El backup completo solo se genera cuando se va a escribir (--apply).
    backup = {}
    if args.apply:
        print("\nIniciando respaldo...")
        backup = backup_tabla(dynamodb)

    planned = []
    errores = []
    for c in approved:
        qid = c['question_id']
        fix = c.get('proposed_fix') or {}
        set_is_correct = fix.get('set_is_correct')
        if not set_is_correct:
            errores.append({'id': qid, 'error': 'proposed_fix.set_is_correct vacio'})
            continue
        item = backup.get(qid)
        if item is None:
            item = table.get_item(Key={'QuestionID': qid}).get('Item')
        if item is None:
            errores.append({'id': qid, 'error': 'QuestionID no existe en la tabla'})
            continue
        try:
            new_opts = build_new_options(item.get('Options'), set_is_correct)
        except ValueError as e:
            errores.append({'id': qid, 'error': str(e)})
            continue
        new_count = int(fix.get('set_correct_count', len(set_is_correct)))
        old_correct = sorted(l for l, o in (item.get('Options') or {}).items()
                             if isinstance(o, dict) and o.get('is_correct'))
        planned.append({
            'id': qid,
            'old_correct': old_correct,
            'new_correct': sorted(l.strip().upper() for l in set_is_correct),
            'old_count': item.get('CorrectCount'),
            'new_count': new_count,
            'new_opts': new_opts,
            'topic': c.get('topic', ''),
        })

    print(f"\n--- CAMBIOS PLANIFICADOS ({len(planned)}) ---")
    for p in planned:
        print(f"  {p['id']} [{p['topic']}]  correct {p['old_correct']} -> {p['new_correct']}"
              f"   count {p['old_count']} -> {p['new_count']}")
    if errores:
        print(f"\n--- OMITIDOS / ERRORES ({len(errores)}) ---")
        for e in errores:
            print(f"  {e['id']}: {e['error']}")

    if not args.apply:
        print("\nModo DRY-RUN. Ejecuta con --apply para realizar los cambios.")
        return

    print("\nAplicando cambios...")
    exitosos = 0
    fallidos = []
    for p in planned:
        try:
            table.update_item(
                Key={'QuestionID': p['id']},
                UpdateExpression="SET #opts = :opts, CorrectCount = :cc",
                ExpressionAttributeNames={'#opts': 'Options'},
                ExpressionAttributeValues={':opts': p['new_opts'], ':cc': p['new_count']},
                ConditionExpression="attribute_exists(QuestionID)",
            )
            exitosos += 1
        except Exception as e:  # noqa: BLE001
            fallidos.append({'id': p['id'], 'error': str(e)})

    print(f"\n--- RESULTADO ---")
    print(f"Actualizados exitosamente: {exitosos}")
    print(f"Fallidos: {len(fallidos)}")
    for f in fallidos:
        print(f"  ID: {f['id']} | Error: {f['error']}")
    print("\nRestaurar (si hace falta): python scripts/migrate_restore.py")


if __name__ == '__main__':
    main()
