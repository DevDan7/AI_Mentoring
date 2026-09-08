// Muestra un mensaje de error en el elemento visible de la pantalla activa.
// Nunca usa alert(): escribe en <div id="errorMsg"> y lo hace visible.
function showError(message) {
    const errorEl = document.getElementById('errorMsg');
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.style.display = 'block';
    }
}

async function apiCall(method, path, body) {
    const token = await getToken();

    if (!token) {
        logout();
        return null;
    }

    const options = {
        method,
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json"
        }
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    let response;
    try {
        response = await fetch(`${CONFIG.apiUrl}${path}`, options);
    } catch (networkErr) {
        showError("Erro de conexão. Verifique sua internet e tente novamente.");
        throw networkErr;
    }

    if (response.status === 401) {
        const newToken = await refreshSession();
        if (!newToken) {
            logout();
            return null;
        }
        options.headers["Authorization"] = `Bearer ${newToken}`;
        try {
            response = await fetch(`${CONFIG.apiUrl}${path}`, options);
        } catch (networkErr) {
            showError("Erro de conexão. Verifique sua internet e tente novamente.");
            throw networkErr;
        }
    }

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        showError(error.message || `Erro ${response.status}`);
        throw new Error(error.message || `Error ${response.status}`);
    }

    return response.json();
}

async function getStudent() {
    return apiCall("GET", "/students/me");
}

async function generateQuiz(quizType, topic, numQuestions) {
    const body = { quiz_type: quizType };
    if (topic !== undefined && topic !== null) {
        body.topic = topic;
    }
    if (numQuestions !== undefined && numQuestions !== null) {
        body.num_questions = numQuestions;
    }
    return apiCall("POST", "/quizzes/generate", body);
}

async function generateFinalExam() {
    return apiCall("POST", "/quizzes/generate", { quiz_type: "final_exam" });
}

async function setFinalExamRelease(studentId, date) {
    return apiCall("PUT", `/students/${studentId}/final-exam-release`, { release_date: date });
}

async function resetFinalExamAttempt(studentId) {
    return apiCall("DELETE", `/students/${studentId}/final-exam-attempt`);
}

async function submitAnswer(quizId, questionId, givenAnswers) {
    return apiCall("POST", "/quizzes/submit", {
        quiz_id: quizId,
        question_id: questionId,
        given_answers: givenAnswers
    });
}

async function getQuizResults(quizId) {
    return apiCall("GET", `/quizzes/${quizId}/results`);
}

async function generateInitialTest() {
    return apiCall("POST", "/quizzes/generate", { quiz_type: "initial" });
}

async function getQuiz(quizId) {
    return apiCall("GET", `/quizzes/${quizId}`);
}

async function getQuizHistory() {
    return apiCall("GET", "/students/me/quizzes");
}

// ========== VALIDACIÓN DE CUPO ==========

async function checkCohortCapacityPublic(cohortId) {
    const response = await fetch(`${CONFIG.apiUrl}/public/cohorts/${cohortId}/capacity`);
    if (!response.ok) {
        throw new Error(`Error ${response.status}`);
    }
    return response.json();
}

// ========== AUTO-CREACIÓN DE PERFIL ==========

async function ensureStudentProfile() {
    try {
        return await getStudent();
    } catch (err) {
        if (err.message.includes("404") || err.message.includes("not found")) {
            try {
                await createStudentProfile();
                return await getStudent();
            } catch (createErr) {
                if (createErr.message.includes("409")) {
                    return await getStudent();
                }
                throw createErr;
            }
        }
        throw err;
    }
}

async function createStudentProfile() {
    const token = localStorage.getItem("id_token");
    let name = "";
    let email = localStorage.getItem("user_email") || "";

    if (token) {
        const payload = parseJwt(token) || {};
        name = payload.name || payload.given_name || (email ? email.split("@")[0] : "");
        email = payload.email || email;
    }

    const pendingCohortId = sessionStorage.getItem('pending_cohort_id');
    const body = {
        name: name || "Nuevo Usuario",
        cohort_id: pendingCohortId || ""
    };

    return apiCall("POST", "/students", body);
}