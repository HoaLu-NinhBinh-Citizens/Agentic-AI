---
name: refactoring
description: Hướng dẫn tái cấu trúc code an toàn, cải thiện thiết kế mà không thay đổi hành vi.
tags: [refactoring, design, clean-code]
version: 1.0
---

# Refactoring Skill

Bạn là một chuyên gia tái cấu trúc code. Hãy áp dụng quy trình sau khi refactor.

## 🔄 Quy Trình Refactoring

1. **Xác định vấn đề** – Code khó đọc, khó mở rộng, hay dễ sinh lỗi
2. **Đảm bảo test coverage** – Phải có test để kiểm tra hành vi không thay đổi
3. **Thực hiện từng bước nhỏ** – Mỗi lần refactor chỉ thay đổi một phần
4. **Chạy test sau mỗi bước** – Đảm bảo không break gì
5. **Code review** – Nhờ người khác review refactor
6. **Document changes** – Giải thích tại sao refactor

## ⚠️ Golden Rule of Refactoring

**Refactor KHÔNG thay đổi hành vi của code - chỉ cải thiện cấu trúc**

```
Input & Output phải giống hệt trước và sau refactor
```

## 🛠️ Kỹ Thuật Refactor Phổ Biến

### 1. Extract Function/Method
**Khi nào:** Function quá dài, có logic phức tạp

```typescript
// ❌ BEFORE - Function dài 100 dòng
function processUser(user) {
    // Validate
    if (!user.email) throw new Error("Email required");
    if (user.email.indexOf("@") === -1) throw new Error("Invalid email");
    
    // Transform
    user.name = user.name.trim().toUpperCase();
    user.email = user.email.toLowerCase();
    
    // Save
    db.users.insert(user);
    logger.log("User saved");
    
    // Notify
    sendWelcomeEmail(user.email);
}

// ✅ AFTER - Extract thành functions nhỏ
function processUser(user) {
    validateUser(user);
    transformUser(user);
    saveUser(user);
    notifyUser(user);
}

function validateUser(user) {
    if (!user.email) throw new Error("Email required");
    if (!isValidEmail(user.email)) throw new Error("Invalid email");
}

function transformUser(user) {
    user.name = user.name.trim().toUpperCase();
    user.email = user.email.toLowerCase();
}
```

**Benefits:**
- Dễ đọc, dễ hiểu
- Dễ test từng phần
- Dễ reuse logic

### 2. Rename Variables/Functions
**Khi nào:** Tên không rõ nghĩa

```rust
// ❌ BAD - Tên tối nghĩa
fn calc(x: i32) -> i32 {
    return x * 0.1;
}

let a = users.filter(|u| u.active);
let b = a.map(|u| u.salary);

// ✅ GOOD - Tên rõ ràng
fn calculateTenPercentDiscount(price: i32) -> i32 {
    return price * 0.1;
}

let activeUsers = users.filter(|u| u.active);
let activeSalaries = activeUsers.map(|u| u.salary);
```

### 3. Replace Magic Numbers/Strings
**Khi nào:** Có hằng số hardcode

```python
# ❌ BAD
def calculate_price(quantity, price):
    if quantity > 100:
        discount = 0.1
    elif quantity > 50:
        discount = 0.05
    else:
        discount = 0
    return quantity * price * (1 - discount)

# ✅ GOOD
MIN_QUANTITY_FOR_SMALL_DISCOUNT = 50
MIN_QUANTITY_FOR_LARGE_DISCOUNT = 100
SMALL_DISCOUNT_RATE = 0.05
LARGE_DISCOUNT_RATE = 0.1

def calculate_price(quantity, price):
    discount = determine_discount_rate(quantity)
    return quantity * price * (1 - discount)

def determine_discount_rate(quantity):
    if quantity > MIN_QUANTITY_FOR_LARGE_DISCOUNT:
        return LARGE_DISCOUNT_RATE
    elif quantity > MIN_QUANTITY_FOR_SMALL_DISCOUNT:
        return SMALL_DISCOUNT_RATE
    return 0
```

### 4. Introduce Parameter Object
**Khi nào:** Function có quá nhiều parameters

```typescript
// ❌ BAD - 7 parameters!
function createUser(
    firstName: string,
    lastName: string,
    email: string,
    phone: string,
    address: string,
    zipCode: string,
    country: string
) { }

// ✅ GOOD - Group related params
interface UserData {
    firstName: string;
    lastName: string;
    email: string;
}

interface ContactInfo {
    phone: string;
    address: string;
    zipCode: string;
    country: string;
}

function createUser(userData: UserData, contact: ContactInfo) { }
```

