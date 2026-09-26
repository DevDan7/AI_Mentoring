// ========== INTERNACIONALIZACIÓN (PT-BR / EN) ==========
// Se carga como primer <script> al final del <body>: el DOM estático ya existe,
// así que las traducciones se aplican de inmediato, antes del JS de cada página.
// Contenido de la BD (enunciados, opciones, explicaciones) y mensajes del backend
// no se traducen.

const I18N = {
    pt: {
        // Común
        "common.logout": "Sair",
        "common.back": "Voltar",
        "common.backToDashboard": "Voltar ao Painel",
        "common.langSwitch": "Idioma",
        "common.connectionError": "Erro de conexão. Verifique sua internet e tente novamente.",
        "common.httpError": "Erro {status}",
        "common.configError": "Não foi possível carregar a configuração. Verifique sua conexão com a internet.",
        "common.question": "Pergunta",

        // Fases / estados / tipos de simulado
        "phase.initial": "Diagnóstico",
        "phase.free_practice": "Prática livre",
        "phase.final_exam": "Exame final",
        "status.completed": "Concluído",
        "status.in_progress": "Em andamento",
        "quizType.initial": "Diagnóstico",
        "quizType.free": "Simulado Livre",
        "quizType.final_exam": "Exame Final",

        // Login / registro (index.html)
        "login.pageTitle": "AI Mentoring - Entrar",
        "login.subtitle": "Plataforma de Simulados e MENTORIA AWS",
        "login.email": "E-mail",
        "login.emailPlaceholder": "seu-email@exemplo.com",
        "login.password": "Senha",
        "login.submit": "Entrar",
        "login.forgot": "Esqueceu sua senha?",
        "login.noAccount": "Não tem conta?",
        "login.registerHere": "Registre-se aqui",
        "login.showPassword": "Mostrar senha",
        "login.hidePassword": "Ocultar senha",
        "register.name": "Nome Completo",
        "register.namePlaceholder": "Seu nome",
        "register.passwordPlaceholder": "Mínimo 8 caracteres",
        "register.passwordHint": "Mínimo 8 caracteres, uma maiúscula e um número",
        "register.submit": "Criar Conta",
        "register.haveAccount": "Já tem conta?",
        "register.loginHere": "Entre aqui",
        "register.passwordInvalid": "A senha deve ter no mínimo 8 caracteres, uma maiúscula e um número.",
        "register.cohortFull": "Turma lotada. Entre em contato com o professor para verificar vagas.",
        "confirm.sentTo": "Enviamos um código de verificação para",
        "confirm.instructions": ". Insira o código para confirmar sua conta.",
        "confirm.code": "Código de Verificação",
        "confirm.submit": "Confirmar Conta",
        "confirm.resend": "Reenviar código",
        "confirm.backToLogin": "Voltar ao login",
        "confirm.success": "Conta confirmada! Agora faça login.",
        "confirm.resent": "Código reenviado. Verifique seu e-mail.",
        "forgot.instructions": "Insira seu e-mail e enviaremos um código para redefinir sua senha.",
        "forgot.submit": "Enviar Código",
        "reset.sentTo": "Insira o código enviado para",
        "reset.instructions": "e sua nova senha.",
        "reset.newPassword": "Nova Senha",
        "reset.submit": "Redefinir Senha",
        "reset.success": "Senha atualizada! Agora faça login.",

        // Errores de Cognito (auth.js)
        "auth.err.login": "Erro ao fazer login",
        "auth.err.emailExists": "Este e-mail já está registrado. Tente fazer login.",
        "auth.err.passwordPolicy": "A senha não atende aos requisitos. Mínimo 8 caracteres, uma maiúscula e um número.",
        "auth.err.invalidParams": "Dados inválidos. Verifique seu e-mail e senha.",
        "auth.err.tooManyAttempts": "Muitas tentativas. Aguarde alguns minutos.",
        "auth.err.tooManyRequests": "Muitas solicitações. Tente mais tarde.",
        "auth.err.signUp": "Erro ao criar a conta",
        "auth.err.codeMismatch": "Código incorreto. Tente novamente.",
        "auth.err.codeExpired": "O código expirou. Solicite um novo.",
        "auth.err.confirm": "Erro ao confirmar a conta",
        "auth.err.resend": "Erro ao reenviar o código",
        "auth.err.userNotFound": "Não existe uma conta com este e-mail.",
        "auth.err.invalidEmail": "Formato de e-mail inválido.",
        "auth.err.forgot": "Erro ao enviar código de recuperação",
        "auth.err.reset": "Erro ao redefinir a senha",

        // Dashboard del alumno
        "dash.pageTitle": "AI Mentoring - Painel",
        "dash.loadingProfile": "Carregando perfil...",
        "dash.profileTitle": "Perfil do Aluno",
        "dash.email": "E-mail:",
        "dash.cohort": "Turma:",
        "dash.defaultName": "Aluno",
        "dash.noCohort": "Sem turma",
        "dash.initialTitle": "Você ainda não realizou seu diagnóstico inicial",
        "dash.initialText": "O diagnóstico inicial ajuda a conhecer seu ponto de partida na preparação para o AWS Cloud Practitioner.",
        "dash.initialBtn": "Fazer Diagnóstico Inicial",
        "dash.resumeTitle": "Você tem um exame final em progresso",
        "dash.resumeText": "Retome de onde parou para não perder as respostas já enviadas.",
        "dash.resumeBtn": "Retomar Exame Final",
        "dash.finalTitle": "Exame Final de Certificação",
        "dash.loading": "Carregando...",
        "dash.finalStart": "Iniciar Exame Final",
        "dash.finalDone": "Exame final já realizado. Entre em contato com seu instrutor para um novo intento.",
        "dash.finalLocked": "Bloqueado pelo professor.",
        "dash.finalLockedUntil": "Bloqueado pelo professor (disponível a partir de {date}).",
        "dash.finalAvailable": "Disponível",
        "dash.newQuizTitle": "Gerar Novo Simulado",
        "dash.topic": "Tema de Certificação AWS",
        "dash.topicGeneral": "General / Outros Serviços",
        "dash.questionCount": "Quantidade de Perguntas",
        "dash.startQuiz": "Iniciar Simulado",
        "dash.historyTitle": "Histórico de Simulados",
        "dash.loadingHistory": "Carregando histórico...",
        "dash.noHistory": "Nenhum simulado realizado ainda.",
        "dash.historyError": "Erro ao carregar histórico.",
        "dash.col.type": "Tipo",
        "dash.col.topic": "Tema",
        "dash.col.status": "Status",
        "dash.col.score": "Score",
        "dash.col.date": "Data",
        "dash.err.profile": "Erro ao carregar perfil: ",
        "dash.err.history": "Erro ao carregar histórico: ",
        "dash.err.initial": "Erro ao gerar diagnóstico: ",

        // Quiz
        "quiz.pageTitle": "AI Mentoring - Simulado",
        "quiz.loading": "Carregando perguntas...",
        "quiz.topic": "Tema:",
        "quiz.question": "Pergunta:",
        "quiz.answered": "Respondidas:",
        "quiz.answeredProgress": "{done} de {total} respondidas",
        "quiz.initialTopic": "Diagnóstico Inicial",
        "quiz.multiple": " (Seleção múltipla)",
        "quiz.submit": "Confirmar Resposta",
        "quiz.next": "Próxima Pergunta",
        "quiz.correct": "Correto!",
        "quiz.incorrect": "Incorreto.",
        "quiz.completedTitle": "Simulado Concluído 🎉",
        "quiz.completedText": "Você respondeu todas as perguntas com sucesso.",
        "quiz.initialCompletedTitle": "Diagnóstico Concluído 🎉",
        "quiz.initialCompletedText": "Diagnóstico concluído! Agora conhecemos seu ponto de partida.",
        "quiz.viewResults": "Ver Resultados",
        "quiz.err.submit": "Erro ao enviar resposta: ",

        // Resultados
        "results.pageTitle": "AI Mentoring - Resultados",
        "results.loading": "Carregando resultados...",
        "results.error": "Erro",
        "results.loadError": "Não foi possível carregar os resultados.",
        "results.summary": "Resumo do Simulado",
        "results.score": "Pontuação Final",
        "results.correctCount": "Corretas",
        "results.total": "Total de Perguntas",
        "results.domainTitle": "Desempenho por Domínio",
        "results.col.domain": "Domínio",
        "results.col.correct": "Corretas",
        "results.col.total": "Total",
        "results.answersTitle": "Detalhamento das Respostas",
        "results.retake": "Realizar Outro Simulado",
        "results.noQuizId": "Não foi encontrado um ID de simulado válido.",
        "results.noAnswers": "Não há respostas registradas para este simulado.",
        "results.correct": "Correta ✅",
        "results.incorrect": "Incorreta ❌",
        "results.statement": "Enunciado:",
        "results.given": "Resposta enviada:",
        "results.expected": "Resposta correta:",
        "results.explanation": "Explicação:",
        "explanation.general": "Explicação geral",
        "explanation.otherOptions": "Outras opções e por que não são as melhores",

        // Panel del profesor
        "teacher.pageTitle": "AI Mentoring - Painel do Professor",
        "teacher.role": "Professor",
        "teacher.kpis": "Indicadores",
        "teacher.kpiTotal": "Total de Alunos",
        "teacher.kpiInitial": "Diagnóstico",
        "teacher.kpiFree": "Prática Livre",
        "teacher.kpiFinal": "Exame Final",
        "teacher.students": "Alunos",
        "teacher.cohort": "Turma",
        "teacher.all": "Todas",
        "teacher.allCohorts": "Todas as turmas",
        "teacher.search": "Buscar nome ou e-mail",
        "teacher.col.name": "Nome",
        "teacher.col.email": "Email",
        "teacher.col.cohort": "Turma",
        "teacher.col.phase": "Fase Atual",
        "teacher.col.finalExam": "Exame Final",
        "teacher.col.actions": "Ações",
        "teacher.historyTitle": "Histórico do Aluno",
        "teacher.close": "Fechar",
        "teacher.col.typeTopic": "Tipo / Tema",
        "teacher.col.details": "Detalhes",
        "teacher.cohortsTitle": "Turmas",
        "teacher.col.cohortName": "Nome",
        "teacher.col.students": "Alunos",
        "teacher.col.max": "Máximo",
        "teacher.btn.history": "Historial",
        "teacher.btn.setExam": "Configurar data",
        "teacher.btn.resetExam": "Resetar tentativa",
        "teacher.notConfigured": "Não configurada",
        "teacher.attempts": "{count} tentativa(s)",
        "teacher.noQuizzes": "Nenhum quiz realizado ainda.",
        "teacher.viewDetails": "Ver detalhes",
        "teacher.promptDate": "Data de liberação do exame final (YYYY-MM-DD ou YYYY-MM-DDTHH:MM, hora local):",
        "teacher.confirmReset": "Resetar a tentativa do exame final deste aluno?",
        "teacher.err.onlyTeachers": "Esta página é apenas para professores. Você será redirecionado para o painel do aluno.",
        "teacher.err.loadStudents": "Erro ao carregar alunos.",
        "teacher.err.loadStudentsDetail": "Erro ao carregar alunos: ",
        "teacher.err.forbidden": "Acesso negado: Você precisa ser um professor para acessar esta página. Faça login com uma conta de professor.",
        "teacher.err.loadCohorts": "Erro ao carregar turmas: ",
        "teacher.err.loadHistory": "Erro ao carregar histórico: ",
        "teacher.err.setDate": "Erro ao configurar data: ",
        "teacher.err.reset": "Erro ao resetar tentativa: ",
        "teacher.err.invalidDate": "Data inválida. Use YYYY-MM-DD ou YYYY-MM-DDTHH:MM."
    },

    en: {
        "common.logout": "Log out",
        "common.back": "Back",
        "common.backToDashboard": "Back to Dashboard",
        "common.langSwitch": "Language",
        "common.connectionError": "Connection error. Check your internet and try again.",
        "common.httpError": "Error {status}",
        "common.configError": "Could not load the configuration. Check your internet connection.",
        "common.question": "Question",

        "phase.initial": "Diagnostic",
        "phase.free_practice": "Free practice",
        "phase.final_exam": "Final exam",
        "status.completed": "Completed",
        "status.in_progress": "In progress",
        "quizType.initial": "Diagnostic",
        "quizType.free": "Free Practice",
        "quizType.final_exam": "Final Exam",

        "login.pageTitle": "AI Mentoring - Sign in",
        "login.subtitle": "AWS Practice Exams & MENTORING Platform",
        "login.email": "Email",
        "login.emailPlaceholder": "your-email@example.com",
        "login.password": "Password",
        "login.submit": "Sign in",
        "login.forgot": "Forgot your password?",
        "login.noAccount": "Don't have an account?",
        "login.registerHere": "Sign up here",
        "login.showPassword": "Show password",
        "login.hidePassword": "Hide password",
        "register.name": "Full Name",
        "register.namePlaceholder": "Your name",
        "register.passwordPlaceholder": "At least 8 characters",
        "register.passwordHint": "At least 8 characters, one uppercase letter and one number",
        "register.submit": "Create Account",
        "register.haveAccount": "Already have an account?",
        "register.loginHere": "Sign in here",
        "register.passwordInvalid": "Password must have at least 8 characters, one uppercase letter and one number.",
        "register.cohortFull": "This cohort is full. Contact your instructor to check availability.",
        "confirm.sentTo": "We sent a verification code to",
        "confirm.instructions": ". Enter the code to confirm your account.",
        "confirm.code": "Verification Code",
        "confirm.submit": "Confirm Account",
        "confirm.resend": "Resend code",
        "confirm.backToLogin": "Back to sign in",
        "confirm.success": "Account confirmed! You can now sign in.",
        "confirm.resent": "Code resent. Check your email.",
        "forgot.instructions": "Enter your email and we'll send you a code to reset your password.",
        "forgot.submit": "Send Code",
        "reset.sentTo": "Enter the code sent to",
        "reset.instructions": "and your new password.",
        "reset.newPassword": "New Password",
        "reset.submit": "Reset Password",
        "reset.success": "Password updated! You can now sign in.",

        "auth.err.login": "Sign-in failed",
        "auth.err.emailExists": "This email is already registered. Try signing in.",
        "auth.err.passwordPolicy": "Password does not meet the requirements. At least 8 characters, one uppercase letter and one number.",
        "auth.err.invalidParams": "Invalid data. Check your email and password.",
        "auth.err.tooManyAttempts": "Too many attempts. Please wait a few minutes.",
        "auth.err.tooManyRequests": "Too many requests. Try again later.",
        "auth.err.signUp": "Failed to create the account",
        "auth.err.codeMismatch": "Incorrect code. Try again.",
        "auth.err.codeExpired": "The code has expired. Request a new one.",
        "auth.err.confirm": "Failed to confirm the account",
        "auth.err.resend": "Failed to resend the code",
        "auth.err.userNotFound": "There is no account with this email.",
        "auth.err.invalidEmail": "Invalid email format.",
        "auth.err.forgot": "Failed to send recovery code",
        "auth.err.reset": "Failed to reset the password",

        "dash.pageTitle": "AI Mentoring - Dashboard",
        "dash.loadingProfile": "Loading profile...",
        "dash.profileTitle": "Student Profile",
        "dash.email": "Email:",
        "dash.cohort": "Cohort:",
        "dash.defaultName": "Student",
        "dash.noCohort": "No cohort",
        "dash.initialTitle": "You haven't taken your initial diagnostic yet",
        "dash.initialText": "The initial diagnostic helps identify your starting point in preparing for AWS Cloud Practitioner.",
        "dash.initialBtn": "Take Initial Diagnostic",
        "dash.resumeTitle": "You have a final exam in progress",
        "dash.resumeText": "Resume where you left off so you don't lose the answers already submitted.",
        "dash.resumeBtn": "Resume Final Exam",
        "dash.finalTitle": "Certification Final Exam",
        "dash.loading": "Loading...",
        "dash.finalStart": "Start Final Exam",
        "dash.finalDone": "Final exam already taken. Contact your instructor for a new attempt.",
        "dash.finalLocked": "Locked by the instructor.",
        "dash.finalLockedUntil": "Locked by the instructor (available from {date}).",
        "dash.finalAvailable": "Available",
        "dash.newQuizTitle": "Generate New Practice Exam",
        "dash.topic": "AWS Certification Topic",
        "dash.topicGeneral": "General / Other Services",
        "dash.questionCount": "Number of Questions",
        "dash.startQuiz": "Start Practice Exam",
        "dash.historyTitle": "Practice Exam History",
        "dash.loadingHistory": "Loading history...",
        "dash.noHistory": "No practice exams taken yet.",
        "dash.historyError": "Error loading history.",
        "dash.col.type": "Type",
        "dash.col.topic": "Topic",
        "dash.col.status": "Status",
        "dash.col.score": "Score",
        "dash.col.date": "Date",
        "dash.err.profile": "Error loading profile: ",
        "dash.err.history": "Error loading history: ",
        "dash.err.initial": "Error generating diagnostic: ",

        "quiz.pageTitle": "AI Mentoring - Practice Exam",
        "quiz.loading": "Loading questions...",
        "quiz.topic": "Topic:",
        "quiz.question": "Question:",
        "quiz.answered": "Answered:",
        "quiz.answeredProgress": "{done} of {total} answered",
        "quiz.initialTopic": "Initial Diagnostic",
        "quiz.multiple": " (Multiple choice)",
        "quiz.submit": "Submit Answer",
        "quiz.next": "Next Question",
        "quiz.correct": "Correct!",
        "quiz.incorrect": "Incorrect.",
        "quiz.completedTitle": "Practice Exam Completed 🎉",
        "quiz.completedText": "You answered all the questions successfully.",
        "quiz.initialCompletedTitle": "Diagnostic Completed 🎉",
        "quiz.initialCompletedText": "Diagnostic completed! Now we know your starting point.",
        "quiz.viewResults": "View Results",
        "quiz.err.submit": "Error submitting answer: ",

        "results.pageTitle": "AI Mentoring - Results",
        "results.loading": "Loading results...",
        "results.error": "Error",
        "results.loadError": "Could not load the results.",
        "results.summary": "Practice Exam Summary",
        "results.score": "Final Score",
        "results.correctCount": "Correct",
        "results.total": "Total Questions",
        "results.domainTitle": "Performance by Domain",
        "results.col.domain": "Domain",
        "results.col.correct": "Correct",
        "results.col.total": "Total",
        "results.answersTitle": "Answer Breakdown",
        "results.retake": "Take Another Practice Exam",
        "results.noQuizId": "No valid practice exam ID was found.",
        "results.noAnswers": "There are no answers recorded for this practice exam.",
        "results.correct": "Correct ✅",
        "results.incorrect": "Incorrect ❌",
        "results.statement": "Question:",
        "results.given": "Your answer:",
        "results.expected": "Correct answer:",
        "results.explanation": "Explanation:",
        "explanation.general": "General explanation",
        "explanation.otherOptions": "Other options and why they aren't the best",

        "teacher.pageTitle": "AI Mentoring - Instructor Dashboard",
        "teacher.role": "Instructor",
        "teacher.kpis": "Indicators",
        "teacher.kpiTotal": "Total Students",
        "teacher.kpiInitial": "Diagnostic",
        "teacher.kpiFree": "Free Practice",
        "teacher.kpiFinal": "Final Exam",
        "teacher.students": "Students",
        "teacher.cohort": "Cohort",
        "teacher.all": "All",
        "teacher.allCohorts": "All cohorts",
        "teacher.search": "Search name or email",
        "teacher.col.name": "Name",
        "teacher.col.email": "Email",
        "teacher.col.cohort": "Cohort",
        "teacher.col.phase": "Current Phase",
        "teacher.col.finalExam": "Final Exam",
        "teacher.col.actions": "Actions",
        "teacher.historyTitle": "Student History",
        "teacher.close": "Close",
        "teacher.col.typeTopic": "Type / Topic",
        "teacher.col.details": "Details",
        "teacher.cohortsTitle": "Cohorts",
        "teacher.col.cohortName": "Name",
        "teacher.col.students": "Students",
        "teacher.col.max": "Maximum",
        "teacher.btn.history": "History",
        "teacher.btn.setExam": "Set date",
        "teacher.btn.resetExam": "Reset attempt",
        "teacher.notConfigured": "Not set",
        "teacher.attempts": "{count} attempt(s)",
        "teacher.noQuizzes": "No quizzes taken yet.",
        "teacher.viewDetails": "View details",
        "teacher.promptDate": "Final exam release date (YYYY-MM-DD or YYYY-MM-DDTHH:MM, local time):",
        "teacher.confirmReset": "Reset this student's final exam attempt?",
        "teacher.err.onlyTeachers": "This page is for instructors only. You will be redirected to the student dashboard.",
        "teacher.err.loadStudents": "Error loading students.",
        "teacher.err.loadStudentsDetail": "Error loading students: ",
        "teacher.err.forbidden": "Access denied: you must be an instructor to access this page. Sign in with an instructor account.",
        "teacher.err.loadCohorts": "Error loading cohorts: ",
        "teacher.err.loadHistory": "Error loading history: ",
        "teacher.err.setDate": "Error setting date: ",
        "teacher.err.reset": "Error resetting attempt: ",
        "teacher.err.invalidDate": "Invalid date. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM."
    }
};

