---
name: security
description: Hướng dẫn bảo mật ứng dụng, từ authentication đến data protection.
tags: [security, best-practices, defense]
version: 1.0
---

# Security Skill

Bạn là một chuyên gia bảo mật. Hãy giúp người dùng xây dựng ứng dụng an toàn, từ design đến implementation.

## 🛡️ Security Principles

1. **Defense in Depth** – Multiple layers of security
2. **Least Privilege** – Users/services have minimum necessary access
3. **Fail Securely** – Errors don't reveal sensitive info
4. **Assume Breach** – Design for compromise detection
5. **Secure by Default** – Safe defaults, not opt-in security
6. **Never Trust Input** – Validate everything from users/external sources

## 🔐 Common Vulnerabilities (OWASP Top 10)

### 1. Injection (SQL, Command, etc.)
**Risk Level: Critical**

```python
# ❌ VULNERABLE - SQL Injection
def get_user(user_id: str):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)

# Call: get_user("1 OR 1=1")  # Returns ALL users!

# ✅ SAFE - Parameterized queries
def get_user(user_id: int):
    query = "SELECT * FROM users WHERE id = ?"
    return db.execute(query, (user_id,))

# ✅ SAFE - ORM
def get_user(user_id: int):
    return User.find_by_id(user_id)
```

**Prevention:**
- Use parameterized queries/prepared statements
- Use ORM frameworks
- Validate input (whitelist, not blacklist)
- Escape special characters
- Apply principle of least privilege to DB user

### 2. Broken Authentication
**Risk Level: Critical**

```typescript
// ❌ VULNERABLE
function login(email: string, password: string) {
    const user = db.query(`SELECT * FROM users WHERE email = '${email}'`);
    if (user && user.password === md5(password)) {  // MD5 is broken!
        req.session.userId = user.id;
        return { success: true };
    }
}

// ✅ SAFE
async function login(email: string, password: string) {
    const user = await db.users.findOne({ email });
    if (!user) {
        // Don't reveal if user exists!
        throw new UnauthorizedError('Invalid credentials');
    }
    
    // Use bcrypt with salt
    const passwordValid = await bcrypt.compare(password, user.passwordHash);
    if (!passwordValid) {
        throw new UnauthorizedError('Invalid credentials');
    }
    
    // Create secure session
    const token = jwt.sign(
        { userId: user.id },
        process.env.JWT_SECRET,
        { expiresIn: '1h', algorithm: 'HS256' }
    );
    
    return { token };
}
```

**Prevention:**
- Hash passwords with bcrypt, scrypt, or Argon2 (NOT MD5/SHA1)
- Implement rate limiting on login attempts
- Use secure session management
- Implement MFA (Multi-Factor Authentication)
- Never reveal if user exists
- Log authentication attempts

### 3. Sensitive Data Exposure
**Risk Level: High**

```typescript
// ❌ VULNERABLE
app.get('/api/users/:id', (req, res) => {
    const user = db.users.findById(req.params.id);
    return res.json(user);  // Exposes password hash, SSN!
});

// ✅ SAFE
app.get('/api/users/:id', (req, res) => {
    const user = db.users.findById(req.params.id);
    // Only return safe fields
    return res.json({
        id: user.id,
        name: user.name,
        email: user.email,
        // Not: passwordHash, ssn, creditCard
    });
});

// ✅ SAFE - Use select/omit in ORM
const user = await User.findById(id).select('-passwordHash -ssn');
```

**Prevention:**
- HTTPS/TLS for all data in transit
- Encrypt sensitive data at rest
- Minimize data collection
- PCI DSS compliance for payment data
- Never log sensitive data
- Implement proper access controls

### 4. XML External Entity (XXE)
**Risk Level: High**

```xml
<!-- ❌ VULNERABLE -->
<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>
```

**Prevention:**
```python
# ✅ SAFE - Disable XXE
import xml.etree.ElementTree as ET

# Disable dangerous entities
for event, elem in ET.iterparse(file, events=['start']):
    if event == 'start':
        # Safely process
        pass

# Better: Use safe libraries like defusedxml
from defusedxml import ElementTree as safe_ET
tree = safe_ET.parse('file.xml')
```

