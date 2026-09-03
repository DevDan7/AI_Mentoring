#!/usr/bin/env python3
"""Pobla el atributo ContentHash en las preguntas de MentoringQuestions.

Calcula el ContentHash con la MISMA funcion content_hash() de src/processor.py
para garantizar consistencia con la dedupe por contenido desplegada.

No es destructivo: solo anade el atributo ContentHash a los items que no lo
tienen. Genera un backup previo (snapshot JSON) para trazabilidad.

USO (requiere credenciales AWS configuradas):
    .venv/bin/python scripts/poblar_content_hash.py           # mode simulacion
    .venv/bin/python scripts/poblar_content_hash.py --apply   # ejecuta update_item
"""
import json
import sys
import time
from datetime import datetime

import boto3

sys.path.insert(0, "src")
from processor import content_hash  # noqa: E402  (misma funcion de dedupe)

TABLE_NAME = "MentoringQuestions"
REGION = "us-east-1"
HASH_ATTR = "ContentHash"


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


def main() -> None:
    apply = "--apply" in sys.argv

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    snapshot = scan_table(table)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"scripts/backup_pre_hash_{ts}.json"
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
    print(f"Backup previo guardado en: {backup_file} ({len(snapshot)} items)")

    missing = [it for it in snapshot if not it.get(HASH_ATTR)]
    print(f"Items totales: {len(snapshot)} | Sin {HASH_ATTR}: {len(missing)}")

    if not missing:
        print("No hay items sin ContentHash. Nada que hacer.")
        return

    # Verificar integridad: todo item tiene QuestionID y QuestionText
    no_text = [it for it in missing if not it.get("QuestionText")]
    if no_text:
        print(f"ADVERTENCIA: {len(no_text)} items sin QuestionText (no se puede hashear):")
        for it in no_text:
            print("  ", it.get("QuestionID"))
    to_update = [it for it in missing if it.get("QuestionText")]
    print(f"Items a actualizar (con QuestionText): {len(to_update)}")

    if not apply:
        print("\nModo simulacion (sin --apply). No se actualizo nada.")
        print("Ejemplo del hash que se calculara:")
        sample = to_update[0]
        print("  QuestionID:", sample["QuestionID"])
        print("  ContentHash:", content_hash(sample["QuestionText"]))
        print("\nPara ejecutar el cambio real, usa: --apply")
        return

    print("\nSe actualizaran", len(to_update), "items con", HASH_ATTR + ".")
    confirm = input("Confirmas? (escribe 'si' para continuar): ").strip().lower()
    if confirm != "si":
        print("Cancelado.")
        return

    updated = 0
    failed = 0
    for it in to_update:
        qid = it["QuestionID"]
        h = content_hash(it["QuestionText"])
        try:
            table.update_item(
                Key={"QuestionID": qid},
                UpdateExpression=f"SET {HASH_ATTR} = :h",
                ExpressionAttributeValues={":h": h},
            )
            updated += 1
            if updated % 20 == 0:
                print(f"  ...{updated} actualizados")
        except Exception as e:
            failed += 1
            print(f"  ERROR al actualizar {qid}: {e}")
        time.sleep(0.05)

    print(f"\nActualizados: {updated} | Errores: {failed}")

    # Verificacion final
    after = scan_table(table)
    still_missing = [it for it in after if not it.get(HASH_ATTR)]
    print(f"Items con {HASH_ATTR}: {len(after) - len(still_missing)} de {len(after)}")


if __name__ == "__main__":
    main()
