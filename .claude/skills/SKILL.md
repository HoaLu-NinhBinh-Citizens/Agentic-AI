# 📚 AirCode Skill Library

Bộ skill comprehensive cho Claude/Cline phục vụ phát triển AirCode. Tất cả 11 skills tập trung vào các khía cạnh khác nhau của quy trình phát triển phần mềm.

## 📁 Danh sách Skill

### 1. 🔍 **Code Review** (`01-code-review.md`)
Hướng dẫn review code hiệu quả, kiểm tra chất lượng, bảo mật, hiệu năng.

**Khi dùng:**
- Reviewing pull requests
- Evaluating code quality
- Checking security issues
- Assessing performance

**Nội dung:**
- 7 bước review code
- Checklist chi tiết
- Ví dụ thực tế
- Best practices

---

### 2. 🐛 **Debugging** (`02-debugging.md`)
Hướng dẫn debug và xử lý lỗi hệ thống, từ phân tích log đến sửa lỗi.

**Khi dùng:**
- Fixing bugs
- Analyzing errors
- Profiling issues
- Finding root causes

**Nội dung:**
- 6 bước debug
- Tools cho Rust, TypeScript, Python
- Common patterns
- Tips cho lỗi khó

---

### 3. 🧪 **Testing** (`03-testing.md`)
Hướng dẫn viết test: unit, integration, e2e.

**Khi dùng:**
- Writing test cases
- Ensuring quality
- Test-driven development
- Coverage analysis

**Nội dung:**
- 4 loại test
- AAA pattern
- Mock/stub strategies
- Tools & frameworks
- Coverage goals

---

### 4. 🔄 **Refactoring** (`04-refactoring.md`)
Hướng dẫn tái cấu trúc code an toàn, cải thiện thiết kế.

**Khi dùng:**
- Improving code structure
- Eliminating technical debt
- Making code maintainable
- Applying design patterns

**Nội dung:**
- 6 bước refactor
- 7 kỹ thuật phổ biến
- Code smells & solutions
- IDE refactoring tools
- When to refactor

---

### 5. 📖 **Documentation** (`05-documentation.md`)
Hướng dẫn viết tài liệu kỹ thuật, README, API docs, comments.

**Khi dùng:**
- Writing README
- API documentation
- Architecture docs
- Code comments
- User guides

**Nội dung:**
- 5 loại tài liệu
- Nguyên tắc viết (5 C)
- Examples & formats
- Documentation tools
- Maturity levels

---

### 6. 🌿 **Git Workflow** (`06-git-workflow.md`)
Hướng dẫn quy trình Git: branch, commit, PR, merge.

**Khi dùng:**
- Creating branches
- Writing commits
- Creating pull requests
- Resolving conflicts
- Managing releases

**Nội dung:**
- Branch naming convention
- Commit message format
- 7 bước workflow
- Rebase vs merge
- Common scenarios
- Git best practices

---

### 7. 🏗️ **Architecture** (`07-architecture.md`)
Hướng dẫn thiết kế kiến trúc module, phân tách trách nhiệm.

**Khi dùng:**
- Designing systems
- Planning modules
- Creating interfaces
- Defining dependencies
- Scaling applications

**Nội dung:**
- 4 nguyên tắc (SOLID)
- Ví dụ AirCode
- Communication patterns
- Common architectures
- Design patterns
- Anti-patterns

---

### 8. ⚡ **Performance** (`08-performance.md`)
Hướng dẫn tối ưu hiệu năng, profiling, caching.

**Khi dùng:**
- Optimizing speed
- Profiling code
- Analyzing bottlenecks
- Improving UX
- Scaling systems

**Nội dung:**
- Performance metrics
- Profiling tools
- 8 optimization techniques
- Caching strategies
- Common problems
- Performance budgets

---

### 9. 🔐 **Security** (`09-security.md`)
Hướng dẫn bảo mật ứng dụng, từ authentication đến data protection.

**Khi dùng:**
- Preventing vulnerabilities
- Implementing auth
- Protecting data
- Security testing
- Compliance

**Nội dung:**
- Security principles
- OWASP Top 10
- SQL injection prevention
- XSS prevention
- Authentication/Authorization
- Encryption & hashing
- Security headers
- Secure coding

