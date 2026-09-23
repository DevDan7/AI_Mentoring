#!/usr/bin/env python3
"""Traduce al Portugués de Brasil (PT-BR) las preguntas existentes de MentoringQuestions
que todavía no tienen traducción, agregando los campos QuestionText_pt y
Options[key].text_pt / explanation_pt.

Es una operación ADITIVA: nunca borra ni pisa los campos en inglés (quedan como fallback
si falta o está incompleta la traducción). El pipeline de ingestión (processor.py) ya
genera estos campos para las fotos nuevas -- este script es solo para el banco existente
al momento de agregar el soporte de idioma.

Mismo patrón que reclasificar_well_architected.py / migrate_fix_answers.py: reporte
primero, --apply separado con backup.

Uso:
    .venv/bin/python scripts/traducir_preguntas_pt.py
    .venv/bin/python scripts/traducir_preguntas_pt.py --apply
"""
import json
import sys
import time
from datetime import datetime

import boto3
from botocore.config import Config

TABLE_NAME = "MentoringQuestions"
REGION = "us-east-1"
MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
REPORT_FILE = "scripts/reporte_traduccion_pt.json"

TRANSLATE_PROMPT = """Traduzí al Portugués de Brasil (PT-BR), de forma natural y técnica \
(no literal palabra por palabra), el siguiente enunciado de examen AWS y sus opciones.

Enunciado: {question_text}

Opciones:
{options_text}

Respondé SOLO con este JSON (mismas claves A/B/C/... que las opciones dadas):
{{
  "question_text_pt": "...",
  "options_pt": {{
    "A": {{"text_pt": "...", "explanation_pt": "..."}},
    "B": {{"text_pt": "...", "explanation_pt": "..."}}
  }}
}}"""


def scan_table(table):
    items = []
    kwargs = {}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def needs_translation(item):
    if not item.get("QuestionText_pt"):
        return True
    options = item.get("Options", {})
    return any(not opt.get("text_pt") for opt in options.values())


def translate(bedrock_runtime, item):
    options = item.get("Options", {})
    options_text = "\n".join(f"{k}: {v.get('text', '')}" for k, v in options.items())
    prompt = TRANSLATE_PROMPT.format(
        question_text=item.get("QuestionText", ""), options_text=options_text
    )
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    })
    response = bedrock_runtime.invoke_model(modelId=MODEL_ID, body=body)
    raw = json.loads(response["body"].read())["content"][0]["text"]
    clean = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(clean)


def main():
    if "--apply" in sys.argv:
        apply_from_report()
        return

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)
    items = scan_table(table)
    pending = [i for i in items if needs_translation(i)]
    print(f"Total ítems: {len(items)} | Pendientes de traducir: {len(pending)}\n")

    bedrock_config = Config(retries={"max_attempts": 3, "mode": "adaptive"})
    bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION, config=bedrock_config)

    results = []
    errors = []
    for item in pending:
        qid = item["QuestionID"]
        try:
            translation = translate(bedrock_runtime, item)
        except Exception as e:
            print(f"  ERROR traduciendo {qid}: {e}")
            errors.append({"QuestionID": qid, "error": str(e)})
            continue
        results.append({"QuestionID": qid, "question_text_pt": translation.get("question_text_pt", ""),
                         "options_pt": translation.get("options_pt", {})})
        print(f"  {qid} traducido")
        time.sleep(0.1)

    print(f"\nTraducidos: {len(results)} | Errores: {len(errors)}")
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump({"total": len(items), "pending": len(pending), "translated": len(results),
                   "errors": errors, "results": results}, f, ensure_ascii=False, indent=2)
    print(f"Reporte guardado en: {REPORT_FILE}")
    print("Revisar el reporte (opcional, es traducción directa) y correr --apply.")


def apply_from_report():
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        report = json.load(f)

    results = report.get("results", [])
    print(f"Ítems a aplicar: {len(results)}")
    if not results:
        print("Nada que aplicar.")
        return

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    all_items = scan_table(table)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"scripts/backup_pre_traduccion_pt_{ts}.json"
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2, default=str)
    print(f"Backup: {backup_file} ({len(all_items)} items)")

    confirm = input("Confirmás aplicar las traducciones? (escribe 'si'): ").strip().lower()
    if confirm != "si":
        print("Cancelado.")
        return

    exitosos = 0
    for r in results:
        qid = r["QuestionID"]
        item = next((i for i in all_items if i["QuestionID"] == qid), None)
        if not item:
            print(f"  SALTEADO (no encontrado): {qid}")
            continue

        options = dict(item.get("Options", {}))
        for key, opt_pt in r.get("options_pt", {}).items():
            if key in options:
                options[key] = dict(options[key])
                options[key]["text_pt"] = opt_pt.get("text_pt", "")
                options[key]["explanation_pt"] = opt_pt.get("explanation_pt", "")

        try:
            table.update_item(
                Key={"QuestionID": qid},
                UpdateExpression="SET QuestionText_pt = :qtp, #opts = :opts",
                ExpressionAttributeNames={"#opts": "Options"},
                ExpressionAttributeValues={
                    ":qtp": r.get("question_text_pt", ""),
                    ":opts": options,
                },
            )
            exitosos += 1
        except Exception as e:
            print(f"  ERROR {qid}: {e}")

    print(f"\nActualizados: {exitosos}/{len(results)}")


if __name__ == "__main__":
    main()
