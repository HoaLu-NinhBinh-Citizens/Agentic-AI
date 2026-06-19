---
name: clean-code
description: Hướng dẫn viết code sạch — đặt tên, hàm nhỏ, DRY, comment "why", giảm phức tạp.
tags: [clean-code, readability, maintainability, best-practices]
version: 1.0
---

# Clean Code Skill

Hướng dẫn **viết** code sạch ngay từ đầu (khác với `code-review` — vốn tập trung
vào việc *review* code người khác). Mục tiêu: code dễ đọc, dễ sửa, ít bug.

> Nguyên tắc nền: code được đọc nhiều hơn được viết. Tối ưu cho người đọc tiếp
> theo (thường là chính bạn 3 tháng sau).

## 1. Đặt tên (naming)

- Tên nói lên **ý định**, không phải kiểu dữ liệu: `elapsedMs` thay vì `t`,
  `activeUsers` thay vì `list`.
- Hàm = động từ (`fetchUser`, `computeBudget`); biến/boolean = tính từ/danh từ
  (`isReady`, `retryCount`).
- Tránh viết tắt mơ hồ (`cfg` ok nếu phổ biến; `tmp2`, `data3` thì không).
- Cùng một khái niệm → cùng một từ trong cả codebase (đừng lẫn `get/fetch/load`).
- Hằng số có tên thay cho magic number: `const MAX_RETRIES = 3;` thay vì `3`.

## 2. Hàm nhỏ, một nhiệm vụ

- Một hàm làm **một việc** ở **một mức trừu tượng**. Nếu phải dùng "và" để mô tả
  → tách.
- Giữ hàm ngắn (lý tưởng < ~30 dòng). Hàm dài = trích các bước thành hàm con
  có tên.
- Ít tham số (≤ 3). Nhiều hơn → gom thành struct/object tham số.
- Tránh **boolean flag param** (`render(true)`); tách thành 2 hàm hoặc dùng enum.
- Trả về sớm (guard clause) thay vì lồng `if` sâu:

  ```python
  # tránh
  def f(x):
      if x is not None:
          if x.ok:
              return do(x)
  # nên
  def f(x):
      if x is None or not x.ok:
          return None
      return do(x)
  ```

## 3. DRY — nhưng đừng abstraction quá sớm

- Lặp lại **kiến thức/quy tắc** → trích ra (hàm, hằng số, config).
- Nhưng **hai đoạn giống nhau tình cờ** chưa chắc nên gộp — chờ tới lần thứ 3
  (rule of three) rồi mới trừu tượng hoá, tránh abstraction sai.
- Trùng lặp dễ sửa hơn abstraction sai.

## 4. Comment — chỉ giải thích "WHY"

- Code tự nói "what/how" qua tên tốt. Comment dành cho **lý do không hiển nhiên**:
  ràng buộc protocol, timing, workaround, hằng số suy ra, quyết định đánh đổi.

  ```c
  // PendSV phải có ưu tiên thấp nhất để context switch chỉ xảy ra khi
  // không còn ISR nào pending (tránh fault khi switch giữa chừng ngắt).
  HAL_NVIC_SetPriority(PendSV_IRQn, 15, 0);
  ```
- Xoá comment thừa lặp lại code (`i++; // tăng i`).
- Code chết → xoá, đừng comment-out (đã có git).

## 5. Giảm độ phức tạp

- Giảm state khả biến; ưu tiên dữ liệu bất biến khi hợp lý.
- Tránh side-effect ẩn: hàm nên hoặc tính toán (trả giá trị) hoặc gây tác động,
  hạn chế làm cả hai.
- Xử lý lỗi tường minh tại biên; đừng nuốt exception âm thầm.
- Một mức lồng (nesting) sâu = một tín hiệu nên tách hàm hoặc đảo điều kiện.

## 6. Tổ chức & nhất quán

- Nhóm code liên quan gần nhau; thứ tự đọc từ trên xuống như kể chuyện
  (hàm gọi đứng trên hàm được gọi nếu ngôn ngữ cho phép).
- **Theo convention sẵn có của dự án** trước khi áp style riêng — nhất quán quan
  trọng hơn "đúng" theo sở thích cá nhân.
- Format tự động (formatter/linter) để khỏi tranh luận style thủ công.

## Checklist nhanh khi viết xong một hàm

- [ ] Tên nói rõ ý định, không cần đọc thân hàm cũng đoán được?
- [ ] Làm đúng một việc, một mức trừu tượng?
- [ ] Không magic number / chuỗi lặp?
- [ ] Guard clause thay vì lồng sâu?
- [ ] Comment chỉ còn phần "why" không hiển nhiên?
- [ ] Đặt tên/style nhất quán với phần còn lại của codebase?

## Khi nào KHÔNG nên "làm sạch"

- Đừng refactor cùng lúc với fix bug/feature (tách commit). → xem `refactoring`.
- Đừng over-engineer cho nhu cầu chưa tồn tại (YAGNI).
- Code hot-path có thể đánh đổi độ sạch lấy hiệu năng — khi đó **comment why**.
  → xem `performance`.
