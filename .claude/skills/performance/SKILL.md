---
name: performance
description: Hướng dẫn tối ưu hiệu năng, profiling, caching, và optimization.
tags: [performance, optimization, profiling]
version: 1.0
---

# Performance Skill

Bạn là một chuyên gia về hiệu năng. Hãy giúp người dùng tối ưu ứng dụng, từ profiling đến optimization.

## ⚡ Performance Golden Rules

1. **Don't optimize prematurely** – Profile first, optimize where it matters
2. **Measure before and after** – Know if optimization actually helps
3. **80/20 rule** – 20% of code causes 80% of problems
4. **User experience matters** – Optimize for perceived performance
5. **Trade-offs exist** – Speed vs readability, speed vs memory

## 📊 Performance Metrics

### Web Applications
```
Core Web Vitals (Google):
- LCP (Largest Contentful Paint) < 2.5s
- FID (First Input Delay) < 100ms  
- CLS (Cumulative Layout Shift) < 0.1

Other metrics:
- First Contentful Paint (FCP)
- Time to Interactive (TTI)
- Time to First Byte (TTFB)
```

### Backend Services
```
- Response time: < 200ms (p95)
- Throughput: requests/second
- Error rate: < 0.1%
- Latency: p50, p95, p99
- Resource usage: CPU, Memory, Disk I/O
```

### Databases
```
- Query time: < 10ms
- Index hit ratio: > 99%
- Connection pool utilization: 60-80%
- Replication lag: < 100ms
```

## 🔍 Profiling & Measuring

### Rust
```bash
# Benchmark with criterion
cargo bench

# Flamegraph (CPU usage)
cargo install flamegraph
cargo flamegraph --release

# Valgrind (memory)
valgrind --leak-check=full ./target/release/app

# perf (Linux)
perf record ./app
perf report
```

### TypeScript/JavaScript
```javascript
// Console timing
console.time('operation');
// ... code ...
console.timeEnd('operation');

// Performance API
const start = performance.now();
// ... code ...
console.log(`Took ${performance.now() - start}ms`);

// Lighthouse (Chrome)
// DevTools → Lighthouse tab

// Node.js profiling
node --prof app.js
node --prof-process isolate-*.log > prof.txt
```

### Python
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# ... code ...

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20
```

## 🚀 Optimization Techniques

### 1. Algorithmic Optimization
**Impact: Huge (10x-100x)**

```rust
// ❌ O(n²) - Slow for large data
fn find_pairs(nums: &[i32]) -> Vec<(i32, i32)> {
    let mut pairs = Vec::new();
    for i in 0..nums.len() {
        for j in i+1..nums.len() {
            if nums[i] + nums[j] == 0 {
                pairs.push((nums[i], nums[j]));
            }
        }
    }
    pairs
}

// ✅ O(n) - Much faster
fn find_pairs(nums: &[i32]) -> Vec<(i32, i32)> {
    use std::collections::HashSet;
    let mut pairs = Vec::new();
    let mut seen = HashSet::new();
    
    for &num in nums {
        let complement = -num;
        if seen.contains(&complement) {
            pairs.push((num, complement));
        }
        seen.insert(num);
    }
    pairs
}
```

### 2. Caching
**Impact: 10x for repeated access**

```typescript
// ❌ Without cache
function expensiveOperation(id: string): User {
    return db.query(`SELECT * FROM users WHERE id = '${id}'`);
}

// ✅ With memoization
const cache = new Map<string, User>();

function expensiveOperation(id: string): User {
    if (cache.has(id)) {
        return cache.get(id)!;
    }
    
    const user = db.query(`SELECT * FROM users WHERE id = '${id}'`);
    cache.set(id, user);
    return user;
}

// ✅ Better: with TTL
class CacheWithTTL<K, V> {
    private cache = new Map<K, { value: V; expires: number }>();
    
    set(key: K, value: V, ttlMs: number) {
        this.cache.set(key, { value, expires: Date.now() + ttlMs });
    }
    
    get(key: K): V | null {
        const entry = this.cache.get(key);
        if (!entry) return null;
        if (entry.expires < Date.now()) {
            this.cache.delete(key);
            return null;
        }
        return entry.value;
    }
}
```

### 3. Database Optimization
**Impact: 10x-100x for queries**

```sql
-- ❌ Slow - No index, N+1 query
SELECT * FROM users WHERE email LIKE '%gmail.com%';
-- For each user, query orders separately

-- ✅ Fast - Index + JOIN
CREATE INDEX idx_email ON users(email);

SELECT u.*, COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE u.email LIKE '%gmail.com%'
GROUP BY u.id;

-- ✅ Optimization tips
-- - Add indexes on frequently searched columns
-- - Use EXPLAIN to understand query plan
-- - Denormalize when reads >> writes
-- - Archive old data
-- - Use read replicas for read-heavy workloads
```

### 4. Lazy Loading & Pagination
**Impact: 5x for large datasets**

```typescript
// ❌ Load all at once
async function getUsers(): Promise<User[]> {
    return db.users.find({});  // Could be millions!
}

// ✅ Pagination
async function getUsers(page: number, limit: number = 20): Promise<User[]> {
    const skip = (page - 1) * limit;
    return db.users.find({})
        .skip(skip)
        .limit(limit);
}

