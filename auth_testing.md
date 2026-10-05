# Auth Testing

Auth: JWT Bearer token in localStorage (`ct_token`), sent as `Authorization: Bearer <token>`.

## API test
```
curl -s -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"rgblack@gmail.com","password":"Treasury2026!"}'
# -> {"token":"...","user":{...,"role":"admin"}}

TOKEN=<token from above>
curl -s http://localhost:8001/api/auth/me -H "Authorization: Bearer $TOKEN"
```

Admin: rgblack@gmail.com / Treasury2026!
