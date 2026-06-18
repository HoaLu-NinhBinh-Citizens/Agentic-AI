---
name: architecture
description: Hướng dẫn thiết kế kiến trúc module, phân tách trách nhiệm và giao tiếp.
tags: [architecture, design, modular]
version: 1.0
---

# Architecture Skill

Bạn là một kiến trúc sư phần mềm. Hãy giúp người dùng thiết kế kiến trúc module có tổ chức và dễ mở rộng.

## 🏗️ Nguyên Tắc Thiết Kế

### 1. Separation of Concerns (Phân tách trách nhiệm)
Mỗi module chỉ làm **một việc**, làm **tốt** việc đó.

```
❌ BAD - User module làm tất cả
UserModule:
  - Handle HTTP requests
  - Validate data
  - Database queries
  - Send emails
  - Log events
  - Cache management

✅ GOOD - Phân tách trách nhiệm
UserService:        // Business logic
UserRepository:     // Database
UserValidator:      // Validation
UserController:     // HTTP handling
```

### 2. Loose Coupling (Ít phụ thuộc)
Các module ít phụ thuộc lẫn nhau, dễ thay đổi.

```rust
// ❌ BAD - Tight coupling
struct Order {
    id: u32,
    payment: PaymentService,  // Direct dependency
}

impl Order {
    fn pay(&self) {
        self.payment.process();  // Can't test without PaymentService
    }
}

// ✅ GOOD - Loose coupling (Dependency Injection)
struct Order {
    id: u32,
}

trait PaymentProcessor {
    fn process(&self) -> Result<()>;
}

impl Order {
    fn pay<P: PaymentProcessor>(&self, processor: &P) -> Result<()> {
        processor.process()  // Can inject mock for testing
    }
}
```

### 3. High Cohesion (Liên kết chặt)
Các thành phần trong module có liên quan chặt chẽ.

```typescript
// ❌ BAD - Low cohesion
class Utilities {
    formatDate() { }
    calculateDiscount() { }
    sendEmail() { }
    parseJson() { }
    // Unrelated methods
}

// ✅ GOOD - High cohesion
class PriceCalculator {
    calculateSubtotal() { }
    calculateTax() { }
    calculateDiscount() { }
    calculateTotal() { }
    // All related to pricing
}
```

### 4. Clean Interfaces (Interface rõ ràng)
Giao tiếp giữa các module qua interface rõ ràng, không leak implementation.

```rust
// ❌ BAD - Complex interface
pub struct Repository {
    pub connection_pool: ConnectionPool,
    pub cache: HashMap<String, Vec<u8>>,
    pub metrics: MetricsCollector,
}

// ✅ GOOD - Clean interface
pub trait UserRepository {
    fn find_by_id(&self, id: u32) -> Result<User>;
    fn save(&self, user: &User) -> Result<()>;
    fn delete(&self, id: u32) -> Result<()>;
}

pub struct SqlUserRepository { /* ... */ }
impl UserRepository for SqlUserRepository { /* ... */ }
```

## 🗂️ Ví Dụ Kiến Trúc: AirCode

### System Architecture
```
┌──────────────────────┐
│  Editor Extension    │  (UI Layer)
│  (VS Code/JetBrains) │
└──────────┬───────────┘
           │ RPC/WebSocket
           │
┌──────────▼───────────┐
│    AICore Service    │  (Backend)
│  (Daemon Process)    │
└──────────┬───────────┘
           │
    ┌──────┴──────┬──────────┬─────────────┐
    │             │          │             │
┌───▼──┐  ┌──────▼───┐  ┌───▼────┐  ┌────▼─────┐
│Cache │  │Indexer   │  │Symbol  │  │Retrieval │
│      │  │(Merkle)  │  │Graph   │  │(Vector)  │
└──────┘  └──────────┘  └────────┘  └──────────┘
```

### Module Details

```
AICore (Main Service)
├── API Layer
│   ├── RPC Handlers (chat, completion, etc)
│   └── Error handling
├── Business Logic Layer
│   ├── ContextBuilder (gather context)
│   ├── Router (route requests to right handler)
│   └── ResponseFormatter (format responses)
├── Data Access Layer
│   ├── IndexerClient (interface to indexer)
│   ├── SymbolGraphDB (SQLite queries)
│   └── RetrievalClient (vector search)
└── Infrastructure
    ├── Config management
    ├── Logging
    └── Metrics
```

## 🔄 Data Flow Example

```
User types in editor
        ↓
Editor sends RPC: "complete(code, position)"
        ↓
AICore receives request
        ↓
ContextBuilder gathers context:
  - Extract relevant code around cursor
  - Query SymbolGraph for types, functions
  - Search Retrieval for similar code patterns
        ↓
LLM processes context + request
        ↓
Formatter prepares response
        ↓
Send back to editor
        ↓
Editor displays completion suggestions
```

## 🎯 When Designing New Module

### 1. Define Responsibility
```
Module: PaymentProcessor

Responsibility: Process payment transactions
Does:
  ✓ Validate payment details
  ✓ Call payment gateway
  ✓ Handle response
  ✓ Update payment status

Doesn't do:
  ✗ Create orders
  ✗ Send emails
  ✗ Update database
```

### 2. Define Public API
```rust
pub trait PaymentProcessor {
    /// Process payment and return transaction ID
    fn process(&self, payment: &Payment) -> Result<TransactionId>;
    
    /// Refund a transaction
    fn refund(&self, transaction_id: TransactionId) -> Result<()>;
    
    /// Get transaction status
    fn get_status(&self, transaction_id: TransactionId) -> Result<Status>;
}
```

