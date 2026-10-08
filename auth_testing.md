# Auth Testing Playbook
This app uses JWT with the token returned in the login response body and sent as
`Authorization: Bearer <token>` (stored in localStorage on the frontend). No cookies.

Step 1: Login
curl -s -X POST $API/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"inspector@indigo.com","password":"inspect123"}'
-> returns { access_token, user }

Step 2: Authenticated call
curl -s $API/api/auth/me -H "Authorization: Bearer <token>"
-> returns the user object

Credentials: inspector@indigo.com / inspect123 (seeded admin "Lead Inspector").