const I18N_LANGS = { pt: { label: "PT", htmlLang: "pt-BR", locale: "pt-BR" }, en: { label: "EN", htmlLang: "en", locale: "en-US" } };

function getLang() {
    try {
        return localStorage.getItem("lang") === "en" ? "en" : "pt";
    } catch (err) {
        return "pt";
    }
}

function getLocale() {
    return I18N_LANGS[getLang()].locale;
}

// Traduce una clave; si falta en el idioma actual cae a PT y, en último caso, devuelve la clave.
function t(key, vars) {
    let text = I18N[getLang()][key] ?? I18N.pt[key] ?? key;
    if (vars) {
        for (const [name, value] of Object.entries(vars)) {
            text = text.replaceAll(`{${name}}`, value);
        }
    }
    return text;
}

// Traduce un valor de enum del backend (fase, status, tipo de quiz); si no hay traducción, devuelve el valor crudo.
function tEnum(prefix, value) {
    if (value === undefined || value === null || value === "") return "";
    const key = `${prefix}.${value}`;
    return key in I18N[getLang()] || key in I18N.pt ? t(key) : String(value);
}

// Aplica las traducciones a los elementos marcados con data-i18n*.
function applyTranslations(root = document) {
    root.querySelectorAll("[data-i18n]").forEach(el => {
        el.textContent = t(el.dataset.i18n);
    });
    root.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
        el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    root.querySelectorAll("[data-i18n-aria-label]").forEach(el => {
        el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel));
    });
    document.documentElement.lang = I18N_LANGS[getLang()].htmlLang;
}

