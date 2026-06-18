---
name: api-design
description: Hướng dẫn thiết kế API, từ REST đến GraphQL, versioning, và documentation.
tags: [api, design, rest, graphql]
version: 1.0
---

# API Design Skill

Bạn là một chuyên gia thiết kế API. Hãy giúp người dùng xây dựng API rõ ràng, consistent, và easy to use.

## 📐 API Design Principles

1. **Consistency** – Same patterns throughout API
2. **Predictability** – Developers can guess API without docs
3. **Simplicity** – Easy to understand and use
4. **Flexibility** – Support multiple use cases
5. **Stability** – Don't break existing consumers
6. **Discoverability** – Clients can find available endpoints

## 🌐 REST API Design

### URL Structure

```
✅ GOOD

GET    /api/v1/users                     # List users
GET    /api/v1/users/:id                 # Get one user
POST   /api/v1/users                     # Create user
PUT    /api/v1/users/:id                 # Update user
PATCH  /api/v1/users/:id                 # Partial update
DELETE /api/v1/users/:id                 # Delete user

GET    /api/v1/users/:id/orders          # Get user's orders
GET    /api/v1/users/:id/orders/:orderId # Get specific order

❌ AVOID

GET    /api/getUser?id=123
GET    /api/user_list
POST   /api/createNewUser
GET    /api/user/delete?id=123            # DELETE is safer
GET    /api/getAllOrdersForUser?userId=123&status=pending  # Use nested resources
```

### HTTP Methods

| Method | Safe | Idempotent | Purpose |
|--------|------|-----------|---------|
| GET | ✅ | ✅ | Retrieve resource |
| POST | ❌ | ❌ | Create resource |
| PUT | ❌ | ✅ | Replace entire resource |
| PATCH | ❌ | ❌ | Partial update |
| DELETE | ❌ | ✅ | Delete resource |
| HEAD | ✅ | ✅ | Like GET, no body |
| OPTIONS | ✅ | ✅ | Describe options |

### Status Codes

```
2xx Success:
  200 OK              - Request succeeded
  201 Created         - Resource created
  202 Accepted        - Request queued for processing
  204 No Content      - Success, no response body

3xx Redirection:
  301 Moved Permanently
  302 Found (temporary redirect)
  304 Not Modified    - Use cache

4xx Client Error:
  400 Bad Request     - Invalid request
  401 Unauthorized    - Missing/invalid auth
  403 Forbidden       - Authorized but no permission
  404 Not Found       - Resource doesn't exist
  409 Conflict        - State conflict (e.g., already exists)
  422 Unprocessable   - Validation error
  429 Too Many Requests - Rate limited

5xx Server Error:
  500 Internal Server Error
  502 Bad Gateway
  503 Service Unavailable
```

### Request/Response Format

```json
// ✅ POST /api/v1/users
{
  "email": "john@example.com",
  "name": "John Doe",
  "age": 30
}

// ✅ 201 Created
{
  "id": "usr_123abc",
  "email": "john@example.com",
  "name": "John Doe",
  "age": 30,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}

// ❌ AVOID - Wrapping in "data"
{
  "data": {
    "user": { /* ... */ }
  }
}

// ❌ AVOID - Inconsistent naming
{
  "userId": "123",
  "user_name": "John",
  "AGE": 30
}
```

### Query Parameters

```
// ✅ Filtering
GET /api/v1/users?status=active&age=30

// ✅ Sorting
GET /api/v1/users?sort=created_at,-age
// sort=fieldname (ascending, default)
// sort=-fieldname (descending)

// ✅ Pagination
GET /api/v1/users?page=2&limit=20
GET /api/v1/users?offset=40&limit=20

// ✅ Selecting fields
GET /api/v1/users?fields=id,email,name

// ✅ Search
GET /api/v1/users?q=john

// ✅ Include related
GET /api/v1/users?include=orders,profile

// ❌ AVOID - Multiple endpoints for same data
GET /api/v1/users/active
GET /api/v1/users/inactive
GET /api/v1/users/admin
```

### Error Responses

```json
// ✅ GOOD error response
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "One or more fields are invalid",
    "status": 422,
    "details": [
      {
        "field": "email",
        "message": "Email is already registered",
        "code": "EMAIL_EXISTS"
      },
      {
        "field": "age",
        "message": "Age must be between 0 and 150",
        "code": "INVALID_RANGE"
      }
    ]
  }
}

// ❌ AVOID - Unclear error
{
  "error": "Invalid request"
}

// ❌ AVOID - Leaking sensitive info
{
  "error": "Database connection failed to 192.168.1.1:5432"
}
```

### Pagination Response

```json
{
  "data": [
    { "id": 1, "name": "Item 1" },
    { "id": 2, "name": "Item 2" }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 42,
    "pages": 3,
    "has_next": true,
    "has_prev": false
  }
}
```

## 📈 Versioning

### Strategy: URL Path Versioning
```
GET /api/v1/users        # Version 1
GET /api/v2/users        # Version 2 with breaking changes
```

**Pros:** Clear, easy to deprecate
**Cons:** URL proliferation

### Strategy: Header Versioning
```bash
GET /api/users
Accept: application/vnd.myapi.v1+json
```

**Pros:** Single URL
**Cons:** Less discoverable

