# Cheradip Backend API Reference

## Base URL
```
Development: http://127.0.0.1:8000/api/
Production: https://cheradip.com/api/
```

## Authentication

### Signup
```http
POST /api/signup/
Content-Type: application/json

{
  "username": "01712345678",
  "password": "password123",
  "fullName": "John Doe",
  "acctype": "Student",
  "group": "Science",
  "gender": "Male",
  "division": "Dhaka",
  "district": "Dhaka",
  "thana": "Dhanmondi",
  "union": "Union Name",
  "village": "Village Name"
}

Response: {
  "authToken": "generated-token-here"
}
```

### Login
```http
POST /api/login/
Content-Type: application/json

{
  "username": "01712345678",
  "password": "password123"
}

Response: {
  "authToken": "token",
  "acctype": "Student",
  "fullName": "John Doe",
  "group": "Science",
  "gender": "Male",
  "division": "Dhaka",
  "district": "Dhaka",
  "thana": "Dhanmondi",
  "union": "Union Name",
  "village": "Village Name"
}
```

## MCQ Question Endpoints

### List Questions
```http
GET /api/questions/
GET /api/questions/?subject=101&subject=275
GET /api/questions/?chapter=01&chapter=02
GET /api/questions/?topic=01
GET /api/questions/?institute=INST001
GET /api/questions/?year=2024
GET /api/questions/?group=S&group=A
GET /api/questions/?search=information technology
GET /api/questions/?qid=2750101001
GET /api/questions/?page=1&page_size=20
```

**Response:**
```json
{
  "count": 150,
  "next": "http://api/questions/?page=2",
  "previous": null,
  "results": [
    {
      "qid": "2750101001",
      "subject": {
        "subject_code": "275",
        "subject_name": "ICT",
        "group": [...]
      },
      "chapter": {
        "chapter_no": "01",
        "chapter_name": "Chapter Name"
      },
      "topic": {
        "topic_no": "01",
        "topic_name": "Topic Name"
      },
      "question": "Question text here",
      "option1": "Option 1",
      "option2": "Option 2",
      "option3": "Option 3",
      "option4": "Option 4",
      "answer": "1",
      "explanation": "Explanation text",
      "uddipok": "Context text",
      "img_question": "http://domain.com/media/images/mcq/275/01/2750101001.png",
      "img_uddipok": null,
      "img_explanation": null,
      "institutes": [...],
      "years": [...]
    }
  ]
}
```

### Get Single Question
```http
GET /api/questions/2750101001/
```

### Create Question
```http
POST /api/questions/
Content-Type: multipart/form-data
Authorization: Token <token>

{
  "subject_code_write": "275",
  "chapter_no_write": "01",
  "topic_no_write": "01",
  "question": "What is ICT?",
  "option1": "Information and Communication Technology",
  "option2": "Internet and Computer Technology",
  "option3": "Information and Computer Technology",
  "option4": "Internet and Communication Technology",
  "answer": "1",
  "explanation": "ICT stands for Information and Communication Technology",
  "uddipok": "Context if any",
  "institute_codes": ["INST001", "INST002"],
  "year_codes": ["2024"],
  "img_question": <file>,
  "img_uddipok": <file>,
  "img_explanation": <file>
}
```

### Update Question
```http
PUT /api/questions/2750101001/
PATCH /api/questions/2750101001/

Content-Type: multipart/form-data
Authorization: Token <token>

{
  "question": "Updated question text",
  "answer": "2",
  ...
}
```

### Delete Question
```http
DELETE /api/questions/2750101001/
Authorization: Token <token>
```

### Get Statistics
```http
GET /api/questions/statistics/
GET /api/questions/statistics/?subject=275

Response: {
  "total_questions": 1500,
  "by_subject": {
    "275": {
      "name": "ICT",
      "count": 500
    }
  },
  "by_year": {
    "2024": {
      "name": "2024",
      "count": 200
    }
  }
}
```

## Related Endpoints

### Groups
```http
GET /api/groups/
GET /api/groups/?group_code=S

Response: [
  {
    "group_code": "S",
    "group_name": "Science"
  }
]
```

### Subjects
```http
GET /api/subjects/
GET /api/subjects/?groups=S,A,B
GET /api/subjects/?subject_code=275

Response: [
  {
    "subject_code": "275",
    "subject_name": "ICT",
    "group": [...],
    "group_codes": ["S", "A", "B"]
  }
]
```