// ✅ Lazy loading (load as user scrolls)
const users = ref<User[]>([]);
let page = 1;

const loadMore = async () => {
    const newUsers = await getUsers(page, 20);
    users.value.push(...newUsers);
    page++;
};
```

### 5. Compression & Minification
**Impact: 70% size reduction**

```bash
# JavaScript
npm install -g terser
terser app.js -o app.min.js -c

# CSS
npm install -g clean-css-cli
cleancss -o app.min.css app.css

# Gzip (server-side)
# Add to response headers:
Content-Encoding: gzip

# Brotli (better than gzip)
# Content-Encoding: br
```

### 6. Asynchronous Processing
**Impact: 10x perceived performance**

```typescript
// ❌ Synchronous - User waits
app.post('/process', async (req, res) => {
    const result = await heavyProcessing(req.body);
    res.json(result);
});

// ✅ Asynchronous - Return immediately
app.post('/process', async (req, res) => {
    // Queue job, return job ID
    const jobId = await queue.enqueue(heavyProcessing, req.body);
    res.json({ jobId, status: 'processing' });
    
    // Process in background
    heavyProcessing(req.body).then(result => {
        // Store result
        results.set(jobId, result);
    });
});

// Get result later
app.get('/process/:jobId', (req, res) => {
    const result = results.get(req.params.jobId);
    if (!result) {
        return res.json({ status: 'processing' });
    }
    res.json({ status: 'done', result });
});
```

### 7. Connection Pooling
**Impact: 5x for database/service calls**

```rust
// ❌ New connection per request (slow)
for _ in 0..100 {
    let conn = db.connect();  // Overhead!
    conn.query("SELECT ...");
}

// ✅ Connection pool
let pool = ConnectionPool::new(10);  // 10 connections

for _ in 0..100 {
    let conn = pool.get();  // Reuse existing
    conn.query("SELECT ...");
}
```

### 8. CDN & Edge Caching
**Impact: 100x-1000x (geographic)**

```
Without CDN:
User in Tokyo → Server in US → 200ms

With CDN:
User in Tokyo → CDN Edge in Tokyo → 20ms
```

## 📋 Performance Optimization Checklist

### Frontend
- [ ] Enable gzip/brotli compression
- [ ] Minify JavaScript/CSS
- [ ] Use lazy loading for images
- [ ] Implement code splitting
- [ ] Cache static assets (1 year TTL)
- [ ] Use CDN for assets
- [ ] Optimize images (WebP, appropriate sizes)
- [ ] Remove unused CSS/JavaScript
- [ ] Implement service worker for offline
- [ ] Monitor Core Web Vitals

### Backend
- [ ] Add indexes to frequently queried fields
- [ ] Implement query caching
- [ ] Use connection pooling
- [ ] Implement rate limiting
- [ ] Use async/background jobs for heavy operations
- [ ] Monitor slow queries (> 100ms)
- [ ] Archive old data
- [ ] Use read replicas for read-heavy
- [ ] Implement request batching
- [ ] Monitor request latency (p50, p95, p99)

### Database
- [ ] Analyze query plans (EXPLAIN)
- [ ] Add appropriate indexes
- [ ] Denormalize if reads >> writes
- [ ] Implement query result caching
- [ ] Use pagination for large results
- [ ] Archive old data to separate tables
- [ ] Monitor connection pool usage
- [ ] Set query timeouts

## 🎯 Common Performance Problems

| Problem | Symptom | Solution |
|---------|---------|----------|
| N+1 Query | Each item triggers query | Use JOINs, batch loading |
| Memory Leak | Growing memory | Find uncleaned resources |
| Missing Indexes | Slow queries | Add indexes to WHERE columns |
| Inefficient Algorithm | Slow for large data | Use better algorithm |
| No Caching | Repeated work | Implement caching |
| Large Payload | Slow transfer | Compress, paginate |
| Blocking Operations | Unresponsive UI | Use async/threads |
| Connection Overhead | Slow connections | Use pooling |

## 📈 Performance Budgets

Set targets for your application:

```yaml
Performance Budgets:
  JavaScript: < 100 KB (gzipped)
  CSS: < 30 KB (gzipped)
  Images: < 2 MB total
  HTML: < 20 KB
  Font: < 50 KB
  
  Core Web Vitals:
    LCP: < 2.5s
    FID: < 100ms
    CLS: < 0.1
  
  Backend:
    API Response: < 200ms (p95)
    Database Query: < 10ms (p95)
```

## 🚀 Tools & Services

### Monitoring
- **DataDog** – APM, infrastructure monitoring
- **New Relic** – Application performance monitoring
- **Sentry** – Error tracking
- **Grafana** – Visualization
- **Prometheus** – Metrics collection

### Analysis
- **Lighthouse** – Web performance audit
- **WebPageTest** – Detailed performance analysis
- **GTmetrix** – Performance benchmarking
- **Chrome DevTools** – Developer profiling

### Optimization
- **ImageOptim** – Image compression
- **Webpack Bundle Analyzer** – Bundle analysis
- **Lighthouse CI** – Automated performance testing
- **Apache JMeter** – Load testing

## 💡 Remember

> "Premature optimization is the root of all evil" - Donald Knuth

- Measure first
- Optimize the 20% that matters (80/20 rule)
- Focus on user experience
- Document trade-offs
- Re-measure after optimization
