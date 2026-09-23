#!/usr/bin/env python3
"""Auditoría de preguntas CASI-duplicadas por contenido en MentoringQuestions.

`detectar_duplicados_contenido.py` solo atrapa coincidencias EXACTAS tras normalizar
(minúsculas/tildes/puntuación). Este script complementa esa auditoría: compara TODAS las
preguntas entre sí con similitud de texto aproximada (difflib.SequenceMatcher) para
detectar pares que son la MISMA pregunta con una redacción levemente distinta (ej. una
foto procesada dos veces por Bedrock con una variación menor de OCR/traducción) — casos que
el ContentHash exacto no detecta porque un cambio de una sola palabra ya produce un hash
distinto.

Solo genera un reporte. NO modifica ni elimina ningún dato — un falso positivo (dos
preguntas legítimamente distintas pero parecidas) borrado a ciegas sería peor que el
problema que se busca resolver, así que la decisión de qué borrar queda para revisión
humana antes de correr limpiar_casi_duplicados_contenido.py --apply.

Uso:
    python scripts/detectar_casi_duplicados_contenido.py [--umbral 0.85] [--print-text]
"""
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from itertools import combinations

import boto3

TABLE_NAME = "MentoringQuestions"
REGION = "us-east-1"
DEFAULT_THRESHOLD = 0.85


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def scan_table(dynamodb) -> list:
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


def parse_threshold(argv) -> float:
    for i, arg in enumerate(argv):
        if arg == "--umbral" and i + 1 < len(argv):
            return float(argv[i + 1])
    return DEFAULT_THRESHOLD


def main() -> None:
    print_text = "--print-text" in sys.argv
    threshold = parse_threshold(sys.argv)

    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    items = scan_table(dynamodb)
    print(f"Total ítems en {TABLE_NAME}: {len(items)}")
    print(f"Umbral de similitud: {threshold}\n")

    normalized = [(item, normalize_text(item.get("QuestionText", ""))) for item in items]
    normalized = [(item, norm) for item, norm in normalized if norm]

    pairs = []
    for (item_a, norm_a), (item_b, norm_b) in combinations(normalized, 2):
        # Descarte rápido: si difieren mucho en longitud no puede superar el umbral.
        if abs(len(norm_a) - len(norm_b)) > max(len(norm_a), len(norm_b)) * (1 - threshold) * 2:
            continue
        ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
        if ratio >= threshold and norm_a != norm_b:  # los idénticos ya los cubre el otro script
            pairs.append((ratio, item_a, item_b))

    pairs.sort(key=lambda p: -p[0])

    print(f"Pares casi-duplicados encontrados (similitud >= {threshold}, no idénticos): "
          f"{len(pairs)}\n")

    if not pairs:
        print("No se encontraron casi-duplicados por encima del umbral.")
        return

    report = []
    for idx, (ratio, item_a, item_b) in enumerate(pairs, 1):
        header = (
            f"[Par {idx}] similitud={ratio:.2f} | Topic A='{item_a.get('Topic', 'N/D')}' "
            f"| Topic B='{item_b.get('Topic', 'N/D')}'"
        )
        print(header)
        print("-" * len(header))
        print(f"  A -> QuestionID={item_a.get('QuestionID')} FileName={item_a.get('FileName', '-')}")
        print(f"  B -> QuestionID={item_b.get('QuestionID')} FileName={item_b.get('FileName', '-')}")
        if print_text:
            print(f"  TEXTO A: {item_a.get('QuestionText', '')}")
            print(f"  TEXTO B: {item_b.get('QuestionText', '')}")
        print()

        report.append({
            "pair": idx,
            "similarity": round(ratio, 4),
            "a": {"QuestionID": item_a["QuestionID"], "Topic": item_a.get("Topic"),
                  "FileName": item_a.get("FileName"), "QuestionText": item_a.get("QuestionText")},
            "b": {"QuestionID": item_b["QuestionID"], "Topic": item_b.get("Topic"),
                  "FileName": item_b.get("FileName"), "QuestionText": item_b.get("QuestionText")},
            "reviewed": False,
            "approved_remove": None,  # a completar a mano: "a" | "b" | null (no es duplicado)
        })

    out_file = "scripts/reporte_casi_duplicados_contenido.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"total_items": len(items), "threshold": threshold,
                   "pairs_found": len(pairs), "pairs": report}, f, ensure_ascii=False, indent=2)
    print(f"\nReporte JSON guardado en: {out_file}")
    print("Revisar a mano cada par y completar 'approved_remove' antes de correr "
          "limpiar_casi_duplicados_contenido.py --apply.")


if __name__ == "__main__":
    main()
