#!/usr/bin/env python3
"""Auditoría de preguntas duplicadas por contenido en la tabla MentoringQuestions.

Lee directamente la tabla DynamoDB MentoringQuestions, normaliza el enunciado
(QuestionText) de cada pregunta y detecta grupos cuyo enunciado normalizado
coincide EXACTAMENTE (deduplicación por "solo idénticas exactas").

Solo genera un reporte. NO modifica ni elimina ningún dato.

Uso:
    python scripts/detectar_duplicados_contenido.py [--print-text]
"""
import json
import re
import sys
import unicodedata
from collections import defaultdict

import boto3

TABLE_NAME = "MentoringQuestions"
REGION = "us-east-1"


def normalize_text(text: str) -> str:
    """Normaliza un enunciado: minúsculas, sin acentos, sin puntuación,
    espacios colapsados. Base del criterio 'solo idénticas exactas'."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def scan_table(dynamodb) -> list:
    """Devuelve todos los ítems de la tabla usando scan con paginación."""
    table = dynamodb.Table(TABLE_NAME)
    items = []
    kwargs = {}
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def main() -> None:
    print_text = "--print-text" in sys.argv

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    items = scan_table(dynamodb)
    print(f"Total ítems en {TABLE_NAME}: {len(items)}\n")

    groups = defaultdict(list)
    missing_text = 0
    for item in items:
        raw = item.get("QuestionText", "")
        if not raw:
            missing_text += 1
        norm = normalize_text(raw)
        groups[norm].append(item)

    duplicates = {norm: lst for norm, lst in groups.items() if len(lst) > 1 and norm}

    print(f"Ítems sin QuestionText: {missing_text}")
    print(f"Grupos con enunciado duplicado (idéntico exacto): {len(duplicates)}\n")

    if not duplicates:
        print("No se encontraron preguntas duplicadas por contenido.")
        return

    total_dup = sum(len(lst) - 1 for lst in duplicates.values())
    print(f"Ítems que se conservarían: {len(items) - total_dup}")
    print(f"Ítems candidatos a eliminar: {total_dup}\n")

    report = []
    for idx, (norm, lst) in enumerate(sorted(duplicates.items(), key=lambda x: -len(x[1])), 1):
        lst_sorted = sorted(lst, key=lambda i: i.get("CreatedAt", i.get("QuestionID", "")))
        keep = lst_sorted[0]
        remove = lst_sorted[1:]

        header = (
            f"[Grupo {idx}] {len(lst)} coincidencias "
            f"| Topic: '{keep.get('Topic', 'N/D')}'"
        )
        print(header)
        print("-" * len(header))
        print(f"  CONSERVAR  -> QuestionID={keep.get('QuestionID')} "
              f"FileName={keep.get('FileName', '-')}")
        for r in remove:
            print(f"  ELIMINAR   -> QuestionID={r.get('QuestionID')} "
                  f"FileName={r.get('FileName', '-')} "
                  f"Topic={r.get('Topic', '-')}")
        if print_text:
            print(f"  TEXTO: {keep.get('QuestionText', '')}\n")
        print()

        report.append({
            "group": idx,
            "count": len(lst),
            "topic": keep.get("Topic"),
            "keep": {"QuestionID": keep["QuestionID"], "FileName": keep.get("FileName")},
            "remove": [{"QuestionID": r["QuestionID"], "FileName": r.get("FileName")}
                       for r in remove],
        })

    out_file = "scripts/reporte_duplicados_contenido.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"total_items": len(items),
                   "groups": len(duplicates),
                   "candidates_to_remove": total_dup,
                   "duplicates": report}, f, ensure_ascii=False, indent=2)
    print(f"\nReporte JSON guardado en: {out_file}")


if __name__ == "__main__":
    main()