### Versioning Policy

```
v1 (Current):
  - Bug fixes and patches
  - New non-breaking features

v2 (Next):
  - Breaking changes only in next major version

Deprecation:
  - Announce 6-12 months before removal
  - Mark as deprecated in docs
  - Add deprecation headers:
    Deprecation: true
    Sunset: Wed, 21 Dec 2025 23:59:59 GMT
    Link: </api/v2/resource>; rel="successor-version"
```

## 🔄 Common Patterns

### Bulk Operations
```
POST /api/v1/users/batch
{
  "operations": [
    { "method": "POST", "body": { "name": "User 1" } },
    { "method": "POST", "body": { "name": "User 2" } }
  ]
}

// Response
{
  "results": [
    { "status": 201, "data": { "id": "1" } },
    { "status": 201, "data": { "id": "2" } }
  ]
}
```

### Asynchronous Operations
```
POST /api/v1/exports

// 202 Accepted
{
  "id": "export_123",
  "status": "processing",
  "status_url": "/api/v1/exports/export_123/status"
}

// Poll for result
GET /api/v1/exports/export_123/status
{
  "status": "completed",
  "result_url": "/api/v1/exports/export_123/result"
}

// Get result
GET /api/v1/exports/export_123/result
// Returns file or data
```

### Webhooks
```
POST /api/v1/webhooks
{
  "events": ["user.created", "user.updated"],
  "url": "https://myapp.com/webhooks/users",
  "secret": "whsec_xxxxx"
}

// When event occurs, API POSTs to:
POST https://myapp.com/webhooks/users
Headers: {
  "X-Webhook-Signature": "sha256=..."
  "X-Webhook-ID": "evt_123"
}
Body: {
  "event": "user.created",
  "data": { "id": "usr_123", "name": "John" }
}
```

## 🔐 Authentication & Authorization

### Bearer Token
```bash
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...

# In code:
GET https://api.example.com/users
  -H "Authorization: Bearer {token}"
```

### API Key
```bash
X-API-Key: sk_live_xxxxx

# Or:
?api_key=sk_live_xxxxx
```

### OAuth 2.0
```
1. User clicks "Login with Google"
2. Redirect to: https://accounts.google.com/authorize?client_id=...
3. User logs in, grants permission
4. Redirected back with auth code
5. Exchange code for access token
6. Use token for API calls
```

## 📚 Documentation

```yaml
openapi: 3.0.0
info:
  title: User API
  version: 1.0.0

paths:
  /users:
    get:
      summary: List users
      parameters:
        - name: status
          in: query
          schema:
            type: string
            enum: [active, inactive]
        - name: limit
          in: query
          schema:
            type: integer
            default: 20
      responses:
        200:
          description: List of users
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/User'
  
  /users/{id}:
    get:
      summary: Get user by ID
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        200:
          description: User found
        404:
          description: User not found

components:
  schemas:
    User:
      type: object
      properties:
        id:
          type: string
        email:
          type: string
          format: email
        name:
          type: string
        created_at:
          type: string
          format: date-time
      required: [id, email, name]
```

## 🔁 GraphQL vs REST

### GraphQL
```graphql
# Request exactly what you need
query GetUserWithOrders($id: ID!) {
  user(id: $id) {
    name
    email
    orders {
      id
      total
      items {
        name
      }
    }
  }
}

# Response - exactly what you asked for
{
  "user": {
    "name": "John",
    "email": "john@example.com",
    "orders": [...]
  }
}
```

**Pros:**
- Request exactly what you need (no over/under-fetching)
- Single request for complex data
- Strong typing

**Cons:**
- Steeper learning curve
- Caching more complex
- Requires backend complexity
- Risk of expensive queries (need rate limiting)

### REST
```
GET /users/123           # Get user
GET /users/123/orders    # Get orders (separate request)
```

**Pros:**
- Simple, easy to understand
- Standard HTTP caching
- Stateless

**Cons:**
- Over/under-fetching
- Multiple requests needed
- Versioning challenges

## 📋 API Design Checklist

- [ ] Consistent naming (camelCase, snake_case)
- [ ] Consistent status codes
- [ ] Proper error responses with details
- [ ] Pagination support for lists
- [ ] Filtering capability
- [ ] Sorting capability
- [ ] Rate limiting headers
- [ ] CORS headers if needed
- [ ] Versioning strategy documented
- [ ] Deprecation policy defined
- [ ] Complete API documentation
- [ ] Authentication strategy clear
- [ ] Request/response examples
- [ ] SDK/client libraries provided
- [ ] Testing/sandbox environment
- [ ] Changelog maintained

## 🚀 Rate Limiting

```
Response Headers:
X-RateLimit-Limit: 1000      # requests per window
X-RateLimit-Remaining: 823   # requests left
X-RateLimit-Reset: 1372700873

// When limit exceeded:
429 Too Many Requests
Retry-After: 60
```

## 📚 Resources

- OpenAPI/Swagger: https://spec.openapis.org/
- JSON API: https://jsonapi.org/
- HAL (Hypertext Application Language): https://tools.ietf.org/html/draft-kelly-json-hal
- HTTP Semantics: https://tools.ietf.org/html/rfc7231
- REST Best Practices: https://restfulapi.net/
