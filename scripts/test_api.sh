#!/bin/bash
set -e

API_URL="https://9ftb5bwpk7.execute-api.us-east-1.amazonaws.com"
COGNITO_URL="https://cognito-idp.us-east-1.amazonaws.com"
CLIENT_ID="m5dcqn9lld9l5vhb8fhug4i80"
USER_EMAIL="danielsvillegas17@gmail.com"
USER_PASS="Test1234!"

echo "=== Paso 1: Obtener IdToken de Cognito ==="
TOKEN=$(curl -s -X POST $COGNITO_URL \
  -H "Content-Type: application/x-amz-json-1.1" \
  -H "X-Amz-Target: AWSCognitoIdentityProviderService.InitiateAuth" \
  -d "{
    \"AuthFlow\": \"USER_PASSWORD_AUTH\",
    \"ClientId\": \"$CLIENT_ID\",
    \"AuthParameters\": {
      \"USERNAME\": \"$USER_EMAIL\",
      \"PASSWORD\": \"$USER_PASS\"
    }
  }" | jq -r '.AuthenticationResult.IdToken') # <-- CORREGIDO: IdToken

if [ "$TOKEN" = "null" ] || [ -z "$TOKEN" ]; then
  echo "ERROR: No se pudo obtener el IdToken de Cognito"
  exit 1
fi
echo "IdToken obtenido exitosamente: ${TOKEN:0:25}..."

echo ""
echo "=== Paso 2: Crear perfil de alumno (POST /students) ==="
curl -s -X POST "$API_URL/students" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cohort": "AWS-2026-Q3"
  }' | jq .

echo ""
echo "=== Paso 3: Obtener perfil autenticado (GET /students/me) ==="
curl -s "$API_URL/students/me" \
  -H "Authorization: Bearer $TOKEN" | jq .

echo ""
echo "=== Paso 4: Actualizar alumno (PUT /students/me) ==="
curl -s -X PUT "$API_URL/students/me" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cohort": "AWS-2026-Q4"
  }' | jq .

echo ""
echo "=== Paso 5: Generar quiz (POST /quizzes/generate) ==="
QUIZ_RESPONSE=$(curl -s -X POST "$API_URL/quizzes/generate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "AWS Well-Architected Framework",
    "count": 3
  }')
echo "$QUIZ_RESPONSE" | jq .

QUIZ_ID=$(echo "$QUIZ_RESPONSE" | jq -r '.quiz_id')
FIRST_QUESTION_ID=$(echo "$QUIZ_RESPONSE" | jq -r '.questions[0].question_id // "test-question-001"')
echo "Quiz ID generado: $QUIZ_ID"
echo "Primer Question ID: $FIRST_QUESTION_ID"

echo ""
echo "=== Paso 6: Enviar respuesta calculada en backend (POST /quizzes/submit) ==="
curl -s -X POST "$API_URL/quizzes/submit" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"quiz_id\": \"$QUIZ_ID\",
    \"question_id\": \"$FIRST_QUESTION_ID\",
    \"given_answers\": [\"A\"]
  }" | jq . # <-- CORREGIDO: Se elimina is_correct

echo ""
echo "=== Paso 7: Obtener resultados del quiz (GET /quizzes/{quizId}/results) ==="
curl -s "$API_URL/quizzes/$QUIZ_ID/results" \
  -H "Authorization: Bearer $TOKEN" | jq .

echo ""
echo "=== Testing End-to-End completado con éxito ==="