### 5. Broken Access Control
**Risk Level: Critical**

```typescript
// ❌ VULNERABLE - No authorization check
app.delete('/api/users/:id', (req, res) => {
    db.users.deleteById(req.params.id);  // Anyone can delete anyone!
    res.json({ success: true });
});

// ✅ SAFE - Check authorization
app.delete('/api/users/:id', authMiddleware, (req, res) => {
    const requesterId = req.user.id;
    const targetId = req.params.id;
    
    // Only allow user to delete own account or admin
    if (requesterId !== targetId && !req.user.isAdmin) {
        throw new ForbiddenError('You cannot delete this user');
    }
    
    db.users.deleteById(targetId);
    res.json({ success: true });
});
```

**Prevention:**
- Implement role-based access control (RBAC)
- Check authorization on every action
- Never trust client-side checks alone
- Use authorization frameworks
- Log access attempts

### 6. Cross-Site Scripting (XSS)
**Risk Level: High**

```html
<!-- ❌ VULNERABLE - Unescaped user input -->
<div>Welcome, <% user.name %></div>
<!-- If name = "<img src=x onerror='alert(\"XSS\")'>", code executes! -->

<!-- ✅ SAFE - Escape output -->
<div>Welcome, <%= escape(user.name) %></div>
<!-- Output: &lt;img src=x onerror='alert(&quot;XSS&quot;)'&gt; -->
```

**TypeScript/React:**
```typescript
// ❌ VULNERABLE
function UserProfile({ user }) {
    return <div dangerouslySetInnerHTML={{ __html: user.bio }} />;
}

// ✅ SAFE
function UserProfile({ user }) {
    return <div>{user.bio}</div>;  // React escapes by default
}
```

**Prevention:**
- Always escape/encode user input
- Use templating engines with auto-escaping
- Use Content Security Policy (CSP) headers
- Validate and sanitize input
- Encode output based on context (HTML, JS, URL)

### 7. Insecure Deserialization
**Risk Level: Critical**

```python
# ❌ VULNERABLE
import pickle

# Never deserialize untrusted data!
data = pickle.loads(user_input)  # Can execute arbitrary code!

# ✅ SAFE
import json

# Use safe formats like JSON
data = json.loads(user_input)  # Can't execute code
```

**Prevention:**
- Don't deserialize untrusted data
- Use safe formats (JSON, YAML with safe loader)
- Use serialization libraries with validation
- Implement deserialization filters

### 8. Using Components with Known Vulnerabilities
**Risk Level: High**

```bash
# Check for vulnerable dependencies
npm audit
npm audit fix

cargo audit
pip install safety
safety check

# Keep dependencies updated
npm update
cargo update
pip install --upgrade
```

**Prevention:**
- Regular dependency updates
- Use `npm audit`, `cargo audit`
- Monitor security advisories
- Use Software Composition Analysis (SCA) tools
- Pin versions for stability, update regularly

### 9. Insufficient Logging & Monitoring
**Risk Level: High**

```typescript
// ✅ GOOD - Log security events
function login(email: string, password: string) {
    try {
        const user = authenticateUser(email, password);
        logger.info('User login', { userId: user.id, email });
        return { success: true };
    } catch (error) {
        // Log failed attempts (rate limiting trigger)
        logger.warn('Failed login attempt', { email });
        throw error;
    }
}

// Log access to sensitive data
app.get('/api/admin/users', authMiddleware, (req, res) => {
    logger.audit('Admin accessed user list', {
        admin: req.user.id,
        timestamp: new Date()
    });
    // ...
});
```

**Prevention:**
- Log authentication/authorization events
- Log data access (especially sensitive)
- Monitor for suspicious patterns
- Alert on security events
- Keep logs secure and auditable

### 10. Insufficient Transport Layer Protection
**Risk Level: High**

