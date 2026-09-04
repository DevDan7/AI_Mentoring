"""Pruebas de verificación del pipeline multimodal de processor.py (sin Rekognition).

Usa unicamente la stdlib (unittest.mock), sin dependencias adicionales.
No ejecuta llamadas reales a AWS: todos los clientes Boto3 se mockean.
"""
import base64
import hashlib
import json
import unittest
from unittest import mock

import processor


def make_event(key="pregunta.png", etag=None):
    if etag is None:
        etag = hashlib.sha256(key.encode()).hexdigest()[:16]
    return {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "Records": [
                            {
                                "s3": {
                                    "bucket": {"name": "fotos"},
                                    "object": {"key": key, "eTag": etag},
                                }
                            }
                        ]
                    }
                )
            }
        ]
    }


class FakeBody:
    """Simula response['body'] con .read()."""

    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text


def make_bedrock_response(raw_text):
    return {"body": FakeBody(json.dumps({"content": [{"text": raw_text}]}).encode())}


def make_valid_json():
    return json.dumps(
        {
            "topic": "Compute & Containers",
            "difficulty": "Medium",
            "question_text": "Which AWS service runs containers?",
            "question_type": "single",
            "correct_count": 1,
            "options": {
                "A": {"text": "EC2", "is_correct": False, "explanation": "x", "keywords": "vm"},
                "B": {"text": "ECS", "is_correct": True, "explanation": "y", "keywords": "containers"},
            },
        }
    )


