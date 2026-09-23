#!/usr/bin/env python3
"""Elimina los casi-duplicados ya revisados y aprobados a mano en
scripts/reporte_casi_duplicados_contenido.json (generado por
detectar_casi_duplicados_contenido.py).

A diferencia de limpiar_duplicados_contenido_v2.py (que decide automáticamente qué
conservar por convención de nombre de archivo), este script NUNCA decide solo: cada par
del reporte debe tener "approved_remove" seteado a mano en "a", "b" (cuál QuestionID
eliminar) o null (no es un duplicado real, se ignora). Pares sin revisar (approved_remove
ausente o el campo "reviewed" en false) se saltean y se listan al final.

Genera backup previo antes de eliminar.

USO:
    .venv/bin/python scripts/limpiar_casi_duplicados_contenido.py
    .venv/bin/python scripts/limpiar_casi_duplicados_contenido.py --apply
"""
import json
import sys
import time
from datetime import datetime

import boto3

TABLE_NAME = "MentoringQuestions"
REGION = "us-east-1"
REPORT_FILE = "scripts/reporte_casi_duplicados_contenido.json"


def main():
    apply = "--apply" in sys.argv

    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        report = json.load(f)

    to_remove = []
    skipped_unreviewed = 0
    skipped_not_dup = 0
    for pair in report.get("pairs", []):
        if not pair.get("reviewed"):
            skipped_unreviewed += 1
            continue
        approved = pair.get("approved_remove")
        if approved is None:
            skipped_not_dup += 1
            continue
        if approved not in ("a", "b"):
            print(f"  ADVERTENCIA: par {pair['pair']} tiene approved_remove inválido "
                  f"({approved!r}), se salta.")
            continue
        victim = pair[approved]
        to_remove.append(victim)
        print(f"  Par {pair['pair']} (sim={pair['similarity']}) -> eliminar "
              f"{victim['QuestionID']} ({approved})")

    print(f"\nPares sin revisar (reviewed=false): {skipped_unreviewed}")
    print(f"Pares revisados y marcados como NO duplicado: {skipped_not_dup}")
    print(f"Total a eliminar: {len(to_remove)}")

    if not to_remove:
        print("Nada que eliminar. Revisá el reporte y completá 'approved_remove' primero.")
        return

    if not apply:
        print("\nModo simulación (sin --apply). Para ejecutar: --apply")
        return

    confirm = input("Confirmás la eliminación? (escribe 'si'): ").strip().lower()
    if confirm != "si":
        print("Cancelado.")
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
    backup_file = f"scripts/backup_pre_casi_duplicados_{ts}.json"
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2, default=str)
    print(f"Backup: {backup_file} ({len(all_items)} items)")

    deleted = 0
    for it in to_remove:
        try:
            table.delete_item(Key={"QuestionID": it["QuestionID"]})
            deleted += 1
            print(f"  Eliminado: {it['QuestionID']}")
        except Exception as e:
            print(f"  ERROR: {it['QuestionID']}: {e}")
        time.sleep(0.05)

    print(f"\nEliminados: {deleted}")


if __name__ == "__main__":
    main()
