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
        throw new Error(data.message || "Error al iniciar sesión");
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
        window.location.href = "index.html";
        return null;
    }
    return token;
}

function logout() {
    localStorage.clear();
    window.location.href = "index.html";
}