class TestProcessorMultimodal(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    @mock.patch("processor.dynamodb")
    @mock.patch("processor.bedrock_runtime")
    @mock.patch("processor.s3_client")
    def test_usa_bedrock_y_no_rekognition(self, s3_client, bedrock_runtime, dynamodb):
        img_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00\x01" * 50
        s3_client.get_object.return_value = {"Body": FakeBody(img_bytes)}
        bedrock_runtime.invoke_model.return_value = make_bedrock_response(make_valid_json())

        table = mock.MagicMock()
        table.query.return_value = {"Items": []}
        dynamodb.Table.return_value = table

        result = processor.lambda_handler(make_event("pregunta.png", etag="abc123"), None)

        self.assertEqual(result["statusCode"], 200)
        # No debe usarse Rekognition
        self.assertFalse(hasattr(processor, "rekognition_client"))

        # El request a Bedrock debe ser multimodal (incluye bloque image base64)
        called_body = bedrock_runtime.invoke_model.call_args.kwargs["body"]
        native_request = json.loads(called_body)
        content = native_request["messages"][0]["content"]

        image_block = next(c for c in content if c["type"] == "image")
        self.assertEqual(image_block["source"]["type"], "base64")
        self.assertEqual(image_block["source"]["media_type"], "image/png")
        self.assertEqual(
            image_block["source"]["data"], base64.b64encode(img_bytes).decode()
        )
        self.assertTrue(any(c["type"] == "text" for c in content))

        # Verificar que se guardó en DynamoDB con la estructura esperada
        table.put_item.assert_called_once()
        item = table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["QuestionID"], "abc123")
        self.assertEqual(item["Topic"], "Compute & Containers")
        self.assertEqual(item["QuestionText"], "Which AWS service runs containers?")
        self.assertEqual(item["CorrectCount"], 1)
        self.assertIn("ContentHash", item)
        self.assertEqual(
            table.put_item.call_args.kwargs.get("ConditionExpression"),
            "attribute_not_exists(QuestionID)",
        )

    @mock.patch("processor.dynamodb")
    @mock.patch("processor.bedrock_runtime")
    @mock.patch("processor.s3_client")
    def test_imagen_jpg_usa_media_type_jpeg(self, s3_client, bedrock_runtime, dynamodb):
        img_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 30
        s3_client.get_object.return_value = {"Body": FakeBody(img_bytes)}
        bedrock_runtime.invoke_model.return_value = make_bedrock_response(make_valid_json())
        dynamodb.Table.return_value = mock.MagicMock()

        processor.lambda_handler(make_event("pregunta.jpg"), None)

        native_request = json.loads(bedrock_runtime.invoke_model.call_args.kwargs["body"])
        content = native_request["messages"][0]["content"]
        image_block = next(c for c in content if c["type"] == "image")
        self.assertEqual(image_block["source"]["media_type"], "image/jpeg")

    @mock.patch("processor.dynamodb")
    @mock.patch("processor.bedrock_runtime")
    @mock.patch("processor.s3_client")
    def test_respuesta_no_json_se_descarta(self, s3_client, bedrock_runtime, dynamodb):
        s3_client.get_object.return_value = {"Body": FakeBody(b"pngdata")}
        bedrock_runtime.invoke_model.return_value = make_bedrock_response("esto no es json")
        table = mock.MagicMock()
        dynamodb.Table.return_value = table

        result = processor.lambda_handler(make_event("pregunta.png"), None)

        self.assertEqual(result["statusCode"], 200)
        # No debe guardarse nada y el mensaje no va a DLQ (no se lanza excepción)
        table.put_item.assert_not_called()

    @mock.patch("processor.dynamodb")
    @mock.patch("processor.bedrock_runtime")
    @mock.patch("processor.s3_client")
    def test_respuesta_sin_pregunta_u_opciones_se_descarta(self, s3_client, bedrock_runtime, dynamodb):
        s3_client.get_object.return_value = {"Body": FakeBody(b"pngdata")}
        bedrock_runtime.invoke_model.return_value = make_bedrock_response(
            json.dumps({"topic": "Billing, Cost Management & Support"})
        )
        table = mock.MagicMock()
        dynamodb.Table.return_value = table

        result = processor.lambda_handler(make_event("pregunta.png"), None)

        self.assertEqual(result["statusCode"], 200)
        table.put_item.assert_not_called()

    @mock.patch("processor.dynamodb")
    @mock.patch("processor.bedrock_runtime")
    @mock.patch("processor.s3_client")
    def test_topic_no_canonico_se_reasigna(self, s3_client, bedrock_runtime, dynamodb):
        s3_client.get_object.return_value = {"Body": FakeBody(b"pngdata")}
        raw = make_valid_json().replace('"Compute & Containers"', '"Inventado X"')
        bedrock_runtime.invoke_model.return_value = make_bedrock_response(raw)
        table = mock.MagicMock()
        table.query.return_value = {"Items": []}
        dynamodb.Table.return_value = table

        processor.lambda_handler(make_event("pregunta.png"), None)

        item = table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["Topic"], "General / Otros Servicios")

    def test_content_hash_estable_para_mismo_texto(self):
        h1 = processor.content_hash("Which AWS service runs containers?")
        h2 = processor.content_hash("Which AWS service runs containers?")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)  # sha256 hexdigest

    def test_content_hash_ignora_mayusculas_acentos_y_puntuacion(self):
        h1 = processor.content_hash("Cuál servicio ejecuta contenedores?")
        h2 = processor.content_hash("Cual servicio ejecuta contenedores")
        self.assertEqual(h1, h2)

    @mock.patch("processor.SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123:topic")
    @mock.patch("processor.sns_client")
    @mock.patch("processor.dynamodb")
    @mock.patch("processor.bedrock_runtime")
    @mock.patch("processor.s3_client")
    def test_imagen_no_procesable_publica_sns(
        self, s3_client, bedrock_runtime, dynamodb, sns_client
    ):
        s3_client.get_object.return_value = {"Body": FakeBody(b"pngdata")}
        bedrock_runtime.invoke_model.return_value = make_bedrock_response("no es json")
        dynamodb.Table.return_value = mock.MagicMock()

        result = processor.lambda_handler(make_event("pregunta.png"), None)

        self.assertEqual(result["statusCode"], 200)
        sns_client.publish.assert_called_once()
        kwargs = sns_client.publish.call_args.kwargs
        self.assertEqual(kwargs["TopicArn"], "arn:aws:sns:us-east-1:123:topic")
        self.assertIn("pregunta.png", kwargs["Message"])

    @mock.patch("processor.SNS_TOPIC_ARN", "")
    @mock.patch("processor.sns_client")
    @mock.patch("processor.dynamodb")
    @mock.patch("processor.bedrock_runtime")
    @mock.patch("processor.s3_client")
    def test_sin_sns_topic_arn_no_publica(
        self, s3_client, bedrock_runtime, dynamodb, sns_client
    ):
        s3_client.get_object.return_value = {"Body": FakeBody(b"pngdata")}
        bedrock_runtime.invoke_model.return_value = make_bedrock_response("no es json")
        dynamodb.Table.return_value = mock.MagicMock()

        processor.lambda_handler(make_event("pregunta.png"), None)

        sns_client.publish.assert_not_called()

    @mock.patch("processor.dynamodb")
    @mock.patch("processor.bedrock_runtime")
    @mock.patch("processor.s3_client")
    def test_duplicado_por_contenido_se_omite(
        self, s3_client, bedrock_runtime, dynamodb
    ):
        s3_client.get_object.return_value = {"Body": FakeBody(b"pngdata")}
        bedrock_runtime.invoke_model.return_value = make_bedrock_response(make_valid_json())
        table = mock.MagicMock()
        dynamodb.Table.return_value = table

        # Primera llamada: query retorna vacio (no duplicado) -> put_item se ejecuta
        table.query.return_value = {"Items": []}
        processor.lambda_handler(make_event("foto1.png"), None)
        self.assertEqual(table.put_item.call_count, 1)
        first_item = table.put_item.call_args.kwargs["Item"]

        # Segunda llamada: query retorna un item (duplicado) -> put_item NO se ejecuta
        table.query.return_value = {"Items": [{"ContentHash": first_item["ContentHash"]}]}
        table.put_item.reset_mock()
        processor.lambda_handler(make_event("foto2.png"), None)
        table.put_item.assert_not_called()

        # Mismo ContentHash, distinto QuestionID
        self.assertNotEqual(
            make_event("foto1.png")["Records"][0]["body"],
            make_event("foto2.png")["Records"][0]["body"],
        )

    @mock.patch("processor.dynamodb")
    @mock.patch("processor.bedrock_runtime")
    @mock.patch("processor.s3_client")
    def test_mismo_contenido_da_mismo_content_hash(
        self, s3_client, bedrock_runtime, dynamodb
    ):
        s3_client.get_object.return_value = {"Body": FakeBody(b"pngdata")}
        bedrock_runtime.invoke_model.return_value = make_bedrock_response(make_valid_json())
        table = mock.MagicMock()
        table.query.return_value = {"Items": []}
        dynamodb.Table.return_value = table

        processor.lambda_handler(make_event("foto1.png"), None)
        first_item = table.put_item.call_args.kwargs["Item"]

        table.put_item.reset_mock()
        processor.lambda_handler(make_event("foto2.png"), None)
        second_item = table.put_item.call_args.kwargs["Item"]

        # Distinto archivo => distinto QuestionID, pero mismo ContentHash (misma pregunta)
        self.assertNotEqual(first_item["QuestionID"], second_item["QuestionID"])
        self.assertEqual(first_item["ContentHash"], second_item["ContentHash"])


if __name__ == "__main__":
    unittest.main()
