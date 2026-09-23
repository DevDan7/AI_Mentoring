// ========== AUTENTICACIÓN Y SESIÓN ==========

async function login(email, password) {
    const payload = {
        AuthFlow: "USER_PASSWORD_AUTH",
        ClientId: CONFIG.clientId,
        AuthParameters: {
            USERNAME: email,
            PASSWORD: password
        }
    };

    const response = await fetch(`https://cognito-idp.${CONFIG.cognitoRegion}.amazonaws.com/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth"
        },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.message || t("auth.err.login"));
    }

    const result = data.AuthenticationResult;
    localStorage.setItem("id_token", result.IdToken);
    localStorage.setItem("access_token", result.AccessToken);
    if (result.RefreshToken) {
        localStorage.setItem("refresh_token", result.RefreshToken);
    }
    localStorage.setItem("user_email", email);

    window.location.href = isTeacher() ? "teacher.html" : "dashboard.html";
}

async function refreshSession() {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) {
        logout();
        return null;
    }

    const payload = {
        AuthFlow: "REFRESH_TOKEN_AUTH",
        ClientId: CONFIG.clientId,
        AuthParameters: {
            REFRESH_TOKEN: refreshToken
        }
    };

    const response = await fetch(`https://cognito-idp.${CONFIG.cognitoRegion}.amazonaws.com/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth"
        },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
        logout();
        return null;
    }

    const result = data.AuthenticationResult;
    localStorage.setItem("id_token", result.IdToken);
    localStorage.setItem("access_token", result.AccessToken);
    if (result.RefreshToken) {
        localStorage.setItem("refresh_token", result.RefreshToken);
    }

    return result.IdToken;
}

function parseJwt(token) {
    if (!token) return null;
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        return JSON.parse(jsonPayload);
    } catch (e) {
        return null;
    }
}

function isTokenExpired(token) {
    if (!token) return true;
    const payload = parseJwt(token);
    if (!payload || !payload.exp) return true;
    const exp = payload.exp * 1000;
    return Date.now() >= exp - 60000;
}

async function getToken() {
    let token = localStorage.getItem("id_token");
    if (!token || isTokenExpired(token)) {
        token = await refreshSession();
    }
    return token;
}

// Verifica la sesión usando getToken() (que hace refresh si es necesario).
// Devuelve null y redirige a index.html solo si el token no se puede renovar.
async function checkAuth() {
    const token = await getToken();
    if (!token) {
        logout();
        return null;
    }
    return token;
}

function logout() {
    localStorage.clear();
    window.location.href = "index.html";
}

// ========== REGISTRO ==========

async function signUp(email, password, name) {
    const payload = {
        ClientId: CONFIG.clientId,
        Username: email,
        Password: password,
        UserAttributes: [
            { Name: "email", Value: email },
            { Name: "name", Value: name }
        ]
    };

    const response = await fetch(`https://cognito-idp.${CONFIG.cognitoRegion}.amazonaws.com/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.SignUp"
        },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
        const code = data.__type || "";
        if (code.includes("UsernameExistsException")) {
            throw new Error(t("auth.err.emailExists"));
        }
        if (code.includes("InvalidPasswordException")) {
            throw new Error(t("auth.err.passwordPolicy"));
        }
        if (code.includes("InvalidParameterException")) {
            throw new Error(t("auth.err.invalidParams"));
        }
        if (code.includes("TooManyRequestsException")) {
            throw new Error(t("auth.err.tooManyAttempts"));
        }
        throw new Error(data.message || t("auth.err.signUp"));
    }

    return data.UserConfirmed;
}

async function confirmSignUp(email, code) {
    const payload = {
        ClientId: CONFIG.clientId,
        Username: email,
        ConfirmationCode: code
    };

    const response = await fetch(`https://cognito-idp.${CONFIG.cognitoRegion}.amazonaws.com/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.ConfirmSignUp"
        },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
        const errCode = data.__type || "";
        if (errCode.includes("CodeMismatchException")) {
            throw new Error(t("auth.err.codeMismatch"));
        }
        if (errCode.includes("ExpiredCodeException")) {
            throw new Error(t("auth.err.codeExpired"));
        }
        if (errCode.includes("TooManyRequestsException")) {
            throw new Error(t("auth.err.tooManyAttempts"));
        }
        throw new Error(data.message || t("auth.err.confirm"));
    }

    return true;
}

async function resendConfirmationCode(email) {
    const payload = {
        ClientId: CONFIG.clientId,
        Username: email
    };

    const response = await fetch(`https://cognito-idp.${CONFIG.cognitoRegion}.amazonaws.com/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.ResendConfirmationCode"
        },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
        if (data.__type?.includes("LimitExceededException")) {
            throw new Error(t("auth.err.tooManyRequests"));
        }
        throw new Error(data.message || t("auth.err.resend"));
    }

    return true;
}

// ========== VERIFICACIÓN DE ROLES ==========

function isTeacher() {
    const idToken = localStorage.getItem("id_token");
    const idPayload = parseJwt(idToken) || {};
    const groups = idPayload['cognito:groups'] || [];
    return groups.includes('Teachers');
}

// ========== RECUPERAR CONTRASEÑA ==========

async function forgotPassword(email) {
    const payload = {
        ClientId: CONFIG.clientId,
        Username: email
    };

    const response = await fetch(`https://cognito-idp.${CONFIG.cognitoRegion}.amazonaws.com/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.ForgotPassword"
        },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
        const code = data.__type || "";
        if (code.includes("UserNotFoundException")) {
            throw new Error(t("auth.err.userNotFound"));
        }
        if (code.includes("InvalidParameterException")) {
            throw new Error(t("auth.err.invalidEmail"));
        }
        if (code.includes("LimitExceededException")) {
            throw new Error(t("auth.err.tooManyRequests"));
        }
        throw new Error(data.message || t("auth.err.forgot"));
    }

    return true;
}

async function confirmForgotPassword(email, code, newPassword) {
    const payload = {
        ClientId: CONFIG.clientId,
        Username: email,
        ConfirmationCode: code,
        Password: newPassword
    };

    const response = await fetch(`https://cognito-idp.${CONFIG.cognitoRegion}.amazonaws.com/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.ConfirmForgotPassword"
        },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
        const errCode = data.__type || "";
        if (errCode.includes("CodeMismatchException")) {
            throw new Error(t("auth.err.codeMismatch"));
        }
        if (errCode.includes("ExpiredCodeException")) {
            throw new Error(t("auth.err.codeExpired"));
        }
        if (errCode.includes("InvalidPasswordException")) {
            throw new Error(t("auth.err.passwordPolicy"));
        }
        if (errCode.includes("TooManyRequestsException")) {
            throw new Error(t("auth.err.tooManyAttempts"));
        }
        throw new Error(data.message || t("auth.err.reset"));
    }

    return true;
}
