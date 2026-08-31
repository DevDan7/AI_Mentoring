# =============================================================================
# Integrations
# =============================================================================

resource "aws_apigatewayv2_integration" "student" {
  api_id                 = aws_apigatewayv2_api.mentoring_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.student_api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_integration" "quiz" {
  api_id                 = aws_apigatewayv2_api.mentoring_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.quiz_engine.invoke_arn
  payload_format_version = "2.0"
}

# =============================================================================
# Student API Routes
# =============================================================================

resource "aws_apigatewayv2_route" "students_post" {
  api_id             = aws_apigatewayv2_api.mentoring_api.id
  route_key          = "POST /students"
  target             = "integrations/${aws_apigatewayv2_integration.student.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "students_me_get" {
  api_id             = aws_apigatewayv2_api.mentoring_api.id
  route_key          = "GET /students/me"
  target             = "integrations/${aws_apigatewayv2_integration.student.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "students_me_put" {
  api_id             = aws_apigatewayv2_api.mentoring_api.id
  route_key          = "PUT /students/me"
  target             = "integrations/${aws_apigatewayv2_integration.student.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "students_get_by_id" {
  api_id             = aws_apigatewayv2_api.mentoring_api.id
  route_key          = "GET /students/{studentId}"
  target             = "integrations/${aws_apigatewayv2_integration.student.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

# =============================================================================
# Quiz Engine Routes
# =============================================================================

resource "aws_apigatewayv2_route" "quizzes_generate" {
  api_id             = aws_apigatewayv2_api.mentoring_api.id
  route_key          = "POST /quizzes/generate"
  target             = "integrations/${aws_apigatewayv2_integration.quiz.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "quizzes_submit" {
  api_id             = aws_apigatewayv2_api.mentoring_api.id
  route_key          = "POST /quizzes/submit"
  target             = "integrations/${aws_apigatewayv2_integration.quiz.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "quizzes_results" {
  api_id             = aws_apigatewayv2_api.mentoring_api.id
  route_key          = "GET /quizzes/{quizId}/results"
  target             = "integrations/${aws_apigatewayv2_integration.quiz.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "quizzes_get" {
  api_id             = aws_apigatewayv2_api.mentoring_api.id
  route_key          = "GET /quizzes/{quizId}"
  target             = "integrations/${aws_apigatewayv2_integration.quiz.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

resource "aws_apigatewayv2_route" "quizzes_complete" {
  api_id             = aws_apigatewayv2_api.mentoring_api.id
  route_key          = "POST /quizzes/{quizId}/complete"
  target             = "integrations/${aws_apigatewayv2_integration.quiz.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
  authorization_type = "JWT"
}

# =============================================================================
# Lambda Permissions
# =============================================================================

resource "aws_lambda_permission" "api_gateway_student" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.student_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.mentoring_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_gateway_quiz" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.quiz_engine.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.mentoring_api.execution_arn}/*/*"
}