### 5. Move Method/Class
**Khi nào:** Method ở class sai, method dùng data của class khác

```rust
// ❌ BAD - calculateDiscount ở Order nhưng logic là của Customer
impl Order {
    fn calculateDiscount(&self, customer: &Customer) -> f32 {
        if customer.is_vip {
            return 0.2;
        }
        return 0.0;
    }
}

// ✅ GOOD - Chuyển logic vào Customer
impl Customer {
    fn getDiscount(&self) -> f32 {
        if self.is_vip {
            return 0.2;
        }
        return 0.0;
    }
}

impl Order {
    fn getTotal(&self, customer: &Customer) -> f32 {
        self.subtotal * (1.0 - customer.getDiscount())
    }
}
```

### 6. Encapsulate
**Khi nào:** Fields trực tiếp access từ ngoài, hoặc có validation logic

```python
# ❌ BAD - Direct field access
class User:
    def __init__(self):
        self.age = 0

user = User()
user.age = -5  # Invalid state!

# ✅ GOOD - Encapsulate with validation
class User:
    def __init__(self):
        self._age = 0
    
    def set_age(self, age: int):
        if age < 0 or age > 150:
            raise ValueError("Invalid age")
        self._age = age
    
    def get_age(self) -> int:
        return self._age
```

### 7. Decompose Conditional
**Khi nào:** Conditional phức tạp, khó đọc

```javascript
// ❌ BAD - Conditional complex
if (customer.age > 18 && 
    customer.orders.length > 5 && 
    customer.totalSpent > 1000 &&
    customer.lastOrderDate < Date.now() - 30*24*60*60*1000) {
    applyVIPDiscount();
}

// ✅ GOOD - Extract conditions
function isEligibleForVIP(customer) {
    return isAdult(customer) &&
           hasEnoughOrders(customer) &&
           hasHighSpending(customer) &&
           isRegularCustomer(customer);
}

function isAdult(customer) { return customer.age > 18; }
function hasEnoughOrders(customer) { return customer.orders.length > 5; }
function hasHighSpending(customer) { return customer.totalSpent > 1000; }
function isRegularCustomer(customer) {
    const thirtyDaysAgo = Date.now() - 30*24*60*60*1000;
    return customer.lastOrderDate < thirtyDaysAgo;
}

if (isEligibleForVIP(customer)) {
    applyVIPDiscount();
}
```

## 📋 Refactoring Checklist

- [ ] Tests pass before refactoring
- [ ] Identify problem (code smell)
- [ ] Pick appropriate technique
- [ ] Make small changes
- [ ] Tests still pass?
- [ ] Commit if green
- [ ] Ask for review
- [ ] Document why

## 🚩 Code Smells (Signs You Need Refactoring)

| Smell | Solution |
|-------|----------|
| Long Method | Extract Method |
| Long Parameter List | Introduce Parameter Object |
| Duplicate Code | Extract Method |
| Complex Conditional | Decompose Conditional |
| Large Class | Extract Class |
| Lazy Class | Inline Class |
| Long Name | Rename |
| Data Clumps | Extract Class |
| Primitive Obsession | Replace with Object |
| Switch Statement | Polymorphism |
| Speculative Generality | Delete unused code |
| Temporary Variable | Replace with Extract Method |
| Message Chains | Hide Delegate |
| Middle Man | Remove Middle Man |
| Alternative Classes | Unify interface |

## 💡 Refactoring Best Practices

✅ **DO:**
- Take small steps
- Run tests constantly
- Use automated tools (IDE refactoring)
- Refactor in dedicated commits (not mixed with features)
- Document changes
- Pair program on complex refactoring

❌ **DON'T:**
- Refactor and add features at same time
- Skip tests
- Change behavior while refactoring
- Refactor code you don't understand
- Ignore code review feedback

## 🔧 IDE Refactoring Tools

### VS Code / WebStorm
```
Rename: F2
Extract Method: Ctrl+Alt+M (Cmd+Alt+M)
Extract Variable: Ctrl+Alt+V
Inline: Ctrl+Alt+N
Move: F6
```

### Rust
```
rust-analyzer: rename, extract function
```

## 📈 When to Refactor?

- **During Feature Development** – Boy Scout Rule (leave code cleaner than you found it)
- **After Bug Fix** – Examine surrounding code
- **Code Review** – Suggest refactoring as improvement
- **Spike** – After exploration, refactor production code

**Avoid refactoring:**
- When under deadline pressure (code freeze period)
- When not covered by tests
- When you don't understand the code
