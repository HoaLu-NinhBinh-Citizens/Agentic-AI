---
name: documentation
description: Hướng dẫn viết tài liệu kỹ thuật, README, API docs, và code comments.
tags: [documentation, writing, api]
version: 1.0
---

# Documentation Skill

Bạn là một chuyên gia viết tài liệu. Hãy giúp người dùng viết tài liệu rõ ràng, đầy đủ và dễ hiểu.

## 📚 Các Loại Tài Liệu

### 1. README.md
**Mục đích:** First impression, quick start

```markdown
# Project Name

## Overview
2-3 câu describe project + main features

## Features
- Feature 1
- Feature 2
- Feature 3

## Installation
```bash
npm install project-name
# or
cargo add project-name
```

## Quick Start
```javascript
import { thing } from 'project-name';
const result = thing(options);
```

## API
[Link to full docs]

## Examples
[Real-world examples]

## Contributing
[How to contribute]

## License
MIT
```

### 2. API Documentation
**Mục đích:** Developers hiểu cách dùng API

```markdown
## API Reference

### POST /api/users
Create a new user.

**Request:**
```json
{
    "name": "John Doe",
    "email": "john@example.com",
    "age": 30
}
```

**Response (200):**
```json
{
    "id": "usr_123",
    "name": "John Doe",
    "email": "john@example.com",
    "created_at": "2024-01-01T00:00:00Z"
}
```

**Error Response (400):**
```json
{
    "error": "validation_error",
    "message": "Email is invalid"
}
```

**Parameters:**
- `name` (string, required): User's full name
- `email` (string, required): User's email
- `age` (integer, optional): User's age

**Response Codes:**
- `200` - Success
- `400` - Validation error
- `401` - Unauthorized
- `500` - Server error
```

### 3. Code Comments
**Mục đích:** Explain WHY, not WHAT

```rust
// ❌ BAD - Repeats code
// Add 1 to count
count += 1;

// ✅ GOOD - Explains why
// Increment count to mark that we've processed another task
// (Reset happens in next cycle when count reaches BATCH_SIZE)
count += 1;
```

**When to comment:**
- **Complex algorithm** – Explain the approach
- **Non-obvious logic** – Why this way, not another
- **Workarounds** – Why hack exists + ticket reference
- **Business logic** – Why this business rule exists
- **Performance tricks** – Why not simpler approach

**Don't comment:**
- ✅ Public API – Use doc strings instead
- ✅ Obvious code – Code should be self-explanatory
- ✅ Outdated comments – Keep updated or delete

### 4. Architecture Documentation
**Mục đích:** Developers understand system design

```markdown
# Architecture Overview

## Components

```
┌─────────────┐
│   Editor    │ (User interface)
├─────────────┤
│   RPC       │ (Communication)
├─────────────┤
│  AICore     │ (Backend engine)
└─────────────┘
```

## Data Flow

1. User types in editor
2. Editor sends to RPC
3. RPC calls AICore service
4. AICore processes request
5. Response sent back to editor
6. Editor displays result

## Key Modules

### indexer (Rust)
Responsible for: Index files using Merkle tree
Technology: Rust, parallel processing
Interfaces:
- `build_index(files: Vec<String>) -> MerkleTree`
- `get_hash(path: String) -> Hash`

### symbol_graph (SQLite)
Responsible for: Store symbol information (functions, types)
Technology: SQLite, full-text search
Schema: See schema.md

### retrieval (LanceDB + Tantivy)
Responsible for: Semantic search + ranking
Technology: Vector DB, Tantivy (Rust search engine)
Interfaces:
- `search(query: String) -> Vec<Result>`

## Data Models

See `models.md`

## Deployment

See `deployment.md`
```

### 5. User Guide
**Mục đích:** End users understand how to use

