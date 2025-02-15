# 🚨 IMPORTANT

Whenever adding new pip installs remember to redeploy:

```sh
pip freeze > requirements.txt
```

## 🌱 Environment Setup

1. 🌀 Clone the repo

2. 🐍 Set up a virtual environment

   ```sh
   python -m venv venv
   venv/Scripts/activate
   ```

3. 📦 Install the requirements

   ```sh
   pip install -r requirements.txt
   ```

4. 📥 Download the `.env` file from Discord where Vincent sent it. Make sure the layout is:

   ```env
   COHERE_API_KEY=<api_key>
   ```

5. 🚀 Run the app locally
   ```sh
   uvicorn app:app --reload
   ```

## 🛠️ Postman Setup

1. 📲 Download Postman agent and create an account

2. 🔍 When testing, make sure you choose the right method (GET, POST, etc.) and the correct URL

3. 📝 For POST requests, ensure you select the right body type (raw, form-data, etc.) and the correct data type (JSON, text, etc.)

## 🧪 Testing with `index.html`

1. 🌐 Open `index.html` in a browser (make sure you have the correct API route, whether using localhost or the actual deployed backend)

2. 🖱️ Click on the button to test the API

3. 🖥️ Check the console for the response
