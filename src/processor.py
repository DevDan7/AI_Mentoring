import json
import boto3
import os
import urllib.parse
import uuid
from datetime import datetime

# 1. Inicializar clientes de AWS
s3_client = boto3.client('s3')
rekognition_client = boto3.client('rekognition') # <--- CAMBIO AQUÍ
bedrock_runtime = boto3.client('bedrock-runtime')
dynamodb = boto3.resource('dynamodb')

TABLE_NAME = os.environ.get('TABLE_NAME', 'MentoringQuestions')

def lambda_handler(event, context):
    for record in event['Records']:
        try:
            body = json.loads(record['body'])
            
            # Validación de seguridad para TestEvents
            if 'Records' not in body:
                print("Mensaje de prueba detectado. Saltando...")
                continue
            
            s3_event = body['Records'][0]
            bucket_name = s3_event['s3']['bucket']['name']
            file_key = urllib.parse.unquote_plus(s3_event['s3']['object']['key'])
            
            print(f"Procesando con Rekognition: {file_key}")

            # 2. Llamar a Amazon Rekognition (Fallback de Textract)
            response_rekognition = rekognition_client.detect_text(
                Image={
                    'S3Object': {
                        'Bucket': bucket_name,
                        'Name': file_key
                    }
                }
            )

            # Extraer el texto detectado (Rekognition usa 'TextDetections')
            full_text = ""
            for item in response_rekognition['TextDetections']:
                if item['Type'] == 'LINE': # Solo tomamos líneas completas para no repetir palabras
                    full_text += item['DetectedText'] + " "
            
            if not full_text:
                print("No se detectó texto en la imagen.")
                continue

            # 3. El Cerebro sigue siendo Bedrock
            print("Enviando texto a Amazon Bedrock...")
            prompt = f"""
            Actúa como un Arquitecto de Soluciones AWS experto y mentor.
            Analiza el siguiente texto extraído de una pregunta de examen:
            "{full_text}"

            Tu tarea es devolver estrictamente un objeto JSON con la siguiente estructura:
            {{
                "topic": "El servicio o concepto principal de AWS (ej: VPC, S3, IAM, EC2)",
                "explanation": "Una explicación clara y educativa de por qué la respuesta es correcta para un alumno Junior",
                "difficulty": "Nivel de dificultad (Fácil, Medio, Difícil)"
            }}
            No incluyas texto adicional fuera del JSON.
            """

            native_request = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            }

            response_bedrock = bedrock_runtime.invoke_model(
                modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                body=json.dumps(native_request)
            )

            # Leer el texto de la IA
            response_body = json.loads(response_bedrock.get("body").read())
            ai_response_text = response_body["content"][0]["text"]
            
            print(f"RESPUESTA CRUDA DE LA IA: {ai_response_text}")

            # --- NUEVA LÓGICA DE LIMPIEZA ---
            # Esto quita los ```json del principio y los ``` del final
            clean_json = ai_response_text.replace("```json", "").replace("```", "").strip()
            
            # Ahora intentamos cargar el JSON limpio
            ai_data = json.loads(clean_json)
            # -------------------------------
            

            # 4. Guardar en DynamoDB
            table = dynamodb.Table(TABLE_NAME)
            table.put_item(
                Item={
                    'QuestionID': str(uuid.uuid4()),
                    'FileName': file_key,
                    'Topic': ai_data['topic'],
                    'Explanation': ai_data['explanation'],
                    'Difficulty': ai_data['difficulty'],
                    'CreatedAt': datetime.now().isoformat()
                }
            )
            print(f"Éxito total para: {file_key}")

        except Exception as e:
            print(f"Error: {str(e)}")
            raise 

    return {'statusCode': 200, 'body': json.dumps('Procesado con Rekognition')}