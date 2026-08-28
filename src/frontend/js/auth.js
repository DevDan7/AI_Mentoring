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
        throw new Error(data.message || "Erro ao fazer login");
    }

    const result = data.AuthenticationResult;
    localStorage.setItem("id_token", result.IdToken);
    localStorage.setItem("access_token", result.AccessToken);
    localStorage.setItem("refresh_token", result.RefreshToken);
    localStorage.setItem("user_email", email);

    window.location.href = "dashboard.html";
}

async function refreshSession() {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) {
        logout();
        return null;
    }

    const payload = {
        AuthFlow: "ALLOW_REFRESH_TOKEN_AUTH",
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

    return result.IdToken;
}

function isTokenExpired(token) {
    if (!token) return true;
    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        const exp = payload.exp * 1000;
        return Date.now() >= exp - 60000;
    } catch {
        return true;
    }
}

async function getToken() {
    let token = localStorage.getItem("id_token");
    if (!token || isTokenExpired(token)) {
        token = await refreshSession();
    }
    return token;
}

function checkAuth() {
    const token = localStorage.getItem("id_token");
    if (!token || isTokenExpired(token)) {
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
            throw new Error("Este e-mail já está registrado. Tente fazer login.");
        }
        if (code.includes("InvalidPasswordException")) {
            throw new Error("A senha não atende aos requisitos. Mínimo 8 caracteres, uma maiúscula e um número.");
        }
        if (code.includes("InvalidParameterException")) {
            throw new Error("Dados inválidos. Verifique seu e-mail e senha.");
        }
        if (code.includes("TooManyRequestsException")) {
            throw new Error("Muitas tentativas. Aguarde alguns minutos.");
        }
        throw new Error(data.message || "Erro ao criar a conta");
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
            throw new Error("Código incorreto. Tente novamente.");
        }
        if (errCode.includes("ExpiredCodeException")) {
            throw new Error("O código expirou. Solicite um novo.");
        }
        if (errCode.includes("TooManyRequestsException")) {
            throw new Error("Muitas tentativas. Aguarde alguns minutos.");
        }
        throw new Error(data.message || "Erro ao confirmar a conta");
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
            throw new Error("Muitas solicitações. Tente mais tarde.");
        }
        throw new Error(data.message || "Erro ao reenviar o código");
    }

    return true;
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
            throw new Error("Não existe uma conta com este e-mail.");
        }
        if (code.includes("InvalidParameterException")) {
            throw new Error("Formato de e-mail inválido.");
        }
        if (code.includes("LimitExceededException")) {
            throw new Error("Muitas solicitações. Tente mais tarde.");
        }
        throw new Error(data.message || "Erro ao enviar código de recuperação");
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
            throw new Error("Código incorreto. Tente novamente.");
        }
        if (errCode.includes("ExpiredCodeException")) {
            throw new Error("O código expirou. Solicite um novo.");
        }
        if (errCode.includes("InvalidPasswordException")) {
            throw new Error("A senha não atende aos requisitos. Mínimo 8 caracteres, uma maiúscula e um número.");
        }
        if (errCode.includes("TooManyRequestsException")) {
            throw new Error("Muitas tentativas. Aguarde alguns minutos.");
        }
        throw new Error(data.message || "Erro ao redefinir a senha");
    }

    return true;
}
