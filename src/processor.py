import json
import os
import urllib.parse
import uuid
from datetime import datetime

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

TABLE_NAME = os.environ.get("TABLE_NAME", "MentoringQuestions")

# Taxonomía canónica de categorías (debe coincidir con dashboard.html <select> y mapa_temas.json)
CANONICAL_TOPICS = [
    "Cloud Concepts & Well-Architected",
    "Security, Identity & Compliance",
    "Compute & Containers",
    "Storage & Database",
    "Networking & Content Delivery",
    "Data, Analytics & Machine Learning",
    "Management, Governance & DevOps",
    "Billing, Cost Management & Support",
    "Application Integration & Serverless Architecture",
    "General / Otros Servicios",
]

# 1. Inicializar clientes de AWS
s3_client = boto3.client("s3")
rekognition_client = boto3.client("rekognition")  # <--- CAMBIO AQUÍ
bedrock_config = Config(
    retries={
        'max_attempts': 6,
        'mode': 'adaptive'
    }
)
bedrock_runtime = boto3.client('bedrock-runtime', config=bedrock_config)
dynamodb = boto3.resource("dynamodb")


def lambda_handler(event, context):
    for record in event["Records"]:
        try:
            body = json.loads(record["body"])

            # Validación de seguridad para TestEvents
            if "Records" not in body:
                print("Mensaje de prueba detectado. Saltando...")
                continue

            s3_event = body["Records"][0]
            bucket_name = s3_event["s3"]["bucket"]["name"]
            file_key = urllib.parse.unquote_plus(s3_event["s3"]["object"]["key"])

            etag = s3_event["s3"]["object"].get("eTag", "").strip('"')
            question_id = etag if etag else str(uuid.uuid4())

            print(f"Procesando con Rekognition: {file_key}")

            # 2. Llamar a Amazon Rekognition (Fallback de Textract)
            response_rekognition = rekognition_client.detect_text(
                Image={"S3Object": {"Bucket": bucket_name, "Name": file_key}}
            )

            # Extraer el texto detectado (Rekognition usa 'TextDetections')
            full_text = ""
            for item in response_rekognition["TextDetections"]:
                if (
                    item["Type"] == "LINE"
                ):  # Solo tomamos líneas completas para no repetir palabras
                    full_text += item["DetectedText"] + " "

            if not full_text:
                print("No se detectó texto en la imagen.")
                continue

            # 3. El Cerebro sigue siendo Bedrock
            print("Enviando texto a Amazon Bedrock...")
            prompt = f"""
You are an expert AWS Solutions Architect and mentor.
Analyze the following text extracted from an AWS certification exam question.
The original text may be in Portuguese, Spanish, or English — regardless of the
source language, you must translate and structure your entire response in English.

Original text:
"{full_text}"

Identify the question statement and its answer options. The question may have
between 4 and 6 options (label them A, B, C, D, and E/F if present — use only
the letters that actually appear in the text, do not invent extra options).

Determine how many correct answers this question requires. Look for phrases like
"Choose TWO", "Select THREE", "(Choose two.)" — if no such phrase appears, assume
it is a single-answer question. Mark exactly that many options as correct.

For each option, determine whether it is correct or incorrect and explain why.

IMPORTANT: For the "topic" field, you MUST use EXACTLY one of these 10 canonical
categories. Do NOT invent new topics. Map the question to the closest match:

- "Cloud Concepts & Well-Architected" — AWS Well-Architected Framework, Cloud Adoption Framework (CAF), Shared Responsibility Model, cloud economics, benefits of cloud computing
- "Security, Identity & Compliance" — IAM, WAF, GuardDuty, security services, DDoS protection, identity federation, compliance
- "Compute & Containers" — EC2 (instances, AMIs, purchasing options, storage, spot), ECS, EKS, Fargate, Lambda, serverless compute
- "Storage & Database" — S3, EBS, EFS, Storage Gateway, RDS, DynamoDB, database migration, NoSQL vs relational
- "Networking & Content Delivery" — VPC (subnets, NACLs, security groups, NAT), ELB, Route 53, CloudFront, edge computing, transit gateways
- "Data, Analytics & Machine Learning" — SageMaker, Athena, Kinesis, data lakes, machine learning services, analytics
- "Management, Governance & DevOps" — CloudFormation, CloudWatch, Systems Manager, multi-account governance, IaC, automation
- "Billing, Cost Management & Support" — Cost Explorer, Trusted Advisor, pricing models, cost optimization, support plans
- "Application Integration & Serverless Architecture" — Step Functions, SQS, SNS, EventBridge, API Gateway, AppSync, serverless orchestration
- "General / Otros Servicios" — if the question does not clearly fit any category above

Return strictly a JSON object with this exact structure, entirely in English:
{{
    "topic": "One of the 10 canonical categories listed above",
    "difficulty": "Difficulty level (Easy, Medium, Hard)",
    "question_text": "The full question statement, translated to English",
    "question_type": "single or multiple",
    "correct_count": "Number of options that are correct (integer, e.g. 1, 2, or 3)",
    "options": {{
        "A": {{
            "text": "Option A text, translated to English",
            "is_correct": true or false,
            "explanation": "Why this option is correct or incorrect, explained for a Junior student",
            "keywords": "2-3 AWS technical keywords associated with this option"
        }},
        "B": {{ ... same structure ... }},
        "C": {{ ... same structure ... }}
        (continue with D, E, F only if they exist in the original text)
    }}
}}
Do not include any text outside the JSON. Do not use markdown or code blocks.
"""

            native_request = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": prompt}]}
                ],
            }

            response_bedrock = bedrock_runtime.invoke_model(
                modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                body=json.dumps(native_request),
            )

            # Leer el texto de la IA
            response_body = json.loads(response_bedrock.get("body").read())
            ai_response_text = response_body["content"][0]["text"]

            print(f"RESPUESTA CRUDA DE LA IA: {ai_response_text}")

            # --- NUEVA LÓGICA DE LIMPIEZA ---
            # Esto quita los ```json del principio y los ``` del final
            clean_json = (
                ai_response_text.replace("```json", "").replace("```", "").strip()
            )

            # Ahora intentamos cargar el JSON limpio
            ai_data = json.loads(clean_json)
            # -------------------------------

            # Validación defensiva: asegurar que el topic esté en la taxonomía canónica
            topic = ai_data.get("topic", "")
            if topic not in CANONICAL_TOPICS:
                print(
                    f"Topic '{topic}' no es canónico. Reasignando a 'General / Otros Servicios'"
                )
                ai_data["topic"] = "General / Otros Servicios"

            # 4. Guardar en DynamoDB
            table = dynamodb.Table(TABLE_NAME)
            try:
                table.put_item(
                    Item={
                        "QuestionID": question_id,
                        "FileName": file_key,
                        "Topic": ai_data["topic"],
                        "Difficulty": ai_data["difficulty"],
                        "QuestionText": ai_data["question_text"],
                        "QuestionType": ai_data["question_type"],
                        "CorrectCount": int(ai_data["correct_count"]),
                        "Options": ai_data["options"],
                        "CreatedAt": datetime.now().isoformat(),
                    },
                    ConditionExpression="attribute_not_exists(QuestionID)",
                )
                print(f"Éxito total para: {file_key}")
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    print(f"Duplicado detectado, omitiendo: {file_key}")
                    continue
                raise

        except Exception as e:
            print(f"Error: {str(e)}")
            raise

    return {"statusCode": 200, "body": json.dumps("Procesado con Rekognition")}
