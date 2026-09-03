import base64
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

            print(f"Procesando imagen con Bedrock multimodal: {file_key}")

            # 2. Leer la imagen directamente desde S3 y codificarla en base64
            image_response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
            image_bytes = image_response["Body"].read()

            extension = file_key.lower().rsplit(".", 1)[-1] if "." in file_key else ""
            media_type = "image/png" if extension == "png" else "image/jpeg"
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

            print(f"Imagen cargada: {len(image_bytes)} bytes ({media_type})")

            # 3. El Cerebro sigue siendo Bedrock (multimodal)
            print("Enviando imagen a Amazon Bedrock...")
            prompt = f"""
You are an expert AWS Solutions Architect and mentor.
Analyze the attached image of an AWS certification exam question.
Look at the whole image: the question statement, its answer options, and any
diagram, table, or figure included.
The original text may be in Portuguese, Spanish, or English — regardless of the
source language, you must translate and structure your entire response in English.

Identify the question statement and its answer options. The question may have
between 4 and 6 options (label them A, B, C, D, and E/F if present — use only
the letters that actually appear in the image, do not invent extra options).

If the image contains a diagram, table, or figure that is relevant to answering
the question, describe it within the explanation of the associated option(s).

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
                "max_tokens": 1500,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_base64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
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

            # --- LÓGICA DE LIMPIEZA ---
            # Esto quita los ```json del principio y los ``` del final
            clean_json = (
                ai_response_text.replace("```json", "").replace("```", "").strip()
            )

            # Ahora intentamos cargar el JSON limpio
            try:
                ai_data = json.loads(clean_json)
            except ValueError:
                print(f"No se pudo analizar la respuesta para: {file_key}")
                continue

            # Validación de contenido utilizable: sin enunciado o sin opciones => descartar
            if not ai_data.get("question_text") or not ai_data.get("options"):
                print(f"Imagen no procesable (sin pregunta/opciones válidas): {file_key}")
                continue
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

    return {"statusCode": 200, "body": json.dumps("Procesado con Bedrock multimodal")}