---

### 10. 📐 **API Design** (`10-api-design.md`)
Hướng dẫn thiết kế API: REST, GraphQL, versioning.

**Khi dùng:**
- Designing REST APIs
- Planning endpoints
- Versioning strategies
- Error handling
- Documentation

**Nội dung:**
- REST principles
- URL structure
- HTTP methods & status codes
- Pagination & filtering
- Versioning & deprecation
- GraphQL vs REST
- Authentication patterns
- Error responses
- Rate limiting

---

### 11. 🗄️ **Database** (`11-database.md`)
Hướng dẫn thiết kế database, schema, indexing, optimization.

**Khi dùng:**
- Designing schemas
- Optimizing queries
- Adding indexes
- Handling migrations
- Scaling database

**Nội dung:**
- Normalization (1NF, 2NF, 3NF)
- Schema design examples
- Keys & relationships
- Indexing strategies
- Query optimization
- Transactions & ACID
- Denormalization
- Data integrity
- Scaling strategies

---

## 🎯 Cách Sử Dụng

### Với Claude
```
Bạn là một chuyên gia về [topic]. 
Sử dụng skill [name] để giúp tôi [task].

Skill content:
[Copy nội dung file skill tương ứng]
```

### Với Cline (IDE Extension)
Khi user mention một topic, tự động thêm skill phù hợp vào context.

### Tích hợp vào Extension
```javascript
// Khi user chat về code review
const skill = loadSkill('code-review');
const context = skill.content + userMessage;
// Pass to Claude API
```

---

## 📊 Skill Coverage

| Area | Covered | Skills |
|------|---------|--------|
| Code Quality | ✅ | Review, Testing, Refactoring, Debugging |
| Architecture | ✅ | Architecture, API Design, Database |
| Development | ✅ | Git Workflow, Documentation |
| Performance | ✅ | Performance, Database Optimization |
| Security | ✅ | Security |
| **Total Coverage** | **✅** | **11 Skills** |

---

## 🔍 Tìm Kiếm Skill Theo Task

### "Tôi muốn cải thiện code"
→ **Code Review** + **Refactoring** + **Testing**

### "Tôi gặp bug khó"
→ **Debugging** + **Testing**

### "Thiết kế API mới"
→ **API Design** + **Database** + **Architecture**

### "Tối ưu hiệu năng"
→ **Performance** + **Database** + **Architecture**

### "Bảo mật ứng dụng"
→ **Security** + **API Design**

### "Quản lý codebase"
→ **Git Workflow** + **Documentation** + **Code Review**

---

## 🚀 Cách Phát Triển

### Thêm Skill Mới
1. Tạo file `NN-name.md`
2. Theo template:
   ```yaml
   ---
   name: [name]
   description: [short description]
   tags: [tags]
   version: 1.0
   ---
   ```
3. Thêm vào danh sách này
4. Update coverage table

### Update Skill Hiện Có
- Cải thiện nội dung
- Thêm ví dụ
- Cập nhật tools/resources
- Increment version number

### Gợi Ý Skill Cần Thêm
- Docker & Containerization
- CI/CD Pipeline
- Monitoring & Observability
- Data Engineering
- Machine Learning
- DevOps
- Mobile Development
- Frontend Performance

---

## 📚 References

### Design & Architecture
- "Clean Architecture" - Robert C. Martin
- "Designing Data-Intensive Applications" - Martin Kleppmann
- "Microservices Patterns" - Chris Richardson

### Development
- "The Pragmatic Programmer"
- "Code Complete" - Steve McConnell
- "Refactoring" - Martin Fowler

### Security
- "Web Application Hacker's Handbook"
- OWASP Top 10
- OWASP Cheat Sheets

### Performance
- "Performance Engineering" techniques
- Database optimization guides
- Web performance best practices

---

## 📝 Version History

- **v1.0** (2024-01)
  - 7 core skills (code-review, debugging, testing, refactoring, documentation, git-workflow, architecture)
  - 4 advanced skills (performance, security, api-design, database)

---

## 📞 Support

- Issues/improvements: Create an issue in repo
- Questions: Check existing docs
- Contributions: Submit PR with improvements

---

**Happy coding! 🎉**