function setLang(lang) {
    try {
        localStorage.setItem("lang", lang);
    } catch (err) {
        // Sin storage: el cambio vale solo para esta vista.
    }
    // Vistas de solo lectura: recargar re-renderiza el contenido generado por JS.
    // index/quiz no recargan para no perder lo tipeado ni el estado de la pregunta.
    if (!document.body.hasAttribute("data-lang-no-reload")) {
        window.location.reload();
        return;
    }
    applyTranslations();
    renderLangSwitcher();
    // Aviso para páginas con contenido de BD ya cargado en memoria (ej. quiz.html)
    // que necesitan volver a pedirlo al backend en el nuevo idioma. Sin listener, no-op.
    document.dispatchEvent(new CustomEvent('i18n:langchange', { detail: { lang } }));
}

function renderLangSwitcher() {
    const current = getLang();
    document.querySelectorAll("#langSwitcher").forEach(container => {
        container.innerHTML = "";
        const group = document.createElement("div");
        group.className = "lang-switch";
        group.setAttribute("role", "group");
        group.setAttribute("aria-label", t("common.langSwitch"));
        for (const [code, meta] of Object.entries(I18N_LANGS)) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.textContent = meta.label;
            btn.lang = meta.htmlLang;
            btn.setAttribute("aria-pressed", String(code === current));
            btn.addEventListener("click", () => {
                if (code !== getLang()) setLang(code);
            });
            group.appendChild(btn);
        }
        container.appendChild(group);
    });
}

applyTranslations();
renderLangSwitcher();