### 3. List Dependencies
```
PaymentProcessor depends on:
  - PaymentGateway (interface, can be mocked)
  - Logger (interface)
  - Config (read-only)

PaymentProcessor is used by:
  - OrderService
  - CheckoutController
```

### 4. Draw Diagram
```
User Request
     ↓
CheckoutController (HTTP)
     ↓
OrderService (business logic)
     ↓
PaymentProcessor (payment handling)
     ↓
PaymentGateway (external service)
```

## 📐 Common Architectures

### Layered Architecture
```
┌─────────────────┐
│ Presentation    │ (UI, Controllers)
├─────────────────┤
│ Business Logic  │ (Services)
├─────────────────┤
│ Data Access     │ (Repositories)
├─────────────────┤
│ Database        │ (Persistence)
└─────────────────┘
```

**Pros:** Simple, familiar
**Cons:** Can become monolithic

### Modular Architecture
```
┌─────────────┬──────────┬────────────┐
│   Auth      │ Orders   │  Payments  │
│ Module      │ Module   │ Module     │
├─────────────┼──────────┼────────────┤
│  Shared Infrastructure (Logging, Config, DB)  │
└─────────────┴──────────┴────────────┘
```

**Pros:** Organized, scalable
**Cons:** Need clear boundaries

### Microservices Architecture
```
┌──────────┐   ┌──────────┐   ┌──────────┐
│Auth Svc  │   │Order Svc │   │Payment   │
│ (Port    │   │ (Port    │   │ Svc      │
│  3001)   │   │  3002)   │   │ (Port    │
└────┬─────┘   └────┬─────┘   └────┬─────┘
     │              │               │
     └──────────────┼───────────────┘
              API Gateway
```

**Pros:** Independent scaling, independent deployment
**Cons:** Distributed systems complexity

## 🔌 Module Communication Patterns

### 1. Direct Dependency
```rust
// Service A uses Service B directly
impl OrderService {
    fn place_order(&self, order: &Order) -> Result<()> {
        // Direct call
        self.payment_service.process(order.total)?;
        self.inventory_service.reserve(order.items)?;
        Ok(())
    }
}
```

**Pros:** Simple, direct
**Cons:** Tight coupling

### 2. Dependency Injection
```rust
pub struct OrderService {
    payment_processor: Box<dyn PaymentProcessor>,
    inventory_manager: Box<dyn InventoryManager>,
}

impl OrderService {
    pub fn new(
        payment: Box<dyn PaymentProcessor>,
        inventory: Box<dyn InventoryManager>,
    ) -> Self {
        Self {
            payment_processor: payment,
            inventory_manager: inventory,
        }
    }
}
```

**Pros:** Loose coupling, testable
**Cons:** More setup

### 3. Event-driven
```rust
// Service A publishes event
pub struct OrderPlacedEvent {
    order_id: u32,
    total: f32,
}

event_bus.publish(OrderPlacedEvent { /* ... */ });

// Services subscribe to events
event_bus.subscribe::<OrderPlacedEvent>(|event| {
    payment_service.process_payment(event.total)?;
    inventory_service.reserve_items(event.order_id)?;
});
```

**Pros:** Very loose coupling, scalable
**Cons:** Harder to debug, eventual consistency issues

### 4. Message Queues
```
Order Service → Publish Order Created → RabbitMQ
                                           ↓
                            Payment Service subscribes
                            Inventory Service subscribes
```

**Pros:** Asynchronous, decoupled, scalable
**Cons:** Complexity, operational overhead

## 📋 Architecture Review Checklist

- [ ] Each module has single responsibility
- [ ] Dependencies flow in one direction (no circular)
- [ ] Interfaces are clean and minimal
- [ ] No unnecessary coupling between modules
- [ ] Each module has clear entry points
- [ ] Testable (can mock dependencies)
- [ ] Easy to understand and navigate
- [ ] Easy to add new features
- [ ] Performance bottlenecks identified
- [ ] Error handling strategy defined
- [ ] Logging strategy defined
- [ ] Documentation exists

## 🚀 Anti-patterns to Avoid

| Anti-pattern | Problem | Solution |
|--------------|---------|----------|
| God Object | One class does everything | Break into smaller classes |
| Spaghetti Code | Tangled dependencies | Apply separation of concerns |
| Circular Dependencies | A depends on B, B depends on A | Restructure, introduce mediator |
| Magic Numbers | Constants hardcoded | Extract to named constants |
| Leaky Abstraction | Implementation details exposed | Hide implementation |
| Feature Envy | Class uses another's data too much | Move logic closer to data |
| Duplicate Code | Same code in multiple places | Extract to shared module |

## 💡 Design Patterns

### Factory Pattern
```rust
pub trait PaymentProcessorFactory {
    fn create(&self, provider: &str) -> Box<dyn PaymentProcessor>;
}

let processor = factory.create("stripe");
```

### Strategy Pattern
```rust
pub trait SortStrategy {
    fn sort(&self, items: &mut Vec<Item>);
}

struct QuickSort;
impl SortStrategy for QuickSort { /* ... */ }

struct BubbleSort;
impl SortStrategy for BubbleSort { /* ... */ }
```

### Observer Pattern
```rust
pub trait EventListener {
    fn on_event(&self, event: &Event);
}

event_emitter.subscribe(Box::new(LogListener));
event_emitter.subscribe(Box::new(MetricsListener));
```

## 📚 Resources

- "Clean Architecture" by Robert C. Martin
- "Design Patterns" by Gang of Four
- "Microservices Patterns" by Chris Richardson
- System Design Primer: https://github.com/donnemartin/system-design-primer
