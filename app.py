from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
import shutil
import os
import re

from langchain_community.document_loaders import PyPDFLoader
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, OllamaLLM

app = FastAPI()

# -----------------------
# Models
# -----------------------
embedding = OllamaEmbeddings(model="nomic-embed-text")
llm = OllamaLLM(model="phi3")

# -----------------------
# Request model
# -----------------------
class Query(BaseModel):
    user_input: str

# -----------------------
# Home
# -----------------------
@app.get("/")
def home():
    return {"message": "API Running ✅ Use /docs"}

# -----------------------
# Global DB
# -----------------------
db = None

# -----------------------
# Load DB if exists
# -----------------------
if os.path.exists("vector_db"):
    db = Chroma(
        persist_directory="vector_db",
        embedding_function=embedding
    )

# -----------------------
# Upload PDF
# -----------------------
@app.post("/upload")
def upload_pdf(file: UploadFile = File(...)):
    global db

    file_path = "temp.pdf"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    loader = PyPDFLoader(file_path)
    documents = loader.load()

    db = Chroma.from_documents(
        documents,
        embedding,
        persist_directory="vector_db"
    )

    return {"message": "PDF uploaded successfully ✅"}

# -----------------------
# Chat API
# -----------------------
@app.post("/chat")
def chat(query: Query):
    global db

    if db is None:
        return {"error": "Upload a PDF first!"}

    user_input = query.user_input

    docs = db.similarity_search(user_input, k=3)
    context = "\n".join([doc.page_content for doc in docs])

    # -----------------------
    # AI Prompt
    # -----------------------
    prompt = f"""
You are a smart medical assistant.

RULES:
- Answer ONLY from the report
- Keep answer short
- Do NOT mention names
- Do NOT add extra information

Report:
{context}

Question:
{user_input}
"""

    try:
        response = llm.invoke(prompt)
    except Exception as e:
        return {"error": str(e)}

    response = response.strip()

    # -----------------------
    # Extract numbers
    # -----------------------
    numbers = re.findall(r'\d+\.?\d*', response)

    if numbers:
        value = float(numbers[0])
        text = user_input.lower()

        # 🔹 Sugar
        if "sugar" in text:
            if value > 140:
                response += " (High Sugar 🚨)"
            elif value < 70:
                response += " (Low Sugar ⚠️)"
            else:
                response += " (Normal Sugar ✅)"

        # 🔹 BP
        elif "bp" in text or "blood pressure" in text:
            if value > 140:
                response += " (High BP 🚨)"
            else:
                response += " (Normal BP ✅)"

        # 🔹 Cholesterol
        elif "cholesterol" in text:
            if value > 200:
                response += " (High Cholesterol 🚨)"
            else:
                response += " (Normal Cholesterol ✅)"

        # 🔹 Hemoglobin
        elif "hemoglobin" in text:
            if value < 12:
                response += " (Low Hemoglobin ⚠️)"
            else:
                response += " (Normal Hemoglobin ✅)"

    # -----------------------
    # Symptom detection
    # -----------------------
    symptoms = ["headache", "fever", "vomiting", "dizziness", "pain"]

    if any(symptom in user_input.lower() for symptom in symptoms):
        response += "\n⚠️ If symptoms persist, consult a doctor."

    return {"response": response}