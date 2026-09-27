#!/usr/bin/env python3
"""Corrige 4 defectos de contenido puntuales encontrados el 26-Sep revisando un
examen final real:

1. b2296f6c...: clave de respuesta incorrecta -- la pregunta ("empresa no puede
   prever la demanda de uso") tenía marcada como correcta "Cost-effective" (B) en
   vez de "Scalable and high performance" (D), siendo literalmente la misma
   pregunta (casi-duplicada, no detectada antes por el bug de autojunk) que otras
   2 en el banco que sí tienen D como correcta.
2. 35e53478...: "AWS Nitro" mal usado en el enunciado ("migrar a AWS Nitro") --
   la pregunta es en realidad sobre AWS Application Discovery Service, sin
   relación con Nitro. Se reemplaza por "AWS" genérico.
3. d625dd9e...: mismo problema ("¿qué recurso de AWS Nitro da baja latencia
   global?") -- las opciones son los beneficios generales de AWS Cloud, no
   características de Nitro. Se reemplaza "AWS Nitro" por "AWS".
4. 977fd801...: contaminación de traducción -- "does Fornece provide" en el
   campo en inglés (la palabra "Fornece" es portugués, se filtró por error en
   una migración anterior). Se quita la palabra sobrante.

Hace backup previo de los 4 ítems antes de escribir. Requiere confirmación
explícita ('SI') antes de aplicar los cambios.

USO:
    .venv/bin/python scripts/corregir_contenido_puntual_20260926.py --dry-run
    .venv/bin/python scripts/corregir_contenido_puntual_20260926.py
"""
import argparse
import json
import os
from datetime import datetime

import boto3

TABLE_NAME = "MentoringQuestions"
REGION = "us-east-1"
BACKUP_DIR = os.path.join("scripts", "backup")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--region", default=REGION)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    table = dynamodb.Table(TABLE_NAME)

    ids = [
        "b2296f6cc1e0e4ee3b6f10cb2add9add",
        "35e53478bb6f6e68eb0e5a9976593be3",
        "d625dd9edccc0ac04f76019aebe85bad",
        "977fd801d94835fbef3526718b99a778",
    ]

    print("Preview de cambios:\n")

    # 1. Corregir clave de respuesta
    print("1) b2296f6c... -> corregir clave de respuesta: D correcta, B incorrecta")

    # 2/3. Reemplazar "AWS Nitro" por "AWS"
    print('2) 35e53478... -> reemplazar "AWS Nitro" por "AWS" en QuestionText/QuestionText_pt')
    print('3) d625dd9e... -> reemplazar "AWS Nitro" por "AWS" en QuestionText/QuestionText_pt')

    # 4. Quitar "Fornece" filtrado
    print('4) 977fd801... -> quitar "Fornece " sobrante en QuestionText (EN)')

    if args.dry_run:
        print("\n[DRY-RUN] No se escribe backup ni se aplica ningún cambio.")
        return 0

    # Backup de los 4 ítems tal cual están hoy
    items = []
    for qid in ids:
        resp = table.get_item(Key={"QuestionID": qid})
        if "Item" in resp:
            items.append(resp["Item"])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_file = os.path.join(BACKUP_DIR, f"backup_pre_correccion_puntual_{ts}.json")
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nBackup escrito en {backup_file} ({len(items)} ítems)")

    confirm = input("Confirmar aplicación de los 4 cambios? [escribir 'SI']: ").strip().upper()
    if confirm != "SI":
        print("Cancelado. Nada fue modificado.")
        return 0

    # 1. Clave de respuesta
    table.update_item(
        Key={"QuestionID": "b2296f6cc1e0e4ee3b6f10cb2add9add"},
        UpdateExpression="SET Options.D.is_correct = :true, Options.B.is_correct = :false",
        ExpressionAttributeValues={":true": True, ":false": False},
    )
    print("[1] Clave de respuesta corregida (D correcta).")

    # 2. AWS Nitro -> AWS (item de migración/Application Discovery Service)
    table.update_item(
        Key={"QuestionID": "35e53478bb6f6e68eb0e5a9976593be3"},
        UpdateExpression="SET QuestionText = :en, QuestionText_pt = :pt",
        ExpressionAttributeValues={
            ":en": (
                "A company plans to migrate its on-premises application to AWS. "
                "The company needs to collect data on usage and configuration of "
                "application components. Which AWS service will meet these requirements?"
            ),
            ":pt": (
                "Uma empresa planeja migrar sua aplicação on-premises para a AWS. "
                "A empresa precisa coletar dados sobre uso e configuração dos "
                "componentes da aplicação. Qual serviço AWS atenderá a esses requisitos?"
            ),
        },
    )
    print('[2] "AWS Nitro" corregido a "AWS" en 35e53478...')

    # 3. AWS Nitro -> AWS (item de infraestructura global)
    table.update_item(
        Key={"QuestionID": "d625dd9edccc0ac04f76019aebe85bad"},
        UpdateExpression="SET QuestionText = :en, QuestionText_pt = :pt",
        ExpressionAttributeValues={
            ":en": (
                "A company wants to provide low latency for its users throughout "
                "the world. Which AWS feature addresses this requirement?"
            ),
            ":pt": (
                "Uma empresa deseja fornecer baixa latência para seus usuários em "
                "todo o mundo. Qual recurso da AWS aborda esse requisito?"
            ),
        },
    )
    print('[3] "AWS Nitro" corregido a "AWS" en d625dd9e...')

    # 4. Quitar "Fornece" filtrado
    table.update_item(
        Key={"QuestionID": "977fd801d94835fbef3526718b99a778"},
        UpdateExpression="SET QuestionText = :en",
        ExpressionAttributeValues={
            ":en": "A company needs to block SQL injection attacks. Which AWS service or resource provides this functionality?",
        },
    )
    print('[4] "Fornece" eliminado del enunciado en inglés de 977fd801...')

    print("\nListo. Los 4 ítems fueron corregidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
