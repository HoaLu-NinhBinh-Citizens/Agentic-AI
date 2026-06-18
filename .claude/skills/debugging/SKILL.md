---
name: debugging
description: Hướng dẫn debug và xử lý lỗi hệ thống, từ phân tích log đến sửa lỗi.
tags: [debugging, error-handling, troubleshooting]
version: 1.0
---

# Debugging Skill

Bạn là một chuyên gia debug. Khi gặp lỗi, hãy áp dụng quy trình sau:

## 🔧 Quy Trình Debug

1. **Xác định triệu chứng** – Lỗi là gì? (crash, wrong output, performance issue)
2. **Thu thập log** – Log ở đâu? (file log, console, telemetry, browser DevTools)
3. **Phân tích nguyên nhân** – Dùng log và stack trace để tìm root cause
4. **Tạo reproduction** – Có thể tái hiện lỗi không? (unit test, manual steps)
5. **Sửa lỗi** – Sửa code, thêm test regression
6. **Xác minh** – Lỗi đã hết chưa? Có side effect không?

## 🛠️ Công Cụ Debug Khuyến Nghị

### Rust
```
dbg!()              // Quick debug print
tracing            // Structured logging
rr (record & replay) // Time-travel debugging
cargo test -- --nocapture  // See println during tests
RUST_BACKTRACE=full
```

### TypeScript/JavaScript
```
console.log()      // Basic
console.table()    // For arrays/objects
console.time()     // Performance
debugger          // Breakpoints
vscode.debug      // VS Code debugger
Chrome DevTools   // Network, memory, performance
```

### Python
```
pdb                // Interactive debugger
logging           // Structured logs
print()           // Quick debug
traceback.print_exc()
ipdb              // Enhanced pdb
```

## 📋 Debug Checklist

### Symptom Analysis
- [ ] Error message rõ ràng?
- [ ] Stack trace có context?
- [ ] Khi nào lỗi xảy ra? (reproducible?)
- [ ] Ai bị ảnh hưởng? (specific user, feature, OS?)

### Information Gathering
- [ ] Kiểm tra logs (tất cả levels)
- [ ] Browser console errors
- [ ] Network requests (failed calls?)
- [ ] System resources (disk, memory, CPU)
- [ ] Recent changes (git diff)

### Root Cause Analysis
- [ ] Search similar issues (GitHub, SO)
- [ ] Check version compatibility
- [ ] Environment differences
- [ ] Dependencies conflict
- [ ] Timing/race conditions

### Testing Fix
- [ ] Unit test for the bug
- [ ] Manual reproduction test
- [ ] Regression test để ensure lỗi không tái phát
- [ ] Edge cases

## 🐛 Ví dụ Debug Session

**Lỗi: "Segmentation fault trong daemon"**

```
1. Triệu chứng: Daemon crashes ngẫu nhiên
2. Log: panic at 'index out of bounds' in index.rs:120
3. Stack trace: 
   → vec.get(index) returns None
   → Code assumes vec[index] exists
4. Root cause: vec được dùng khi nó rỗng
5. Fix: Thêm check if vec.is_empty() hoặc better error handling
6. Verify: Tạo test case với empty vector
```

## 💡 Debugging Tips

- **Divide & Conquer** – Isolate problem area
- **Add Logging** – Trace execution flow
- **Use Breakpoints** – Pause at suspicious points
- **Change One Thing** – Don't change multiple things at once
- **Test Hypotheses** – Verify your assumptions
- **Version Control** – Know what changed
- **Ask for Help** – Rubber duck debugging, pair programming
- **Document** – Note what you learned

## 🚨 Khi Gặp Lỗi Khó

1. Tìm kiếm lỗi tương tự trên GitHub/Stack Overflow
2. Kiểm tra version dependencies có conflict không
3. Xóa cache/build artifacts và rebuild
4. Test với version khác nhau
5. Chạy với debug flags:
   - Rust: `RUST_BACKTRACE=full`
   - Node: `DEBUG=* node app.js`
   - Python: `python -m pdb app.py`
6. Xem source code của library gây lỗi
7. Use binary search – git bisect để find which commit broke things

## 📊 Common Bug Patterns

| Pattern | Symptoms | Check |
|---------|----------|-------|
| Off-by-one | Array index out of range | Loop bounds |
| Null pointer | Crash on access | null checks |
| Race condition | Intermittent errors | Synchronization |
| Memory leak | Increasing memory usage | Resource cleanup |
| Type mismatch | Runtime errors | Type conversions |
| Async issues | Callbacks not fired | Promise handling |
