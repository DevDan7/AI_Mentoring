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

    let response = await fetch(`${CONFIG.apiUrl}${path}`, options);

    if (response.status === 401) {
        const newToken = await refreshSession();
        if (!newToken) {
            logout();
            return null;
        }
        options.headers["Authorization"] = `Bearer ${newToken}`;
        response = await fetch(`${CONFIG.apiUrl}${path}`, options);
    }

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.message || `Error ${response.status}`);
    }

    return response.json();
}

async function getStudent() {
    return apiCall("GET", "/students/me");
}

async function updateStudent(data) {
    return apiCall("PUT", "/students/me", data);
}

async function generateQuiz(topic, count) {
    return apiCall("POST", "/quizzes/generate", { topic, count });
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

async function completeQuiz(quizId) {
    return apiCall("POST", `/quizzes/${quizId}/complete`, {});
}

async function getQuiz(quizId) {
    return apiCall("GET", `/quizzes/${quizId}`);
}

async function getQuizHistory() {
    return apiCall("GET", "/students/me/quizzes");
}

// ========== VALIDACIÓN DE CUPO ==========

async function checkCohortCapacity(cohortId) {
    return apiCall("GET", `/cohorts/${cohortId}/capacity`);
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

    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        name = payload.name || payload.given_name || email.split("@")[0];
        email = payload.email || email;
    } catch {
        // Si no se puede decodificar, usar lo disponible
    }

    const body = {
        name: name,
        cohort: ""
    };

    const pendingCohortId = sessionStorage.getItem('pending_cohort_id');
    if (pendingCohortId) {
        body.cohort_id = pendingCohortId;
    }

    return apiCall("POST", "/students", body);
}
