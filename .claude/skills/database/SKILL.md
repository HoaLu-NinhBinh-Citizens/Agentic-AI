---
name: database
description: Hướng dẫn thiết kế database, từ schema design đến optimization.
tags: [database, design, sql, performance]
version: 1.0
---

# Database Skill

Bạn là một chuyên gia thiết kế database. Hãy giúp người dùng xây dựng schema hiệu quả, safe, và scalable.

## 📋 Normalization

### 1NF (First Normal Form)
- Each column contains only atomic (indivisible) values
- No repeating groups

```sql
-- ❌ BAD - Repeating groups
CREATE TABLE Orders (
    order_id INT,
    customer_name VARCHAR(100),
    items VARCHAR(255)  -- "Item1, Item2, Item3" - violates 1NF!
);

-- ✅ GOOD - Separate table for items
CREATE TABLE Orders (
    order_id INT PRIMARY KEY,
    customer_name VARCHAR(100)
);

CREATE TABLE OrderItems (
    item_id INT PRIMARY KEY,
    order_id INT FOREIGN KEY,
    item_name VARCHAR(100)
);
```

### 2NF (Second Normal Form)
- Must satisfy 1NF
- All non-key attributes must depend on the entire primary key

```sql
-- ❌ BAD - Partial dependency
CREATE TABLE StudentCourses (
    student_id INT,
    course_id INT,
    professor_name VARCHAR(100),  -- Depends only on course_id, not student!
    grade CHAR(1),
    PRIMARY KEY (student_id, course_id)
);

-- ✅ GOOD - Remove partial dependency
CREATE TABLE StudentCourses (
    student_id INT,
    course_id INT,
    grade CHAR(1),
    PRIMARY KEY (student_id, course_id)
);

CREATE TABLE Courses (
    course_id INT PRIMARY KEY,
    professor_name VARCHAR(100)
);
```

### 3NF (Third Normal Form)
- Must satisfy 2NF
- No transitive dependencies (non-key columns depending on other non-key columns)

```sql
-- ❌ BAD - Transitive dependency
CREATE TABLE Employees (
    emp_id INT PRIMARY KEY,
    emp_name VARCHAR(100),
    dept_id INT,
    dept_name VARCHAR(100),  -- Depends on dept_id, not emp_id!
    dept_manager VARCHAR(100)
);

-- ✅ GOOD - Remove transitive dependency
CREATE TABLE Employees (
    emp_id INT PRIMARY KEY,
    emp_name VARCHAR(100),
    dept_id INT FOREIGN KEY
);

CREATE TABLE Departments (
    dept_id INT PRIMARY KEY,
    dept_name VARCHAR(100),
    dept_manager VARCHAR(100)
);
```

## 🗂️ Schema Design

### User Table Example
```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    avatar_url VARCHAR(255),
    status ENUM('active', 'inactive', 'deleted') DEFAULT 'active',
    email_verified_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_email (email),
    INDEX idx_username (username),
    INDEX idx_status (status)
);
```

### Order-Product Relationship (Many-to-Many)
```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    total_amount DECIMAL(10, 2),
    status ENUM('pending', 'confirmed', 'shipped', 'delivered', 'cancelled'),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status)
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    unit_price DECIMAL(10, 2),
    
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id),
    INDEX idx_order_id (order_id),
    INDEX idx_product_id (product_id)
);

CREATE TABLE products (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2),
    inventory INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 🔑 Keys & Relationships

### Primary Key
```sql
-- ✅ Auto-increment ID
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(255) UNIQUE
);

-- ✅ UUID
CREATE TABLE users (
    id CHAR(36) PRIMARY KEY,
    email VARCHAR(255) UNIQUE
);
```

### Foreign Key
```sql
CREATE TABLE posts (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    title VARCHAR(255),
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ON DELETE options:
-- CASCADE - Delete posts when user deleted
-- RESTRICT - Prevent deletion if posts exist
-- SET NULL - Set user_id to NULL (column must allow NULL)
-- NO ACTION - Similar to RESTRICT
```

### Unique Constraint
```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    username VARCHAR(50) UNIQUE NOT NULL,
    ssn VARCHAR(11) UNIQUE NOT NULL
);