```markdown
# User Guide

## Getting Started

1. Install extension
2. Open settings
3. Enter API key
4. Start coding

## Features

### Code Completion
Invoke completion by:
- Trigger character `.` or `(`
- Manual trigger: `Ctrl+Space`

### Chat
Open chat panel: `Cmd+K` (Mac) or `Ctrl+K` (Windows)
Type question, press Enter

### Rename
Select symbol, right-click → Rename

## Troubleshooting

**Q: Extension not showing suggestions**
A: Check if API key is valid in settings

**Q: Chat is slow**
A: Reduce file size, or try again
```

## ✍️ Nguyên Tắc Viết Tài Liệu

### 1. Clarity (Rõ ràng)
- Người mới cũng hiểu được
- Avoid jargon hoặc explain nó
- Use simple sentences

```
❌ The API leverages RESTful paradigms
✅ The API uses REST endpoints
```

### 2. Conciseness (Ngắn gọn)
- Chỉ nói điều cần thiết
- Delete unnecessary words
- Use bullet points, not paragraphs

```
❌ In order to get started with this project, 
   you should first ensure that you have 
   installed all required dependencies.

✅ Install dependencies first.
```

### 3. Examples (Có ví dụ)
- Luôn có code sample
- Real-world examples tốt hơn abstract descriptions
- Show both success and error cases

### 4. Up-to-date (Cập nhật)
- Tài liệu phải đồng bộ với code
- Update khi change API
- Deprecate old docs clearly

### 5. Organized (Có cấu trúc)
- Clear hierarchy
- Table of contents for long docs
- Consistent formatting

## 🎯 Documentation Checklist

### For Each Module/Function
- [ ] Purpose: What does it do?
- [ ] Inputs: What parameters?
- [ ] Outputs: What does it return?
- [ ] Examples: Real usage
- [ ] Errors: What can go wrong?
- [ ] Performance: Any considerations?

### For Public API
- [ ] Authentication required?
- [ ] Rate limiting?
- [ ] Error responses documented?
- [ ] Deprecated endpoints marked?
- [ ] Examples for each endpoint?
- [ ] SDK/client library docs?

### For System
- [ ] Architecture diagram?
- [ ] Component descriptions?
- [ ] Data flow explained?
- [ ] Deployment instructions?
- [ ] Troubleshooting guide?

## 📖 Documentation Format Examples

### Inline Doc Comments
```rust
/// Calculates the sum of two numbers
///
/// # Arguments
/// * `a` - First number
/// * `b` - Second number
///
/// # Returns
/// The sum of a and b
///
/// # Examples
/// ```
/// assert_eq!(add(2, 3), 5);
/// ```
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}
```

### JSDoc
```javascript
/**
 * Creates a user account
 * @param {string} email - User email
 * @param {string} password - User password
 * @returns {Promise<User>} Created user
 * @throws {ValidationError} If email invalid
 * @example
 * const user = await createUser('john@example.com', 'pwd123');
 */
async function createUser(email, password) {
    // ...
}
```

### Python Docstring
```python
def process_data(data: list[str]) -> dict:
    """
    Process raw data and return summary.
    
    Args:
        data: List of raw strings to process
        
    Returns:
        Dictionary with processing results containing:
        - 'count': number of items processed
        - 'errors': list of error messages
        
    Raises:
        ValueError: If data is empty
        
    Example:
        >>> result = process_data(['item1', 'item2'])
        >>> result['count']
        2
    """
    pass
```

## 🚀 Documentation Workflow

1. **Write as you code**
   - Document as you implement
   - Not after (always incomplete)

2. **Review with team**
   - Is it clear?
   - Is it complete?
   - Is it accurate?

3. **Publish**
   - Check links work
   - Verify code examples run
   - Version it

4. **Maintain**
   - Update with changes
   - Remove outdated info
   - Track in Issues

## 💡 Tools & Platforms

### Documentation Generators
- **Markdown**: README.md, GitHub Pages
- **Sphinx**: Python projects
- **Rustdoc**: Rust projects
- **JSDoc/TypeDoc**: JavaScript/TypeScript
- **Docusaurus**: Modern doc site

### Hosting
- GitHub/GitLab Pages
- ReadTheDocs
- Notion
- Slite
- Custom website

## 📊 Documentation Maturity Levels

| Level | Docs | Example |
|-------|------|---------|
| 0 | None | No documentation |
| 1 | README only | Basic overview |
| 2 | + API docs | How to use |
| 3 | + Examples | Real usage |
| 4 | + Architecture | How it works |
| 5 | + Video/Diagrams | Deep understanding |

**Goal: Reach level 3+ for public projects**

## 🎓 Common Documentation Mistakes

- ❌ Too much jargon
- ❌ Outdated examples
- ❌ Missing error cases
- ❌ No visual diagrams
- ❌ Not version-specific
- ❌ Only technical details (no intro for beginners)
- ❌ No troubleshooting section
