# Documentación Técnica — AI Mentoring

> Documentación interna del proyecto: arquitectura, decisiones técnicas, pruebas y changelog.
> Para documentación pública dirigida a reclutadores, ver `README.md` en la raíz del proyecto.

---

## Archivos de Documentación

| Archivo | Propósito | Cuándo actualizar |
|---------|-----------|-------------------|
| [architecture.md](architecture.md) | Arquitectura del sistema, modelo de datos, decisiones de diseño, conocimiento del proyecto | Cambios en servicios AWS, modelo de datos, decisiones técnicas |
| [technical-log.md](technical-log.md) | Pruebas de rendimiento, problemas detectados, soluciones aplicadas, métricas | Nuevas pruebas, problemas encontrados, soluciones implementadas |
| [changelog.md](changelog.md) | Log cronológico consolidado de todos los cambios significativos | Cada cambio relevante del proyecto (features, fixes, infra) |
| [roadmap.html](roadmap.html) | Roadmap visual del proyecto | Cambios en hitos o prioridades |

### Archivos de Referencia

| Archivo | Propósito |
|---------|-----------|
| `questions/` | Imágenes de preguntas de examen procesadas |

---

## Cómo Mantener la Documentación

### Regla General

**Cada cambio significativo debe documentarse en al menos un archivo:**

- **Cambio de infraestructura** → `architecture.md` + `changelog.md`
- **Cambio de código Lambda** → `technical-log.md` + `changelog.md`
- **Bug fix importante** → `changelog.md`
- **Prueba de rendimiento** → `technical-log.md`
- **Decisión técnica** → `architecture.md`

### Formato Esperado

#### Entrada en `changelog.md`

```markdown
### YYYY-MM-DD — Título descriptivo
- Cambio principal (PR #XX)
- Archivos modificados: `archivo1.py`, `archivo2.tf`
- Detallesrelevantes (opcional)
```

#### Sección en `technical-log.md`

```markdown
## Nombre de la Prueba o Problema — Fecha

### Contexto
Breve descripción del por qué se hizo esta prueba o se detectó este problema.

### Métricas / Resultados
| Métrica | Valor |
|---------|-------|
| ... | ... |

### Análisis
Qué significan los resultados y qué se decidió hacer.
```

#### Sección en `architecture.md`

```markdown
## Nombre del Componente o Decisión

### Descripción
Qué es y para qué sirve.

### Configuración Actual
Detalles técnicos relevantes.

### Decisión Técnica
Por qué se implementó así y no de otra manera.
```

---

## Estructura del Proyecto (Referencia Rápida)

```
AI_Mentoring/
├── src/
│   ├── processor.py              # Lambda: OCR + Bedrock + DynamoDB
│   ├── student_api.py            # Lambda: CRUD de estudiantes + cohortes
│   ├── quiz_engine.py            # Lambda: quizzes y resultados
│   └── frontend/                 # Frontend (HTML/JS)
│       ├── index.html
│       ├── dashboard.html
│       ├── quiz.html
│       ├── results.html
│       └── js/
├── *.tf                          # Terraform (20 archivos)
├── .opencode/                    # Configuración OpenCode
├── doc/                          # Esta documentación
├── scripts/                      # Scripts de utilería
├── events/                       # Eventos de prueba API Gateway
└── README.md                     # Documentación pública
```

---

## Servicios AWS en Uso

| Servicio | Propósito | Archivo Terraform principal |
|----------|-----------|------------------------------|
| S3 | Bucket de fotos de examen | `main.tf` |
| SQS | Cola de ingesta + DLQ | `main.tf` |
| SNS | Notificaciones por email | `main.tf` |
| Lambda | 3 handlers (processor, student_api, quiz_engine) | `lambda.tf`, `lambda_student_api.tf`, `lambda_quiz_engine.tf` |
| DynamoDB | 5 tablas (MentoringQuestions, Students, Quizzes, QuizResults, Cohorts) | `dynamodb*.tf` |
| Bedrock | Claude Haiku 4.5 para clasificación | (invocado desde `processor.py`) |
| Rekognition | OCR de fotos | (invocado desde `processor.py`) |
| API Gateway | HTTP API con JWT Authorizer | `api_gateway*.tf` |
| Cognito | Autenticación de alumnos | `cognito.tf` |
| Amplify | Hosting del frontend | `amplify.tf` |
| IAM | Roles y políticas | `iam.tf`, `iam_student_api.tf` |
| CloudFront | CDN (legacy, pendiente de limpieza) | `frontend.tf` |

---

## Notas para Agentes de IA

Al trabajar en este proyecto, los agentes de IA deben:

1. **Consultar `architecture.md`** antes de proponer cambios de infraestructura
2. **Consultar `technical-log.md`** antes de modificar el pipeline de procesamiento
3. **Consultar `changelog.md`** para entender el contexto de cambios anteriores
4. **Documentar cada cambio significativo** en el archivo correspondiente
5. **Seguir el formato** definido en esta sección

Para más reglas, ver `AGENTS.md` en la raíz del proyecto.
