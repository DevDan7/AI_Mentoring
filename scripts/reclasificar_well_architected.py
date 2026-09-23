#!/usr/bin/env python3
"""Reclasifica las preguntas del tema 'Cloud Concepts & Well-Architected' en dos
sub-categorías: 'AWS Well-Architected Framework' (los 6 pilares) y
'Cloud Concepts & Value Proposition' (el resto del Dominio 1: valor de la nube, modelos
de despliegue, economía de la nube, migración, etc.).

Motivo: Daniel notó demasiadas preguntas de Well-Architected en el examen final (esperaba
un máximo de 6). Un match por palabra clave ("well-architected" en el texto) subestima el
conteo real -- hay preguntas sobre los 6 pilares (confiabilidad, optimización de costos,
excelencia operacional, rendimiento, seguridad, sostenibilidad) que no mencionan
"well-architected" literalmente. Por eso se usa Bedrock (mismo modelo que processor.py)
para clasificar semánticamente cada pregunta.

Solo genera un reporte para revisión manual -- mismo patrón que normalizar_temas.py y
migrate_fix_answers.py. NO modifica DynamoDB. La aplicación real (UpdateItem con backup)
se hace en un paso separado, después de que Daniel revise el reporte.

Uso:
    .venv/bin/python scripts/reclasificar_well_architected.py
    .venv/bin/python scripts/reclasificar_well_architected.py --apply   # tras revisar el reporte
"""
import json
import sys
import time
from datetime import datetime

import boto3
from botocore.config import Config
from boto3.dynamodb.conditions import Key

TABLE_NAME = "MentoringQuestions"
REGION = "us-east-1"
OLD_TOPIC = "Cloud Concepts & Well-Architected"
NEW_TOPIC_GENERAL = "Cloud Concepts & Value Proposition"
NEW_TOPIC_WAF = "AWS Well-Architected Framework"
REPORT_FILE = "scripts/reporte_reclasificacion_well_architected.json"
MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

CLASSIFY_PROMPT = """Sos un experto en la certificación AWS Certified Cloud Practitioner (CLF-C02).
Clasificá la siguiente pregunta del Dominio 1 (Cloud Concepts) en UNA de estas dos categorías:

- "well_architected_framework": pregunta sobre el AWS Well-Architected Framework o sus 6 \
pilares (excelencia operacional, seguridad, confiabilidad, eficiencia de rendimiento, \
optimización de costos, sostenibilidad), sus principios de diseño, o herramientas \
relacionadas (AWS Well-Architected Tool, Trusted Advisor en ese contexto).
- "cloud_concepts_general": cualquier otra pregunta del Dominio 1 (propuesta de valor de \
la nube, modelos de despliegue, economía de la nube, migración a la nube, elasticidad, \
alta disponibilidad, modelos de responsabilidad compartida a nivel conceptual, etc.).

Pregunta:
{question_text}

Respondé SOLO con el JSON: {{"category": "well_architected_framework"}} o \
{{"category": "cloud_concepts_general"}}"""


def scan_topic_items(table, topic):
    items = []
    response = table.query(IndexName="TopicIndex", KeyConditionExpression=Key("Topic").eq(topic))
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response:
        response = table.query(
            IndexName="TopicIndex", KeyConditionExpression=Key("Topic").eq(topic),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))
    return items


def classify(bedrock_runtime, question_text):
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 100,
        "messages": [{
            "role": "user",
            "content": [{"type": "text", "text": CLASSIFY_PROMPT.format(question_text=question_text)}],
        }],
    })
    response = bedrock_runtime.invoke_model(modelId=MODEL_ID, body=body)
    raw = json.loads(response["body"].read())["content"][0]["text"]
    clean = raw.replace("```json", "").replace("```", "").strip()
    parsed = json.loads(clean)
    category = parsed.get("category")
    if category not in ("well_architected_framework", "cloud_concepts_general"):
        raise ValueError(f"Categoría inesperada: {category!r}")
    return category


def main():
    apply_mode = "--apply" in sys.argv

    if apply_mode:
        apply_from_report()
        return

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)
    items = scan_topic_items(table, OLD_TOPIC)
    print(f"Preguntas en '{OLD_TOPIC}': {len(items)}\n")

    bedrock_config = Config(retries={"max_attempts": 3, "mode": "adaptive"})
    bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION, config=bedrock_config)

    results = []
    errors = []
    for item in items:
        qid = item["QuestionID"]
        text = item.get("QuestionText", "")
        try:
            category = classify(bedrock_runtime, text)
        except Exception as e:
            print(f"  ERROR clasificando {qid}: {e}")
            errors.append({"QuestionID": qid, "error": str(e)})
            continue
        new_topic = NEW_TOPIC_WAF if category == "well_architected_framework" else NEW_TOPIC_GENERAL
        results.append({"QuestionID": qid, "QuestionText": text, "category": category,
                         "new_topic": new_topic, "approved": None})
        print(f"  {qid} -> {category}")
        time.sleep(0.1)

    waf_count = sum(1 for r in results if r["category"] == "well_architected_framework")
    general_count = len(results) - waf_count
    print(f"\n--- RESUMEN ---")
    print(f"{NEW_TOPIC_WAF}: {waf_count}")
    print(f"{NEW_TOPIC_GENERAL}: {general_count}")
    print(f"Errores: {len(errors)}")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump({"old_topic": OLD_TOPIC, "total": len(items), "waf_count": waf_count,
                   "general_count": general_count, "errors": errors, "results": results},
                  f, ensure_ascii=False, indent=2)
    print(f"\nReporte guardado en: {REPORT_FILE}")
    print("Revisar cada 'category' a mano, setear 'approved': true en los correctos, y "
          "correr --apply.")


def apply_from_report():
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        report = json.load(f)

    to_apply = [r for r in report["results"] if r.get("approved") is True]
    print(f"Ítems aprobados para reclasificar: {to_apply and len(to_apply) or 0} de "
          f"{len(report['results'])}")
    if not to_apply:
        print("Nada aprobado todavía. Editá el reporte y seteá 'approved': true.")
        return

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    all_items = []
    kwargs = {}
    while True:
        resp = table.scan(**kwargs)
        all_items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"scripts/backup_pre_reclasificacion_{ts}.json"
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2, default=str)
    print(f"Backup: {backup_file} ({len(all_items)} items)")

    confirm = input("Confirmás la reclasificación? (escribe 'si'): ").strip().lower()
    if confirm != "si":
        print("Cancelado.")
        return

    exitosos = 0
    for r in to_apply:
        try:
            table.update_item(
                Key={"QuestionID": r["QuestionID"]},
                UpdateExpression="SET #top = :new_topic, OriginalTopic = :old_topic",
                ExpressionAttributeNames={"#top": "Topic"},
                ExpressionAttributeValues={":new_topic": r["new_topic"], ":old_topic": OLD_TOPIC},
            )
            exitosos += 1
        except Exception as e:
            print(f"  ERROR {r['QuestionID']}: {e}")
    print(f"\nActualizados: {exitosos}/{len(to_apply)}")


if __name__ == "__main__":
    main()
