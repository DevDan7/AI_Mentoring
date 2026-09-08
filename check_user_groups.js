// Simple script to check current user's Cognito groups
// Run this in browser console when logged into the application

function checkUserGroups() {
    const idToken = localStorage.getItem("id_token");
    if (!idToken) {
        console.log("No ID token found. User is not logged in.");
        return;
    }
    
    // Parse JWT token
    const parseJwt = (token) => {
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            return JSON.parse(jsonPayload);
        } catch (e) {
            console.error("Error parsing JWT:", e);
            return null;
        }
    };
    
    const payload = parseJwt(idToken);
    if (!payload) {
        console.log("Could not parse JWT token");
        return;
    }
    
    console.log("User ID:", payload.sub);
    console.log("User email:", payload.email);
    console.log("User name:", payload.name);
    
    // Check for groups
    const groups = payload['cognito:groups'];
    console.log("Cognito groups:", groups);
    
    if (Array.isArray(groups)) {
        const isTeacher = groups.includes('Teachers');
        console.log("Is teacher?", isTeacher);
        if (!isTeacher) {
            console.log("❌ User is NOT in Teachers group. This is why teacher dashboard shows 403 errors.");
            console.log("To fix: Add this user to 'Teachers' group in Cognito Console.");
        } else {
            console.log("✅ User IS in Teachers group. Teacher dashboard should work.");
        }
    } else if (typeof groups === 'string') {
        console.log("Groups as string (may need parsing):", groups);
        try {
            // Try to parse as JSON (API Gateway v2 serializes arrays as JSON strings)
            const parsedGroups = JSON.parse(groups);
            if (Array.isArray(parsedGroups)) {
                const isTeacher = parsedGroups.includes('Teachers');
                console.log("Is teacher (parsed)?", isTeacher);
            }
        } catch (e) {
            console.log("Could not parse groups string as JSON");
        }
    } else {
        console.log("No groups found in token");
    }
    
    // Check token expiration
    if (payload.exp) {
        const expDate = new Date(payload.exp * 1000);
        const now = new Date();
        console.log("Token expires:", expDate.toLocaleString());
        console.log("Is token expired?", now > expDate ? "Yes" : "No");
    }
}

// Run the check
checkUserGroups();