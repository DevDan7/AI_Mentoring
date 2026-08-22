import boto3
import json
import argparse
import datetime
import collections

TABLE_NAME = 'MentoringQuestions'
MAPA_FILE = 'scripts/mapa_temas.json'


def load_mapa():
    with open(MAPA_FILE, 'r') as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith('_')}


def backup_tabla(dynamodb):
    table = dynamodb.Table(TABLE_NAME)
    items = []
    response = table.scan()
    items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'scripts/backup_pre_migracion_{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(items, f, indent=2, default=str)
    print(f"Respaldo guardado en: {filename}")
    return items


def main():
    parser = argparse.ArgumentParser(
        description='Normaliza el campo Topic de MentoringQuestions usando mapa_temas.json'
    )
    parser.add_argument('--apply', action='store_true',
                        help='Aplica los cambios reales en DynamoDB (sin este flag es dry-run)')
    args = parser.parse_args()

    dynamodb = boto3.resource('dynamodb')
    mapa = load_mapa()

    print("Iniciando respaldo...")
    items = backup_tabla(dynamodb)

    table = dynamodb.Table(TABLE_NAME)

    to_update = []
    no_match = collections.Counter()
    resumen_categorias = collections.Counter()
    ya_migrados = 0
    sin_topic = 0
    fallidos = []

    for item in items:
        if 'OriginalTopic' in item:
            ya_migrados += 1
            continue

        topic_actual = item.get('Topic')
        if not topic_actual:
            sin_topic += 1
            continue

        if topic_actual in mapa:
            categoria_nueva = mapa[topic_actual]
            to_update.append({
                'id': item['QuestionID'],
                'old': topic_actual,
                'new': categoria_nueva
            })
            resumen_categorias[categoria_nueva] += 1
        else:
            no_match[topic_actual] += 1

    print(f"\n--- RESUMEN DE NORMALIZACIÓN ---")
    print(f"Ítems escaneados:              {len(items)}")
    print(f"Ya migrados (omitidos):        {ya_migrados}")
    print(f"Sin campo Topic:               {sin_topic}")
    print(f"Ítems a normalizar:            {len(to_update)}")
    print(f"Ítems sin match:               {sum(no_match.values())}")

    print(f"\n--- NORMALIZACIÓN POR CATEGORÍA ---")
    for cat, count in sorted(resumen_categorias.items()):
        print(f"  {cat}: {count}")

    print(f"\n--- EJEMPLOS DE NORMALIZACIÓN (hasta 5) ---")
    for u in to_update[:5]:
        print(f"  QuestionID: {u['id']} | '{u['old']}' -> '{u['new']}'")

    if no_match:
        print(f"\n--- SIN MATCH (Revisar manualmente) ---")
        for topic, count in sorted(no_match.items()):
            print(f"  '{topic}' ({count} items)")

    if args.apply:
        print(f"\nAplicando cambios...")
        exitosos = 0
        for u in to_update:
            try:
                table.update_item(
                    Key={'QuestionID': u['id']},
                    UpdateExpression="SET #top = :new_topic, OriginalTopic = :old_topic",
                    ExpressionAttributeNames={'#top': 'Topic'},
                    ExpressionAttributeValues={
                        ':new_topic': u['new'],
                        ':old_topic': u['old']
                    }
                )
                exitosos += 1
            except Exception as e:
                fallidos.append({'id': u['id'], 'error': str(e)})

        print(f"\n--- RESULTADO DE APLICACIÓN ---")
        print(f"Actualizados exitosamente: {exitosos}")
        print(f"Fallidos: {len(fallidos)}")
        for f in fallidos:
            print(f"  ID: {f['id']} | Error: {f['error']}")
    else:
        print("\nModo DRY-RUN. Ejecuta con --apply para realizar los cambios.")


if __name__ == '__main__':
    main()
