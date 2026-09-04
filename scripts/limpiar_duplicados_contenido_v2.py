#!/usr/bin/env python3
"""Elimina duplicados por contenido en MentoringQuestions.

Para cada par de items con el mismo ContentHash, conserva la version original
(question_XXX.png) y elimina la version Captura de pantalla_*.png.
Si ambos son del mismo tipo, elimina el mas reciente (por CreatedAt).

Genera backup previo antes de eliminar.

USO:
    .venv/bin/python scripts/limpiar_duplicados_contenido_v2.py
    .venv/bin/python scripts/limpiar_duplicados_contenido_v2.py --apply
"""
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime

import boto3

TABLE_NAME = "MentoringQuestions"
REGION = "us-east-1"


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


def pick_to_remove(pair):
    """De un par de items con mismo ContentHash, decide cual eliminar.
    Conserva question_XXX.png y elimina Captura de pantalla_*.png.
    Si ambos son del mismo tipo, elimina el CreatedAt mas reciente.
    """
    f0 = pair[0].get("FileName", "")
    f1 = pair[1].get("FileName", "")
    is_q0 = f0.startswith("question_")
    is_q1 = f1.startswith("question_")
    if is_q0 and not is_q1:
        return pair[1]
    if is_q1 and not is_q0:
        return pair[0]
    c0 = pair[0].get("CreatedAt", "")
    c1 = pair[1].get("CreatedAt", "")
    return pair[0] if c0 >= c1 else pair[1]


def main():
    apply = "--apply" in sys.argv

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    items = scan_table(table)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"scripts/backup_pre_dedupe_v2_{ts}.json"
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2, default=str)
    print(f"Backup: {backup_file} ({len(items)} items)")

    hash_counts = Counter(it.get("ContentHash") for it in items if it.get("ContentHash"))
    collisions = {h: c for h, c in hash_counts.items() if c > 1}

    if not collisions:
        print("No hay colisiones. Nada que limpiar.")
        return

    to_remove = []
    for h, count in collisions.items():
        pair = [it for it in items if it.get("ContentHash") == h]
        victim = pick_to_remove(pair)
        to_remove.append(victim)
        print(f"  Colision {h[:16]}... -> eliminar: {victim.get('FileName')} ({victim['QuestionID']})")

    print(f"\nTotal a eliminar: {len(to_remove)}")

    if not apply:
        print("\nModo simulacion (sin --apply).")
        print("Para ejecutar: --apply")
        return

    confirm = input("Confirmas la eliminacion? (escribe 'si'): ").strip().lower()
    if confirm != "si":
        print("Cancelado.")
        return

    deleted = 0
    for it in to_remove:
        try:
            table.delete_item(Key={"QuestionID": it["QuestionID"]})
            deleted += 1
            print(f"  Eliminado: {it['FileName']}")
        except Exception as e:
            print(f"  ERROR: {it['FileName']}: {e}")
        time.sleep(0.05)

    print(f"\nEliminados: {deleted}")

    after = scan_table(table)
    after_hashes = [it.get("ContentHash") for it in after if it.get("ContentHash")]
    remaining_collisions = len(after_hashes) - len(set(after_hashes))
    print(f"Items restantes: {len(after)}")
    print(f"Colisiones restantes: {remaining_collisions}")


if __name__ == "__main__":
    main()
