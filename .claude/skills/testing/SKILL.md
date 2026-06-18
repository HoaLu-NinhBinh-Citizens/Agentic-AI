---
name: testing
description: Hướng dẫn viết test đơn vị, integration test và end-to-end test.
tags: [testing, quality, tdd]
version: 1.0
---

# Testing Skill

Bạn là một chuyên gia về testing. Hãy giúp người dùng viết test tốt, đảm bảo chất lượng code.

## 🧪 Các Loại Test

### 1. Unit Test
- Kiểm tra từng function/method riêng lẻ
- Isolated từ dependencies (mock nếu cần)
- Nhanh, dễ viết, dễ debug
- Nên có 60-70% coverage

**Ví dụ:**
```rust
#[test]
fn test_add_positive_numbers() {
    assert_eq!(add(2, 3), 5);
}
```

### 2. Integration Test
- Kiểm tra tương tác giữa nhiều modules
- Sử dụng real dependencies
- Chậm hơn unit test nhưng bắt lỗi interaction bugs
- 15-20% coverage

**Ví dụ:**
```typescript
test("user can login and access dashboard", async () => {
    const user = await createUser({ email: "test@test.com" });
    const response = await login(user.email, password);
    expect(response.status).toBe(200);
});
```

### 3. End-to-End Test
- Kiểm tra toàn bộ user flow
- Thông qua UI/API như user thật
- Thường chậm, expensive, nhưng catch real bugs
- 10-15% coverage

**Ví dụ:**
```javascript
test("user can complete checkout flow", async () => {
    await page.goto('http://shop.com');
    await page.click('button:has-text("Add to Cart")');
    await page.click('button:has-text("Checkout")');
    // ... fill payment info
    await expect(page).toHaveTitle("Order Confirmed");
});
```

### 4. Regression Test
- Kiểm tra lỗi cũ không tái phát
- Thêm test mỗi khi fix bug
- Tăng overall test coverage

## 📝 Nguyên Tắc Viết Test Tốt

### 1. One Behavior Per Test
```rust
// ❌ BAD - Test nhiều hành vi
#[test]
fn test_user_operations() {
    let mut user = User::new("John");
    assert_eq!(user.name, "John");
    user.age = 30;
    assert!(user.age >= 18);
}

// ✅ GOOD - Test một hành vi
#[test]
fn test_user_creation_with_name() {
    let user = User::new("John");
    assert_eq!(user.name, "John");
}

#[test]
fn test_user_is_adult_when_age_greater_than_18() {
    let mut user = User::new("John");
    user.age = 30;
    assert!(user.age >= 18);
}
```

### 2. Clear Test Names
```
test_[function_name]_[scenario]_[expected_result]

test_calculate_discount_for_premium_user_returns_20_percent
test_parse_date_with_invalid_format_throws_error
test_fetch_user_when_network_offline_returns_cached_data
```

### 3. Use Mocks & Stubs
```typescript
// Mock external service
const mockApiCall = jest.fn().mockResolvedValue({ data: "test" });

// Stub database
const mockDb = { query: jest.fn().mockReturnValue([]) };
```

### 4. Arrange-Act-Assert (AAA)
```typescript
test("should calculate total price with tax", () => {
    // Arrange
    const calculator = new PriceCalculator();
    const subtotal = 100;
    
    // Act
    const total = calculator.calculateWithTax(subtotal, 0.1);
    
    // Assert
    expect(total).toBe(110);
});
```

### 5. Test Independence
```rust
// ❌ BAD - Test 2 phụ thuộc vào test 1
#[test]
fn test_create_user() { /* ... */ }

#[test]
fn test_get_user() {
    // Expects user created by test_create_user - COUPLING!
}

// ✅ GOOD - Mỗi test setup dữ liệu của riêng nó
#[test]
fn test_get_user() {
    let user = create_test_user(); // Local setup
    // ...
}
```

## 🛠️ Testing Tools

### Rust
```
cargo test              // Run tests
mockall                 // Mocking
proptest                // Property-based testing
criterion               // Benchmarking
```

### TypeScript/JavaScript
```
jest                    // Full testing framework
vitest                  // Fast, Vite-native
mocha + chai            // Testing + assertions
testcafe                // E2E testing
playwright              // Browser automation
```

### Python
```
pytest                  // Modern testing
unittest                // Standard library
mock                    // Mocking
hypothesis              // Property-based testing
```

## 📊 Test Coverage Goals

| Type | Coverage | Notes |
|------|----------|-------|
| Unit | 60-80% | Core logic |
| Integration | 15-25% | Module interactions |
| E2E | 10-20% | Critical user paths |
| **Total** | **80-90%** | Balance quality & speed |

## ✅ Testing Checklist

### Before Writing Code
- [ ] Understand requirements
- [ ] Identify test scenarios
- [ ] Plan test data

### While Writing Tests
- [ ] Test happy path
- [ ] Test error cases
- [ ] Test edge cases
- [ ] Test boundary values
- [ ] Use descriptive names
- [ ] Keep tests DRY

### Before Committing
- [ ] All tests pass
- [ ] Code coverage maintained
- [ ] No flaky tests
- [ ] Performance acceptable
- [ ] Documentation updated

## 🚀 Test-Driven Development (TDD)

```
1. Write failing test (RED)
2. Write minimal code to pass test (GREEN)
3. Refactor code & tests (REFACTOR)
4. Repeat
```

**Benefits:**
- Better design (easier to test = cleaner API)
- Fewer bugs (caught early)
- Living documentation (tests show usage)
- Confidence to refactor

## 💡 Common Mistakes

- ❌ Testing implementation details instead of behavior
- ❌ Not testing error cases
- ❌ Flaky tests (time-dependent, random)
- ❌ Over-mocking (breaks integration)
- ❌ Slow tests (use test doubles, parallel execution)
- ❌ Duplicate test data setup (DRY principle)

## 🎯 Coverage Analysis

```bash
# Rust
cargo tarpaulin

# TypeScript
npm run coverage

# Python
pytest --cov
```

Focus on **meaningful coverage**, not just hitting a percentage target.
