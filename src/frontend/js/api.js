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
