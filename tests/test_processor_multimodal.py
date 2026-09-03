"""Pruebas de verificación del pipeline multimodal de processor.py (sin Rekognition).

Usa unicamente la stdlib (unittest.mock), sin dependencias adicionales.
No ejecuta llamadas reales a AWS: todos los clientes Boto3 se mockean.
"""
import base64
import json
import unittest
from unittest import mock

import processor


def make_event(key="pregunta.png"):
    return {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "Records": [
                            {
                                "s3": {
                                    "bucket": {"name": "fotos"},
                                    "object": {"key": key, "eTag": "abc123"},
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
        dynamodb.Table.return_value = table

        result = processor.lambda_handler(make_event("pregunta.png"), None)

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
        dynamodb.Table.return_value = table

        processor.lambda_handler(make_event("pregunta.png"), None)

        item = table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["Topic"], "General / Otros Servicios")


if __name__ == "__main__":
    unittest.main()