### Chapters
```http
GET /api/chapters/
GET /api/chapters/?subjects=275,101
GET /api/chapters/?chapter_no=01

Response: [
  {
    "id": 1,
    "subject": {...},
    "subject_code": "275",
    "subject_name": "ICT",
    "chapter_no": "01",
    "chapter_name": "Chapter Name"
  }
]
```

### Topics
```http
GET /api/topics/
GET /api/topics/?chapters=1,2,3
GET /api/topics/?topic_no=01

Response: [
  {
    "id": 1,
    "chapter": {...},
    "chapter_no": "01",
    "chapter_name": "Chapter Name",
    "subject_code": "275",
    "topic_no": "01",
    "topic_name": "Topic Name"
  }
]
```

### Institutes
```http
GET /api/instituteTypes/
GET /api/instituteTypes/?institute_code=INST001
GET /api/instituteTypes/?institute_type=Type1&institute_type=Type2

Response: [
  {
    "institute_code": "INST001",
    "institute_name": "Institute Name",
    "institute_type": "Type1"
  }
]
```

### Years
```http
GET /api/years/
GET /api/years/?year_code=2024
GET /api/years/?institutes=INST001,INST002

Response: [
  {
    "year_code": "2024",
    "year_name": "2024"
  }
]
```

## User Profile Endpoints

### Update Profile
```http
POST /api/profile_update/
Content-Type: application/json

{
  "username": "01712345678",
  "password": "current_password",
  "fullName": "Updated Name",
  "group": "Business Studies",
  "gender": "Female",
  ...
}
```

### Update Password
```http
POST /api/password_update/
Content-Type: application/json

{
  "username": "01712345678",
  "password": "old_password",
  "newpassword": "new_password123"
}
```

### Update Mobile Number
```http
POST /api/mobile_update/
Content-Type: application/json

{
  "username": "01712345678",
  "newusername": "01787654321",
  "password": "current_password"
}
```

### Check Username Exists
```http
GET /api/username/?username=01712345678

Response: {
  "exists": true
}
```

### Check Password
```http
GET /api/password/?username=01712345678&password=password123

Response: {
  "exists": true
}
```

## Order Endpoints

### Get User Orders
```http
GET /api/myorder/01712345678/
Authorization: Token <token>
```

### Get Items
```http
GET /api/item/
```

## Location Endpoints

### Get Divisions
```http
GET /api/divisions/

Response: ["Dhaka", "Chittagong", "Rajshahi", ...]
```

### Get Districts
```http
GET /api/districts/?division=Dhaka

Response: ["Dhaka", "Gazipur", "Narayanganj", ...]
```

### Get Thanas
```http
GET /api/thanas/?division=Dhaka&district=Dhaka

Response: ["Dhanmondi", "Gulshan", "Uttara", ...]
```

## Notification Endpoints

### Get Notifications
```http
GET /api/notification/

Response: [
  {
    "id": 1,
    "text": "Notification text",
    "link": "https://example.com"
  }
]
```

## Error Responses

### 400 Bad Request
```json
{
  "error": "Validation error",
  "details": {
    "field_name": ["Error message"]
  }
}
```

### 401 Unauthorized
```json
{
  "error": "Invalid credentials"
}
```

### 404 Not Found
```json
{
  "detail": "Not found."
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error"
}
```

## Pagination

All list endpoints support pagination:
- `?page=1` - Page number
- Default page size: 100
- Response includes: `count`, `next`, `previous`, `results`

## Filtering

Most endpoints support filtering via query parameters:
- Multiple values: `?subject=101&subject=275`
- Single value: `?subject_code=275`
- Search: `?search=query`

## Authentication Headers

For protected endpoints, include:
```
Authorization: Token <your-token-here>
```

Or use session authentication if logged in via Django admin.

## Image Upload

When uploading images, use `multipart/form-data`:
```javascript
const formData = new FormData();
formData.append('img_question', fileInput.files[0]);
formData.append('question', 'Question text');
// ... other fields

fetch('/api/questions/', {
  method: 'POST',
  headers: {
    'Authorization': 'Token your-token'
  },
  body: formData
});
```

## Notes

- All timestamps are in UTC
- Image URLs are absolute URLs when returned
- Bengali text is properly encoded in responses
- All list endpoints support pagination
- Search is case-insensitive
- Filtering supports multiple values (array)

