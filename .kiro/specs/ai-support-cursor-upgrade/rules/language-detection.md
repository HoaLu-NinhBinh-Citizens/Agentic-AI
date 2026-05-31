# Language Detection Rule

## Rule ID
`LANG001`

## Description
Detects the language of user input and ensures response is in the same language.

## Supported Languages
- Vietnamese (vi)
- English (en)
- Chinese (zh)
- Japanese (ja)
- Korean (ko)
- French (fr)
- German (de)
- Spanish (es)
- Portuguese (pt)
- Russian (ru)

## Detection Method
Primary signal: Opening salutation or closing signature patterns.
Fallback: Text language detection via character set and common word patterns.

## Language Patterns

### Vietnamese
```
Xin chào | Chào | Cảm ơn | Tôi | Làm sao | Giúp | Hỏi | Cho tôi
```

### English
```
Hello | Hi | Thanks | Thank you | I need | How do | Help | Can you | Please
```

### Chinese
```
你好 | 谢谢 | 我 | 怎么 | 帮助 | 请问
```

### Japanese
```
こんにちは | ありがとう | お願いします | どう | 助けて
```

### Korean
```
안녕하세요 | 감사합니다 | 어떻게 | 도와주세요
```

## Implementation

```python
LANGUAGE_PATTERNS = {
    "vi": [
        r"Xin chào", r"Chào", r"Cảm ơn", r"Tôi", r"Làm sao",
        r"Giúp", r"Hỏi", r"Cho tôi", r"thêm", r"tạo", r"sửa"
    ],
    "en": [
        r"Hello", r"Hi", r"Thanks", r"Thank you", r"I need",
        r"How do", r"Help", r"Can you", r"Please", r"add", r"create", r"fix"
    ],
    "zh": [
        r"你好", r"谢谢", r"我", r"怎么", r"帮助", r"请问",
        r"添加", r"创建", r"修改"
    ],
    "ja": [
        r"こんにちは", r"ありがとう", r"お願いします",
        r"どう", r"助けて", r"追加", r"作成", r"修正"
    ],
    "ko": [
        r"안녕하세요", r"감사합니다", r"어떻게",
        r"도와주세요", r"추가", r"생성", r"수정"
    ]
}

def detect_language(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    
    for lang, patterns in LANGUAGE_PATTERNS.items():
        score = sum(1 for p in patterns if re.search(p, text_lower, re.IGNORECASE))
        if score > 0:
            scores[lang] = score
    
    if scores:
        return max(scores, key=scores.get)
    
    # Fallback: check Unicode ranges
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"[\u3040-\u309f\u30a0-\u30ff]", text):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"
    if re.search(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", text, re.IGNORECASE):
        return "vi"
    
    return "en"  # Default to English
```
