#!/usr/bin/env python3
"""Sube a MentoringQuestions las preguntas aprobadas en scripts/revisar_preguntas_nuevas.html.

Lee un JSON exportado desde ese HTML (botón "Descargar aprobadas"), le agrega los
campos que la base de datos espera (QuestionID, ContentHash, CorrectCount, CreatedAt),
verifica que ninguna sea casi-duplicada de otra ya existente en el mismo tema (mismo
método que scripts/detectar_casi_duplicados_contenido.py) y recién entonces las
inserta con put_item condicional (nunca sobreescribe un QuestionID existente).

USO (requiere credenciales AWS válidas en el entorno local, nunca CI/CD):
    .venv/bin/python scripts/subir_preguntas_aprobadas.py --file scripts/preguntas_aprobadas.json --dry-run
    .venv/bin/python scripts/subir_preguntas_aprobadas.py --file scripts/preguntas_aprobadas.json
"""
import argparse
import difflib
import hashlib
import json
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

TABLE_NAME = "MentoringQuestions"
REGION = "us-east-1"
SIMILARITY_THRESHOLD = 0.85


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="JSON exportado por revisar_preguntas_nuevas.html")
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--table", default=TABLE_NAME)
    parser.add_argument("--dry-run", action="store_true", help="Solo valida y muestra el reporte, no escribe nada.")
    return parser.parse_args(argv)


def content_hash(text):
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]", "", normalized.lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_for_similarity(text):
    normalized = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def is_near_duplicate(a, b, threshold=SIMILARITY_THRESHOLD):
    na, nb = normalize_for_similarity(a), normalize_for_similarity(b)
    if not na or not nb:
        return False
    return difflib.SequenceMatcher(None, na, nb).ratio() >= threshold


def build_item(q):
    correct_count = sum(1 for opt in q["options"].values() if opt.get("is_correct"))
    return {
        "QuestionID": uuid.uuid4().hex,
        "Topic": q["topic"],
        "QuestionType": q.get("question_type", "single"),
        "Difficulty": q.get("difficulty", "Medium"),
        "QuestionText": q["question_text"],
        "QuestionText_pt": q.get("question_text_pt", ""),
        "CorrectCount": correct_count,
        "ContentHash": content_hash(q["question_text"]),
        "CreatedAt": datetime.now(timezone.utc).isoformat(),
        "Options": {
            key: {
                "text": opt["text"],
                "text_pt": opt.get("text_pt", ""),
                "is_correct": bool(opt.get("is_correct", False)),
                "explanation": opt.get("explanation", ""),
                "explanation_pt": opt.get("explanation_pt", ""),
                "keywords": opt.get("keywords", ""),
            }
            for key, opt in q["options"].items()
        },
    }


def main(argv=None):
    args = parse_args(argv)

    with open(args.file, "r", encoding="utf-8") as f:
        approved = json.load(f)

    print(f"Preguntas en el archivo: {len(approved)}")

    # Validación de esquema básica.
    errors = []
    for i, q in enumerate(approved):
        correct = [k for k, v in q.get("options", {}).items() if v.get("is_correct")]
        if len(correct) != 1:
            errors.append(f"  [{i}] {q.get('question_text', '')[:50]!r}: {len(correct)} opciones correctas (debe ser 1)")
        if len(q.get("options", {})) != 4:
            errors.append(f"  [{i}] {q.get('question_text', '')[:50]!r}: {len(q.get('options', {}))} opciones (debe ser 4)")

    if errors:
        print("ERRORES DE ESQUEMA (no se sube nada hasta corregir):")
        for e in errors:
            print(e)
        return 1

    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    table = dynamodb.Table(args.table)

    # Chequeo de similaridad contra la BD real, por tema (mismo criterio que el
    # filtro en tiempo real de src/quiz_engine.py y el detector offline).
    print("\nChequeando casi-duplicados contra la base de datos real...")
    topic_cache = {}
    warnings = []
    for i, q in enumerate(approved):
        topic = q["topic"]
        if topic not in topic_cache:
            resp = table.query(IndexName="TopicIndex", KeyConditionExpression=Key("Topic").eq(topic))
            topic_cache[topic] = resp.get("Items", [])
        for existing in topic_cache[topic]:
            ratio = difflib.SequenceMatcher(
                None,
                normalize_for_similarity(q["question_text"]),
                normalize_for_similarity(existing.get("QuestionText", "")),
            ).ratio()
            if ratio >= SIMILARITY_THRESHOLD:
                warnings.append(
                    f"  [{i}] {q['question_text'][:60]!r} ~ {ratio:.3f} similar a "
                    f"QuestionID={existing['QuestionID']} ({existing.get('QuestionText', '')[:60]!r})"
                )

    if warnings:
        print("ADVERTENCIA: posibles casi-duplicados contra la BD real (revisar antes de subir):")
        for w in warnings:
            print(w)
    else:
        print("  Ninguna colisión >= 0.85 contra la base de datos real.")

    items = [build_item(q) for q in approved]

    print(f"\nDistribución por tema a insertar:")
    from collections import Counter
    for topic, count in Counter(q["topic"] for q in approved).most_common():
        print(f"  {topic}: {count}")

    if args.dry_run:
        print("\n[DRY-RUN] No se escribe nada. Usá sin --dry-run para insertar.")
        return 0

    if warnings:
        confirm = input("\nHay posibles casi-duplicados. ¿Subir igual? [escribir 'SI']: ").strip().upper()
        if confirm != "SI":
            print("Cancelado. Revisá las advertencias y volvé a exportar desde el HTML si hace falta.")
            return 1

    confirm = input(f"\nConfirmar inserción de {len(items)} preguntas nuevas? [escribir 'SI']: ").strip().upper()
    if confirm != "SI":
        print("Cancelado. Nada fue modificado.")
        return 0

    inserted = 0
    for item in items:
        try:
            table.put_item(Item=item, ConditionExpression="attribute_not_exists(QuestionID)")
            inserted += 1
        except ClientError as e:
            print(f"  ERROR insertando {item['QuestionID']}: {e}")

    print(f"\nInsertadas: {inserted}/{len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