-- Composite unique
CREATE TABLE user_emails (
    id BIGINT PRIMARY KEY,
    user_id BIGINT,
    email VARCHAR(255),
    UNIQUE KEY unique_user_email (user_id, email)
);
```

## 🏃 Indexing

### When to Index
```sql
-- ✅ Frequently searched columns
CREATE INDEX idx_email ON users(email);
CREATE INDEX idx_username ON users(username);

-- ✅ Columns used in WHERE clause
CREATE INDEX idx_status ON orders(status);

-- ✅ Columns used in JOIN
CREATE INDEX idx_user_id ON posts(user_id);

-- ✅ Foreign keys (usually auto-indexed)
CREATE INDEX idx_category_id ON products(category_id);

-- ❌ Avoid indexing
-- - Columns with low selectivity (few unique values)
-- - Columns rarely used in queries
-- - Columns that update frequently (index maintenance overhead)
```

### Types of Indexes

```sql
-- Single column index
CREATE INDEX idx_email ON users(email);

-- Composite index (order matters!)
-- Best for: WHERE user_id = ? AND status = ?
CREATE INDEX idx_user_status ON orders(user_id, status);

-- Text search index
CREATE FULLTEXT INDEX idx_description ON products(description);

-- Unique index
CREATE UNIQUE INDEX idx_email ON users(email);

-- Checking existing indexes
SHOW INDEXES FROM users;
EXPLAIN SELECT * FROM users WHERE email = 'test@example.com';
```

### Index Best Practices
```sql
-- ✅ Use EXPLAIN to verify index usage
EXPLAIN SELECT * FROM orders WHERE user_id = 123 AND status = 'pending';

-- ❌ Index not used if:
-- - WHERE clause uses function on indexed column
SELECT * FROM orders WHERE YEAR(created_at) = 2024;  -- Avoid!

-- ✅ Better approach for dates
SELECT * FROM orders WHERE created_at >= '2024-01-01' AND created_at < '2025-01-01';

-- ❌ Using OR can prevent index usage
SELECT * FROM users WHERE email = 'test@example.com' OR phone = '123456789';

-- ✅ Better with UNION
SELECT * FROM users WHERE email = 'test@example.com'
UNION
SELECT * FROM users WHERE phone = '123456789';
```

## 🔄 Transactions

```sql
START TRANSACTION;

-- Multiple operations
INSERT INTO orders (user_id, total) VALUES (1, 100);
UPDATE users SET balance = balance - 100 WHERE id = 1;

-- If all successful, COMMIT
COMMIT;

-- Or rollback if error
ROLLBACK;

-- Using transaction in code:
BEGIN;
  INSERT INTO orders (user_id, total) VALUES (1, 100);
  UPDATE users SET balance = balance - 100 WHERE id = 1;
  
  -- Check for errors, then:
  COMMIT;
EXCEPTION
  WHEN ... THEN
    ROLLBACK;
```

### ACID Properties
- **Atomicity** – Transaction all-or-nothing
- **Consistency** – Database stays valid
- **Isolation** – Transactions don't interfere
- **Durability** – Committed data persists

## 📊 Query Optimization

### Common Issues

#### N+1 Query Problem
```sql
-- ❌ BAD - N+1 queries
SELECT * FROM users;
-- For each user:
SELECT * FROM orders WHERE user_id = ?;

-- ✅ GOOD - Single query with JOIN
SELECT u.*, COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id;

-- ✅ Or: Eager loading in ORM
users = User.includes(:orders).all
```

#### Missing Index
```sql
-- ❌ SLOW - Full table scan
SELECT * FROM orders WHERE user_id = 123 AND status = 'pending';

-- ✅ FAST - With index
CREATE INDEX idx_user_status ON orders(user_id, status);
SELECT * FROM orders WHERE user_id = 123 AND status = 'pending';
```

#### Inefficient JOIN
```sql
-- ❌ SLOW - Joining large tables without indexes
SELECT * FROM orders o
JOIN users u ON o.user_id = u.id;

-- ✅ FAST - Index on foreign key
CREATE INDEX idx_user_id ON orders(user_id);
SELECT * FROM orders o
JOIN users u ON o.user_id = u.id;
```

#### SELECT *
```sql
-- ❌ SLOW - Unnecessary columns
SELECT * FROM users;

