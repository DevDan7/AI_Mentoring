# Teacher Dashboard Setup Guide

## Problem
The teacher dashboard is returning 403 Forbidden errors because the current user is not in the 'Teachers' Cognito group.

## Solutions

### Option 1: Add Existing User to Teachers Group (AWS Console)
1. Go to AWS Cognito Console
2. Navigate to User Pools → `us-east-1_YolmrF9tp` (AI_Mentoring-StudentsPool-dev)
3. Go to Users and groups
4. Find your user email
5. Click "Add user to group"
6. Select "Teachers" group
7. Save

### Option 2: Add User via AWS CLI
```bash
# Install AWS CLI first if not installed
aws cognito-idp admin-add-user-to-group \
  --user-pool-id us-east-1_YolmrF9tp \
  --username user@example.com \
  --group-name Teachers \
  --region us-east-1
```

### Option 3: Create New Teacher User
1. Go to the application login page
2. Click "Sign up" and create a new account
3. Use AWS Console or CLI (as above) to add this new user to Teachers group
4. Log out and log back in with the new teacher account

## Verification
After adding a user to the Teachers group:
1. Log out of the application
2. Log back in with the teacher user
3. Navigate to teacher.html
4. You should now be able to see students and cohorts without 403 errors

## Technical Details
- The API Gateway routes `/students` and `/cohorts` require JWT authorization
- The Lambda function `student_api.py` checks for `cognito:groups` claim containing "Teachers"
- The frontend `teacher.js` checks `isTeacher()` function which looks for "Teachers" in the JWT token
- Users without "Teachers" group get 403 Forbidden responses

## Frontend Improvements Already Made
1. Better error messages showing "Acesso negado: Você precisa ser um professor"
2. Automatic redirect to student dashboard after 3 seconds
3. Early permission check in `initTeacherDashboard()`

## Troubleshooting
If you still see 403 errors after adding to Teachers group:
1. Clear browser localStorage (tokens are cached)
2. Log out and log back in
3. Check browser console for detailed error messages
4. Verify the user is actually in the Teachers group in Cognito Console