```typescript
// ❌ VULNERABLE - HTTP (unencrypted)
app.listen(3000);  // No HTTPS!

// ✅ SAFE - HTTPS required
import https from 'https';
import fs from 'fs';

const options = {
    key: fs.readFileSync('private-key.pem'),
    cert: fs.readFileSync('certificate.pem')
};

https.createServer(options, app).listen(443);

// Or use framework utilities
app.use(helmet());  // Set security headers

// ✅ Force HTTPS redirect
app.use((req, res, next) => {
    if (req.header('x-forwarded-proto') !== 'https') {
        res.redirect(`https://${req.header('host')}${req.url}`);
    } else {
        next();
    }
});
```

**Prevention:**
- Use HTTPS/TLS for all data
- Valid certificates only
- HSTS headers
- Secure cookies (Secure, HttpOnly, SameSite flags)

## 🔒 Security Headers

```typescript
import helmet from 'helmet';

app.use(helmet());  // Sets many headers:

// Content Security Policy - prevent XSS
res.header('Content-Security-Policy', "default-src 'self'");

// X-Frame-Options - prevent clickjacking
res.header('X-Frame-Options', 'DENY');

// X-Content-Type-Options - prevent MIME sniffing
res.header('X-Content-Type-Options', 'nosniff');

// Strict-Transport-Security - force HTTPS
res.header('Strict-Transport-Security', 'max-age=31536000');

// Referrer-Policy - control referrer info
res.header('Referrer-Policy', 'strict-origin-when-cross-origin');

// Permissions-Policy - control browser features
res.header('Permissions-Policy', 'geolocation=(), camera=()');
```

## 🚨 Secure Coding Practices

### Input Validation
```python
from pydantic import BaseModel, EmailStr, validator

class UserCreate(BaseModel):
    email: EmailStr  # Validates email format
    age: int
    
    @validator('age')
    def age_must_be_valid(cls, v):
        if v < 0 or v > 150:
            raise ValueError('Age must be between 0 and 150')
        return v

# Usage
try:
    user = UserCreate(email="john@example.com", age=25)
except ValidationError as e:
    return error_response(e.errors())
```

### CSRF Protection
```typescript
import csrf from 'csurf';

app.use(csrf());

// Add token to forms
app.get('/form', (req, res) => {
    res.render('form', { csrfToken: req.csrfToken() });
});

// Validate token on POST
app.post('/form', csrf(), (req, res) => {
    // Token is automatically validated
    // Process form
});
```

### Password Requirements
```python
import re

def validate_password(password: str):
    """
    Password must have:
    - At least 12 characters
    - Uppercase letter
    - Lowercase letter
    - Number
    - Special character
    """
    if len(password) < 12:
        raise ValueError('Password too short')
    if not re.search(r'[A-Z]', password):
        raise ValueError('Missing uppercase letter')
    if not re.search(r'[a-z]', password):
        raise ValueError('Missing lowercase letter')
    if not re.search(r'\d', password):
        raise ValueError('Missing number')
    if not re.search(r'[!@#$%^&*]', password):
        raise ValueError('Missing special character')
```

## 📋 Security Checklist

- [ ] HTTPS/TLS enabled
- [ ] Passwords hashed with bcrypt/scrypt
- [ ] Input validation on all endpoints
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (escape output)
- [ ] CSRF protection tokens
- [ ] Rate limiting on auth endpoints
- [ ] MFA implemented
- [ ] Secure headers set
- [ ] Dependency vulnerabilities checked
- [ ] Secrets not in code
- [ ] Error messages don't leak info
- [ ] Logging for audit trail
- [ ] Access controls implemented
- [ ] Data encrypted at rest
- [ ] Regular security testing

## 🔍 Testing for Security

```bash
# OWASP ZAP - Web security scanner
docker run -t owasp/zap2docker-stable zap-baseline.py -t https://app.com

# Burp Suite - Manual testing
# Interactive proxy for finding vulnerabilities

# npm security audit
npm audit

# SAST - Static Application Security Testing
npm install --save-dev eslint-plugin-security
```

## 📚 Resources

- OWASP Top 10: https://owasp.org/www-project-top-ten/
- OWASP Cheat Sheet Series: https://cheatsheetseries.owasp.org/
- CWE Top 25: https://cwe.mitre.org/top25/
- "The Web Application Hacker's Handbook"
- Security headers: https://securityheaders.com