-- ✅ FAST - Only needed columns
SELECT id, email, username FROM users;
```

## 🗃️ Denormalization (When Needed)

Denormalization sacrifices normal form for performance.

```sql
-- Normalized
CREATE TABLE user_stats (
    id INT PRIMARY KEY,
    user_id INT FOREIGN KEY,
    posts_count INT,
    followers_count INT,
    created_at TIMESTAMP
);

-- ❌ Problem: Every post insertion requires updating user_stats
INSERT INTO posts (user_id, title) VALUES (1, 'My Post');
UPDATE user_stats SET posts_count = posts_count + 1 WHERE user_id = 1;

-- ✅ Denormalized: Store cache in users table
ALTER TABLE users ADD COLUMN cached_posts_count INT DEFAULT 0;
-- Update cache periodically or on write

-- ✅ Better: Use materialized view or cache layer (Redis)
-- Instead of denormalizing in database
```

## 🔐 Data Integrity

### Constraints
```sql
-- NOT NULL
CREATE TABLE users (
    email VARCHAR(255) NOT NULL
);

-- CHECK
CREATE TABLE users (
    age INT CHECK (age >= 0 AND age <= 150)
);

-- DEFAULT
CREATE TABLE orders (
    status ENUM(...) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- UNIQUE
CREATE TABLE users (
    email VARCHAR(255) UNIQUE
);

-- FOREIGN KEY
CREATE TABLE posts (
    user_id INT FOREIGN KEY REFERENCES users(id)
);
```

### Data Validation
```sql
-- ✅ Database-level validation
CREATE TABLE users (
    email VARCHAR(255) UNIQUE NOT NULL,
    age INT CHECK (age >= 18),
    status ENUM('active', 'inactive') DEFAULT 'active'
);

-- ✅ Application-level validation (also!)
// Validate in code too - don't rely only on database
```

## 🔄 Migrations

```bash
# Using migrations framework (Rails, Django, etc)
# Create migration
rails db:create_migration CreateUsers

# Migration file
class CreateUsers < ActiveRecord::Migration[6.0]
  def change
    create_table :users do |t|
      t.string :email, null: false
      t.string :username, null: false
      t.string :password_hash
      
      t.timestamps
    end
    
    add_index :users, :email, unique: true
  end
end

# Run migrations
rails db:migrate

# Rollback if needed
rails db:rollback

# Safe migration pattern:
# 1. Add new column
# 2. Deploy code to use new column
# 3. Copy data to new column
# 4. Remove old column
```

## 📈 Scaling Database

### Read Replicas
```
Write Master (Primary)
    ↓
    ├→ Read Replica 1
    ├→ Read Replica 2
    └→ Read Replica 3

// Primary: All writes
// Replicas: Read-only, catch up (replication lag)
```

### Sharding
```
User ID 1-1000000 → Shard 1 (Database 1)
User ID 1000001-2000000 → Shard 2 (Database 2)
User ID 2000001-3000000 → Shard 3 (Database 3)

// Horizontal partitioning
```

### Caching Layer
```
Application
    ↓
Redis/Memcached (Cache)
    ↓
Database

// Cache frequently accessed data
// Reduces database load
```

## 📋 Database Design Checklist

- [ ] Normalized schema (3NF minimum)
- [ ] Primary keys defined
- [ ] Foreign keys with ON DELETE policy
- [ ] Indexes on frequently searched columns
- [ ] Composite indexes where needed
- [ ] UNIQUE constraints for uniqueness
- [ ] CHECK constraints for data validation
- [ ] DEFAULT values for common fields
- [ ] NOT NULL where appropriate
- [ ] Timestamps (created_at, updated_at)
- [ ] Soft deletes considered (status field)
- [ ] Migrations for schema changes
- [ ] Backup strategy
- [ ] Performance testing
- [ ] Documentation

## 🚀 Tools

- **DBeaver** – SQL IDE and database tool
- **Adminer** – Simple database management
- **SQLAlchemy** – Python ORM
- **Sequelize** – JavaScript ORM
- **TypeORM** – TypeScript ORM
- **Prisma** – Modern ORM
- **Flyway/Liquibase** – Migration tools

## 📚 Resources

- "Designing Data-Intensive Applications"
- "SQL Performance Explained"
- Database documentation (PostgreSQL, MySQL, MongoDB)
- EXPLAIN ANALYZE your queries!
