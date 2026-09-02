#!/usr/bin/env python3
"""Limpieza de preguntas duplicadas por contenido en la tabla MentoringQuestions.

Elimina los QuestionID marcados como "remove" en reporte_duplicados_contenido.json
(conservando los QuestionID "keep" de cada grupo).

Genera un backup previo (snapshot JSON) antes de eliminar, para trazabilidad.

USO (requiere credenciales AWS configuradas):
    .venv/bin/python scripts/limpiar_duplicados_contenido.py
    .venv/bin/python scripts/limpiar_duplicados_contenido.py --apply   # ejecuta el borrado
"""
import json
import sys
import time
from datetime import datetime

import boto3

TABLE_NAME = "MentoringQuestions"
REGION = "us-east-1"
REPORT_FILE = "scripts/reporte_duplicados_contenido.json"


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

    with open(REPORT_FILE, encoding="utf-8") as f:
        report = json.load(f)

    remove_ids = [q["QuestionID"] for d in report["duplicates"] for q in d["remove"]]
    keep_ids = [d["keep"]["QuestionID"] for d in report["duplicates"]]

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    # Snapshot previo completo de la tabla
    snapshot = scan_table(table)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"scripts/backup_pre_limpieza_{ts}.json"
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
    print(f"Backup previo guardado en: {backup_file} ({len(snapshot)} ítems)")

    # Sanity check: solo eliminar si existen en la tabla
    existing = {it["QuestionID"] for it in snapshot}
    missing = [qid for qid in remove_ids if qid not in existing]
    if missing:
        print(f"ADVERTENCIA: {len(missing)} QuestionID no existen en la tabla:")
        for m in missing:
            print("  ", m)
    real_remove = [qid for qid in remove_ids if qid in existing]

    # Verificar integridad: ningún keep debe aparecer también como remove
    overlap = set(remove_ids) & set(keep_ids)
    if overlap:
        print(f"ERROR: hay conflicto keep/remove: {overlap}")
        sys.exit(1)

    print(f"\nA eliminar: {len(real_remove)} | A conservar: {len(keep_ids)}")
    if not apply:
        print("\nModo simulación (sin --apply). No se borró nada.")
        print("Confirmación final de los IDs a eliminar:")
        for qid in real_remove:
            print("  ", qid)
        print("\nPara ejecutar el borrado real, usa: --apply")
        return

    # Ejecutar borrado con confirmación de sí/no
    print("\nSe ejecutará el borrado de", len(real_remove), "ítems.")
    confirm = input("¿Confirmas el borrado definitivo? (escribe 'si' para continuar): ").strip().lower()
    if confirm != "si":
        print("Borrado cancelado.")
        return

    deleted = 0
    failed = 0
    for qid in real_remove:
        try:
            table.delete_item(Key={"QuestionID": qid})
            deleted += 1
            print(f"  Eliminado {qid}")
        except Exception as e:
            failed += 1
            print(f"  ERROR al eliminar {qid}: {e}")
        time.sleep(0.05)  # evitar throttling en PAY_PER_REQUEST

    print(f"\nEliminados: {deleted} | Errores: {failed}")
    final_count = len(scan_table(table))
    print(f"Ítems restantes en tabla: {final_count}")


if __name__ == "__main__":
    main()
